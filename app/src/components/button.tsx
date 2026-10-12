import { ActivityIndicator, Pressable, StyleSheet } from 'react-native';

import { Radius } from '@/constants/theme';
import { usePalette } from '@/hooks/use-palette';

import { Icon, type IconName } from './icon';
import { Text } from './text';

type ButtonProps = {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary';
  icon?: IconName;
  disabled?: boolean;
  /** Shows a spinner and ignores presses while work is in flight. */
  loading?: boolean;
};

export function Button({ label, onPress, variant = 'primary', icon, disabled = false, loading = false }: ButtonProps) {
  const palette = usePalette();
  const primary = variant === 'primary';
  const fg = primary ? 'onIndigo' : 'ink';
  const inactive = disabled || loading;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive, busy: loading }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        primary
          ? { backgroundColor: palette.indigo }
          : { backgroundColor: palette.card, borderColor: palette.line, borderWidth: 1 },
        disabled && styles.disabled,
        pressed && styles.pressed,
      ]}>
      {loading ? <ActivityIndicator color={palette[fg]} /> : icon ? <Icon name={icon} color={fg} /> : null}
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
  disabled: { opacity: 0.45 },
  pressed: { transform: [{ scale: 0.985 }], opacity: 0.92 },
});
