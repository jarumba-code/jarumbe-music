import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, typography } from '../constants/theme';

export type ComingSoonCardProps = {
  title: string;
  message: string;
  icon?: keyof typeof Ionicons.glyphMap;
  badgeText?: string;
};

export function ComingSoonCard({ title, message, icon = 'time-outline', badgeText = 'COMING SOON' }: ComingSoonCardProps) {
  const { colors } = useTheme();

  return (
    <View style={[styles.container, { backgroundColor: colors.bgElevated, borderColor: colors.borderSubtle }]}>
      <View style={styles.header}>
        <View style={[styles.iconWrap, { backgroundColor: colors.bgElevated2 }]}>
          <Ionicons name={icon} size={24} color={colors.accentPrimary} />
        </View>
        <View style={[styles.badge, { backgroundColor: colors.bgElevated2 }]}>
          <Text style={[styles.badgeText, { color: colors.textSecondary }]}>{badgeText}</Text>
        </View>
      </View>
      <Text style={[styles.title, { color: colors.textPrimary }]}>{title}</Text>
      <Text style={[styles.message, { color: colors.textSecondary }]}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    gap: spacing.sm,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: spacing.xs,
  },
  iconWrap: {
    width: 48,
    height: 48,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.sm,
  },
  badgeText: {
    fontSize: typography.captionSmall.fontSize,
    fontWeight: '700',
    letterSpacing: typography.captionSmall.letterSpacing,
  },
  title: {
    fontSize: typography.h2.fontSize,
    fontWeight: typography.h2.fontWeight,
  },
  message: {
    fontSize: typography.body.fontSize,
    lineHeight: typography.body.lineHeight,
  },
});
