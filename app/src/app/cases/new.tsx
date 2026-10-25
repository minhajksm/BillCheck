import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/button';
import { CaseFields, validateCase, type CaseFormErrors, type CaseFormValues } from '@/components/case-fields';
import { FormScreen } from '@/components/form-screen';
import { useToast } from '@/components/toast';
import { createCase } from '@/data/cases-api';

/**
 * Opening a case by hand: one admission of one member, the details printed on
 * the admission slip. For a family setting one up before the first bill.
 */
export default function NewCaseScreen() {
  const { memberId } = useLocalSearchParams<{ memberId: string }>();
  const { t } = useTranslation();
  const toast = useToast();
  const { state } = useAuth();
  const [values, setValues] = useState<CaseFormValues>({
    title: '',
    hospitalName: '',
    hospitalArea: '',
    patientName: '',
    ipNumber: '',
    bed: '',
    admittedOn: new Date().toISOString().slice(0, 10),
    dischargedOn: '',
  });
  const [errors, setErrors] = useState<CaseFormErrors>({});
  const [saving, setSaving] = useState(false);

  if (state.status !== 'signedIn') return null;
  const token = state.token;

  const submit = async () => {
    const found = validateCase(values, t);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSaving(true);
    try {
      const created = await createCase(token, memberId, {
        ...values,
        bed: values.bed.trim() || undefined,
        dischargedOn: values.dischargedOn.trim() || undefined,
      });
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
      <CaseFields
        values={values}
        errors={errors}
        onChange={(key, value) => setValues((current) => ({ ...current, [key]: value }))}
      />
    </FormScreen>
  );
}
