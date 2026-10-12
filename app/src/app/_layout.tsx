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

import { AuthProvider, useAuth } from '@/auth/auth-context';
import { ToastProvider } from '@/components/toast';
import { Colors } from '@/constants/theme';
import { useDeviceLanguage } from '@/i18n';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const palette = Colors[scheme];
  const base = scheme === 'dark' ? DarkTheme : DefaultTheme;

  useDeviceLanguage();

  return (
    <ThemeProvider
      value={{
        ...base,
        colors: { ...base.colors, background: palette.app, card: palette.app, text: palette.ink, border: palette.line },
      }}>
      <AuthProvider>
        <ToastProvider>
          <RootNavigator />
        </ToastProvider>
      </AuthProvider>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
    </ThemeProvider>
  );
}

/** Signed-in people see the app; everyone else sees the sign-in screens. */
function RootNavigator() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const { state } = useAuth();
  const [fontsLoaded, fontError] = useFonts({ Mukta_400Regular, Mukta_500Medium, Mukta_600SemiBold, Mukta_700Bold });
  // On a font error, carry on with the system font.
  const ready = (fontsLoaded || fontError !== null) && state.status !== 'loading';

  useEffect(() => {
    if (ready) SplashScreen.hideAsync();
  }, [ready]);

  // Keep the splash screen up while fonts load and the saved session is checked.
  if (!ready) return null;

  const signedIn = state.status === 'signedIn';
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: Colors[scheme].app } }}>
      <Stack.Protected guard={signedIn}>
        <Stack.Screen name="index" />
        <Stack.Screen name="cases/[caseId]" />
      </Stack.Protected>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
    </Stack>
  );
}
