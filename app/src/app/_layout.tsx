import {
  Mukta_400Regular,
  Mukta_500Medium,
  Mukta_600SemiBold,
  Mukta_700Bold,
  useFonts,
} from '@expo-google-fonts/mukta';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { useColorScheme } from 'react-native';

import { ToastProvider } from '@/components/toast';
import { Colors } from '@/constants/theme';
import { useDeviceLanguage } from '@/i18n';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const palette = Colors[scheme];
  const base = scheme === 'dark' ? DarkTheme : DefaultTheme;
  const [fontsLoaded, fontError] = useFonts({ Mukta_400Regular, Mukta_500Medium, Mukta_600SemiBold, Mukta_700Bold });

  useDeviceLanguage();

  useEffect(() => {
    if (fontsLoaded || fontError) SplashScreen.hideAsync();
  }, [fontsLoaded, fontError]);

  // On a font error, fall through and render with the system font.
  if (!fontsLoaded && !fontError) return null;

  return (
    <ThemeProvider
      value={{
        ...base,
        colors: { ...base.colors, background: palette.app, card: palette.app, text: palette.ink, border: palette.line },
      }}>
      <ToastProvider>
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: palette.app } }} />
      </ToastProvider>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
    </ThemeProvider>
  );
}
