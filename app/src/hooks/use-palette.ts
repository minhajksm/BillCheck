import { useColorScheme } from 'react-native';

import { Colors, type Palette } from '@/constants/theme';

export function usePalette(): Palette {
  return useColorScheme() === 'dark' ? Colors.dark : Colors.light;
}
