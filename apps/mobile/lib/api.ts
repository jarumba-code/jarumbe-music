import { Platform } from 'react-native';
import { createClient, Session, SupabaseClient } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';

import { Favorite, Playlist, PlaylistTrack, Profile, RecentlyPlayed, SearchResponse, Track } from './types';

export const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || 'https://jarumbe-music-production.up.railway.app';
const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL || '';
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY || '';

export const apiConfig = {
  apiBaseUrl: API_BASE_URL,
  supabaseUrl: SUPABASE_URL,
  supabaseAnonKey: SUPABASE_ANON_KEY,
};

// Singleton Supabase client shared by AuthContext and the API layer.
// getAccessToken() must use the SAME client instance that AuthContext uses so
// in-memory session state (set via setSession / exchangeCodeForSession) is
// visible to protected API requests without a storage round-trip race.
let _supabaseClient: SupabaseClient | null = null;

export function getSupabaseClient(): SupabaseClient {
  if (!_supabaseClient) {
    _supabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: Platform.OS === 'web',
        // Jarumba uses the authorization-code (PKCE) flow end to end:
        // signInWithOAuth() sends a code_challenge, Supabase redirects back to
        // jarumba://auth/callback?code=..., and the app exchanges that code with
        // exchangeCodeForSession(). @supabase/auth-js defaults to 'implicit',
        // which skips the code_challenge and returns tokens in the URL fragment,
        // so the flow type must be set explicitly.
        flowType: 'pkce',
        storage: {
          getItem: async (key: string) => SecureStore.getItemAsync(key),
          setItem: async (key: string, value: string) => SecureStore.setItemAsync(key, value),
          removeItem: async (key: string) => SecureStore.deleteItemAsync(key),
        },
      },
    });
  }
  return _supabaseClient;
}

// Exported for use by AuthContext so both layers share one client instance.
export const supabase = getSupabaseClient();

// Module-level session reference that AuthContext updates so getAccessToken()
// always uses the session that AuthContext has already restored, avoiding a
// race with SecureStore reads inside supabase.auth.getSession().
let _currentSession: Session | null = null;

export function setCurrentSession(session: Session | null): void {
  _currentSession = session;
}

export async function getAccessToken(): Promise<string | null> {
  // Prefer the session AuthContext restored; fall back to a fresh getSession()
  // only when no local reference is available.
  if (_currentSession?.access_token) {
    return _currentSession.access_token;
  }
  const supabase = getSupabaseClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

// Helper: check whether a valid Supabase session is currently available.
// Used to gate authenticated requests until session restoration finishes.
export async function isAuthReady(): Promise<boolean> {
  if (_currentSession?.access_token) {
    return true;
  }
  const supabase = getSupabaseClient();
  const { data } = await supabase.auth.getSession();
  return !!data.session?.access_token;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getAccessToken();
  const headers = new Headers(init.headers || {});
  headers.set('Accept', 'application/json');
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const text = await response.text();
    let detail = 'Request failed';
    try {
      const parsed = JSON.parse(text);
      detail = typeof parsed?.detail === 'string' ? parsed.detail : detail;
    } catch {
      detail = text || detail;
    }

    if (response.status === 429) {
      const retryAfter = Number(response.headers.get('Retry-After') ?? '0');
      throw new Error(`Rate limited${retryAfter > 0 ? `; retry in ${retryAfter}s` : ''}`);
    }

    throw new Error(`${response.status}: ${detail}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return (await response.json()) as T;
  }

  return undefined as T;
}

function formatApiError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error ?? '');

  if (/401/.test(message)) return 'Your session expired. Please sign in again.';
  if (/429/.test(message)) return 'Too many searches. Please wait a moment and try again.';
  if (/502|503/.test(message)) return 'Music search is temporarily unavailable. Please try again soon.';
  if (/Failed to fetch|Network|fetch/i.test(message)) return 'Network error. Please check your connection and try again.';

  return message || 'Unable to search music right now.';
}

export async function searchTracks(query: string, limit = 20, offset = 0): Promise<SearchResponse> {
  const normalizedQuery = query.trim();
  if (!normalizedQuery) {
    return {
      query: '',
      limit,
      offset,
      total: 0,
      results: [],
    };
  }

  const url = `/api/v1/music/search?q=${encodeURIComponent(normalizedQuery)}&limit=${limit}&offset=${offset}`;

  try {
    return await request<SearchResponse>(url, { method: 'GET' });
  } catch (error) {
    throw new Error(formatApiError(error));
  }
}

export async function getMe(): Promise<Profile> {
  return request<Profile>('/api/v1/me', { method: 'GET' });
}

export async function getFavorites(): Promise<Favorite[]> {
  return request<Favorite[]>('/api/v1/favorites', { method: 'GET' });
}

export async function addFavorite(payload: Omit<Favorite, 'id' | 'user_id' | 'created_at'>): Promise<Favorite> {
  return request<Favorite>('/api/v1/favorites', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function removeFavorite(provider: string, providerTrackId: string): Promise<void> {
  await request<void>(`/api/v1/favorites/${encodeURIComponent(provider)}/${encodeURIComponent(providerTrackId)}`, {
    method: 'DELETE',
  });
}

export async function getPlaylists(): Promise<Playlist[]> {
  return request<Playlist[]>('/api/v1/playlists', { method: 'GET' });
}

export async function createPlaylist(payload: { name: string; description?: string | null; is_public?: boolean }): Promise<Playlist> {
  return request<Playlist>('/api/v1/playlists', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function getPlaylist(playlistId: string): Promise<Playlist> {
  return request<Playlist>(`/api/v1/playlists/${playlistId}`, { method: 'GET' });
}

export async function addTrackToPlaylist(playlistId: string, payload: Omit<PlaylistTrack, 'id' | 'playlist_id' | 'added_at'>): Promise<PlaylistTrack> {
  return request<PlaylistTrack>(`/api/v1/playlists/${playlistId}/tracks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function removeTrackFromPlaylist(playlistId: string, trackId: string): Promise<void> {
  await request<void>(`/api/v1/playlists/${playlistId}/tracks/${trackId}`, {
    method: 'DELETE',
  });
}

export async function getRecentlyPlayed(): Promise<RecentlyPlayed[]> {
  return request<RecentlyPlayed[]>('/api/v1/recently-played', { method: 'GET' });
}

export async function recordRecentlyPlayed(payload: Omit<RecentlyPlayed, 'id' | 'user_id' | 'played_at'>): Promise<RecentlyPlayed> {
  return request<RecentlyPlayed>('/api/v1/recently-played', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function normalizeTrack(raw: Partial<Track> & { id?: string }): Track {
  return {
    id: raw.id ?? `${raw.provider ?? 'provider'}:${raw.provider_track_id ?? 'unknown'}`,
    provider: raw.provider ?? 'jamendo',
    provider_track_id: raw.provider_track_id ?? raw.id ?? 'unknown',
    title: raw.title ?? 'Untitled Track',
    artist: raw.artist ?? 'Unknown Artist',
    album: raw.album ?? null,
    duration: raw.duration ?? null,
    artwork_url: raw.artwork_url ?? null,
    stream_url: raw.stream_url ?? null,
    download_url: raw.download_url ?? null,
    download_allowed: Boolean(raw.download_allowed),
    license_url: raw.license_url ?? null,
    license_name: raw.license_name ?? null,
    source_url: raw.source_url ?? null,
    release_date: raw.release_date ?? null,
  };
}
