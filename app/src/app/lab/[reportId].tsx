import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useState, type ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { AppHeader } from '@/components/app-header';
import { Banner } from '@/components/banner';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { Chip, type ChipTone } from '@/components/chip';
import { Screen } from '@/components/screen';
import { Segmented } from '@/components/segmented';
import { Text } from '@/components/text';
import { useToast } from '@/components/toast';
import {
  deleteLabReport,
  readLabReport,
  type LabLanguage,
  type LabReport,
  type LabStatus,
} from '@/data/lab-api';
import { useAsync } from '@/hooks/use-async';

/** Each language in its own script, the same whatever the app is set to. */
const LANGUAGE_NAMES: Record<LabLanguage, string> = { en: 'English', hi: 'हिंदी' };

/**
 * Against the printed range only. Outside it is amber -- worth asking, as on
 * a bill -- never red: red would read as a verdict, and this is a question
 * for the doctor.
 */
const STATUS_TONE: Record<LabStatus, ChipTone> = {
  low: 'amber',
  high: 'amber',
  in_range: 'green',
  no_range: 'grey',
};

const STATUS_LABEL = {
  low: 'lab.statusLow',
  high: 'lab.statusHigh',
  in_range: 'lab.statusInRange',
  no_range: 'lab.statusNoRange',
} as const;

export default function LabReportScreen() {
  const { reportId } = useLocalSearchParams<{ reportId: string }>();
  const { t } = useTranslation();
  const { state } = useAuth();
  const token = state.status === 'signedIn' ? state.token : null;

  const load = useCallback(async () => {
    if (!token) throw new Error('signed out');
    return readLabReport(token, reportId);
  }, [token, reportId]);
  const loaded = useAsync(load);

  const header = <AppHeader title={t('lab.title')} showBack />;
  if (loaded.status === 'loading') {
    return (
      <Screen header={header}>
        <Text color="ink2">{t('common.loading')}</Text>
      </Screen>
    );
  }
  if (loaded.status === 'error' || !token) {
    return (
      <Screen header={header}>
        <Text>{t('lab.notFound')}</Text>
        <Button variant="secondary" label={t('common.goHome')} onPress={() => router.replace('/')} />
      </Screen>
    );
  }
  return <Explained report={loaded.value} token={token} header={header} />;
}

/**
 * A report, explained.
 *
 * The figures are the report's own, word for word and number for number, in
 * either language: only the explanation around them changes. Every result is
 * set against the range the report printed beside it, and the screen ends
 * where the explanation has to -- with what to ask the doctor, and a plain
 * line saying this is not a diagnosis.
 */
function Explained({ report, token, header }: { report: LabReport; token: string; header: ReactNode }) {
  const { t, i18n } = useTranslation();
  const toast = useToast();
  // Hindi for a Hindi phone; English otherwise, Marathi included, since the
  // reader writes the two. Either is one tap away.
  const [language, setLanguage] = useState<LabLanguage>(i18n.language === 'hi' ? 'hi' : 'en');
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const remove = async () => {
    setDeleting(true);
    try {
      await deleteLabReport(token, report.id);
      toast(t('lab.deleted'));
      router.replace('/');
    } catch {
      setDeleting(false);
      toast(t('lab.deleteFailed'));
    }
  };

  const about = [report.patientName, report.reportDate].filter(Boolean).join(' · ');

  return (
    <Screen header={header}>
      <Text variant="hello" weight="bold">
        {report.labName || t('lab.unnamedLab')}
      </Text>
      {about ? <Text color="ink2">{about}</Text> : null}

      {report.urgent ? (
        <View style={styles.section}>
          <Banner tone="amber" icon="alert-circle" title={t('lab.urgentTitle')} body={t('lab.urgentBody')} />
        </View>
      ) : null}

      <View style={styles.section}>
        <Segmented
          options={(['en', 'hi'] as const).map((value) => ({ value, label: LANGUAGE_NAMES[value] }))}
          value={language}
          onChange={setLanguage}
        />
      </View>

      <Card style={styles.card}>
        <Text variant="small" weight="semibold" color="ink2" accessibilityRole="header">
          {t('lab.summary')}
        </Text>
        <Text>{report.summary[language]}</Text>
      </Card>

      <Text variant="small" weight="semibold" color="ink2" style={styles.heading} accessibilityRole="header">
        {t('lab.results')}
      </Text>
      {report.tests.map((test, index) => (
        <Card key={`${test.name}-${index}`} style={styles.test}>
          <View style={styles.testTop}>
            <Text weight="bold" style={styles.testName}>
              {test.name}
            </Text>
            <Chip tone={STATUS_TONE[test.status]} label={t(STATUS_LABEL[test.status])} />
          </View>
          <Text variant="metric" weight="bold">
            {test.unit ? `${test.value} ${test.unit}` : test.value}
          </Text>
          {test.range ? (
            <Text variant="small" color="ink2">
              {t('lab.printedRange', { range: test.range })}
            </Text>
          ) : null}
          <Text style={styles.explanation}>{test.explanation[language]}</Text>
        </Card>
      ))}

      {report.questions[language].length > 0 ? (
        <Card style={styles.card}>
          <Text variant="small" weight="semibold" color="ink2" accessibilityRole="header">
            {t('lab.askDoctor')}
          </Text>
          {report.questions[language].map((question, index) => (
            <Text key={index}>{`${index + 1}. ${question}`}</Text>
          ))}
        </Card>
      ) : null}

      <Text variant="faint" style={styles.fine}>
        {t('lab.notDiagnosis')}
      </Text>

      <View style={styles.delete}>
        {confirming ? (
          <>
            <Text color="ink2">{t('lab.confirmDelete')}</Text>
            <Button
              variant="danger"
              label={t('lab.confirmDeleteAction')}
              loading={deleting}
              onPress={remove}
            />
            <Button variant="secondary" label={t('common.cancel')} onPress={() => setConfirming(false)} />
          </>
        ) : (
          <Button
            variant="danger"
            icon="trash-2"
            label={t('lab.delete')}
            onPress={() => setConfirming(true)}
          />
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { marginTop: 14 },
  card: { padding: 16, gap: 6, marginTop: 4 },
  heading: { marginTop: 22, marginBottom: 8 },
  test: { padding: 16, gap: 4, marginBottom: 10 },
  testTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 },
  testName: { flex: 1 },
  explanation: { marginTop: 6 },
  fine: { marginTop: 18, lineHeight: 18 },
  delete: { marginTop: 22, gap: 10 },
});
