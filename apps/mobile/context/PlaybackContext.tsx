import React, { createContext, useContext, useEffect, useState, useMemo } from 'react';
import { useAudioPlayer, setAudioModeAsync, AudioPlayer } from 'expo-audio';
import { Track } from '../lib/types';
import { recordRecentlyPlayed } from '../lib/api';

type PlaybackContextType = {
  currentTrack: Track | null;
  isPlaying: boolean;
  position: number;
  duration: number;
  playTrack: (track: Track) => void;
  pause: () => void;
  resume: () => void;
  seekTo: (position: number) => void;
  togglePlayPause: () => void;
  player: AudioPlayer | null;
};

const PlaybackContext = createContext<PlaybackContextType | undefined>(undefined);

export function PlaybackProvider({ children }: { children: React.ReactNode }) {
  const [currentTrack, setCurrentTrack] = useState<Track | null>(null);
  const player = useAudioPlayer(null);

  useEffect(() => {
    setAudioModeAsync({
      playsInSilentMode: true,
      shouldPlayInBackground: true,
    });
  }, []);

  const isPlaying = player?.playing ?? false;
  // Attempt to read current position; expo-audio player might have currentTime
  // We'll use 0 as fallback if unavailable.
  const position = (player as any)?.currentTime ?? 0;
  const duration = currentTrack?.duration ?? 0;

  const playTrack = (track: Track) => {
    if (track.stream_url) {
      setCurrentTrack(track);
      player.replace(track.stream_url);
      player.play();
      
      // Record to recently played
      recordRecentlyPlayed({
        provider: track.provider,
        provider_track_id: track.provider_track_id,
        title: track.title,
        artist: track.artist,
        album: track.album,
        duration: track.duration,
        artwork_url: track.artwork_url,
        license_url: track.license_url,
        license_name: track.license_name,
      }).catch(err => console.log('Failed to record recently played', err));
    } else {
      console.warn('[PLAYBACK DEBUG] No stream_url for track');
    }
  };

  const pause = () => player.pause();
  const resume = () => player.play();
  const seekTo = (pos: number) => player.seekTo(pos);
  const togglePlayPause = () => {
    if (isPlaying) {
      pause();
    } else {
      resume();
    }
  };

  const value = useMemo(
    () => ({
      currentTrack,
      isPlaying,
      position,
      duration,
      playTrack,
      pause,
      resume,
      seekTo,
      togglePlayPause,
      player,
    }),
    [currentTrack, isPlaying, position, duration, player]
  );

  return <PlaybackContext.Provider value={value}>{children}</PlaybackContext.Provider>;
}

export function usePlayback() {
  const context = useContext(PlaybackContext);
  if (context === undefined) {
    return {
      currentTrack: null,
      isPlaying: false,
      position: 0,
      duration: 0,
      playTrack: () => {},
      pause: () => {},
      resume: () => {},
      seekTo: () => {},
      togglePlayPause: () => {},
      player: null,
    };
  }
  return context;
}
