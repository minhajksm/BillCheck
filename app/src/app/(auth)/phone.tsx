import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth, type AuthMode } from '@/auth/auth-context';
import { authErrorMessage } from '@/auth/error-message';
import { Button } from '@/components/button';
import { FormScreen } from '@/components/form-screen';
import { TextField } from '@/components/text-field';
import { isValidMobile, nationalDigits } from '@/lib/phone';

export default function PhoneScreen() {
  const { t } = useTranslation();
  const { requestOtp } = useAuth();
  const { mode = 'signup' } = useLocalSearchParams<{ mode?: AuthMode }>();
  const [digits, setDigits] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const valid = isValidMobile(digits);
  // Only complain once a full 10 digits are in and they can't be a mobile.
  const formatError = digits.length === 10 && !valid ? t('auth.errors.invalidPhone') : null;

  const send = async () => {
    if (!valid || sending) return;
    setSending(true);
    setError(null);
    try {
      const resendAfter = await requestOtp(digits);
      router.push({ pathname: '/verify', params: { mode, resendAfter: String(resendAfter) } });
    } catch (e) {
      setError(authErrorMessage(t, e));
    } finally {
      setSending(false);
    }
  };

  return (
    <FormScreen
      title={mode === 'login' ? t('auth.phoneTitleLogin') : t('auth.phoneTitleSignup')}
      subtitle={t('auth.phoneSubtitle')}
      footer={<Button label={t('auth.sendCode')} onPress={send} disabled={!valid} loading={sending} />}>
      <TextField
        label={t('auth.phoneLabel')}
        prefix="+91"
        large
        value={digits}
        onChangeText={(text) => {
          setDigits(nationalDigits(text));
          setError(null);
        }}
        placeholder={t('auth.phonePlaceholder')}
        keyboardType="phone-pad"
        autoComplete="tel"
        textContentType="telephoneNumber"
        autoFocus
        returnKeyType="send"
        onSubmitEditing={send}
        error={error ?? formatError}
      />
    </FormScreen>
  );
}
