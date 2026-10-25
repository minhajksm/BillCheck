import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/button';
import { FormScreen } from '@/components/form-screen';
import { Text } from '@/components/text';
import { TextField } from '@/components/text-field';
import { useToast } from '@/components/toast';
import { createMember, readMember, updateMember, type MemberDetails } from '@/data/members-api';
import { ageOn } from '@/lib/age';
import { isValidMobile, nationalDigits } from '@/lib/phone';

/** The form's own state: every field as typed, the phone as its 10 digits. */
type Values = { name: string; dateOfBirth: string; phone: string; email: string; address: string };
type Errors = Partial<Record<keyof Values, string>>;

const EMPTY: Values = { name: '', dateOfBirth: '', phone: '', email: '', address: '' };
// The API checks properly. This only catches what is plainly not an address.
const LOOKS_LIKE_EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

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
  const [values, setValues] = useState<Values>(EMPTY);
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  const token = state.status === 'signedIn' ? state.token : null;

  // Editing starts from what they have.
  useEffect(() => {
    if (!memberId || !token) return;
    readMember(token, memberId)
      .then((member) =>
        setValues({
          name: member.name,
          dateOfBirth: member.dateOfBirth ?? '',
          phone: member.phone ? nationalDigits(member.phone) : '',
          email: member.email ?? '',
          address: member.address ?? '',
        }),
      )
      .catch(() => undefined);
  }, [memberId, token]);

  if (!token) return null;

  const set = (key: keyof Values) => (value: string) =>
    setValues((current) => ({ ...current, [key]: key === 'phone' ? nationalDigits(value) : value }));
  const age = values.dateOfBirth ? ageOn(values.dateOfBirth.trim(), new Date()) : undefined;

  const validate = (): Errors => {
    const found: Errors = {};
    if (!values.name.trim()) found.name = t('newCase.required');
    if (values.dateOfBirth.trim() && age === undefined) found.dateOfBirth = t('members.badDob');
    if (values.phone && !isValidMobile(values.phone)) found.phone = t('members.badPhone');
    if (values.email.trim() && !LOOKS_LIKE_EMAIL.test(values.email.trim()))
      found.email = t('members.badEmail');
    return found;
  };

  const submit = async () => {
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const details: MemberDetails = {
      name: values.name.trim(),
      dateOfBirth: values.dateOfBirth.trim() || undefined,
      phone: values.phone ? `+91${values.phone}` : undefined,
      email: values.email.trim() || undefined,
      address: values.address.trim() || undefined,
    };
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
      <TextField
        label={t('members.nameLabel')}
        placeholder={t('members.namePlaceholder')}
        value={values.name}
        onChangeText={set('name')}
        error={errors.name}
        autoCapitalize="words"
        autoFocus={!memberId}
        maxLength={80}
      />
      <TextField
        label={t('members.dobLabel')}
        placeholder={t('members.dobPlaceholder')}
        value={values.dateOfBirth}
        onChangeText={set('dateOfBirth')}
        error={errors.dateOfBirth}
        autoCapitalize="none"
        keyboardType="numbers-and-punctuation"
        maxLength={10}
      />
      {age !== undefined ? (
        <Text variant="small" color="ink2">
          {t('members.age', { age })}
        </Text>
      ) : null}
      <TextField
        label={t('members.phoneLabel')}
        prefix="+91"
        value={values.phone}
        onChangeText={set('phone')}
        error={errors.phone}
        keyboardType="phone-pad"
        textContentType="telephoneNumber"
        maxLength={14}
      />
      <TextField
        label={t('members.emailLabel')}
        value={values.email}
        onChangeText={set('email')}
        error={errors.email}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
        textContentType="emailAddress"
        maxLength={254}
      />
      <TextField
        label={t('members.addressLabel')}
        value={values.address}
        onChangeText={set('address')}
        multiline
        maxLength={300}
      />
    </FormScreen>
  );
}
