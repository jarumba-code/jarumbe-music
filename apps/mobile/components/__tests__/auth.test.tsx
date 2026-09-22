import React from 'react';
import { Pressable, Text } from 'react-native';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import * as WebBrowser from 'expo-web-browser';

import { AuthProvider, useAuth } from '../../context/AuthContext';
import { buildApiHeaders, buildGoogleRedirectUrl, describeOAuthCallback, parseOAuthCallback, sanitizeUrlForLogging, toProfile } from '../../lib/auth';

const mockExchangeCodeForSession = jest.fn();
const mockSignInWithOAuth = jest.fn();
const mockOpenAuthSessionAsync = jest.spyOn(WebBrowser, 'openAuthSessionAsync');

jest.mock('../../lib/api', () => {
  // Shared auth surface: AuthContext consumes the `supabase` singleton directly,
  // while getSupabaseClient() is kept for module-contract parity.
  const authMock = {
    getSession: jest.fn().mockResolvedValue({ data: { session: null }, error: null }),
    onAuthStateChange: jest.fn().mockReturnValue({ data: { subscription: { unsubscribe: jest.fn() } } }),
    // Delegated lazily: AuthContext calls these while the test module (and these
    // jest.fn declarations) are still initializing.
    signInWithOAuth: (...args: unknown[]) => mockSignInWithOAuth(...args),
    exchangeCodeForSession: (...args: unknown[]) => mockExchangeCodeForSession(...args),
    signOut: jest.fn(),
  };

  return {
    getMe: jest.fn(),
    setCurrentSession: jest.fn(),
    isAuthReady: jest.fn().mockResolvedValue(false),
    getAccessToken: jest.fn().mockResolvedValue(null),
    getSupabaseClient: () => ({ auth: authMock }),
    supabase: { auth: authMock },
  };
});

function TestConsumer() {
  const { session, loading, error, profile } = useAuth();

  return (
    <>
      <Text testID="auth-status">{loading ? 'loading' : session ? 'authenticated' : 'unauthenticated'}</Text>
      {error ? <Text>{error}</Text> : null}
      {profile ? <Text>{profile.display_name}</Text> : null}
    </>
  );
}

function SignInConsumer() {
  const { signInWithGoogle, error } = useAuth();

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Continue with Google"
        onPress={() => {
          void signInWithGoogle();
        }}>
        <Text>Continue with Google</Text>
      </Pressable>
      {error ? <Text testID="sign-in-error">{error}</Text> : null}
    </>
  );
}

