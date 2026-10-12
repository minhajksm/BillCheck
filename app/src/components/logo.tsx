import { StyleSheet, View } from 'react-native';

import { usePalette } from '@/hooks/use-palette';

/** The bill mark from the prototype: two ruled lines over a marigold band. */
export function Logo({ size = 26 }: { size?: number }) {
  const palette = usePalette();
  const unit = size / 26;
  const line = { height: 2 * unit, backgroundColor: palette.onIndigo, marginHorizontal: 6 * unit };

  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[styles.mark, { width: size, height: size, borderRadius: 7 * unit, backgroundColor: palette.indigo }]}>
      <View style={[line, { marginTop: 7 * unit }]} />
      <View style={[line, { marginTop: 2 * unit }]} />
      <View
        style={[
          styles.band,
          { height: 4 * unit, left: 5 * unit, right: 5 * unit, bottom: 5 * unit, backgroundColor: palette.marigold },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  mark: { position: 'relative' },
  band: { position: 'absolute', borderRadius: 2, opacity: 0.9 },
});
