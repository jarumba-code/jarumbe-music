import React from 'react';
import { Pressable, StyleSheet, Text, ViewStyle, TextStyle } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, typography } from '../constants/theme';

export type ChipProps = {
  label: string;
  icon?: React.ReactNode;
  active?: boolean;
  onPress?: () => void;
  style?: ViewStyle;
  textStyle?: TextStyle;
};

export function Chip({ label, icon, active, onPress, style, textStyle }: ChipProps) {
  const { colors } = useTheme();

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={[
        styles.chip,
        {
          backgroundColor: active ? colors.accentTint10 : colors.bgElevated,
          borderColor: active ? colors.accentPrimary : colors.borderSubtle,
        },
        style,
      ]}>
      {icon}
      <Text
        style={[
          styles.label,
          { color: active ? colors.accentPrimary : colors.textSecondary },
          textStyle,
        ]}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  label: {
    fontSize: typography.caption.fontSize,
    fontWeight: '500',
  },
});
