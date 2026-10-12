import { StyleSheet, Text as RNText, type TextProps as RNTextProps } from 'react-native';

import { FontFamily, type FontWeight, type Palette } from '@/constants/theme';
import { usePalette } from '@/hooks/use-palette';

const variants = StyleSheet.create({
  body: { fontSize: 15, lineHeight: 22 },
  small: { fontSize: 14, lineHeight: 20 },
  faint: { fontSize: 13, lineHeight: 18 },
  title: { fontSize: 18, lineHeight: 22 },
  hello: { fontSize: 24, lineHeight: 30, letterSpacing: -0.2 },
  metric: { fontSize: 22, lineHeight: 30, letterSpacing: -0.2 },
});

export type TextVariant = keyof typeof variants;

export type TextProps = RNTextProps & {
  variant?: TextVariant;
  weight?: FontWeight;
  color?: keyof Palette;
};

const defaultColor: Partial<Record<TextVariant, keyof Palette>> = { faint: 'ink3' };

/**
 * Mukta ships one file per weight, so weight picks the font family rather
 * than fontWeight, which Android ignores for custom fonts.
 */
export function Text({ variant = 'body', weight = 'regular', color, style, ...rest }: TextProps) {
  const palette = usePalette();
  return (
    <RNText
      style={[
        variants[variant],
        { fontFamily: FontFamily[weight], color: palette[color ?? defaultColor[variant] ?? 'ink'] },
        style,
      ]}
      {...rest}
    />
  );
}
