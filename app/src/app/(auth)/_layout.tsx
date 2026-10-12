import { Stack } from 'expo-router';

import { usePalette } from '@/hooks/use-palette';

export default function AuthLayout() {
  const palette = usePalette();
  return (
    <Stack
      initialRouteName="welcome"
      screenOptions={{ headerShown: false, contentStyle: { backgroundColor: palette.app } }}
    />
  );
}
