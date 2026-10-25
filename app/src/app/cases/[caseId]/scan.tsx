import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/auth/auth-context';
import { AppHeader } from '@/components/app-header';
import { Button } from '@/components/button';
import { PagePreview } from '@/components/page-preview';
import { ReadingBill } from '@/components/reading-bill';
import { Text } from '@/components/text';
import { useToast } from '@/components/toast';
import { Gutter } from '@/constants/theme';
import { checkFirstBill, uploadBill } from '@/data/cases-api';
import { takeStagedPages } from '@/data/page-inbox';
import { scanErrorMessage } from '@/data/scan-errors';
import { MAX_PAGES, usePagePicker } from '@/hooks/use-page-picker';
import { usePalette } from '@/hooks/use-palette';

/**
 * Capturing the bill.
 *
 * A bill is often several pages, and families photograph them one at a time at
 * the counter, so pages collect here and go up together. Nothing is sent until
 * "Check bill" — a half-photographed bill would be audited as if items were
 * missing.
 *
 * Reached three ways. From a case, it adds a day's bill to it. From a
 * member, or from the home screen, with the first page already picked there,
 * the bill opens its own case: everything a case needs is printed on the page
 * the family is already holding. From a member the case is theirs; from the
 * home screen the family is asked whose it is once the bill is read, with
 * the name printed on it offered.
 */
export default function ScanScreen() {
  const { caseId, memberId } = useLocalSearchParams<{ caseId?: string; memberId?: string }>();
  const { t } = useTranslation();
  const palette = usePalette();
  const toast = useToast();
  const { state } = useAuth();
  // Whatever the home screen picked on the way here, taken once as this
  // screen's starting state rather than set after it has drawn empty.
  const picker = usePagePicker(takeStagedPages);
  const [checking, setChecking] = useState(false);
  // How much of the upload has gone. The waiting screen's first step is the
  // one thing on it that is measured rather than estimated.
  const [sent, setSent] = useState(0);

  if (state.status !== 'signedIn') return null;
  const token = state.token;
  const { pages, preparing } = picker;
  const ready = pages.length > 0 || preparing;

  const checkBill = async () => {
    if (pages.length === 0) {
      toast(t('scan.needPage'));
      return;
    }
    setSent(0);
    setChecking(true);
    try {
      const bill = caseId
        ? await uploadBill(token, caseId, pages, undefined, setSent)
        : await checkFirstBill(token, pages, memberId, setSent);
      // Scanned before choosing anyone: ask whose it is, then the report.
      router.replace(
        caseId || memberId
          ? { pathname: '/bills/[billId]', params: { billId: bill.id } }
          : { pathname: '/file', params: { kind: 'bill', id: bill.caseId, billId: bill.id } },
      );
    } catch (error) {
      // The pages stay, so a retry doesn't mean photographing them again.
      setChecking(false);
      toast(scanErrorMessage(t, error, MAX_PAGES));
    }
  };

  if (checking) {
    return (
      <SafeAreaView
        style={[styles.fill, { backgroundColor: palette.app }]}
        edges={['top', 'left', 'right', 'bottom']}>
        <ReadingBill sent={sent} pages={pages.length} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView
      style={[styles.fill, { backgroundColor: palette.app }]}
      edges={['top', 'left', 'right', 'bottom']}>
      <AppHeader title={caseId ? t('scan.title') : t('scan.titleFirst')} showBack />

      <ScrollView contentContainerStyle={styles.body}>
        <Text color="ink2" style={styles.hint}>
          {pages.length > 0
            ? t('scan.hintCaptured', { count: pages.length })
            : caseId
              ? t('scan.hintEmpty')
              : t('scan.hintFirstEmpty')}
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

      {/* Once there is a page to check, checking it is what the family came
          to do: it leads, and photographing another drops to a secondary. */}
      <View style={styles.controls}>
        {ready ? (
          <Button icon="check" label={t('scan.checkBill')} onPress={checkBill} loading={preparing} />
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
  body: { paddingHorizontal: Gutter, paddingBottom: 18 },
  hint: { textAlign: 'center', marginTop: 14 },
  thumbs: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    justifyContent: 'center',
    marginTop: 12,
  },
  controls: { padding: Gutter, gap: 10 },
});
