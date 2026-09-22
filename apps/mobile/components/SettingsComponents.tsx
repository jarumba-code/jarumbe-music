import React from 'react';
import { View, Text, StyleSheet, Pressable, Switch } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, typography } from '../constants/theme';

export function SettingSection({ title, children }: { title: string; children: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={styles.section}>
      <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>{title}</Text>
      <View style={[styles.sectionCard, { backgroundColor: colors.bgElevated, borderColor: colors.borderSubtle }]}>
        {children}
      </View>
    </View>
  );
}

export function SettingRow({ label, value, onPress, isLast = false, disabled = false }: { label: string; value?: string; onPress?: () => void; isLast?: boolean; disabled?: boolean }) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress || disabled}
      style={({ pressed }) => [
        styles.row,
        !isLast && { borderBottomWidth: 1, borderBottomColor: colors.borderSubtle },
        pressed && onPress && { backgroundColor: colors.bgElevated2 },
        disabled && { opacity: 0.5 },
      ]}>
      <Text style={[styles.rowLabel, { color: colors.textPrimary }]}>{label}</Text>
      {value && <Text style={[styles.rowValue, { color: colors.textSecondary }]}>{value}</Text>}
    </Pressable>
  );
}

export function SettingRowWithChevron({ label, value, onPress, isLast = false, disabled = false }: { label: string; value?: string; onPress?: () => void; isLast?: boolean; disabled?: boolean }) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress || disabled}
      style={({ pressed }) => [
        styles.row,
        !isLast && { borderBottomWidth: 1, borderBottomColor: colors.borderSubtle },
        pressed && onPress && { backgroundColor: colors.bgElevated2 },
        disabled && { opacity: 0.5 },
      ]}>
      <Text style={[styles.rowLabel, { color: colors.textPrimary }]}>{label}</Text>
      <View style={styles.rowRight}>
        {value && <Text style={[styles.rowValue, { color: colors.textSecondary }]}>{value}</Text>}
        <Ionicons name="chevron-forward" size={16} color={colors.textSecondary} />
      </View>
    </Pressable>
  );
}

export function SettingRowWithToggle({ label, value, onToggle, isLast = false, disabled = false }: { label: string; value: boolean; onToggle: (val: boolean) => void; isLast?: boolean; disabled?: boolean }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.row, !isLast && { borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }, disabled && { opacity: 0.5 }]}>
      <Text style={[styles.rowLabel, { color: colors.textPrimary }]}>{label}</Text>
      <Switch
        value={value}
        onValueChange={onToggle}
        disabled={disabled}
        trackColor={{ false: colors.borderSubtle, true: colors.accentPrimary }}
        thumbColor={colors.white}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    marginBottom: spacing.xl,
  },
  sectionTitle: {
    fontSize: typography.h2.fontSize,
    fontWeight: typography.h2.fontWeight,
    marginBottom: spacing.md,
    paddingHorizontal: spacing.md,
  },
  sectionCard: {
    borderRadius: radius.md,
    borderWidth: 1,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    minHeight: 56,
  },
  rowLabel: {
    fontSize: typography.body.fontSize,
  },
  rowValue: {
    fontSize: typography.body.fontSize,
  },
  rowRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
});
