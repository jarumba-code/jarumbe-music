import React from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, typography } from '../constants/theme';
import { NotificationCard } from '../components/NotificationCard';
import { IconButton } from '../components/IconButton';
import { EmptyState } from '../components/EmptyState';

export function NotificationsScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation();

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.bgBase }]}>
      <View style={styles.header}>
        <IconButton icon={<Ionicons name="arrow-back" size={24} color={colors.textPrimary} />} onPress={() => navigation.goBack()} />
        <Text style={[styles.title, { color: colors.textPrimary }]}>Notifications</Text>
        <View style={{ width: 40 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <EmptyState 
          title="All caught up" 
          message="No new notifications. Updates and alerts will appear here when available." 
          icon="notifications-outline" 
        />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    height: 56,
  },
  title: {
    fontSize: typography.h2.fontSize,
    fontWeight: typography.h2.fontWeight,
  },
  content: {
    padding: spacing.xl,
  },
  list: {
    gap: spacing.sm,
  },
});
