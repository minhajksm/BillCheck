import { Redirect, router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/auth/auth-context';
import { AppHeader } from '@/components/app-header';
import { Button } from '@/components/button';
import { PagePreview } from '@/components/page-preview';
import { Text } from '@/components/text';
import { useToast } from '@/components/toast';
import { Gutter } from '@/constants/theme';
import { uploadLabReport } from '@/data/lab-api';
import { takeStagedPages } from '@/data/page-inbox';
import { scanErrorMessage } from '@/data/scan-errors';
import { MAX_PAGES, usePagePicker } from '@/hooks/use-page-picker';
import { usePalette } from '@/hooks/use-palette';

/**
 * Capturing a lab report.
 *
 * The bill scan screen's shape -- pages collect, nothing goes until the family
 * says so -- because a lab report is often several pages too, and explaining
 * half of one would leave results out without saying so.
 */
export default function NewLabReportScreen() {
  const { t } = useTranslation();
  const palette = usePalette();
  const toast = useToast();
  const { state } = useAuth();
  // Whatever the home screen picked on the way here.
  const picker = usePagePicker(takeStagedPages);
  const [reading, setReading] = useState(false);

  if (state.status !== 'signedIn') return null;
  // Nothing is read before they have agreed to it.
  if (!state.user.lab_consent) return <Redirect href="/lab/consent" />;

  const token = state.token;
  const { pages, preparing } = picker;
  const ready = pages.length > 0 || preparing;

  const explain = async () => {
    if (pages.length === 0) return;
    setReading(true);
    try {
      const report = await uploadLabReport(token, pages);
      router.replace({ pathname: '/lab/[reportId]', params: { reportId: report.id } });
    } catch (error) {
      // The pages stay, so a retry doesn't mean photographing them again.
      setReading(false);
      toast(scanErrorMessage(t, error, MAX_PAGES));
    }
  };

  if (reading) {
    return (
      <SafeAreaView
        style={[styles.fill, styles.waiting, { backgroundColor: palette.app }]}
        edges={['top', 'left', 'right', 'bottom']}>
        <ActivityIndicator size="large" color={palette.indigo} />
        <Text variant="title" weight="bold" style={styles.waitingTitle}>
          {t('lab.reading')}
        </Text>
        <Text color="ink2" style={styles.centred}>
          {t('lab.readingBody')}
        </Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView
      style={[styles.fill, { backgroundColor: palette.app }]}
      edges={['top', 'left', 'right', 'bottom']}>
      <AppHeader title={t('lab.newTitle')} showBack />

      <ScrollView contentContainerStyle={styles.body}>
        <Text color="ink2" style={styles.hint}>
          {pages.length > 0 ? t('lab.hintCaptured', { count: pages.length }) : t('lab.hintEmpty')}
        </Text>
        <View style={styles.thumbs}>
          {pages.map((page, index) => (
            <PagePreview
              key={`${page.uri}-${index}`}
              page={page}
              number={index + 1}
              alone={pages.length === 1}
              onRemove={() => picker.removePage(index)}
            />
          ))}
        </View>
      </ScrollView>

      <View style={styles.controls}>
        {ready ? (
          <Button icon="file-text" label={t('lab.explain')} onPress={explain} loading={preparing} />
        ) : null}
        <Button
          variant={ready ? 'secondary' : 'primary'}
          icon="camera"
          label={t('scan.takePhoto')}
          onPress={() => void picker.takePhoto()}
        />
        <Button
          variant="secondary"
          icon="upload"
          label={t('scan.choosePages')}
          onPress={() => void picker.choosePages()}
        />
        <Button
          variant="secondary"
          icon="file-text"
          label={t('scan.choosePdf')}
          onPress={() => void picker.choosePdf()}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  waiting: { alignItems: 'center', justifyContent: 'center', paddingHorizontal: Gutter, gap: 8 },
  waitingTitle: { marginTop: 12 },
  centred: { textAlign: 'center' },
  body: { paddingHorizontal: Gutter, paddingBottom: 18 },
  hint: { textAlign: 'center', marginTop: 14 },
  thumbs: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, justifyContent: 'center', marginTop: 12 },
  controls: { padding: Gutter, gap: 10 },
});
