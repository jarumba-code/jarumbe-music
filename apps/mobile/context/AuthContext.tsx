import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Session, User } from '@supabase/supabase-js';
import * as WebBrowser from 'expo-web-browser';

WebBrowser.maybeCompleteAuthSession();

import { getMe, setCurrentSession } from '../lib/api';
import { buildGoogleRedirectUrl, describeOAuthCallback, getErrorMessage, parseOAuthCallback, sanitizeUrlForLogging, toProfile } from '../lib/auth';
import { supabase } from '../lib/api';
import { Profile } from '../lib/types';

type AuthContextValue = {
  session: Session | null;
  user: User | null;
  profile: Profile | null;
  loading: boolean;
  error: string | null;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const hydrateProfile = useCallback(async (currentSession: Session | null) => {
    if (!currentSession) {
      setProfile(null);
      setUser(null);
      return;
    }

    setUser(currentSession.user ?? null);
    try {
      const nextProfile = await getMe();
      setProfile(toProfile(nextProfile));
      setError(null);
    } catch (caught) {
      setError(getErrorMessage(caught, 'Unable to load your profile.'));
      setProfile(null);
    }
  }, []);

  useEffect(() => {
    let mounted = true;

    const restoreSession = async () => {
      try {
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (!mounted) return;

        if (sessionError) {
          setError(getErrorMessage(sessionError, 'Session restore failed.'));
        }

        const currentSession = data.session ?? null;
        setSession(currentSession);
        setCurrentSession(currentSession);
        await hydrateProfile(currentSession);
      } catch (caught) {
        if (!mounted) return;
        setError(getErrorMessage(caught, 'Unable to restore your session.'));
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    const { data: authListener } = supabase.auth.onAuthStateChange(async (_event, nextSession) => {
      if (!mounted) return;
      setSession(nextSession);
      setCurrentSession(nextSession);
      if (nextSession) {
        setUser(nextSession.user ?? null);
        setLoading(true);
        try {
          const nextProfile = await getMe();
          setProfile(toProfile(nextProfile));
          setError(null);
        } catch (caught) {
          setError(getErrorMessage(caught, 'Unable to load your profile.'));
          setProfile(null);
        } finally {
          setLoading(false);
        }
      } else {
        setCurrentSession(null);
        setProfile(null);
        setUser(null);
        setLoading(false);
      }
    });

    restoreSession();

    return () => {
      mounted = false;
      authListener.subscription.unsubscribe();
    };
  }, [hydrateProfile]);

  const signInWithGoogle = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const redirectTo = buildGoogleRedirectUrl();
      console.log('[OAuth Diagnostic] Generated redirectTo:', sanitizeUrlForLogging(redirectTo));

      const { data, error: authError } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo,
          skipBrowserRedirect: true,
        },
      });

      if (authError) {
        throw authError;
      }

      const authUrl = data?.url;
      if (!authUrl) {
        throw new Error('Google sign in did not return an auth URL.');
      }

      // Flow id of this sign-in call. It selects the code verifier that
      // signInWithOAuth() just stored locally, so it takes precedence over any
      // value found in the callback URL.
      const signInFlowId = data?.flowId ?? null;

      // Non-sensitive: reports only whether the runtime can hash the PKCE code
      // challenge (S256). Without WebCrypto, Supabase falls back to the 'plain'
      // challenge method, which the Auth server also accepts.
      const hasWebCrypto =
        typeof (globalThis as { crypto?: { subtle?: unknown } }).crypto?.subtle !== 'undefined';
      console.log('[OAuth Diagnostic] WebCrypto available for S256 challenge:', hasWebCrypto);

      console.log('[OAuth Diagnostic] Supabase authUrl format:', sanitizeUrlForLogging(authUrl));

      const browserResult = await WebBrowser.openAuthSessionAsync(authUrl, redirectTo, {
        showInRecents: true,
      });

      console.log('[OAuth Diagnostic] WebBrowser result type:', browserResult.type);

      if (browserResult.type === 'cancel') {
        throw new Error('Google sign in was cancelled.');
      }

      if (browserResult.type !== 'success' || !browserResult.url) {
        throw new Error('Google sign in failed to return to the app.');
      }

      // Structure only: scheme/host/port/path and parameter names, never values.
      console.log('[OAuth Diagnostic] WebBrowser callback:', describeOAuthCallback(browserResult.url));

      const callback = parseOAuthCallback(browserResult.url);
      if (callback.error) {
        console.log('[OAuth Diagnostic] Callback error:', callback.error);
        throw new Error(callback.message || callback.error);
      }

      if (!callback.code) {
        throw new Error('No authorization code was returned from the OAuth callback.');
      }

      const flowId = signInFlowId ?? callback.flowId ?? null;
      const { data: sessionData, error: exchangeError } = await supabase.auth.exchangeCodeForSession(
        callback.code,
        flowId ? { flowId } : undefined,
      );
      if (exchangeError) {
        throw exchangeError;
      }

      if (!sessionData.session) {
        throw new Error('Google sign in completed without a session.');
      }

      setSession(sessionData.session);
      setCurrentSession(sessionData.session);
      setUser(sessionData.session.user ?? null);
      setLoading(false);
      setError(null);
    } catch (caught) {
      setError(getErrorMessage(caught, 'Google sign in failed.'));
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    setLoading(true);
    try {
      const { error: signOutError } = await supabase.auth.signOut();
      if (signOutError) {
        throw signOutError;
      }
      setSession(null);
      setCurrentSession(null);
      setUser(null);
      setProfile(null);
      setError(null);
    } catch (caught) {
      setError(getErrorMessage(caught, 'Sign out failed.'));
    } finally {
      setLoading(false);
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ session, user, profile, loading, error, signInWithGoogle, signOut }),
    [session, user, profile, loading, error, signInWithGoogle, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
