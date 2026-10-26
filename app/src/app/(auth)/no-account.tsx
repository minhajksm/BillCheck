import { Redirect } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { authErrorMessage } from '@/auth/error-message';
import { Button } from '@/components/button';
import { Checkbox } from '@/components/checkbox';
import { FormScreen } from '@/components/form-screen';
import { Text } from '@/components/text';
import { Radius } from '@/constants/theme';
import { usePalette } from '@/hooks/use-palette';

/**
 * Starting without an account: the way in while REQUIRE_SIGN_IN is off.
 *
 * A family holding a bill at the billing desk should not have to wait for an
 * SMS. This opens an account tied to this phone and nothing else, which means
 * the trade has to be said plainly before they agree to it: there is no number
 * to sign back in with, so the bills cannot be moved to another phone or
 * recovered if this one is lost. Consent is asked here either way: DPDP does
 * not care whether we know the person's number.
 */
export default function NoAccountScreen() {
  const { t } = useTranslation();
  const palette = usePalette();
  const { state, signInMode, continueWithoutSignIn } = useAuth();
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Once signed in, the root layout takes over navigation.
  if (state.status === 'signedIn') return null;
  // Still asking how people get in: nothing to show yet.
  if (signInMode === 'checking') return null;
  if (signInMode !== 'off') return <Redirect href="/welcome" />;

  const submit = async () => {
    if (!consent || busy) return;
    setBusy(true);
    setError(null);
    try {
      // On success the root layout moves to the home screen.
      await continueWithoutSignIn();
    } catch (e) {
      setError(authErrorMessage(t, e));
      setBusy(false);
    }
  };

  return (
    <FormScreen
      title={t('auth.noAccountTitle')}
      subtitle={t('auth.noAccountSubtitle')}
      footer={<Button label={t('auth.startChecking')} onPress={submit} disabled={!consent} loading={busy} />}>
      <View style={[styles.warning, { backgroundColor: palette.soft, borderColor: palette.line }]}>
        <Text weight="bold">{t('auth.noAccountKeepTitle')}</Text>
        <Text variant="small" color="ink2">
          {t('auth.noAccountKeepBody')}
        </Text>
      </View>
      <Checkbox checked={consent} onChange={setConsent} label={t('auth.noAccountConsent')} />
      {error ? (
        <Text variant="small" color="red">
          {error}
        </Text>
      ) : null}
    </FormScreen>
  );
}

const styles = StyleSheet.create({
  warning: {
    borderWidth: 1,
    borderRadius: Radius.card,
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 6,
  },
});
