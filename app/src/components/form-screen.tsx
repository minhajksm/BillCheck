import type { ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Gutter } from '@/constants/theme';

import { AppHeader } from './app-header';
import { Text } from './text';

type FormScreenProps = {
  title: string;
  subtitle?: ReactNode;
  showBack?: boolean;
  children: ReactNode;
  /** Pinned under the content, e.g. the main button. */
  footer?: ReactNode;
};

/** Layout for the sign-in steps: heading, fields, button above the keyboard. */
export function FormScreen({ title, subtitle, showBack = true, children, footer }: FormScreenProps) {
  return (
    <SafeAreaView style={styles.fill} edges={['top', 'left', 'right', 'bottom']}>
      <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        {showBack ? <AppHeader title="" showBack /> : <View style={styles.spacer} />}
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Text variant="hello" weight="bold" accessibilityRole="header">
            {title}
          </Text>
          {subtitle ? (
            typeof subtitle === 'string' ? (
              <Text color="ink2" style={styles.subtitle}>
                {subtitle}
              </Text>
            ) : (
              <View style={styles.subtitle}>{subtitle}</View>
            )
          ) : null}
          <View style={styles.fields}>{children}</View>
        </ScrollView>
        {footer ? <View style={styles.footer}>{footer}</View> : null}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  spacer: { height: 56 },
  content: { paddingHorizontal: Gutter, paddingBottom: 24 },
  subtitle: { marginTop: 4 },
  fields: { marginTop: 24, gap: 18 },
  footer: { paddingHorizontal: Gutter, paddingBottom: 16, paddingTop: 8, gap: 10 },
});
