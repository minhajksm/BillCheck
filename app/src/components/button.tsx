import { Pressable, StyleSheet } from 'react-native';

import { Radius } from '@/constants/theme';
import { usePalette } from '@/hooks/use-palette';

import { Icon, type IconName } from './icon';
import { Text } from './text';

type ButtonProps = {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary';
  icon?: IconName;
};

export function Button({ label, onPress, variant = 'primary', icon }: ButtonProps) {
  const palette = usePalette();
  const primary = variant === 'primary';
  const fg = primary ? 'onIndigo' : 'ink';

  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        primary
          ? { backgroundColor: palette.indigo }
          : { backgroundColor: palette.card, borderColor: palette.line, borderWidth: 1 },
        pressed && styles.pressed,
      ]}>
      {icon ? <Icon name={icon} color={fg} /> : null}
      <Text weight="semibold" color={fg}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 48,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: Radius.button,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  pressed: { transform: [{ scale: 0.985 }], opacity: 0.92 },
});
