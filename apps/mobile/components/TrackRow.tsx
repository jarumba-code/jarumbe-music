import React from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, typography } from '../constants/theme';
import { Track } from '../lib/types';
import { IconButton } from './IconButton';

export type TrackRowProps = {
  track: Track;
  index?: number;
  isActive?: boolean;
  onPress?: (track: Track) => void;
  onToggleFavorite?: (track: Track) => void;
  isFavorite?: boolean;
  onMenuPress?: (track: Track) => void;
  showMenu?: boolean;
  durationLabel?: string;
};

export function TrackRow({ track, index, isActive = false, onPress, onToggleFavorite, isFavorite = false, onMenuPress, showMenu = true, durationLabel }: TrackRowProps) {
  const { colors } = useTheme();
  
  const titleColor = isActive ? colors.accentPrimary : colors.textPrimary;
  const titleWeight = isActive ? '700' : '400';

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${track.title} by ${track.artist}`}
      onPress={() => onPress?.(track)}
      style={({ pressed }) => [
        styles.row, 
        pressed && styles.pressed, 
        isActive && { backgroundColor: colors.accentTint10 }
      ]}>
      {isActive ? <View style={[styles.activeStrip, { backgroundColor: colors.accentPrimary }]} /> : null}
      
      {index !== undefined && (
        <Text style={[styles.index, { color: colors.textSecondary }]}>{index}</Text>
      )}

      {track.artwork_url ? (
        <Image source={{ uri: track.artwork_url }} style={[styles.artwork, { backgroundColor: colors.bgElevated2 }]} resizeMode="cover" />
      ) : (
        <View style={[styles.artwork, { backgroundColor: colors.bgElevated2 }]} />
      )}
      
      <View style={styles.meta}>
        <Text style={[styles.title, { color: titleColor, fontWeight: titleWeight }]} numberOfLines={1}>{track.title}</Text>
        <Text style={[styles.artist, { color: colors.textSecondary }]} numberOfLines={1}>{track.artist}</Text>
        {track.provider ? <Text style={[styles.provider, { color: colors.accentPrimary }]} numberOfLines={1}>{track.provider}</Text> : null}
      </View>
      
      <View style={styles.actions}>
        {durationLabel ? <Text style={[styles.duration, { color: colors.textSecondary }]}>{durationLabel}</Text> : null}
        
        {onToggleFavorite ? (
          <IconButton
            icon={<Ionicons name={isFavorite ? 'heart' : 'heart-outline'} size={20} color={isFavorite ? colors.accentPrimary : colors.textSecondary} />}
            onPress={() => onToggleFavorite(track)}
            size={36}
          />
        ) : null}
        
        {(onMenuPress || showMenu) ? (
          <IconButton
            icon={<Ionicons name="ellipsis-vertical" size={20} color={colors.textSecondary} />}
            onPress={() => onMenuPress ? onMenuPress(track) : null}
            size={36}
          />
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 64,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    backgroundColor: 'transparent',
    marginVertical: 2,
  },
  pressed: {
    opacity: 0.8,
  },
  activeStrip: {
    width: 3,
    height: 32,
    borderRadius: radius.sm,
    marginRight: spacing.sm,
  },
  index: {
    width: 24,
    fontSize: typography.body.fontSize,
    textAlign: 'center',
    marginRight: spacing.sm,
  },
  artwork: {
    width: 48,
    height: 48,
    borderRadius: radius.md,
  },
  meta: {
    flex: 1,
    marginLeft: spacing.md,
    justifyContent: 'center',
  },
  title: {
    fontSize: typography.body.fontSize,
    lineHeight: typography.body.lineHeight,
  },
  artist: {
    marginTop: 2,
    fontSize: typography.caption.fontSize,
    lineHeight: typography.caption.lineHeight,
  },
  provider: {
    marginTop: 2,
    fontSize: typography.captionSmall.fontSize,
    textTransform: 'capitalize',
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    marginLeft: spacing.sm,
  },
  duration: {
    fontSize: typography.caption.fontSize,
    marginRight: spacing.sm,
  },
});
