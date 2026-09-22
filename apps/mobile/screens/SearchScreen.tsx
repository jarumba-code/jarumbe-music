import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, SafeAreaView, ScrollView, StyleSheet, Text, View, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { TrackRow } from '../components/TrackRow';
import { SearchBar } from '../components/SearchBar';
import { Chip } from '../components/Chip';
import { GenreCard } from '../components/GenreCard';
import { SectionHeader } from '../components/SectionHeader';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';
import { useTheme } from '../context/ThemeContext';
import { usePlayback } from '../context/PlaybackContext';
import { radius, spacing, typography } from '../constants/theme';
import { searchTracks } from '../lib/api';
import { Track } from '../lib/types';

const GENRE_SHORTCUTS = [
  { name: 'Afrobeats', icon: 'musical-note', query: 'afrobeats' },
  { name: 'Jazz', icon: 'headset', query: 'jazz' },
  { name: 'Rock', icon: 'flash', query: 'rock' },
  { name: 'Amapiano', icon: 'radio', query: 'amapiano' },
];

export function SearchScreen() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Track[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const requestIdRef = useRef(0);
  const lastQueryRef = useRef('');
  
  const { colors } = useTheme();
  const { currentTrack, playTrack } = usePlayback();

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setLoading(false);
      setError(null);
      lastQueryRef.current = '';
      return;
    }

    if (trimmed === lastQueryRef.current) {
      return;
    }

    lastQueryRef.current = trimmed;
    const activeRequestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);

    const timer = setTimeout(async () => {
      try {
        const response = await searchTracks(trimmed, 20, 0);
        if (activeRequestId !== requestIdRef.current) return;
        setResults(response.results ?? []);
        setError(null);
      } catch (caught) {
        if (activeRequestId !== requestIdRef.current) return;
        const message = caught instanceof Error ? caught.message : 'Unable to search music right now.';
        setError(message);
        setResults([]);
      } finally {
        if (activeRequestId === requestIdRef.current) {
          setLoading(false);
        }
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  const hasResults = results.length > 0;
  const showEmptyState = !loading && !error && query.trim().length > 0 && !hasResults;
  const isSearchActive = query.trim().length > 0;

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.bgBase }]}>
      <ScrollView contentContainerStyle={[styles.content, currentTrack && { paddingBottom: 80 }]} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <View style={styles.headerTitleWrap}>
            <Ionicons name="musical-notes" size={24} color={colors.accentPrimary} />
            <Text style={[styles.title, { color: colors.textPrimary }]}>Search</Text>
          </View>
          <View style={[styles.avatar, { backgroundColor: colors.bgElevated, alignItems: 'center', justifyContent: 'center' }]}>
            <Ionicons name="person" size={16} color={colors.textTertiary} />
          </View>
        </View>

        <SearchBar value={query} onChangeText={setQuery} placeholder="Search for tracks..." onClear={() => setQuery('')} />

        {isSearchActive ? (
          <View style={styles.filterRow}>
            <Chip label="All" active onPress={() => {}} />
            <Chip label="Songs" onPress={() => {}} />
            <Chip label="Artists" style={{ opacity: 0.5 }} onPress={() => {}} />
            <Chip label="Playlists" style={{ opacity: 0.5 }} onPress={() => {}} />
          </View>
        ) : null}

        {loading ? (
          <View style={styles.stateContainer}>
            <ActivityIndicator color={colors.accentPrimary} size="large" testID="search-loading" />
          </View>
        ) : null}

        {error ? (
          <ErrorState message={error} onRetry={() => setQuery(query || 'afrobeats')} />
        ) : null}

        {showEmptyState ? (
          <EmptyState title="No tracks found" message="Try a different phrase or artist name." icon="search-outline" />
        ) : null}

        {!loading && hasResults ? (
          <View style={styles.resultsWrap}>
            {results.map((track) => (
              <TrackRow
                key={`${track.provider}:${track.provider_track_id}`}
                track={track}
                isActive={currentTrack?.provider_track_id === track.provider_track_id}
                durationLabel={track.duration ? `${Math.floor(track.duration / 60)}:${String(track.duration % 60).padStart(2, '0')}` : undefined}
                onPress={(t) => playTrack(t)}
                showMenu={false}
              />
            ))}
          </View>
        ) : null}

        {!isSearchActive && !loading ? (
          <View style={styles.browseWrap}>
            <SectionHeader title="Browse Genres" />
            <View style={styles.genreGrid}>
              {GENRE_SHORTCUTS.map((genre) => (
                <View key={genre.query} style={styles.genreCardWrapper}>
                  <GenreCard
                    name={genre.name}
                    icon={genre.icon as keyof typeof Ionicons.glyphMap}
                    onPress={() => setQuery(genre.query)}
                  />
                </View>
              ))}
            </View>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  content: {
    padding: spacing.xl,
    gap: spacing.lg,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  headerTitleWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  title: {
    fontSize: typography.h1.fontSize,
    fontWeight: typography.h1.fontWeight,
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
  },
  filterRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  stateContainer: {
    padding: spacing.xl,
    alignItems: 'center',
    justifyContent: 'center',
  },
  resultsWrap: {
    gap: spacing.xs,
  },
  browseWrap: {
    marginTop: spacing.md,
  },
  genreGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginTop: spacing.sm,
  },
  genreCardWrapper: {
    width: '47%',
  },
});
