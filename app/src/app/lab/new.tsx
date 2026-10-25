import { Redirect, router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/auth/auth-context';
import { AppHeader } from '@/components/app-header';
import { AddPagesButton } from '@/components/add-pages';
import { Banner } from '@/components/banner';
import { Button } from '@/components/button';
import { PagePreview } from '@/components/page-preview';
import { Text } from '@/components/text';
import { Gutter } from '@/constants/theme';
import { uploadLabReport } from '@/data/lab-api';
import { takeStagedPages } from '@/data/page-inbox';
import { scanErrorMessage, scanErrorTitle } from '@/data/scan-errors';
import { MAX_PAGES, usePagePicker } from '@/hooks/use-page-picker';
import { usePalette } from '@/hooks/use-palette';

/**
 * Capturing a lab report.
 *
 * The bill scan screen's shape -- pages collect, nothing goes until the family
 * says so -- because a lab report is often several pages too, and explaining
 * half of one would leave results out without saying so.
 *
 * From a member, the report is theirs. From the home screen, the family is
 * asked whose it is once it is read, as with a bill.
 */
export default function NewLabReportScreen() {
  const { memberId } = useLocalSearchParams<{ memberId?: string }>();
  const { t } = useTranslation();
  const palette = usePalette();
  const { state } = useAuth();
  // Whatever the home screen picked on the way here.
  const picker = usePagePicker(takeStagedPages);
  const [reading, setReading] = useState(false);
  // Why the last read failed, shown until the pages change.
  const [failure, setFailure] = useState<{ title: string; body: string } | null>(null);

  if (state.status !== 'signedIn') return null;
  // Nothing is read before they have agreed to it.
  if (!state.user.lab_consent) {
    return <Redirect href={{ pathname: '/lab/consent', params: memberId ? { memberId } : {} }} />;
  }

  const token = state.token;
  const { pages, preparing } = picker;
  const ready = pages.length > 0 || preparing;

  const explain = async () => {
    if (pages.length === 0) return;
    setFailure(null);
    setReading(true);
    try {
      const report = await uploadLabReport(token, pages, memberId);
      router.replace(
        memberId
          ? { pathname: '/lab/[reportId]', params: { reportId: report.id } }
          : { pathname: '/file', params: { kind: 'lab', id: report.id } },
      );
    } catch (error) {
      // The pages stay, so a retry doesn't mean photographing them again.
      setReading(false);
      setFailure({ title: scanErrorTitle(t, error, 'lab'), body: scanErrorMessage(t, error, MAX_PAGES) });
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
        {/* Stays until the pages change, unlike a toast: a family reading
            "this looks like a scan report" needs time to read where it goes. */}
        {failure ? (
          <View style={styles.failure}>
            <Banner tone="amber" icon="alert-circle" title={failure.title} body={failure.body} />
          </View>
        ) : null}
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
              onRemove={() => {
                setFailure(null);
                picker.removePage(index);
              }}
            />
          ))}
        </View>
      </ScrollView>

      <View style={styles.controls}>
        {ready ? (
          <Button icon="file-text" label={t('lab.explain')} onPress={explain} loading={preparing} />
        ) : null}
        <AddPagesButton
          variant={ready ? 'secondary' : 'primary'}
          label={pages.length > 0 ? t('scan.addAnotherPage') : t('scan.addPages')}
          picker={picker}
          onPicked={() => setFailure(null)}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  failure: { marginTop: 14 },
  waiting: { alignItems: 'center', justifyContent: 'center', paddingHorizontal: Gutter, gap: 8 },
  waitingTitle: { marginTop: 12 },
  centred: { textAlign: 'center' },
  body: { paddingHorizontal: Gutter, paddingBottom: 18 },
  hint: { textAlign: 'center', marginTop: 14 },
  thumbs: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, justifyContent: 'center', marginTop: 12 },
  controls: { padding: Gutter, gap: 10 },
});
