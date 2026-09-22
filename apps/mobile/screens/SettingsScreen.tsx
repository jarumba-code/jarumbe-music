import React from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { radius, spacing, typography } from '../constants/theme';
import { SettingSection, SettingRowWithChevron, SettingRowWithToggle } from '../components/SettingsComponents';
import { IconButton } from '../components/IconButton';
import { SecondaryButton } from '../components/SecondaryButton';

export function SettingsScreen() {
  const { colors, colorScheme, toggleColorScheme } = useTheme();
  const { profile, user, signOut, loading } = useAuth();
  const navigation = useNavigation<any>();

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.bgBase }]}>
      <View style={styles.header}>
        <View style={styles.headerTitleWrap}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>Settings</Text>
        </View>
        <IconButton icon={<Ionicons name="create-outline" size={24} color={colors.textPrimary} />} onPress={() => {}} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.profileSection}>
          <View style={[styles.avatar, { backgroundColor: colors.bgElevated }]}>
            {profile?.avatar_url ? (
              <Ionicons name="person" size={32} color={colors.textTertiary} />
            ) : (
              <Ionicons name="person" size={32} color={colors.textTertiary} />
            )}
          </View>
          <View>
            <Text style={[styles.name, { color: colors.textPrimary }]}>{profile?.display_name ?? user?.email ?? 'Jarumba user'}</Text>
            <Text style={[styles.email, { color: colors.textSecondary }]}>{user?.email}</Text>
          </View>
        </View>

        <SettingSection title="Account">
          <SettingRowWithChevron label="Change Password" onPress={() => {}} />
          <SettingRowWithChevron label="Email Preferences" isLast onPress={() => {}} />
        </SettingSection>

        <SettingSection title="Preferences">
          <SettingRowWithToggle
            label="Dark Mode"
            value={colorScheme === 'dark'}
            onToggle={toggleColorScheme}
          />
          <SettingRowWithChevron label="Audio Quality" value="High" onPress={() => {}} />
          <SettingRowWithChevron label="Offline Storage" value="2.1 GB" isLast onPress={() => {}} />
        </SettingSection>

        <SettingSection title="About">
          <SettingRowWithChevron label="Terms of Service" onPress={() => navigation.navigate('Terms')} />
          <SettingRowWithChevron label="Privacy Policy" isLast onPress={() => navigation.navigate('Privacy')} />
        </SettingSection>

        <SettingSection title="Danger Zone">
          <View style={styles.dangerZone}>
            <SecondaryButton title={loading ? 'Signing out...' : 'Sign out'} onPress={() => signOut()} disabled={loading} />
          </View>
        </SettingSection>
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
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    marginBottom: spacing.md,
  },
  headerTitleWrap: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  title: {
    fontSize: typography.h1.fontSize,
    fontWeight: typography.h1.fontWeight,
  },
  content: {
    padding: spacing.xl,
    paddingTop: 0,
    gap: spacing.lg,
  },
  profileSection: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginBottom: spacing.xl,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  name: {
    fontSize: typography.h2.fontSize,
    fontWeight: typography.h2.fontWeight,
  },
  email: {
    fontSize: typography.body.fontSize,
  },
  dangerZone: {
    padding: spacing.md,
  },
});
