import { forwardRef, useState } from 'react';
import { StyleSheet, TextInput, View, type TextInputProps } from 'react-native';

import { FontFamily, Radius } from '@/constants/theme';
import { usePalette } from '@/hooks/use-palette';

import { Text } from './text';

type TextFieldProps = TextInputProps & {
  label: string;
  /** Fixed text before the input, e.g. "+91". */
  prefix?: string;
  error?: string | null;
  large?: boolean;
};

export const TextField = forwardRef<TextInput, TextFieldProps>(function TextField(
  { label, prefix, error, large = false, style, onFocus, onBlur, ...rest },
  ref,
) {
  const palette = usePalette();
  const [focused, setFocused] = useState(false);
  const borderColor = error ? palette.red : focused ? palette.indigo : palette.line;
  return (
    <View style={styles.wrap}>
      <Text variant="small" weight="semibold" color="ink2">
        {label}
      </Text>
      <View
        style={[
          styles.box,
          { backgroundColor: palette.card, borderColor },
          focused && styles.focused,
        ]}>
        {prefix ? (
          <Text weight="semibold" style={[styles.prefix, large && styles.largeText]} color="ink2">
            {prefix}
          </Text>
        ) : null}
        <TextInput
          ref={ref}
          accessibilityLabel={label}
          placeholderTextColor={palette.ink3}
          onFocus={(e) => {
            setFocused(true);
            onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            onBlur?.(e);
          }}
          style={[
            styles.input,
            large && styles.largeText,
            { color: palette.ink, fontFamily: FontFamily.medium },
            style,
          ]}
          {...rest}
        />
      </View>
      {error ? (
        <Text variant="small" color="red" accessibilityLiveRegion="polite">
          {error}
        </Text>
      ) : null}
    </View>
  );
});

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  box: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: Radius.button,
    paddingHorizontal: 14,
    minHeight: 52,
  },
  prefix: { marginRight: 8 },
  focused: { borderWidth: 2, paddingHorizontal: 13 },
  // The box shows focus, so drop the browser's own outline on web.
  input: { flex: 1, fontSize: 16, paddingVertical: 12, outlineWidth: 0 },
  largeText: { fontSize: 20, letterSpacing: 1 },
});
