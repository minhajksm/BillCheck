import type { ReactNode } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Gutter } from '@/constants/theme';

/** Safe-area screen with a header that stays put while the content scrolls. */
export function Screen({ header, children }: { header: ReactNode; children: ReactNode }) {
  return (
    <SafeAreaView style={styles.fill} edges={['top', 'left', 'right']}>
      <ScrollView style={styles.fill} contentContainerStyle={styles.scroll} stickyHeaderIndices={[0]}>
        {header}
        <View style={styles.pad}>{children}</View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  scroll: { flexGrow: 1 },
  pad: { paddingHorizontal: Gutter, paddingTop: 2, paddingBottom: 28 },
});
