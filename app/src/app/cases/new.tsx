import { router } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/button';
import { FormScreen } from '@/components/form-screen';
import { TextField } from '@/components/text-field';
import { useToast } from '@/components/toast';
import { createCase } from '@/data/cases-api';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Opening a case: one admission, the details printed on the admission slip. */
export default function NewCaseScreen() {
  const { t } = useTranslation();
  const toast = useToast();
  const { state } = useAuth();
  const [values, setValues] = useState({
    title: '',
    hospitalName: '',
    hospitalArea: '',
    patientName: '',
    ipNumber: '',
    bed: '',
    admittedOn: new Date().toISOString().slice(0, 10),
  });
  const [errors, setErrors] = useState<Partial<Record<keyof typeof values, string>>>({});
  const [saving, setSaving] = useState(false);

  if (state.status !== 'signedIn') return null;
  const token = state.token;

  const set = (key: keyof typeof values) => (value: string) =>
    setValues((current) => ({ ...current, [key]: value }));

  const submit = async () => {
    const required: (keyof typeof values)[] = [
      'title',
      'hospitalName',
      'hospitalArea',
      'patientName',
      'ipNumber',
    ];
    const found: Partial<Record<keyof typeof values, string>> = {};
    for (const key of required) {
      if (!values[key].trim()) found[key] = t('newCase.required');
    }
    if (!ISO_DATE.test(values.admittedOn)) found.admittedOn = t('newCase.badDate');
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSaving(true);
    try {
      const created = await createCase(token, { ...values, bed: values.bed.trim() || undefined });
      router.replace({ pathname: '/cases/[caseId]', params: { caseId: created.id } });
    } catch {
      setSaving(false);
      toast(t('newCase.failed'));
    }
  };

  return (
    <FormScreen
      title={t('newCase.title')}
      subtitle={t('newCase.subtitle')}
      footer={<Button label={t('newCase.create')} loading={saving} onPress={submit} />}>
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
    </FormScreen>
  );
}
