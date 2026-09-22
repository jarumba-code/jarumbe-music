import React, { useState } from 'react';
import { View, Text, StyleSheet, Image, Pressable, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { useTheme } from '../context/ThemeContext';
import { usePlayback } from '../context/PlaybackContext';
import { radius, spacing, typography } from '../constants/theme';
import { IconButton } from '../components/IconButton';
import { ActionSheet, ActionItem } from '../components/ActionSheet';

function formatTime(seconds: number) {
  if (!seconds || isNaN(seconds)) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function NowPlayingScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<any>();
  const { currentTrack, isPlaying, togglePlayPause, position, duration } = usePlayback();
  
  const [isFavorite, setIsFavorite] = useState(false);
  const [menuVisible, setMenuVisible] = useState(false);

  if (!currentTrack) {
    return (
      <SafeAreaView style={[styles.screen, { backgroundColor: colors.bgBase }]}>
        <View style={styles.header}>
          <IconButton icon={<Ionicons name="chevron-down" size={24} color={colors.textPrimary} />} onPress={() => navigation.goBack()} />
        </View>
        <View style={styles.empty}>
          <Ionicons name="musical-notes" size={64} color={colors.textTertiary} />
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>No track playing</Text>
        </View>
      </SafeAreaView>
    );
  }

  const progress = duration > 0 ? (position / duration) * 100 : 0;

  const actions: ActionItem[] = [
    { label: 'Add to Playlist', icon: 'list', onPress: () => {} },
    { label: 'Share', icon: 'share-outline', onPress: () => {} },
    { label: 'View Artist', icon: 'person', onPress: () => {} },
  ];

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.bgBase }]}>
      <View style={styles.header}>
        <IconButton icon={<Ionicons name="chevron-down" size={28} color={colors.textPrimary} />} onPress={() => navigation.goBack()} />
        <Text style={[styles.headerTitle, { color: colors.textSecondary }]}>Now Playing</Text>
        <IconButton icon={<Ionicons name="ellipsis-vertical" size={24} color={colors.textPrimary} />} onPress={() => setMenuVisible(true)} />
      </View>

      <View style={styles.content}>
        <View style={styles.artworkWrap}>
          {currentTrack.artwork_url ? (
            <Image source={{ uri: currentTrack.artwork_url }} style={[styles.artwork, { backgroundColor: colors.bgElevated2 }]} />
          ) : (
            <View style={[styles.artwork, { backgroundColor: colors.bgElevated2, alignItems: 'center', justifyContent: 'center' }]}>
              <Ionicons name="musical-notes" size={80} color={colors.textTertiary} />
            </View>
          )}
        </View>

        <View style={styles.infoWrap}>
          <View style={styles.infoText}>
            <Text style={[styles.title, { color: colors.textPrimary }]} numberOfLines={1}>{currentTrack.title}</Text>
            <Text style={[styles.artist, { color: colors.textSecondary }]} numberOfLines={1}>{currentTrack.artist}</Text>
          </View>
          <IconButton
            icon={<Ionicons name={isFavorite ? 'heart' : 'heart-outline'} size={28} color={isFavorite ? colors.accentPrimary : colors.textPrimary} />}
            onPress={() => setIsFavorite(!isFavorite)}
          />
        </View>

        <View style={styles.scrubberWrap}>
          <View style={[styles.track, { backgroundColor: colors.borderSubtle }]}>
            <View style={[styles.progress, { backgroundColor: colors.accentPrimary, width: `${progress}%` }]} />
            <View style={[styles.thumb, { backgroundColor: colors.white, left: `${progress}%` }]} />
          </View>
          <View style={styles.timeWrap}>
            <Text style={[styles.time, { color: colors.textSecondary }]}>{formatTime(position)}</Text>
            <Text style={[styles.time, { color: colors.textSecondary }]}>{formatTime(duration)}</Text>
          </View>
        </View>

        <View style={styles.controlsWrap}>
          <IconButton icon={<Ionicons name="shuffle" size={24} color={colors.textSecondary} />} disabled size={48} />
          <IconButton icon={<Ionicons name="play-skip-back" size={32} color={colors.textSecondary} />} disabled size={64} />
          
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={isPlaying ? 'Pause' : 'Play'}
            style={({ pressed }) => [styles.playPauseBtn, { backgroundColor: colors.accentPrimary }, pressed && { opacity: 0.8 }]}
            onPress={togglePlayPause}>
            <Ionicons name={isPlaying ? 'pause' : 'play'} size={32} color={colors.white} style={styles.playIcon} />
          </Pressable>

          <IconButton icon={<Ionicons name="play-skip-forward" size={32} color={colors.textSecondary} />} disabled size={64} />
          <IconButton icon={<Ionicons name="repeat" size={24} color={colors.textSecondary} />} disabled size={48} />
        </View>
      </View>
      
      <ActionSheet
        visible={menuVisible}
        onClose={() => setMenuVisible(false)}
        title={currentTrack.title}
        subtitle={currentTrack.artist}
        actions={actions}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    height: 56,
  },
  headerTitle: {
    fontSize: typography.bodyBold.fontSize,
    fontWeight: typography.bodyBold.fontWeight,
    letterSpacing: typography.bodyBold.letterSpacing,
    textTransform: 'uppercase',
  },
  content: {
    flex: 1,
    paddingHorizontal: spacing.xl,
    justifyContent: 'center',
    paddingBottom: spacing.xxl,
  },
  artworkWrap: {
    width: '100%',
    aspectRatio: 1,
    marginBottom: spacing.xxl,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.3,
    shadowRadius: 20,
    elevation: 10,
  },
  artwork: {
    width: '100%',
    height: '100%',
    borderRadius: radius.lg,
  },
  infoWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.xl,
  },
  infoText: {
    flex: 1,
    marginRight: spacing.md,
  },
  title: {
    fontSize: typography.h1.fontSize,
    fontWeight: typography.h1.fontWeight,
    marginBottom: 4,
  },
  artist: {
    fontSize: typography.h2.fontSize,
  },
  scrubberWrap: {
    marginBottom: spacing.xl,
  },
  track: {
    height: 4,
    borderRadius: 2,
    width: '100%',
    marginBottom: spacing.sm,
    justifyContent: 'center',
  },
  progress: {
    height: '100%',
    borderRadius: 2,
    position: 'absolute',
    left: 0,
    top: 0,
  },
  thumb: {
    width: 12,
    height: 12,
    borderRadius: 6,
    position: 'absolute',
    marginLeft: -6,
  },
  timeWrap: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  time: {
    fontSize: typography.captionSmall.fontSize,
    fontVariant: ['tabular-nums'],
  },
  controlsWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.sm,
  },
  playPauseBtn: {
    width: 72,
    height: 72,
    borderRadius: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  playIcon: {
    marginLeft: 4, // optical alignment for play icon
  },
  empty: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyText: {
    marginTop: spacing.md,
    fontSize: typography.h2.fontSize,
  },
});
