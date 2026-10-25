import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/button';
import { FormScreen } from '@/components/form-screen';
import { TextField } from '@/components/text-field';
import { useToast } from '@/components/toast';
import { createMember, readMember, renameMember } from '@/data/members-api';

/**
 * Adding someone to look after, or renaming them.
 *
 * Only a name: whatever the family calls them. "Papa" to one of them is
 * "Ramesh Sharma" on a bill, and either is fine here. With `memberId`, this
 * renames that member instead.
 */
export default function NewMemberScreen() {
  const { memberId } = useLocalSearchParams<{ memberId?: string }>();
  const { t } = useTranslation();
  const toast = useToast();
  const { state } = useAuth();
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const token = state.status === 'signedIn' ? state.token : null;

  // Renaming starts from the name they have.
  useEffect(() => {
    if (!memberId || !token) return;
    readMember(token, memberId)
      .then((member) => setName(member.name))
      .catch(() => undefined);
  }, [memberId, token]);

  if (!token) return null;

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError(t('newCase.required'));
      return;
    }
    setError(null);
    setSaving(true);
    try {
      if (memberId) {
        await renameMember(token, memberId, trimmed);
        router.back();
      } else {
        const created = await createMember(token, trimmed);
        router.replace({ pathname: '/members/[memberId]', params: { memberId: created.id } });
      }
    } catch {
      setSaving(false);
      toast(memberId ? t('members.saveFailed') : t('members.addFailed'));
    }
  };

  return (
    <FormScreen
      title={memberId ? t('members.renameTitle') : t('members.newTitle')}
      subtitle={memberId ? undefined : t('members.newSubtitle')}
      footer={
        <Button label={memberId ? t('members.save') : t('members.add')} loading={saving} onPress={submit} />
      }>
      <TextField
        label={t('members.nameLabel')}
        placeholder={t('members.namePlaceholder')}
        value={name}
        onChangeText={setName}
        error={error}
        autoCapitalize="words"
        autoFocus={!memberId}
        maxLength={80}
        returnKeyType="done"
        onSubmitEditing={submit}
      />
    </FormScreen>
  );
}
