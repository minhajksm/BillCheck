import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { useAuth } from '@/auth/auth-context';
import { AppHeader } from '@/components/app-header';
import { Button } from '@/components/button';
import { CaseFields, validateCase, type CaseFormErrors, type CaseFormValues } from '@/components/case-fields';
import { FormScreen } from '@/components/form-screen';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useToast } from '@/components/toast';
import { deleteCase, readCase, updateCase } from '@/data/cases-api';
import type { Case } from '@/data/types';
import { useAsync } from '@/hooks/use-async';

/** Correcting the admission details, and ending the case altogether. */
export default function EditCaseScreen() {
  const { caseId } = useLocalSearchParams<{ caseId: string }>();
  const { t } = useTranslation();
  const { state } = useAuth();
  const token = state.status === 'signedIn' ? state.token : null;

  const load = useCallback(async () => {
    if (!token) throw new Error('signed out');
    return readCase(token, caseId);
  }, [token, caseId]);
  const loaded = useAsync(load);

  if (loaded.status === 'loading') {
    return (
      <Screen header={<AppHeader title="" showBack />}>
        <Text color="ink2">{t('common.loading')}</Text>
      </Screen>
    );
  }
  if (loaded.status === 'error' || !token) {
    return (
      <Screen header={<AppHeader title="" showBack />}>
        <Text>{t('case.notFound')}</Text>
        <Button variant="secondary" label={t('common.goHome')} onPress={() => router.replace('/')} />
      </Screen>
    );
  }
  return <EditCase item={loaded.value} token={token} />;
}

function EditCase({ item, token }: { item: Case; token: string }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [values, setValues] = useState<CaseFormValues>({
    title: item.title,
    hospitalName: item.hospital.name,
    hospitalArea: item.hospital.area,
    patientName: item.patient.name,
    ipNumber: item.patient.ipNumber,
    bed: item.patient.bed,
    admittedOn: item.admittedOn ?? '',
    dischargedOn: item.closedOn ?? '',
  });
  const [errors, setErrors] = useState<CaseFormErrors>({});
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const save = async () => {
    const found = validateCase(values, t);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSaving(true);
    try {
      // Emptying the discharge date says the patient is still in hospital.
      await updateCase(token, item.id, {
        ...values,
        bed: values.bed.trim() || undefined,
        dischargedOn: values.dischargedOn.trim() || undefined,
      });
      router.back();
    } catch {
      setSaving(false);
      toast(t('editCase.failed'));
    }
  };

  const remove = async () => {
    setDeleting(true);
    try {
      await deleteCase(token, item.id);
      router.replace('/');
    } catch {
      setDeleting(false);
      setConfirming(false);
      toast(t('editCase.deleteFailed'));
    }
  };

  return (
    <FormScreen
      title={t('editCase.title')}
      subtitle={t('editCase.subtitle')}
      footer={<Button label={t('editCase.save')} loading={saving} onPress={save} />}>
      <CaseFields
        values={values}
        errors={errors}
        onChange={(key, value) => setValues((current) => ({ ...current, [key]: value }))}
      />

      {item.isOwner ? (
        <View style={styles.danger}>
          {confirming ? (
            // Spelled out rather than hidden behind a dialog: this takes the
            // bills away from everyone on the case, and it cannot be undone.
            <>
              <Text color="ink2">{t('editCase.confirmDelete', { name: item.title })}</Text>
              <Button
                variant="danger"
                label={t('editCase.confirmDeleteAction')}
                loading={deleting}
                onPress={remove}
              />
              <Button variant="secondary" label={t('common.cancel')} onPress={() => setConfirming(false)} />
            </>
          ) : (
            <Button variant="secondary" label={t('editCase.delete')} onPress={() => setConfirming(true)} />
          )}
        </View>
      ) : null}
    </FormScreen>
  );
}

const styles = StyleSheet.create({
  danger: { marginTop: 28, gap: 10 },
});
