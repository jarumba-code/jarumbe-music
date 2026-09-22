import React from 'react';
import { Pressable, Text, StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, typography } from '../constants/theme';

export type GenreCardProps = {
  name: string;
  icon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
};

export function GenreCard({ name, icon, onPress }: GenreCardProps) {
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
      <View style={styles.header}>
        <Text style={[styles.name, { color: colors.textPrimary }]}>{name}</Text>
        <Ionicons name={icon} size={20} color={colors.accentPrimary} />
      </View>
      <Ionicons name="arrow-forward" size={16} color={colors.textSecondary} style={styles.arrow} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    minWidth: '45%',
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    height: 100,
    justifyContent: 'space-between',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  name: {
    fontSize: typography.bodyBold.fontSize,
    fontWeight: typography.bodyBold.fontWeight,
  },
  arrow: {
    alignSelf: 'flex-end',
  },
});
