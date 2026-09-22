import React, { useEffect, useState, useCallback } from 'react';
import { RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';

import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { usePlayback } from '../context/PlaybackContext';
import { getFavorites, getRecentlyPlayed, normalizeTrack } from '../lib/api';
import { Favorite, RecentlyPlayed } from '../lib/types';
import { radius, spacing, typography } from '../constants/theme';
import { TrackCard } from '../components/TrackCard';
import { ComingSoonCard } from '../components/ComingSoonCard';
import { SectionHeader } from '../components/SectionHeader';
import { TrackRow } from '../components/TrackRow';

export function HomeScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<any>();
  const { profile, session, loading: authLoading } = useAuth();
  const { currentTrack, playTrack } = usePlayback();
  
  const [favoritesCount, setFavoritesCount] = useState<number>(0);
  const [recent, setRecent] = useState<RecentlyPlayed[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [authReady, setAuthReady] = useState(false);

  // Wait for auth to be ready before allowing data loads
  useEffect(() => {
    if (!authLoading && session) {
      setAuthReady(true);
    }
  }, [authLoading, session]);

  const loadData = async () => {
    if (!authReady || !session) {
      return;
    }
    try {
      const [favs, recents] = await Promise.all([
        getFavorites(),
        getRecentlyPlayed(),
      ]);
      setFavoritesCount(favs.length);
      setRecent(recents.slice(0, 5)); // Limit to 5 for home screen
    } catch (e) {
      console.log('Failed to load home data', e);
    } finally {
      setRefreshing(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      if (authReady && session) {
        loadData();
      }
    }, [authReady, session])
  );

  const onRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handlePlayRecent = (item: RecentlyPlayed) => {
    const track = normalizeTrack(item);
    playTrack(track);
  };

  // Mock clear recent for now as there is no endpoint to clear them
  const handleClearRecent = () => {
    setRecent([]);
  };

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.bgBase }]}>
      <ScrollView
        contentContainerStyle={[styles.content, currentTrack && { paddingBottom: 80 }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accentPrimary} />}
      >
        <View style={styles.header}>
          <Text style={[styles.greeting, { color: colors.textSecondary }]}>
            Good morning{profile?.display_name ? `, ${profile.display_name}` : ''}
          </Text>
        </View>

        <View style={styles.section}>
          <SectionHeader title="Your Library" />
          <TrackCard
            title="Liked Songs"
            subtitle="Your favorite tracks"
            count={favoritesCount}
            icon="heart"
            onPress={() => navigation.navigate('Library')}
          />
        </View>

        {recent.length > 0 && (
          <View style={styles.section}>
            <SectionHeader title="Recently Played" actionLabel="Clear" onActionPress={handleClearRecent} />
            <View style={styles.recentList}>
              {recent.map((item) => (
                <TrackRow
                  key={item.id}
                  track={normalizeTrack(item)}
                  isActive={currentTrack?.provider_track_id === item.provider_track_id}
                  onPress={() => handlePlayRecent(item)}
                  showMenu={false}
                />
              ))}
            </View>
          </View>
        )}

        <View style={styles.section}>
          <SectionHeader title="Playlists & Collections" />
          <ComingSoonCard
            title="Custom Playlists"
            message="Create, share, and collaborate on playlists. The backend is ready, frontend coming in Phase 2."
            icon="list"
          />
        </View>

        <View style={styles.section}>
          <SectionHeader title="Offline Storage" />
          <ComingSoonCard
            title="Download for Offline"
            message="Take your music anywhere without a connection. Coming soon."
            icon="cloud-download-outline"
            badgeText="PREVIEW"
          />
        </View>
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
    gap: spacing.xl,
  },
  header: {
    marginBottom: spacing.sm,
  },
  greeting: {
    fontSize: typography.h1.fontSize,
    fontWeight: typography.h1.fontWeight,
    letterSpacing: typography.h1.letterSpacing,
  },
  section: {
    gap: spacing.sm,
  },
  recentList: {
    gap: 4,
  },
});
