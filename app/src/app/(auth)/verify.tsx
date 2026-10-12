import { Redirect, router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { useAuth, type AuthMode } from '@/auth/auth-context';
import { authErrorMessage } from '@/auth/error-message';
import { Button } from '@/components/button';
import { FormScreen } from '@/components/form-screen';
import { Text } from '@/components/text';
import { TextField } from '@/components/text-field';
import { useToast } from '@/components/toast';
import { formatPhone } from '@/lib/phone';

const CODE_LENGTH = 6;

export default function VerifyScreen() {
  const { t } = useTranslation();
  const toast = useToast();
  const { state, verifyOtp, requestOtp } = useAuth();
  const { mode = 'signup', resendAfter = '30' } = useLocalSearchParams<{ mode?: AuthMode; resendAfter?: string }>();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [wait, setWait] = useState(Number(resendAfter) || 30);

  useEffect(() => {
    if (wait <= 0) return;
    const timer = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);

  // Once signed in, the root layout takes over navigation.
  if (state.status === 'signedIn') return null;
  const phone = state.status === 'signedOut' ? state.phone : null;
  if (!phone) return <Redirect href="/welcome" />;

  const submit = async (value = code) => {
    if (value.length !== CODE_LENGTH || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await verifyOtp(value);
      // Signed in: the root layout moves to the home screen by itself.
      if (result === 'signupRequired') router.replace({ pathname: '/profile', params: { mode } });
    } catch (e) {
      setError(authErrorMessage(t, e));
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setError(null);
    try {
      setWait(await requestOtp(phone));
      toast(t('auth.codeResent'));
    } catch (e) {
      setError(authErrorMessage(t, e));
    }
  };

  return (
    <FormScreen
      title={t('auth.verifyTitle')}
      subtitle={
        <View style={styles.sentTo}>
          <Text color="ink2">{t('auth.verifySubtitle', { phone: formatPhone(phone) })}</Text>
          <Pressable accessibilityRole="button" onPress={() => router.back()} hitSlop={8}>
            <Text weight="semibold" color="indigoInk">
              {t('auth.changeNumber')}
            </Text>
          </Pressable>
        </View>
      }
      footer={
        <Button
          label={t('auth.verify')}
          onPress={() => submit()}
          disabled={code.length !== CODE_LENGTH}
          loading={busy}
        />
      }>
      <TextField
        label={t('auth.codeLabel')}
        large
        value={code}
        onChangeText={(text) => {
          const digits = text.replace(/\D/g, '').slice(0, CODE_LENGTH);
          setCode(digits);
          setError(null);
          // Submit as soon as the last digit is in, including SMS autofill.
          if (digits.length === CODE_LENGTH) submit(digits);
        }}
        keyboardType="number-pad"
        autoComplete="sms-otp"
        textContentType="oneTimeCode"
        maxLength={CODE_LENGTH}
        autoFocus
        error={error}
      />
      {wait > 0 ? (
        <Text variant="small" color="ink3">
          {t('auth.resendIn', { seconds: wait })}
        </Text>
      ) : (
        <Pressable accessibilityRole="button" onPress={resend} hitSlop={8} style={styles.resend}>
          <Text variant="small" weight="semibold" color="indigoInk">
            {t('auth.resend')}
          </Text>
        </Pressable>
      )}
    </FormScreen>
  );
}

const styles = StyleSheet.create({
  sentTo: { gap: 4, alignItems: 'flex-start' },
  resend: { alignSelf: 'flex-start' },
});
