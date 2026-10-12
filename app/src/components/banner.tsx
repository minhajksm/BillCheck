import { Pressable, StyleSheet, View } from 'react-native';

import { Radius, type Palette } from '@/constants/theme';
import { usePalette } from '@/hooks/use-palette';

import { Icon, type IconName } from './icon';
import { Text } from './text';

export type BannerTone = 'indigo' | 'amber' | 'green';

const tones: Record<BannerTone, { bg: keyof Palette; fg: keyof Palette }> = {
  indigo: { bg: 'indigoSoft', fg: 'indigoInk' },
  amber: { bg: 'marigoldSoft', fg: 'marigoldInk' },
  green: { bg: 'greenSoft', fg: 'green' },
};

type BannerProps = {
  tone: BannerTone;
  icon: IconName;
  title: string;
  body: string;
  /** When set, the banner is a button and shows a chevron. */
  onPress?: () => void;
};

export function Banner({ tone, icon, title, body, onPress }: BannerProps) {
  const palette = usePalette();
  const { bg, fg } = tones[tone];

  const content = (
    <>
      <Icon name={icon} color={fg} />
      <View style={styles.text}>
        <Text weight="bold" color={fg}>
          {title}
        </Text>
        <Text variant="small" color={fg}>
          {body}
        </Text>
      </View>
      {onPress ? <Icon name="chevron-right" color={fg} /> : null}
    </>
  );

  if (!onPress) {
    return <View style={[styles.banner, { backgroundColor: palette[bg] }]}>{content}</View>;
  }
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [styles.banner, { backgroundColor: palette[bg] }, pressed && styles.pressed]}>
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    borderRadius: Radius.card,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginTop: 12,
  },
  text: { flex: 1 },
  pressed: { opacity: 0.85 },
});
