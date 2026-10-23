import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/button';
import { Logo } from '@/components/logo';
import { Text } from '@/components/text';
import { Gutter } from '@/constants/theme';

export default function WelcomeScreen() {
  const { t } = useTranslation();
  const { anonymousAllowed } = useAuth();
  return (
    <SafeAreaView style={styles.fill} edges={['top', 'bottom', 'left', 'right']}>
      <View style={styles.hero}>
        <Logo size={64} />
        <Text weight="bold" style={styles.name} accessibilityRole="header">
          {t('common.appName')}
        </Text>
        <Text color="ink2" style={styles.tagline}>
          {t('auth.welcomeTagline')}
        </Text>
      </View>
      <View style={styles.actions}>
        <Button
          label={t('auth.createAccount')}
          onPress={() => router.push({ pathname: '/phone', params: { mode: 'signup' } })}
        />
        <Button
          variant="secondary"
          label={t('auth.logIn')}
          onPress={() => router.push({ pathname: '/phone', params: { mode: 'login' } })}
        />
        {/* Only when the API is set up for it: without it the next screen's
            button can only fail. */}
        {anonymousAllowed ? (
          <Button
            variant="quiet"
            label={t('auth.withoutAccount')}
            onPress={() => router.push('/no-account')}
          />
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, paddingHorizontal: Gutter },
  hero: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  name: { fontSize: 32, lineHeight: 40, marginTop: 8 },
  tagline: { textAlign: 'center', maxWidth: 300 },
  actions: { gap: 10, paddingBottom: 16 },
});
