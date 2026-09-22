import React from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { spacing, typography } from '../constants/theme';
import { IconButton } from './IconButton';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';

export type LegalDocumentScreenProps = {
  title: string;
  lastUpdated: string;
  children: React.ReactNode;
};

export function LegalDocumentScreen({ title, lastUpdated, children }: LegalDocumentScreenProps) {
  const { colors } = useTheme();
  const navigation = useNavigation();

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.bgBase }]}>
      <View style={[styles.header, { borderBottomColor: colors.borderSubtle }]}>
        <IconButton
          icon={<Ionicons name="arrow-back" size={24} color={colors.textPrimary} />}
          onPress={() => navigation.goBack()}
        />
        <Text style={[styles.headerTitle, { color: colors.textPrimary }]}>{title}</Text>
        <View style={{ width: 40 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={[styles.title, { color: colors.textPrimary }]}>{title}</Text>
        <Text style={[styles.updated, { color: colors.textSecondary }]}>Last Updated: {lastUpdated}</Text>
        <View style={styles.body}>{children}</View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    height: 56,
    borderBottomWidth: 1,
  },
  headerTitle: {
    fontSize: typography.h2.fontSize,
    fontWeight: typography.h2.fontWeight,
  },
  content: {
    padding: spacing.xl,
    paddingBottom: spacing.xxl,
  },
  title: {
    fontSize: typography.display.fontSize,
    fontWeight: typography.display.fontWeight,
    marginBottom: spacing.sm,
  },
  updated: {
    fontSize: typography.caption.fontSize,
    marginBottom: spacing.xl,
  },
  body: {
    gap: spacing.md,
  },
});
