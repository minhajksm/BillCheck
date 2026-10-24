import { Pressable, StyleSheet, View } from 'react-native';

import { usePalette } from '@/hooks/use-palette';

import { Text } from './text';

/**
 * Two or three options, one chosen: the bill report's tabs and a lab
 * report's language. Announced as tabs, since that is what it behaves like.
 */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  const palette = usePalette();
  return (
    <View style={[styles.segmented, { backgroundColor: palette.soft }]} accessibilityRole="tablist">
      {options.map((option) => {
        const on = option.value === value;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="tab"
            accessibilityState={{ selected: on }}
            onPress={() => onChange(option.value)}
            style={[
              styles.segment,
              on && {
                backgroundColor: palette.card,
                borderColor: palette.line,
              },
            ]}>
            <Text weight="semibold" color={on ? 'ink' : 'ink2'}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  segmented: {
    flexDirection: 'row',
    borderRadius: 12,
    padding: 3,
    gap: 3,
    marginBottom: 14,
  },
  segment: {
    flex: 1,
    paddingVertical: 7,
    borderRadius: 9,
    alignItems: 'center',
    borderWidth: 0,
  },
});
