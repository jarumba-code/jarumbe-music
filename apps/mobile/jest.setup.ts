import '@testing-library/jest-native/extend-expect';

// Supabase credentials used by lib/api's module-level createClient(). Jest does
// not load .env files, so without these the client constructor throws before any
// test can run. These are throwaway values; no request is ever made.
process.env.EXPO_PUBLIC_SUPABASE_URL =
  process.env.EXPO_PUBLIC_SUPABASE_URL || 'https://test-project.supabase.co';
process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY =
  process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY || 'test-anon-key';

jest.mock('expo-audio', () => ({
  useAudioPlayer: jest.fn(() => ({
    play: jest.fn(),
    pause: jest.fn(),
    replace: jest.fn(),
    seekTo: jest.fn(),
    playing: false,
    currentTime: 0,
  })),
  useAudioPlayerStatus: jest.fn(() => ({
    playing: false,
    currentTime: 0,
    duration: 0,
  })),
  setAudioModeAsync: jest.fn().mockResolvedValue(undefined),
  AudioPlayer: jest.fn(),
}));
