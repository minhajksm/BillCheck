import { StyleSheet, View } from 'react-native';

import type { Palette } from '@/constants/theme';
import { usePalette } from '@/hooks/use-palette';

import { Text } from './text';

export type ChipTone = 'red' | 'amber' | 'green' | 'indigo' | 'grey';

const tones: Record<ChipTone, { bg: keyof Palette; fg: keyof Palette }> = {
  red: { bg: 'redSoft', fg: 'red' },
  amber: { bg: 'marigoldSoft', fg: 'marigoldInk' },
  green: { bg: 'greenSoft', fg: 'green' },
  indigo: { bg: 'indigoSoft', fg: 'indigoInk' },
  grey: { bg: 'soft', fg: 'ink2' },
};

export function Chip({ tone, label }: { tone: ChipTone; label: string }) {
  const palette = usePalette();
  const { bg, fg } = tones[tone];
  return (
    <View style={[styles.chip, { backgroundColor: palette[bg] }]}>
      <Text variant="faint" weight="semibold" color={fg} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 1,
    alignSelf: 'flex-start',
    flexShrink: 0,
  },
});
