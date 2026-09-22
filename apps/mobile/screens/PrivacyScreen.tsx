import React from 'react';
import { Text } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { LegalDocumentScreen } from '../components/LegalDocumentScreen';
import { typography } from '../constants/theme';

export function PrivacyScreen() {
  const { colors } = useTheme();
  
  return (
    <LegalDocumentScreen title="Privacy Policy" lastUpdated="September 2026">
      <Text style={{ color: colors.textPrimary, fontSize: typography.body.fontSize }}>
        Your privacy is critically important to us.
      </Text>
      <Text style={{ color: colors.textPrimary, fontSize: typography.body.fontSize, marginTop: 16 }}>
        Data We Collect
      </Text>
      <Text style={{ color: colors.textSecondary, fontSize: typography.body.fontSize }}>
        We only collect data necessary to provide a personalized music experience...
      </Text>
    </LegalDocumentScreen>
  );
}
