import React from 'react';
import { View } from 'react-native';
import { createBottomTabNavigator, BottomTabBar } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { NavigationContainer } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';

import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { HomeScreen } from '../screens/HomeScreen';
import { LibraryScreen } from '../screens/LibraryScreen';
import { LoginScreen } from '../screens/LoginScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { SearchScreen } from '../screens/SearchScreen';
import { NowPlayingScreen } from '../screens/NowPlayingScreen';
import { NotificationsScreen } from '../screens/NotificationsScreen';
import { TermsScreen } from '../screens/TermsScreen';
import { PrivacyScreen } from '../screens/PrivacyScreen';
import { MiniPlayer } from '../components/MiniPlayer';

const Tab = createBottomTabNavigator();
const MainStack = createNativeStackNavigator();
const RootStack = createNativeStackNavigator();
const AuthStack = createNativeStackNavigator();

function TabNavigator() {
  const { colors } = useTheme();

  return (
    <Tab.Navigator
      tabBar={(props) => (
        <View>
          <MiniPlayer />
          <BottomTabBar {...props} />
        </View>
      )}
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarStyle: {
          backgroundColor: colors.bgElevated,
          borderTopColor: colors.borderSubtle,
        },
        tabBarActiveTintColor: colors.accentPrimary,
        tabBarInactiveTintColor: colors.textTertiary,
        tabBarIcon: ({ focused, color, size }) => {
          let iconName: keyof typeof Ionicons.glyphMap = 'help';

          if (route.name === 'Home') {
            iconName = focused ? 'home' : 'home-outline';
          } else if (route.name === 'Search') {
            iconName = focused ? 'search' : 'search-outline';
          } else if (route.name === 'Library') {
            iconName = focused ? 'library' : 'library-outline';
          } else if (route.name === 'Settings') {
            iconName = focused ? 'settings' : 'settings-outline';
          }

          return <Ionicons name={iconName} size={size} color={color} />;
        },
      })}>
      <Tab.Screen name="Home" component={HomeScreen} />
      <Tab.Screen name="Search" component={SearchScreen} />
      <Tab.Screen name="Library" component={LibraryScreen} />
      <Tab.Screen name="Settings" component={SettingsScreen} />
    </Tab.Navigator>
  );
}

function MainStackNavigator() {
  return (
    <MainStack.Navigator screenOptions={{ headerShown: false }}>
      <MainStack.Screen name="Tabs" component={TabNavigator} />
      <MainStack.Screen name="Notifications" component={NotificationsScreen} />
      <MainStack.Screen name="Terms" component={TermsScreen} />
      <MainStack.Screen name="Privacy" component={PrivacyScreen} />
    </MainStack.Navigator>
  );
}

function AuthStackNavigator() {
  return (
    <AuthStack.Navigator screenOptions={{ headerShown: false }}>
      <AuthStack.Screen name="Login" component={LoginScreen} />
      <AuthStack.Screen name="Terms" component={TermsScreen} />
      <AuthStack.Screen name="Privacy" component={PrivacyScreen} />
    </AuthStack.Navigator>
  );
}

export function AppNavigator() {
  const { session, loading } = useAuth();
  const { colors } = useTheme();

  if (loading) {
    return null;
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.bgBase }}>
      <NavigationContainer>
        {session ? (
          <RootStack.Navigator screenOptions={{ headerShown: false }}>
            <RootStack.Screen name="MainStack" component={MainStackNavigator} />
            <RootStack.Screen 
              name="NowPlaying" 
              component={NowPlayingScreen} 
              options={{ presentation: 'fullScreenModal' }} 
            />
          </RootStack.Navigator>
        ) : (
          <AuthStackNavigator />
        )}
      </NavigationContainer>
    </View>
  );
}
