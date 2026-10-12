import { Redirect, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth, type AuthMode } from '@/auth/auth-context';
import { authErrorMessage } from '@/auth/error-message';
import { Button } from '@/components/button';
import { Checkbox } from '@/components/checkbox';
import { FormScreen } from '@/components/form-screen';
import { TextField } from '@/components/text-field';

/** Last sign-up step for a verified number: name and consent. */
export default function ProfileScreen() {
  const { t } = useTranslation();
  const { state, completeSignup } = useAuth();
  const { mode = 'signup' } = useLocalSearchParams<{ mode?: AuthMode }>();
  const [name, setName] = useState('');
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Once signed in, the root layout takes over navigation.
  if (state.status === 'signedIn') return null;
  if (state.status !== 'signedOut' || !state.signupToken) return <Redirect href="/welcome" />;

  const ready = name.trim().length > 0 && consent;

  const submit = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    try {
      // On success the root layout moves to the home screen.
      await completeSignup(name.trim());
    } catch (e) {
      setError(authErrorMessage(t, e));
      setBusy(false);
    }
  };

  return (
    <FormScreen
      title={t('auth.profileTitle')}
      // Someone who tapped "Log in" with a new number should know why they're here.
      subtitle={mode === 'login' ? t('auth.profileSubtitleNew') : t('auth.profileSubtitle')}
      showBack={false}
      footer={<Button label={t('auth.finishSignup')} onPress={submit} disabled={!ready} loading={busy} />}>
      <TextField
        label={t('auth.nameLabel')}
        value={name}
        onChangeText={setName}
        placeholder={t('auth.namePlaceholder')}
        autoComplete="name"
        textContentType="name"
        autoCapitalize="words"
        maxLength={80}
        autoFocus
        error={error}
      />
      <Checkbox checked={consent} onChange={setConsent} label={t('auth.consent')} />
    </FormScreen>
  );
}
