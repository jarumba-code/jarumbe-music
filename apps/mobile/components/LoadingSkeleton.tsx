import React, { useEffect } from 'react';
import { StyleSheet, Animated, ViewStyle } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { radius } from '../constants/theme';

export type LoadingSkeletonProps = {
  style?: ViewStyle;
};

export function LoadingSkeleton({ style }: LoadingSkeletonProps) {
  const { colors } = useTheme();
  const animatedValue = new Animated.Value(0);

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(animatedValue, {
          toValue: 1,
          duration: 1000,
          useNativeDriver: true,
        }),
        Animated.timing(animatedValue, {
          toValue: 0,
          duration: 1000,
          useNativeDriver: true,
        }),
      ])
    ).start();
  }, []);

  const opacity = animatedValue.interpolate({
    inputRange: [0, 1],
    outputRange: [0.3, 0.7],
  });

  return (
    <Animated.View
      style={[
        styles.skeleton,
        { backgroundColor: colors.bgElevated2, opacity },
        style,
      ]}
    />
  );
}

const styles = StyleSheet.create({
  skeleton: {
    borderRadius: radius.sm,
  },
});
