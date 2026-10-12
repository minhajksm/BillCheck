import { Pressable, StyleSheet, View } from 'react-native';

import { usePalette } from '@/hooks/use-palette';

import { Icon } from './icon';
import { Text } from './text';

type CheckboxProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
};

export function Checkbox({ checked, onChange, label }: CheckboxProps) {
  const palette = usePalette();
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      accessibilityLabel={label}
      onPress={() => onChange(!checked)}
      style={styles.row}>
      <View
        style={[
          styles.box,
          checked
            ? { backgroundColor: palette.indigo, borderColor: palette.indigo }
            : { backgroundColor: palette.card, borderColor: palette.ink3 },
        ]}>
        {checked ? <Icon name="check" size={16} color="onIndigo" /> : null}
      </View>
      <Text variant="small" color="ink2" style={styles.label}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  box: {
    width: 24,
    height: 24,
    borderRadius: 6,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  label: { flex: 1 },
});
