import React from 'react';
import { Text } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { LegalDocumentScreen } from '../components/LegalDocumentScreen';
import { typography } from '../constants/theme';

export function TermsScreen() {
  const { colors } = useTheme();
  
  return (
    <LegalDocumentScreen title="Terms of Service" lastUpdated="September 2026">
      <Text style={{ color: colors.textPrimary, fontSize: typography.body.fontSize }}>
        Welcome to Jarumba Music! By using our app, you agree to these terms...
      </Text>
      <Text style={{ color: colors.textPrimary, fontSize: typography.body.fontSize, marginTop: 16 }}>
        1. Usage Guidelines
      </Text>
      <Text style={{ color: colors.textSecondary, fontSize: typography.body.fontSize }}>
        You agree to use Jarumba for personal, non-commercial purposes only...
      </Text>
    </LegalDocumentScreen>
  );
}
