import React from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';

import { palette, radius, spacing, typography } from '../constants/theme';

export type PrimaryButtonProps = {
  title: string;
  onPress?: () => void;
  disabled?: boolean;
  fullWidth?: boolean;
};

export function PrimaryButton({ title, onPress, disabled, fullWidth = true }: PrimaryButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled}
      onPress={onPress}
      style={[styles.button, fullWidth && styles.fullWidth, disabled && styles.disabled]}>
      <Text style={styles.text}>{title}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    height: 52,
    borderRadius: radius.pill,
    backgroundColor: palette.accentPrimary,
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
    color: palette.bgBase,
    fontSize: typography.bodyBold.fontSize,
    fontWeight: typography.bodyBold.fontWeight,
  },
});
