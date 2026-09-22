import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, typography } from '../constants/theme';

export type NotificationCardProps = {
  title: string;
  message: string;
  time: string;
  isUnread?: boolean;
  onPress?: () => void;
};

export function NotificationCard({ title, message, time, isUnread = false, onPress }: NotificationCardProps) {
  const { colors } = useTheme();

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.container,
        { backgroundColor: isUnread ? colors.bgElevated2 : colors.bgElevated },
        pressed && { opacity: 0.8 },
      ]}>
      <View style={[styles.iconWrap, { backgroundColor: colors.accentTint10 }]}>
        <Ionicons name="notifications" size={24} color={colors.accentPrimary} />
      </View>
      <View style={styles.content}>
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.textPrimary }]} numberOfLines={1}>{title}</Text>
          <Text style={[styles.time, { color: colors.textTertiary }]}>{time}</Text>
        </View>
        <Text style={[styles.message, { color: colors.textSecondary }]} numberOfLines={2}>{message}</Text>
      </View>
      {isUnread && <View style={[styles.dot, { backgroundColor: colors.accentPrimary }]} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    padding: spacing.md,
    borderRadius: radius.md,
    alignItems: 'center',
  },
  iconWrap: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  content: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  title: {
    fontSize: typography.bodyBold.fontSize,
    fontWeight: typography.bodyBold.fontWeight,
    flex: 1,
    marginRight: spacing.sm,
  },
  time: {
    fontSize: typography.caption.fontSize,
  },
  message: {
    fontSize: typography.body.fontSize,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginLeft: spacing.sm,
  },
});
