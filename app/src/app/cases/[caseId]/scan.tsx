import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/auth/auth-context';
import { AppHeader } from '@/components/app-header';
import { Button } from '@/components/button';
import { Icon } from '@/components/icon';
import { ReadingBill } from '@/components/reading-bill';
import { Text } from '@/components/text';
import { useToast } from '@/components/toast';
import { Gutter, Radius } from '@/constants/theme';
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
 * Reached two ways. From a case, it adds a day's bill to it. From the home
 * screen, with no case and the first page already picked there, the bill opens
 * its own case: everything a case needs is printed on the page the family is
 * already holding.
 */
export default function ScanScreen() {
  const { caseId } = useLocalSearchParams<{ caseId?: string }>();
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
        : await checkFirstBill(token, pages, undefined, setSent);
      router.replace({
        pathname: '/bills/[billId]',
        params: { billId: bill.id },
      });
    } catch (error) {
      // The pages stay, so a retry doesn't mean photographing them again.
      setChecking(false);
      toast(scanErrorMessage(t, error, MAX_PAGES));
    }
  };

  if (checking) {
    return (
      <SafeAreaView style={[styles.fill, { backgroundColor: palette.app }]} edges={['top', 'left', 'right']}>
        <ReadingBill sent={sent} pages={pages.length} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: palette.app }]} edges={['top', 'left', 'right']}>
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
            <Pressable
              key={`${page.uri}-${index}`}
              accessibilityRole="button"
              accessibilityLabel={t('scan.remove', { number: index + 1 })}
              onPress={() => picker.removePage(index)}
              style={[styles.thumb, { backgroundColor: palette.soft, borderColor: palette.line }]}>
              <Text weight="semibold" color="ink2">
                {index + 1}
              </Text>
              <Icon name="x" size={14} color="ink3" />
            </Pressable>
          ))}
        </View>
      </ScrollView>

      <View style={styles.controls}>
        <Button icon="camera" label={t('scan.takePhoto')} onPress={() => void picker.takePhoto()} />
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
        {pages.length > 0 || preparing ? (
          <Button
            variant="secondary"
            icon="check"
            label={t('scan.checkBill')}
            onPress={checkBill}
            loading={preparing}
          />
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  body: { paddingHorizontal: Gutter, paddingBottom: 18 },
  hint: { textAlign: 'center', marginTop: 18 },
  thumbs: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    justifyContent: 'center',
    marginTop: 18,
  },
  thumb: {
    width: 56,
    height: 72,
    borderRadius: Radius.icon,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
  },
  controls: { padding: Gutter, gap: 10 },
});
