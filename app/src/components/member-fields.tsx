import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import type { MemberDetails } from '@/data/members-api';
import { ageOn } from '@/lib/age';
import { isValidMobile, nationalDigits } from '@/lib/phone';

import { Text } from './text';
import { TextField } from './text-field';

/** The form's own state: every field as typed, the phone as its 10 digits. */
export type MemberValues = {
  name: string;
  dateOfBirth: string;
  phone: string;
  email: string;
  address: string;
};
export type MemberErrors = Partial<Record<keyof MemberValues, string>>;

export const EMPTY_MEMBER: MemberValues = { name: '', dateOfBirth: '', phone: '', email: '', address: '' };

// The API checks properly. This only catches what is plainly not an address.
const LOOKS_LIKE_EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** A member's details as the form shows them. */
export function memberValues(details: Partial<MemberDetails>): MemberValues {
  return {
    name: details.name ?? '',
    dateOfBirth: details.dateOfBirth ?? '',
    phone: details.phone ? nationalDigits(details.phone) : '',
    email: details.email ?? '',
    address: details.address ?? '',
  };
}

/** Only the name is needed; whatever else is filled in has to be what it says. */
export function validateMember(values: MemberValues, t: TFunction): MemberErrors {
  const found: MemberErrors = {};
  if (!values.name.trim()) found.name = t('newCase.required');
  if (values.dateOfBirth.trim() && ageOn(values.dateOfBirth.trim(), new Date()) === undefined) {
    found.dateOfBirth = t('members.badDob');
  }
  if (values.phone && !isValidMobile(values.phone)) found.phone = t('members.badPhone');
  if (values.email.trim() && !LOOKS_LIKE_EMAIL.test(values.email.trim())) found.email = t('members.badEmail');
  return found;
}

/** What the API is sent: empty fields left out, the phone in full. */
export function memberDetails(values: MemberValues): MemberDetails {
  return {
    name: values.name.trim(),
    dateOfBirth: values.dateOfBirth.trim() || undefined,
    phone: values.phone ? `+91${values.phone}` : undefined,
    email: values.email.trim() || undefined,
    address: values.address.trim() || undefined,
  };
}

/**
 * A member's name and details, shared by adding or editing a member and by
 * filing a scan under someone new, so the two can't drift into asking for
 * different things. Age is shown as the date of birth is typed, never asked.
 */
export function MemberFields({
  values,
  errors,
  onChange,
  autoFocusName = false,
  ageHint,
}: {
  values: MemberValues;
  errors: MemberErrors;
  onChange: (values: MemberValues) => void;
  autoFocusName?: boolean;
  /** Said under the date of birth while it is empty, e.g. the age a bill printed. */
  ageHint?: string;
}) {
  const { t } = useTranslation();
  const set = (key: keyof MemberValues) => (value: string) =>
    onChange({ ...values, [key]: key === 'phone' ? nationalDigits(value) : value });
  const age = values.dateOfBirth ? ageOn(values.dateOfBirth.trim(), new Date()) : undefined;

  return (
    <>
      <TextField
        label={t('members.nameLabel')}
        placeholder={t('members.namePlaceholder')}
        value={values.name}
        onChangeText={set('name')}
        error={errors.name}
        autoCapitalize="words"
        autoFocus={autoFocusName}
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
      ) : ageHint && !values.dateOfBirth.trim() ? (
        <Text variant="small" color="ink2">
          {ageHint}
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
    </>
  );
}
