import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/button';
import { FormScreen } from '@/components/form-screen';
import {
  EMPTY_MEMBER,
  MemberFields,
  memberDetails,
  memberValues,
  validateMember,
  type MemberErrors,
  type MemberValues,
} from '@/components/member-fields';
import { useToast } from '@/components/toast';
import { createMember, readMember, updateMember } from '@/data/members-api';

/**
 * Adding someone to look after, or editing their details.
 *
 * Only the name is needed: whatever the family calls them. "Papa" to one of
 * them is "Ramesh Sharma" on a bill, and either is fine here. The rest -- date
 * of birth, mobile, email, address -- is filled in where it is known, and age
 * is worked out from the date of birth rather than asked for, so it never
 * goes stale. With `memberId`, this edits that member instead.
 */
export default function MemberFormScreen() {
  const { memberId } = useLocalSearchParams<{ memberId?: string }>();
  const { t } = useTranslation();
  const toast = useToast();
  const { state } = useAuth();
  const [values, setValues] = useState<MemberValues>(EMPTY_MEMBER);
  const [errors, setErrors] = useState<MemberErrors>({});
  const [saving, setSaving] = useState(false);
  const token = state.status === 'signedIn' ? state.token : null;

  // Editing starts from what they have.
  useEffect(() => {
    if (!memberId || !token) return;
    readMember(token, memberId)
      .then((member) => setValues(memberValues(member)))
      .catch(() => undefined);
  }, [memberId, token]);

  if (!token) return null;

  const submit = async () => {
    const found = validateMember(values, t);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const details = memberDetails(values);
    setSaving(true);
    try {
      if (memberId) {
        await updateMember(token, memberId, details);
        router.back();
      } else {
        const created = await createMember(token, details);
        router.replace({ pathname: '/members/[memberId]', params: { memberId: created.id } });
      }
    } catch {
      setSaving(false);
      toast(memberId ? t('members.saveFailed') : t('members.addFailed'));
    }
  };

  return (
    <FormScreen
      title={memberId ? t('members.editTitle') : t('members.newTitle')}
      subtitle={memberId ? undefined : t('members.newSubtitle')}
      footer={
        <Button label={memberId ? t('members.save') : t('members.add')} loading={saving} onPress={submit} />
      }>
      <MemberFields values={values} errors={errors} onChange={setValues} autoFocusName={!memberId} />
    </FormScreen>
  );
}
