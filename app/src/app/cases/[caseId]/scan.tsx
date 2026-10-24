import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, View } from 'react-native';
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
import { checkFirstBill, uploadBill, type ScannedPage } from '@/data/cases-api';
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
            <Page
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

/**
 * One captured page.
 *
 * The photograph itself, not a numbered box: a family has to be able to see
 * that the page is square in frame and the small print is legible before
 * spending a minute of waiting on it. A single page gets the full width,
 * because a thumbnail the size of a stamp proves nothing and left most of
 * the screen empty. A PDF has no picture to show, so it shows its name.
 */
function Page({
  page,
  number,
  alone,
  onRemove,
}: {
  page: ScannedPage;
  number: number;
  alone: boolean;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const palette = usePalette();

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={t('scan.remove', { number })}
      onPress={onRemove}
      style={[
        styles.thumb,
        alone && styles.thumbAlone,
        { backgroundColor: palette.soft, borderColor: palette.line },
      ]}>
      {page.type.startsWith('image/') ? (
        // `contain`, not `cover`: a cropped preview would hide the very edge
        // a family is checking is in frame.
        <Image source={{ uri: page.uri }} style={styles.thumbImage} resizeMode="contain" />
      ) : (
        <View style={styles.thumbFile}>
          <Icon name="file-text" size={28} color="ink2" />
          <Text variant="faint" numberOfLines={2} style={styles.thumbName}>
            {page.name}
          </Text>
        </View>
      )}
      <View
        style={[styles.badge, styles.number, { backgroundColor: palette.app, borderColor: palette.line }]}>
        <Text variant="faint" weight="bold" color="ink2">
          {number}
        </Text>
      </View>
      <View
        style={[styles.badge, styles.remove, { backgroundColor: palette.app, borderColor: palette.line }]}>
        <Icon name="x" size={14} color="ink2" />
      </View>
    </Pressable>
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
  thumb: {
    width: '48%',
    // About the shape of a bill page, so one of them fills the screen the way
    // the page it shows does.
    aspectRatio: 3 / 4,
    borderRadius: Radius.card,
    borderWidth: 1,
    overflow: 'hidden',
  },
  thumbAlone: { width: '100%' },
  thumbImage: { width: '100%', height: '100%' },
  thumbFile: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 8, padding: 12 },
  thumbName: { textAlign: 'center' },
  badge: {
    position: 'absolute',
    minWidth: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  number: { top: 8, left: 8 },
  remove: { top: 8, right: 8 },
  controls: { padding: Gutter, gap: 10 },
});
