import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { palette, radius, spacing, typography } from '../constants/theme';

export type SegmentedTabsProps = {
  tabs: string[];
  activeTab: string;
  onChange: (tab: string) => void;
};

export function SegmentedTabs({ tabs, activeTab, onChange }: SegmentedTabsProps) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.container}>
      {tabs.map((tab) => {
        const isActive = tab === activeTab;
        return (
          <Pressable
            key={tab}
            accessibilityRole="button"
            accessibilityLabel={tab}
            onPress={() => onChange(tab)}
            style={[styles.tab, isActive && styles.activeTab]}>
            <Text style={[styles.label, isActive && styles.activeLabel]}>{tab}</Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingVertical: spacing.xs,
    gap: spacing.sm,
  },
  tab: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: 'transparent',
    minHeight: 36,
    justifyContent: 'center',
  },
  activeTab: {
    backgroundColor: palette.accentPrimary,
  },
  label: {
    color: palette.textSecondary,
    fontSize: typography.caption.fontSize,
    fontWeight: '600',
  },
  activeLabel: {
    color: palette.bgBase,
  },
});
