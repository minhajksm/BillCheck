import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import { TextField } from '@/components/text-field';

/** The admission details, as printed on the admission slip. */
export type CaseFormValues = {
  title: string;
  hospitalName: string;
  hospitalArea: string;
  patientName: string;
  ipNumber: string;
  bed: string;
  admittedOn: string;
};

export type CaseFormErrors = Partial<Record<keyof CaseFormValues, string>>;

export const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Everything but the bed has to be filled in; the date has to be a date. */
export function validateCase(values: CaseFormValues, t: TFunction): CaseFormErrors {
  const required: (keyof CaseFormValues)[] = [
    'title',
    'hospitalName',
    'hospitalArea',
    'patientName',
    'ipNumber',
  ];
  const found: CaseFormErrors = {};
  for (const key of required) {
    if (!values[key].trim()) found[key] = t('newCase.required');
  }
  if (!ISO_DATE.test(values.admittedOn)) found.admittedOn = t('newCase.badDate');
  return found;
}

/**
 * The admission details form, shared by starting a case and correcting one.
 *
 * One list of fields: a field added here reaches both screens, and neither can
 * drift into asking for something the other doesn't.
 */
export function CaseFields({
  values,
  errors,
  onChange,
}: {
  values: CaseFormValues;
  errors: CaseFormErrors;
  onChange: (key: keyof CaseFormValues, value: string) => void;
}) {
  const { t } = useTranslation();
  const set = (key: keyof CaseFormValues) => (value: string) => onChange(key, value);

  return (
    <>
      <TextField
        label={t('newCase.caseTitle')}
        placeholder={t('newCase.caseTitlePlaceholder')}
        value={values.title}
        onChangeText={set('title')}
        error={errors.title}
      />
      <TextField
        label={t('newCase.hospital')}
        placeholder={t('newCase.hospitalPlaceholder')}
        value={values.hospitalName}
        onChangeText={set('hospitalName')}
        error={errors.hospitalName}
      />
      <TextField
        label={t('newCase.area')}
        placeholder={t('newCase.areaPlaceholder')}
        value={values.hospitalArea}
        onChangeText={set('hospitalArea')}
        error={errors.hospitalArea}
      />
      <TextField
        label={t('newCase.patient')}
        placeholder={t('newCase.patientPlaceholder')}
        value={values.patientName}
        onChangeText={set('patientName')}
        error={errors.patientName}
      />
      <TextField
        label={t('newCase.ipNumber')}
        placeholder={t('newCase.ipPlaceholder')}
        value={values.ipNumber}
        onChangeText={set('ipNumber')}
        error={errors.ipNumber}
      />
      <TextField label={t('newCase.bed')} value={values.bed} onChangeText={set('bed')} />
      <TextField
        label={t('newCase.admittedOn')}
        placeholder={t('newCase.admittedPlaceholder')}
        value={values.admittedOn}
        onChangeText={set('admittedOn')}
        error={errors.admittedOn}
        autoCapitalize="none"
      />
    </>
  );
}
