import { Platform } from 'react-native';
import { makeRedirectUri } from 'expo-auth-session';

import { Profile } from './types';

export const JARUMBA_OAUTH_SCHEME = 'jarumba';
export const JARUMBA_OAUTH_PATH = 'auth/callback';
export const JARUMBA_OAUTH_CALLBACK = 'jarumba://auth/callback';

// Fragment parameters produced by the implicit grant. Jarumba does not use this
// flow; the names are only used to report the mismatch safely.
const IMPLICIT_GRANT_PARAMS = [
  'access_token',
  'refresh_token',
  'expires_at',
  'expires_in',
  'provider_token',
  'provider_refresh_token',
  'token_type',
];

function decodeParamValue(raw: string): string {
  try {
    return decodeURIComponent(raw.replace(/\+/g, ' '));
  } catch {
    return raw;
  }
}

function parseParamString(raw: string): Record<string, string> {
  const params: Record<string, string> = {};
  if (!raw) return params;

  raw.split('&').forEach((pair) => {
    if (!pair) return;
    const separatorIdx = pair.indexOf('=');
    const rawKey = separatorIdx === -1 ? pair : pair.slice(0, separatorIdx);
    const key = decodeParamValue(rawKey).trim();
    if (!key || key in params) return;
    params[key] = separatorIdx === -1 ? '' : decodeParamValue(pair.slice(separatorIdx + 1));
  });

  return params;
}

export function getOAuthCallbackParams(url: string): {
  query: Record<string, string>;
  fragment: Record<string, string>;
} {
  if (!url) return { query: {}, fragment: {} };

  const hashIdx = url.indexOf('#');
  const withoutFragment = hashIdx === -1 ? url : url.slice(0, hashIdx);
  const fragmentRaw = hashIdx === -1 ? '' : url.slice(hashIdx + 1);
  const queryIdx = withoutFragment.indexOf('?');
  const queryRaw = queryIdx === -1 ? '' : withoutFragment.slice(queryIdx + 1);

  return { query: parseParamString(queryRaw), fragment: parseParamString(fragmentRaw) };
}

/**
 * Structure-only view of an OAuth callback URL for diagnostics.
 *
 * React Native's `URL` polyfill cannot describe custom schemes such as
 * `jarumba://` (empty host/pathname) and reports an empty search for URLs whose
 * parameters live in the fragment, so the URL is split manually instead.
 * Only parameter NAMES are returned - never values.
 */
export function describeOAuthCallback(url: string): string {
  if (!url) return 'scheme=none host=none port=none path=none query=[] fragment=[]';

  const hashIdx = url.indexOf('#');
  const withoutFragment = hashIdx === -1 ? url : url.slice(0, hashIdx);
  const queryIdx = withoutFragment.indexOf('?');
  const base = queryIdx === -1 ? withoutFragment : withoutFragment.slice(0, queryIdx);

  const schemeIdx = base.indexOf('://');
  const scheme = (schemeIdx === -1 ? '' : base.slice(0, schemeIdx)).replace(/:$/, '');
  const afterScheme = schemeIdx === -1 ? base : base.slice(schemeIdx + 3);
  const slashIdx = afterScheme.indexOf('/');
  const authority = slashIdx === -1 ? afterScheme : afterScheme.slice(0, slashIdx);
  const path = slashIdx === -1 ? '' : afterScheme.slice(slashIdx);
  const portIdx = authority.lastIndexOf(':');
  const port = portIdx === -1 ? '' : authority.slice(portIdx + 1);
  const host = portIdx === -1 ? authority : authority.slice(0, portIdx);

  const { query, fragment } = getOAuthCallbackParams(url);

  return [
    `scheme=${scheme || 'none'}`,
    `host=${host || 'none'}`,
    `port=${port || 'none'}`,
    `path=${path || 'none'}`,
    `query=[${Object.keys(query).join(',')}]`,
    `fragment=[${Object.keys(fragment).join(',')}]`,
  ].join(' ');
}

export function buildApiHeaders(accessToken?: string | null, extraHeaders?: Record<string, string>) {
  const headers = new Headers();
  headers.set('Accept', 'application/json');

  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  if (extraHeaders) {
    Object.entries(extraHeaders).forEach(([key, value]) => {
      headers.set(key, value);
    });
  }

  return headers;
}

