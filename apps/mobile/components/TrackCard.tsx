import React from 'react';
import { Pressable, Text, StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, typography } from '../constants/theme';

export type TrackCardProps = {
  title: string;
  subtitle: string;
  count?: number;
  icon?: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
};

export function TrackCard({ title, subtitle, count, icon, onPress }: TrackCardProps) {
  const { colors } = useTheme();

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.container,
        {
          backgroundColor: colors.bgElevated,
          borderColor: pressed ? colors.accentPrimary : colors.borderSubtle,
        },
      ]}>
      <View style={[styles.iconWrap, { backgroundColor: colors.accentTint10 }]}>
        {icon ? (
          <Ionicons name={icon} size={32} color={colors.accentPrimary} />
        ) : (
          <Ionicons name="musical-notes" size={32} color={colors.accentPrimary} />
        )}
      </View>
      
      <View style={styles.content}>
        <Text style={[styles.title, { color: colors.textPrimary }]}>{title}</Text>
        <Text style={[styles.subtitle, { color: colors.textSecondary }]}>{subtitle}</Text>
      </View>
      
      {count !== undefined && (
        <View style={[styles.countBadge, { backgroundColor: colors.bgElevated2 }]}>
          <Text style={[styles.countText, { color: colors.textPrimary }]}>{count}</Text>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    alignItems: 'center',
  },
  iconWrap: {
    width: 64,
    height: 64,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
  },
  title: {
    fontSize: typography.h2.fontSize,
    fontWeight: typography.h2.fontWeight,
    marginBottom: 4,
  },
  subtitle: {
    fontSize: typography.body.fontSize,
  },
  countBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  countText: {
    fontSize: typography.caption.fontSize,
    fontWeight: '600',
  },
});
