import React from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, typography } from '../constants/theme';

export type SecondaryButtonProps = {
  title: string;
  onPress?: () => void;
  disabled?: boolean;
  fullWidth?: boolean;
};

export function SecondaryButton({ title, onPress, disabled, fullWidth = true }: SecondaryButtonProps) {
  const { colors } = useTheme();

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        {
          borderColor: colors.borderSubtle,
          backgroundColor: pressed ? colors.bgElevated2 : 'transparent',
        },
        fullWidth && styles.fullWidth,
        disabled && styles.disabled,
      ]}>
      <Text style={[styles.text, { color: colors.textPrimary }]}>{title}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    height: 52,
    borderRadius: radius.pill,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    marginVertical: spacing.sm,
  },
  fullWidth: {
    width: '100%',
  },
  disabled: {
    opacity: 0.5,
  },
  text: {
    fontSize: typography.bodyBold.fontSize,
    fontWeight: typography.bodyBold.fontWeight,
  },
});
