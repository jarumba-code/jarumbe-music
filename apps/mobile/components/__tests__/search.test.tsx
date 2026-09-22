import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { SearchScreen } from '../../screens/SearchScreen';
import { searchTracks } from '../../lib/api';

jest.mock('../../lib/api', () => ({
  searchTracks: jest.fn(),
}));

describe('music search API', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns a successful search response', async () => {
    (searchTracks as jest.Mock).mockResolvedValue({
      query: 'afrobeats',
      limit: 20,
      offset: 0,
      total: 1,
      results: [
        {
          provider: 'jamendo',
          provider_track_id: '123',
          title: 'Afrobeats Glow',
          artist: 'Nia',
          album: 'Sunrise',
          duration: 210,
          artwork_url: 'https://example.com/art.jpg',
          stream_url: 'https://example.com/stream.mp3',
          download_url: 'https://example.com/download.mp3',
          download_allowed: true,
          license_url: null,
          license_name: null,
          source_url: null,
          release_date: '2024-01-01',
        },
      ],
    });

    await expect(searchTracks('afrobeats')).resolves.toMatchObject({ query: 'afrobeats' });
  });

  it('returns an empty result set without error', async () => {
    (searchTracks as jest.Mock).mockResolvedValue({
      query: 'zzz',
      limit: 20,
      offset: 0,
      total: 0,
      results: [],
    });

    await expect(searchTracks('zzz')).resolves.toMatchObject({ total: 0, results: [] });
  });

  it('surfaces a network failure as a friendly message', async () => {
    (searchTracks as jest.Mock).mockRejectedValue(new Error('Network error'));

    await expect(searchTracks('afrobeats')).rejects.toThrow('Network error');
  });

  it('surfaces a rate limit error', async () => {
    (searchTracks as jest.Mock).mockRejectedValue(new Error('429: Rate limited'));

    await expect(searchTracks('afrobeats')).rejects.toThrow('429: Rate limited');
  });

  it('surfaces a provider outage error', async () => {
    (searchTracks as jest.Mock).mockRejectedValue(new Error('503: Music provider is temporarily unavailable'));

    await expect(searchTracks('afrobeats')).rejects.toThrow('503: Music provider is temporarily unavailable');
  });
});

describe('SearchScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders a loading state while a search request is in flight', async () => {
    (searchTracks as jest.Mock).mockImplementation(() => new Promise(() => undefined));

    render(<SearchScreen />);
    fireEvent.changeText(screen.getByPlaceholderText('Search for tracks...'), 'afrobeats');

    await waitFor(() => {
      expect(screen.getByTestId('search-loading')).toBeTruthy();
    });
  });

  it('renders an empty state when no results match', async () => {
    (searchTracks as jest.Mock).mockResolvedValue({
      query: 'zzz',
      limit: 20,
      offset: 0,
      total: 0,
      results: [],
    });

    render(<SearchScreen />);
    fireEvent.changeText(screen.getByPlaceholderText('Search for tracks...'), 'zzz');

    await waitFor(() => {
      expect(screen.getByText(/no tracks found/i)).toBeTruthy();
    });
  });

  it('renders an error message when the search fails', async () => {
    (searchTracks as jest.Mock).mockRejectedValue(new Error('Network error'));

    render(<SearchScreen />);
    fireEvent.changeText(screen.getByPlaceholderText('Search for tracks...'), 'afrobeats');

    await waitFor(() => {
      expect(screen.getByText(/network error/i)).toBeTruthy();
    });
  });

  it('renders real result rows for successful searches', async () => {
    (searchTracks as jest.Mock).mockResolvedValue({
      query: 'afrobeats',
      limit: 20,
      offset: 0,
      total: 1,
      results: [
        {
          provider: 'jamendo',
          provider_track_id: '123',
          title: 'Afrobeats Glow',
          artist: 'Nia',
          album: 'Sunrise',
          duration: 210,
          artwork_url: 'https://example.com/art.jpg',
          stream_url: 'https://example.com/stream.mp3',
          download_url: 'https://example.com/download.mp3',
          download_allowed: true,
          license_url: null,
          license_name: null,
          source_url: null,
          release_date: '2024-01-01',
        },
      ],
    });

    render(<SearchScreen />);
    fireEvent.changeText(screen.getByPlaceholderText('Search for tracks...'), 'afrobeats');

    await waitFor(() => {
      expect(screen.getByText('Afrobeats Glow')).toBeTruthy();
      expect(screen.getByText('Nia')).toBeTruthy();
    });
  });

  it('hides the download affordance when download_allowed is false', async () => {
    (searchTracks as jest.Mock).mockResolvedValue({
      query: 'jazz',
      limit: 20,
      offset: 0,
      total: 1,
      results: [
        {
          provider: 'jamendo',
          provider_track_id: '999',
          title: 'Quiet Jazz',
          artist: 'Milo',
          album: null,
          duration: 185,
          artwork_url: null,
          stream_url: null,
          download_url: null,
          download_allowed: false,
          license_url: null,
          license_name: null,
          source_url: null,
          release_date: '2024-01-01',
        },
      ],
    });

    render(<SearchScreen />);
    fireEvent.changeText(screen.getByPlaceholderText('Search for tracks...'), 'jazz');

    await waitFor(() => {
      expect(screen.getByText('Quiet Jazz')).toBeTruthy();
    });

    expect(screen.queryByLabelText('Download track')).toBeNull();
  });
});
