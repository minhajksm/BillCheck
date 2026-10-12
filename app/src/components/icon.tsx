import Feather from '@expo/vector-icons/Feather';
import type { ComponentProps } from 'react';

import type { Palette } from '@/constants/theme';
import { usePalette } from '@/hooks/use-palette';

/** Feather's outline style is the closest match to the prototype's icons. */
export type IconName = ComponentProps<typeof Feather>['name'];

type IconProps = {
  name: IconName;
  size?: number;
  color?: keyof Palette;
};

export function Icon({ name, size = 20, color = 'ink' }: IconProps) {
  const palette = usePalette();
  return <Feather name={name} size={size} color={palette[color]} accessibilityElementsHidden importantForAccessibility="no" />;
}
