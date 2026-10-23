import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { usePalette } from '@/hooks/use-palette';
import { initials } from '@/lib/format';

import { Icon } from './icon';
import { Text } from './text';

type AvatarProps = {
  name: string;
  /** Stands in for the name when there is none, as on a device-only account:
   * a screen reader needs something to read, and initials need two letters. */
  label?: string;
  tone?: 'indigo' | 'green';
  style?: StyleProp<ViewStyle>;
};

export function Avatar({ name, label, tone = 'indigo', style }: AvatarProps) {
  const palette = usePalette();
  const indigo = tone === 'indigo';
  const letters = initials(name);
  return (
    <View
      accessible
      accessibilityLabel={name || label}
      style={[
        styles.avatar,
        { backgroundColor: indigo ? palette.indigoSoft : palette.greenSoft, borderColor: palette.app },
        style,
      ]}>
      {letters ? (
        <Text variant="faint" weight="bold" color={indigo ? 'indigoInk' : 'green'} style={styles.label}>
          {letters}
        </Text>
      ) : (
        <Icon name="user" size={15} color={indigo ? 'indigoInk' : 'green'} />
      )}
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
