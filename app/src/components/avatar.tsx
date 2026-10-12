import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { usePalette } from '@/hooks/use-palette';
import { initials } from '@/lib/format';

import { Text } from './text';

type AvatarProps = {
  name: string;
  tone?: 'indigo' | 'green';
  style?: StyleProp<ViewStyle>;
};

export function Avatar({ name, tone = 'indigo', style }: AvatarProps) {
  const palette = usePalette();
  const indigo = tone === 'indigo';
  return (
    <View
      accessible
      accessibilityLabel={name}
      style={[
        styles.avatar,
        { backgroundColor: indigo ? palette.indigoSoft : palette.greenSoft, borderColor: palette.app },
        style,
      ]}>
      <Text variant="faint" weight="bold" color={indigo ? 'indigoInk' : 'green'} style={styles.label}>
        {initials(name)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  avatar: {
    width: 30,
    height: 30,
    borderRadius: 15,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: { fontSize: 12, lineHeight: 16 },
});
