export type ThemePalette = {
  bgBase: string;
  bgElevated: string;
  bgElevated2: string;
  accentPrimary: string;
  accentDim: string;
  accentTint10: string;
  accentSecondary: string;
  textPrimary: string;
  textSecondary: string;
  textTertiary: string;
  textDisabled: string;
  borderSubtle: string;
  divider: string;
  error: string;
  success: string;
  white: string;
};

export const darkPalette: ThemePalette = {
  bgBase: '#07100B', // Updated from #0B0F0D
  bgElevated: '#111C15', // Updated from #121714
  bgElevated2: '#17231B', // Updated from #1A211D
  accentPrimary: '#22C55E', // Jarumba Green, updated from #1ED760
  accentDim: '#16a34a', // Darker shade of Jarumba Green
  accentTint10: 'rgba(34,197,94,0.10)',
  accentSecondary: '#FF8A3D',
  textPrimary: '#F5F7F5',
  textSecondary: '#9BA39D',
  textTertiary: '#656B67',
  textDisabled: '#454A47',
  borderSubtle: '#232823',
  divider: '#1C211E',
  error: '#FF5C5C',
  success: '#22C55E',
  white: '#FFFFFF',
};

export const lightPalette: ThemePalette = {
  bgBase: '#F9F9F8', // Warm off-white
  bgElevated: '#FFFFFF', // White cards
  bgElevated2: '#F0F0EE',
  accentPrimary: '#22C55E', // Same Jarumba Green
  accentDim: '#16a34a',
  accentTint10: 'rgba(34,197,94,0.10)',
  accentSecondary: '#FF8A3D',
  textPrimary: '#07100B', // Dark text
  textSecondary: '#656B67',
  textTertiary: '#9BA39D',
  textDisabled: '#C4C9C6',
  borderSubtle: '#E2E5E3',
  divider: '#EBEFEB',
  error: '#FF5C5C',
  success: '#22C55E',
  white: '#FFFFFF',
};

// Default backward compatible palette
export const palette = darkPalette;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  pill: 999,
};

export const typography = {
  display: {
    fontSize: 32,
    lineHeight: 36,
    fontWeight: '700' as const,
    letterSpacing: -0.5,
  },
  h1: {
    fontSize: 24,
    lineHeight: 28,
    fontWeight: '700' as const,
    letterSpacing: -0.3,
  },
  h2: {
    fontSize: 18,
    lineHeight: 22,
    fontWeight: '600' as const,
    letterSpacing: 0,
  },
  body: {
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '400' as const,
    letterSpacing: 0,
  },
  bodyBold: {
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '600' as const,
    letterSpacing: 0,
  },
  caption: {
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '400' as const,
    letterSpacing: 0,
  },
  captionSmall: {
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '500' as const,
    letterSpacing: 0.5,
  },
};

export const layout = {
  appPadding: 16,
  tabletMaxWidth: 24,
  sectionGap: 24,
};

export const theme = {
  colors: palette,
  spacing,
  radius,
  typography,
  layout,
};

export function getTheme(mode: 'light' | 'dark') {
  return {
    ...theme,
    colors: mode === 'light' ? lightPalette : darkPalette,
  };
}