export function buildGoogleRedirectUrl() {
  if (Platform.OS === 'web') {
    return typeof window !== 'undefined' ? `${window.location.origin}/auth/callback` : 'http://localhost:8081/auth/callback';
  }

  // In a standalone/development build the registered Expo scheme is
  // `jarumba`, so this must resolve to `jarumba://auth/callback`.
  // Passing the scheme explicitly keeps Expo Go / dev-client proxy URLs
  // from leaking into the native OAuth redirect.
  try {
    const nativeRedirect = makeRedirectUri({
      scheme: JARUMBA_OAUTH_SCHEME,
      path: JARUMBA_OAUTH_PATH,
    });
    if (nativeRedirect.startsWith(`${JARUMBA_OAUTH_SCHEME}://`)) {
      return nativeRedirect;
    }
    return JARUMBA_OAUTH_CALLBACK;
  } catch {
    return JARUMBA_OAUTH_CALLBACK;
  }
}

export function parseOAuthCallback(url: string): {
  code?: string;
  flowId?: string;
  error?: string;
  message?: string;
} {
  if (!url || !url.startsWith('http') && !url.includes('://') && !url.includes('?')) {
    return { error: 'malformed_redirect', message: 'Invalid OAuth redirect URL.' };
  }

  const { query, fragment } = getOAuthCallbackParams(url);

  const error = query.error || fragment.error;
  const errorDescription = query.error_description || fragment.error_description;
  const flowId = query.flow_id || query.sb_flow_id || fragment.flow_id || fragment.sb_flow_id || undefined;
  // Jarumba uses the PKCE flow, so the authorization code always arrives as a
  // query string parameter. Fragment parameters are never treated as a code.
  const code = query.code || undefined;

  if (error) {
    return {
      error,
      message: errorDescription || `OAuth error: ${error}`,
    };
  }

  if (!code) {
    if (IMPLICIT_GRANT_PARAMS.some((name) => name in query || name in fragment)) {
      return {
        error: 'implicit_flow_callback',
        message: 'Received an implicit-flow callback (token fragment) but this app uses PKCE. Expected an authorization code in the query string.',
      };
    }

    return {
      error: 'missing_code',
      message: 'No authorization code was returned from the OAuth provider.',
    };
  }

  return { code, flowId };
}

export function toProfile(data: Partial<Profile> | null | undefined): Profile | null {
  if (!data) return null;

  return {
    id: data.id ?? '',
    display_name: data.display_name ?? null,
    avatar_url: data.avatar_url ?? null,
    created_at: data.created_at ?? new Date().toISOString(),
    updated_at: data.updated_at ?? new Date().toISOString(),
  };
}

export function getErrorMessage(error: unknown, fallback = 'Something went wrong') {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === 'string' && error.length > 0) return error;
  if (error && typeof error === 'object' && 'message' in error && typeof (error as { message?: string }).message === 'string') {
    return (error as { message: string }).message;
  }
  return fallback;
}

export function sanitizeUrlForLogging(rawUrl: string): string {
  if (!rawUrl) return '';

  const hashIdx = rawUrl.indexOf('#');
  const withoutFragment = hashIdx === -1 ? rawUrl : rawUrl.slice(0, hashIdx);
  const fragment = hashIdx === -1 ? '' : rawUrl.slice(hashIdx + 1);
  const queryIdx = withoutFragment.indexOf('?');
  const base = queryIdx === -1 ? withoutFragment : withoutFragment.slice(0, queryIdx);
  const queryStr = queryIdx === -1 ? '' : withoutFragment.slice(queryIdx + 1);

  const redact = (paramString: string) =>
    paramString
      .split('&')
      .map((p) => {
        const [k] = p.split('=');
        return k ? `${k}=[REDACTED]` : '';
      })
      .filter(Boolean)
      .join('&');

  const redactedQuery = redact(queryStr);
  const sanitized = redactedQuery ? `${base}?${redactedQuery}` : base;

  if (!fragment) return sanitized;

  const redactedFragment = redact(fragment);
  return redactedFragment ? `${sanitized}#${redactedFragment}` : sanitized;
}

