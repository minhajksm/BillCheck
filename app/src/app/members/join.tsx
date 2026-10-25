import { router } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/button';
import { FormScreen } from '@/components/form-screen';
import { TextField } from '@/components/text-field';
import { useToast } from '@/components/toast';
import { joinMember } from '@/data/members-api';

/**
 * Following someone with a code from family.
 *
 * The code is what a follower shared from that person's screen. It expires
 * and can be withdrawn, which is why the member's id alone is never enough.
 */
export default function JoinMemberScreen() {
  const { t } = useTranslation();
  const toast = useToast();
  const { state } = useAuth();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);

  if (state.status !== 'signedIn') return null;
  const token = state.token;

  const submit = async () => {
    // A code pasted from a message often brings a space or a line with it.
    const trimmed = code.trim();
    if (!trimmed) {
      setError(t('newCase.required'));
      return;
    }
    setError(null);
    setJoining(true);
    try {
      const member = await joinMember(token, trimmed);
      toast(t('members.joined', { name: member.name }));
      router.replace({ pathname: '/members/[memberId]', params: { memberId: member.id } });
    } catch {
      setJoining(false);
      setError(t('members.joinFailed'));
    }
  };

  return (
    <FormScreen
      title={t('members.joinTitle')}
      subtitle={t('members.joinSubtitle')}
      footer={<Button label={t('members.join')} loading={joining} onPress={submit} />}>
      <TextField
        label={t('members.codeLabel')}
        value={code}
        onChangeText={setCode}
        error={error}
        autoCapitalize="none"
        autoCorrect={false}
        autoFocus
        maxLength={64}
        returnKeyType="done"
        onSubmitEditing={submit}
      />
    </FormScreen>
  );
}
