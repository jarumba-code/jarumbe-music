import React from 'react';
import { StatusBar } from 'expo-status-bar';

import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { PlaybackProvider } from './context/PlaybackContext';
import { AppNavigator } from './navigation/AppNavigator';

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <PlaybackProvider>
          <StatusBar style="auto" />
          <AppNavigator />
        </PlaybackProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
