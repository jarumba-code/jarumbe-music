export type Track = {
  id: string;
  provider: string;
  provider_track_id: string;
  title: string;
  artist: string;
  album?: string | null;
  duration?: number | null;
  artwork_url?: string | null;
  stream_url?: string | null;
  download_url?: string | null;
  download_allowed: boolean;
  license_url?: string | null;
  license_name?: string | null;
  source_url?: string | null;
  release_date?: string | null;
};

export type SearchResponse = {
  query: string;
  limit: number;
  offset: number;
  total: number;
  results: Track[];
};

export type Profile = {
  id: string;
  display_name?: string | null;
  avatar_url?: string | null;
  created_at: string;
  updated_at: string;
};

export type Favorite = {
  id: string;
  user_id: string;
  provider: string;
  provider_track_id: string;
  title: string;
  artist: string;
  album?: string | null;
  duration?: number | null;
  artwork_url?: string | null;
  license_url?: string | null;
  license_name?: string | null;
  created_at: string;
};

export type Playlist = {
  id: string;
  user_id: string;
  name: string;
  description?: string | null;
  is_public: boolean;
  created_at: string;
  updated_at: string;
};

export type PlaylistTrack = {
  id: string;
  playlist_id: string;
  position: number;
  provider: string;
  provider_track_id: string;
  title: string;
  artist: string;
  album?: string | null;
  duration?: number | null;
  artwork_url?: string | null;
  license_url?: string | null;
  license_name?: string | null;
  added_at: string;
};

export type RecentlyPlayed = {
  id: string;
  user_id: string;
  provider: string;
  provider_track_id: string;
  title: string;
  artist: string;
  album?: string | null;
  duration?: number | null;
  artwork_url?: string | null;
  license_url?: string | null;
  license_name?: string | null;
  played_at: string;
};
