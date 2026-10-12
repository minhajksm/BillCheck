/**
 * Design tokens ported from docs/prototype.html. Keep these in sync with the
 * prototype's :root variables (light) and its dark-mode overrides.
 */

export const Colors = {
  light: {
    app: '#F5F6F9',
    card: '#FFFFFF',
    soft: '#EDEFF5',
    ink: '#1B2140',
    ink2: '#525877',
    ink3: '#80859F',
    line: '#DDE0EA',
    indigo: '#2E3A8C',
    onIndigo: '#FFFFFF',
    indigoSoft: '#E5E8F7',
    indigoInk: '#2E3A8C',
    marigold: '#F2A71B',
    marigoldSoft: '#FDF0D5',
    marigoldInk: '#7A4D00',
    red: '#B4322A',
    redSoft: '#FBE7E5',
    green: '#2F7A4B',
    greenSoft: '#E1F1E6',
  },
  dark: {
    app: '#141827',
    card: '#1C2134',
    soft: '#242A42',
    ink: '#ECEEF7',
    ink2: '#B2B7CF',
    ink3: '#7E84A2',
    line: '#2D3352',
    indigo: '#9AA6F2',
    onIndigo: '#11152A',
    indigoSoft: '#262C55',
    indigoInk: '#B9C2F7',
    marigold: '#F5B53D',
    marigoldSoft: '#3A2C0E',
    marigoldInk: '#F7CB72',
    red: '#F08A80',
    redSoft: '#3D1E1C',
    green: '#7CCB98',
    greenSoft: '#183021',
  },
} as const;

export type Palette = { [K in keyof typeof Colors.light]: string };

/** Mukta covers Latin and Devanagari, so en, hi, and mr share one family. */
export const FontFamily = {
  regular: 'Mukta_400Regular',
  medium: 'Mukta_500Medium',
  semibold: 'Mukta_600SemiBold',
  bold: 'Mukta_700Bold',
} as const;

export type FontWeight = keyof typeof FontFamily;

export const Radius = {
  button: 14,
  card: 16,
  icon: 12,
} as const;

/** Horizontal page padding, matching the prototype's .pad. */
export const Gutter = 18;
