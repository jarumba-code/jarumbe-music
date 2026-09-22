import React from 'react';
import { Pressable, StyleSheet, ViewStyle } from 'react-native';
import { useTheme } from '../context/ThemeContext';

export type IconButtonProps = {
  icon: React.ReactNode;
  onPress?: () => void;
  size?: number;
  style?: ViewStyle;
  disabled?: boolean;
};

export function IconButton({ icon, onPress, size = 40, style, disabled = false }: IconButtonProps) {
  const { colors } = useTheme();

  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: !disabled && pressed ? colors.bgElevated2 : 'transparent',
          opacity: disabled ? 0.35 : 1,
        },
        style,
      ]}>
      {icon}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});
