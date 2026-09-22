import React, { createContext, useContext, useEffect, useState, useMemo } from 'react';
import { Appearance, ColorSchemeName } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { getTheme, ThemePalette, darkPalette } from '../constants/theme';

type ThemeMode = 'system' | 'light' | 'dark';

type ThemeContextType = {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  colors: ThemePalette;
  isDark: boolean;
  colorScheme: 'dark' | 'light';
  toggleColorScheme: () => void;
};

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const STORAGE_KEY = 'jarumba-theme-mode';

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>('system');
  const [systemScheme, setSystemScheme] = useState<ColorSchemeName | null | undefined>(Appearance.getColorScheme());

  useEffect(() => {
    // Load persisted mode
    SecureStore.getItemAsync(STORAGE_KEY).then((storedMode) => {
      if (storedMode === 'light' || storedMode === 'dark' || storedMode === 'system') {
        setMode(storedMode);
      }
    });
  }, []);

  useEffect(() => {
    // Listen for system theme changes
    const subscription = Appearance.addChangeListener(({ colorScheme }) => {
      setSystemScheme(colorScheme);
    });
    return () => subscription.remove();
  }, []);

  const handleSetMode = (newMode: ThemeMode) => {
    setMode(newMode);
    SecureStore.setItemAsync(STORAGE_KEY, newMode);
  };

  const isDark = mode === 'dark' || (mode === 'system' && systemScheme === 'dark');
  const activeMode: 'dark' | 'light' = isDark ? 'dark' : 'light';
  const colorScheme: 'dark' | 'light' = activeMode;
  const toggleColorScheme = () => {
    handleSetMode(isDark ? 'light' : 'dark');
  };
  
  const value = useMemo(
    () => ({
      mode,
      setMode: handleSetMode,
      colors: getTheme(activeMode).colors,
      isDark,
      colorScheme,
      toggleColorScheme,
    }),
    [mode, activeMode, isDark, colorScheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    return {
      mode: 'system' as ThemeMode,
      setMode: () => {},
      colors: darkPalette,
      isDark: true,
      colorScheme: 'dark' as const,
      toggleColorScheme: () => {},
    };
  }
  return context;
}
