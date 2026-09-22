import React, { useEffect, useCallback, useState } from 'react';
import { RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';

import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { usePlayback } from '../context/PlaybackContext';
import { getFavorites, normalizeTrack } from '../lib/api';
import { Favorite } from '../lib/types';
import { radius, spacing, typography } from '../constants/theme';
import { TrackRow } from '../components/TrackRow';
import { EmptyState } from '../components/EmptyState';
import { ActionSheet, ActionItem } from '../components/ActionSheet';

export function LibraryScreen() {
  const { colors } = useTheme();
  const { session, loading: authLoading } = useAuth();
  const { currentTrack, playTrack } = usePlayback();
  
  const [favorites, setFavorites] = useState<Favorite[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  
  // Wait for auth to be ready before allowing data loads
  useEffect(() => {
    if (!authLoading && session) {
      setAuthReady(true);
    }
  }, [authLoading, session]);
  
  // Track context menu state
  const [menuVisible, setMenuVisible] = useState(false);
  const [selectedFavorite, setSelectedFavorite] = useState<Favorite | null>(null);

  const loadFavorites = async () => {
    if (!authReady || !session) {
      return;
    }
    try {
      const data = await getFavorites();
      setFavorites(data);
    } catch (e) {
      console.log('Failed to load favorites', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      if (authReady && session) {
        loadFavorites();
      }
    }, [authReady, session])
  );

  const onRefresh = () => {
    setRefreshing(true);
    loadFavorites();
  };

  const handlePlay = (item: Favorite) => {
    playTrack(normalizeTrack(item));
  };

  const handleMenuPress = (item: Favorite) => {
    setSelectedFavorite(item);
    setMenuVisible(true);
  };

  const actions: ActionItem[] = [
    {
      label: 'Remove from Liked Songs',
      icon: 'heart-dislike',
      destructive: true,
      onPress: () => {
        // Mock remove for now, typically call removeFavorite and refresh
        setFavorites((prev) => prev.filter((f) => f.id !== selectedFavorite?.id));
      },
    },
    {
      label: 'Share',
      icon: 'share-outline',
      onPress: () => {},
    },
  ];

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.bgBase }]}>
      <ScrollView
        contentContainerStyle={[styles.content, currentTrack && { paddingBottom: 80 }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accentPrimary} />}
      >
        <Text style={[styles.title, { color: colors.textPrimary }]}>Liked Songs</Text>
        <Text style={[styles.subtitle, { color: colors.textSecondary }]}>{favorites.length} {favorites.length === 1 ? 'song' : 'songs'}</Text>
        
        {!loading && favorites.length === 0 ? (
          <View style={styles.emptyWrap}>
            <EmptyState
              title="No liked songs yet"
              message="Tap the heart on any track to add it to your library."
              icon="heart-outline"
            />
          </View>
        ) : null}

        <View style={styles.list}>
          {favorites.map((item) => (
            <TrackRow
              key={item.id}
              track={normalizeTrack(item)}
              isActive={currentTrack?.provider_track_id === item.provider_track_id}
              onPress={() => handlePlay(item)}
              onMenuPress={() => handleMenuPress(item)}
              isFavorite={true}
            />
          ))}
        </View>
      </ScrollView>
      
      <ActionSheet
        visible={menuVisible}
        onClose={() => setMenuVisible(false)}
        title={selectedFavorite?.title}
        subtitle={selectedFavorite?.artist}
        actions={actions}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  content: {
    padding: spacing.xl,
    gap: spacing.sm,
  },
  title: {
    fontSize: typography.h1.fontSize,
    fontWeight: typography.h1.fontWeight,
  },
  subtitle: {
    fontSize: typography.body.fontSize,
    marginBottom: spacing.md,
  },
  list: {
    gap: 4,
  },
  emptyWrap: {
    marginTop: spacing.xxl,
  },
});
