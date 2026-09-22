import React, { useState } from 'react';
import { ActivityIndicator, SafeAreaView, StyleSheet, Text, View, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';

import { PrimaryButton } from '../components/PrimaryButton';
import { Chip } from '../components/Chip';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, typography } from '../constants/theme';
import { useAuth } from '../context/AuthContext';

export function LoginScreen() {
  const { signInWithGoogle, loading, error } = useAuth();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { colors } = useTheme();
  const navigation = useNavigation<any>();

  const handleGoogleLogin = async () => {
    setIsSubmitting(true);
    try {
      await signInWithGoogle();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.bgBase }]}>
      <View style={styles.container}>
        <View style={styles.header}>
          <Ionicons name="musical-notes" size={32} color={colors.accentPrimary} />
          <Text style={[styles.brandName, { color: colors.textPrimary }]}>Jarumba Music</Text>
        </View>

        <View style={styles.content}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>
            Your sound.{'\n'}Your rules.
          </Text>
          
          <View style={styles.pills}>
            <Chip label="Millions of songs" icon={<Ionicons name="musical-note" size={16} color={colors.accentPrimary} />} active style={styles.pill} />
            <Chip label="Ad-free listening" icon={<Ionicons name="headset" size={16} color={colors.accentPrimary} />} active style={styles.pill} />
            <Chip label="Offline playback" icon={<Ionicons name="cloud-offline" size={16} color={colors.accentPrimary} />} active style={styles.pill} />
          </View>
        </View>

        <View style={styles.footer}>
          {error ? <Text style={[styles.errorText, { color: colors.error }]}>{error}</Text> : null}
          <PrimaryButton title={isSubmitting || loading ? 'Signing in...' : 'Continue with Google'} onPress={handleGoogleLogin} disabled={isSubmitting || loading} />
          {(isSubmitting || loading) && <ActivityIndicator style={styles.spinner} color={colors.accentPrimary} />}
          
          <Text style={[styles.legalText, { color: colors.textTertiary }]}>
            By continuing, you agree to the{' '}
            <Text style={[styles.link, { color: colors.textSecondary }]} onPress={() => navigation.navigate('Terms')}>Terms of Use</Text>
            {' '}and acknowledge the{' '}
            <Text style={[styles.link, { color: colors.textSecondary }]} onPress={() => navigation.navigate('Privacy')}>Privacy Policy</Text>.
          </Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  container: {
    flex: 1,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.xl,
    justifyContent: 'space-between',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  brandName: {
    fontSize: typography.h2.fontSize,
    fontWeight: typography.h2.fontWeight,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
  },
  title: {
    fontSize: 48,
    lineHeight: 52,
    fontWeight: '700',
    letterSpacing: -1,
    marginBottom: spacing.xl,
  },
  pills: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  pill: {
    alignSelf: 'flex-start',
  },
  footer: {
    width: '100%',
  },
  errorText: {
    marginBottom: spacing.md,
    fontSize: typography.caption.fontSize,
    textAlign: 'center',
  },
  spinner: {
    marginTop: spacing.md,
  },
  legalText: {
    marginTop: spacing.lg,
    fontSize: typography.captionSmall.fontSize,
    textAlign: 'center',
    lineHeight: 18,
  },
  link: {
    textDecorationLine: 'underline',
  },
});
