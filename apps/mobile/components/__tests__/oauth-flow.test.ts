import * as SecureStore from 'expo-secure-store';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async () => null),
  setItemAsync: jest.fn(async () => undefined),
  deleteItemAsync: jest.fn(async () => undefined),
}));

const storageMock = SecureStore.setItemAsync as unknown as jest.Mock;

// The API module reads EXPO_PUBLIC_* values at import time, so the test env is
// applied before it is required. No module registry resets here: resetting
// would create a second expo-secure-store mock instance and detach storageMock.
Object.assign(process.env, {
  EXPO_PUBLIC_SUPABASE_URL: 'https://test-project.supabase.co',
  EXPO_PUBLIC_SUPABASE_ANON_KEY: 'test-anon-key',
  EXPO_PUBLIC_API_BASE_URL: 'https://api.test.invalid',
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { getSupabaseClient } = require('../../lib/api') as typeof import('../../lib/api');

const GOOGLE_OPTIONS = { redirectTo: 'jarumba://auth/callback', skipBrowserRedirect: true };

describe('supabase PKCE configuration', () => {
  beforeEach(() => {
    storageMock.mockClear();
  });

  it('configures the Supabase client for the PKCE flow', () => {
    const client = getSupabaseClient();
    const authSettings = client.auth as unknown as { flowType?: string };

    // auth-js defaults to 'implicit', which returns tokens in the URL fragment
    // instead of an authorization code.
    expect(authSettings.flowType).toBe('pkce');
  });

  it('requests a PKCE code challenge when signing in with Google', async () => {
    const client = getSupabaseClient();

    const { data, error } = await client.auth.signInWithOAuth({
      provider: 'google',
      options: GOOGLE_OPTIONS,
    });

    expect(error).toBeNull();
    const parsed = new URL(data?.url ?? '');
    const paramNames = Array.from(parsed.searchParams.keys());

    expect(paramNames).toContain('provider');
    expect(paramNames).toContain('redirect_to');
    expect(paramNames).toContain('code_challenge');
    expect(paramNames).toContain('code_challenge_method');
    expect(parsed.searchParams.get('redirect_to') ?? '').toContain('jarumba://auth/callback');
  });

  it('persists the PKCE code verifier through the SecureStore adapter', async () => {
    const client = getSupabaseClient();

    await client.auth.signInWithOAuth({ provider: 'google', options: GOOGLE_OPTIONS });

    const storedKeys = storageMock.mock.calls.map(([key]) => String(key));
    expect(storedKeys.some((key) => key.endsWith('-code-verifier'))).toBe(true);
  });
});
