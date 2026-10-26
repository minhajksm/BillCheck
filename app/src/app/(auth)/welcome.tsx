import { router } from 'expo-router';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/button';
import { Logo } from '@/components/logo';
import { Text } from '@/components/text';
import { Gutter } from '@/constants/theme';
import { usePalette } from '@/hooks/use-palette';

/**
 * The way in, as the API is set up for it (REQUIRE_SIGN_IN).
 *
 * Signing in on: create an account or log in, with a phone number. Off: one
 * button, on to the consent screen, and no sign-in anywhere. Nothing is
 * offered until the API has said which, so a button that would only fail is
 * never on screen.
 */
export default function WelcomeScreen() {
  const { t } = useTranslation();
  const palette = usePalette();
  const { signInMode, recheckSignIn } = useAuth();

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
        {signInMode === 'checking' ? (
          // A server waking from idle can take ten seconds or more.
          <View style={styles.waiting} accessibilityLiveRegion="polite">
            <ActivityIndicator color={palette.indigo} />
            <Text color="ink2">{t('auth.connecting')}</Text>
          </View>
        ) : null}
        {signInMode === 'unreachable' ? (
          <>
            <Text color="ink2" style={styles.centred}>
              {t('auth.errors.network')}
            </Text>
            <Button variant="secondary" label={t('common.tryAgain')} onPress={recheckSignIn} />
          </>
        ) : null}
        {signInMode === 'off' ? (
          <Button label={t('auth.getStarted')} onPress={() => router.push('/no-account')} />
        ) : null}
        {signInMode === 'required' ? (
          <>
            <Button
              label={t('auth.createAccount')}
              onPress={() => router.push({ pathname: '/phone', params: { mode: 'signup' } })}
            />
            <Button
              variant="secondary"
              label={t('auth.logIn')}
              onPress={() => router.push({ pathname: '/phone', params: { mode: 'login' } })}
            />
          </>
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
  waiting: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, minHeight: 52 },
  centred: { textAlign: 'center' },
});
