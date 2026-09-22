import React from 'react';
import { View, Text, StyleSheet, Pressable, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { useTheme } from '../context/ThemeContext';
import { usePlayback } from '../context/PlaybackContext';
import { radius, spacing, typography } from '../constants/theme';
import { IconButton } from './IconButton';

export function MiniPlayer() {
  const { colors } = useTheme();
  const { currentTrack, isPlaying, togglePlayPause } = usePlayback();
  const navigation = useNavigation<any>();

  if (!currentTrack) return null;

  return (
    <Pressable
      style={[styles.container, { backgroundColor: colors.bgElevated2, borderTopColor: colors.borderSubtle }]}
      onPress={() => navigation.navigate('NowPlaying')}>
      
      {currentTrack.artwork_url ? (
        <Image source={{ uri: currentTrack.artwork_url }} style={styles.artwork} />
      ) : (
        <View style={[styles.artwork, { backgroundColor: colors.bgElevated }]}>
          <Ionicons name="musical-notes" size={20} color={colors.textTertiary} />
        </View>
      )}

      <View style={styles.info}>
        <Text style={[styles.title, { color: colors.textPrimary }]} numberOfLines={1}>
          {currentTrack.title}
        </Text>
        <Text style={[styles.artist, { color: colors.textSecondary }]} numberOfLines={1}>
          {currentTrack.artist}
        </Text>
      </View>

      <IconButton
        icon={<Ionicons name={isPlaying ? 'pause' : 'play'} size={24} color={colors.textPrimary} />}
        onPress={togglePlayPause}
        size={40}
      />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    height: 64,
  },
  artwork: {
    width: 48,
    height: 48,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  info: {
    flex: 1,
    marginLeft: spacing.sm,
    justifyContent: 'center',
  },
  title: {
    fontSize: typography.bodyBold.fontSize,
    fontWeight: typography.bodyBold.fontWeight,
    marginBottom: 2,
  },
  artist: {
    fontSize: typography.caption.fontSize,
  },
});
