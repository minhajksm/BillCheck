import { Redirect, router, useLocalSearchParams } from 'expo-router';
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
 * Asked once, before the first lab report.
 *
 * The consent given at sign-up covers "the bills I add", used "only to check
 * my bills". A lab report is neither, so it is asked for again, as its own
 * act and in its own words -- including the one thing a family most needs to
 * hear before reading an explanation of their results: this is not a doctor.
 */
export default function LabConsentScreen() {
  // Passed on, so a report started from a member is still theirs.
  const { memberId } = useLocalSearchParams<{ memberId?: string }>();
  const next = { pathname: '/lab/new' as const, params: memberId ? { memberId } : {} };
  const { t } = useTranslation();
  const palette = usePalette();
  const { state, agreeToLabReports } = useAuth();
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (state.status !== 'signedIn') return null;
  if (state.user.lab_consent) return <Redirect href={next} />;

  const submit = async () => {
    if (!consent || busy) return;
    setBusy(true);
    setError(null);
    try {
      await agreeToLabReports();
      router.replace(next);
    } catch (e) {
      setError(authErrorMessage(t, e));
      setBusy(false);
    }
  };

  return (
    <FormScreen
      title={t('lab.consentTitle')}
      subtitle={t('lab.consentSubtitle')}
      footer={
        <Button label={t('lab.consentContinue')} onPress={submit} disabled={!consent} loading={busy} />
      }>
      <View style={[styles.note, { backgroundColor: palette.soft, borderColor: palette.line }]}>
        <Text variant="small">{t('lab.consentWhat')}</Text>
        <Text variant="small" weight="semibold">
          {t('lab.consentNotDoctor')}
        </Text>
      </View>
      <Checkbox checked={consent} onChange={setConsent} label={t('lab.consentAgree')} />
      {error ? (
        <Text variant="small" color="red">
          {error}
        </Text>
      ) : null}
    </FormScreen>
  );
}

const styles = StyleSheet.create({
  note: { borderWidth: 1, borderRadius: Radius.card, paddingHorizontal: 16, paddingVertical: 14, gap: 10 },
});