describe('auth bootstrap and helpers', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('starts with a non-authenticated session while restoring state', async () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.queryByTestId('auth-status')).toBeTruthy();
      expect(screen.getByTestId('auth-status').props.children).not.toBe('authenticated');
    });

    expect(screen.getByTestId('auth-status').props.children).toBe('unauthenticated');
  });

  it('builds Authorization headers for authenticated API calls', () => {
    const headers = buildApiHeaders('abc123');
    expect(headers.get('Authorization')).toBe('Bearer abc123');
  });

  it('builds a valid Expo redirect URI for the current environment', () => {
    const redirect = buildGoogleRedirectUrl();
    expect(redirect).toMatch(/auth\/callback|jarumba:\/\/auth\/callback/);
  });

  it('parses a successful OAuth callback with a code', () => {
    const parsed = parseOAuthCallback('exp://localhost:8081/--/auth/callback?code=test-code&flow_id=test-flow');
    expect(parsed.code).toBe('test-code');
    expect(parsed.flowId).toBe('test-flow');
  });

  it('parses the native PKCE callback on the Jarumba scheme', () => {
    const parsed = parseOAuthCallback('jarumba://auth/callback?code=pkce-code');
    expect(parsed.code).toBe('pkce-code');
    expect(parsed.error).toBeUndefined();
  });

  it('flags an implicit-flow token fragment instead of treating it as PKCE', () => {
    const parsed = parseOAuthCallback(
      'jarumba://auth/callback#access_token=FAKE_ACCESS&refresh_token=FAKE_REFRESH&expires_at=1&expires_in=3600&provider_token=FAKE_PROVIDER',
    );
    expect(parsed.error).toBe('implicit_flow_callback');
    expect(parsed.code).toBeUndefined();
    expect(`${parsed.error} ${parsed.message}`).not.toContain('FAKE');
  });

  it('reports callback structure without leaking parameter values', () => {
    const summary = describeOAuthCallback('jarumba://auth/callback?code=SECRET_CODE&flow_id=SECRET_FLOW');
    expect(summary).toContain('scheme=jarumba');
    expect(summary).toContain('host=auth');
    expect(summary).toContain('path=/callback');
    expect(summary).toContain('query=[code,flow_id]');
    expect(summary).not.toContain('SECRET_CODE');
    expect(summary).not.toContain('SECRET_FLOW');
  });

  it('reports fragment parameter names for an implicit callback without values', () => {
    const summary = describeOAuthCallback('jarumba://auth/callback#access_token=FAKE_ACCESS&refresh_token=FAKE_REFRESH');
    expect(summary).toContain('fragment=[access_token,refresh_token]');
    expect(summary).toContain('query=[]');
    expect(summary).not.toContain('FAKE');
  });

  it('parses a cancelled OAuth callback without a code', () => {
    const parsed = parseOAuthCallback('exp://localhost:8081/--/auth/callback?error=access_denied&error_description=User+cancelled');
    expect(parsed.error).toBe('access_denied');
    expect(parsed.message).toContain('cancel');
  });

  it('maps backend profile data to the frontend profile model', () => {
    const profile = toProfile({ id: '123', display_name: 'Jarumba User', avatar_url: 'https://x', created_at: '2024-01-01', updated_at: '2024-01-01' });
    expect(profile?.display_name).toBe('Jarumba User');
  });

  it('sanitizes sensitive query parameter values for diagnostic logging', () => {
    const url = 'exp://192.168.1.50:8081/--/auth/callback?code=secret_code_123&flow_id=flow_abc';
    const sanitized = sanitizeUrlForLogging(url);
    expect(sanitized).toBe('exp://192.168.1.50:8081/--/auth/callback?code=[REDACTED]&flow_id=[REDACTED]');
    expect(sanitized).not.toContain('secret_code_123');
  });

  it('never logs fragment token values', () => {
    const sanitized = sanitizeUrlForLogging('jarumba://auth/callback#access_token=FAKE_ACCESS&refresh_token=FAKE_REFRESH');
    expect(sanitized).toBe('jarumba://auth/callback#access_token=[REDACTED]&refresh_token=[REDACTED]');
    expect(sanitized).not.toContain('FAKE');
  });

  it('exchanges the PKCE code from the Jarumba callback with its flow id', async () => {
    mockSignInWithOAuth.mockResolvedValue({
      data: {
        provider: 'google',
        url: 'https://test-project.supabase.co/auth/v1/authorize?provider=google',
        flowId: 'flow-id-1234',
      },
      error: null,
    });
    mockOpenAuthSessionAsync.mockResolvedValue({ type: 'success', url: 'jarumba://auth/callback?code=auth-code-123' });
    mockExchangeCodeForSession.mockResolvedValue({
      data: { session: { user: { id: 'user-1' }, access_token: 'token' } },
      error: null,
    });

    render(
      <AuthProvider>
        <SignInConsumer />
      </AuthProvider>,
    );

    fireEvent.press(screen.getByLabelText('Continue with Google'));

    await waitFor(() => {
      expect(mockExchangeCodeForSession).toHaveBeenCalledWith('auth-code-123', { flowId: 'flow-id-1234' });
    });

    expect(mockOpenAuthSessionAsync).toHaveBeenCalledWith(
      'https://test-project.supabase.co/auth/v1/authorize?provider=google',
      'jarumba://auth/callback',
      { showInRecents: true },
    );
  });

  it('reports an implicit-flow token callback as an error instead of a session', async () => {
    mockSignInWithOAuth.mockResolvedValue({
      data: {
        provider: 'google',
        url: 'https://test-project.supabase.co/auth/v1/authorize?provider=google',
        flowId: 'flow-id-1234',
      },
      error: null,
    });
    mockOpenAuthSessionAsync.mockResolvedValue({
      type: 'success',
      url: 'jarumba://auth/callback#access_token=FAKE_ACCESS&refresh_token=FAKE_REFRESH&expires_in=3600&token_type=bearer',
    });

    render(
      <AuthProvider>
        <SignInConsumer />
      </AuthProvider>,
    );

    fireEvent.press(screen.getByLabelText('Continue with Google'));

    await waitFor(() => {
      expect(screen.getByTestId('sign-in-error')).toBeTruthy();
    });

    expect(mockExchangeCodeForSession).not.toHaveBeenCalled();
    expect(screen.getByTestId('sign-in-error').props.children).not.toContain('FAKE_ACCESS');
  });
});

