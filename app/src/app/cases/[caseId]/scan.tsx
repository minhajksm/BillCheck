import * as ImagePicker from 'expo-image-picker';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/auth/auth-context';
import { AppHeader } from '@/components/app-header';
import { Button } from '@/components/button';
import { Icon } from '@/components/icon';
import { Text } from '@/components/text';
import { useToast } from '@/components/toast';
import { Gutter, Radius } from '@/constants/theme';
import { uploadBill, type ScannedPage } from '@/data/cases-api';
import { preparePage } from '@/data/prepare-page';
import { usePalette } from '@/hooks/use-palette';

const MAX_PAGES = 12;

/**
 * Capturing the bill.
 *
 * A bill is often several pages, and families photograph them one at a time at
 * the counter, so pages collect here and go up together. Nothing is sent until
 * "Check bill" — a half-photographed bill would be audited as if items were
 * missing.
 */
export default function ScanScreen() {
  const { caseId } = useLocalSearchParams<{ caseId: string }>();
  const { t } = useTranslation();
  const palette = usePalette();
  const toast = useToast();
  const { state } = useAuth();
  const [pages, setPages] = useState<ScannedPage[]>([]);
  const [checking, setChecking] = useState(false);
  const [preparing, setPreparing] = useState(false);

  if (state.status !== 'signedIn') return null;
  const token = state.token;

  const addAssets = async (assets: ImagePicker.ImagePickerAsset[]) => {
    setPreparing(true);
    try {
      // Scaled down to what the reader uses, so a many-page bill uploads fast
      // and stays under the request limit.
      const added = await Promise.all(
        assets.map((asset, index) => {
          const pageNumber = pages.length + index + 1;
          return preparePage(asset, pageNumber, {
            uri: asset.uri,
            name: asset.fileName ?? `page-${pageNumber}.jpg`,
            type: asset.mimeType ?? 'image/jpeg',
          });
        }),
      );
      setPages((current) => [...current, ...added].slice(0, MAX_PAGES));
    } finally {
      setPreparing(false);
    }
  };

  const takePhoto = async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      toast(t('scan.cameraDenied'));
      return;
    }
    // Full quality here: the page is compressed once, when it is scaled down.
    const result = await ImagePicker.launchCameraAsync({ quality: 1 });
    if (!result.canceled) await addAssets(result.assets);
  };

  const choosePages = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      quality: 1,
      allowsMultipleSelection: true,
      selectionLimit: MAX_PAGES - pages.length,
    });
    if (!result.canceled) await addAssets(result.assets);
  };

  const checkBill = async () => {
    if (pages.length === 0) {
      toast(t('scan.needPage'));
      return;
    }
    setChecking(true);
    try {
      const bill = await uploadBill(token, caseId, pages);
      router.replace({ pathname: '/bills/[billId]', params: { billId: bill.id } });
    } catch {
      setChecking(false);
      toast(t('scan.failed'));
    }
  };

  if (checking) return <Checking />;

  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: palette.app }]} edges={['top', 'left', 'right']}>
      <AppHeader title={t('scan.title')} showBack />

      <ScrollView contentContainerStyle={styles.body}>
        <Text color="ink2" style={styles.hint}>
          {pages.length === 0 ? t('scan.hintEmpty') : t('scan.hintCaptured', { count: pages.length })}
        </Text>

        <View style={styles.thumbs}>
          {pages.map((page, index) => (
            <Pressable
              key={`${page.uri}-${index}`}
              accessibilityRole="button"
              accessibilityLabel={t('scan.remove', { number: index + 1 })}
              onPress={() => setPages((current) => current.filter((_, i) => i !== index))}
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
        <Button icon="camera" label={t('scan.takePhoto')} onPress={takePhoto} />
        <Button variant="secondary" icon="upload" label={t('scan.choosePages')} onPress={choosePages} />
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

/** What the family sees while the bill is read and checked. */
function Checking() {
  const { t } = useTranslation();
  const palette = usePalette();
  const steps = [t('scan.step1'), t('scan.step2'), t('scan.step3')];

  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: palette.app }]} edges={['top', 'left', 'right']}>
      <View style={styles.checking}>
        <View style={[styles.checkingIcon, { backgroundColor: palette.indigoSoft }]}>
          <Icon name="file-text" size={34} color="indigoInk" />
        </View>
        <Text variant="title" weight="bold" accessibilityRole="header">
          {t('scan.takesSeconds')}
        </Text>
        <View style={styles.steps} accessibilityRole="progressbar">
          {steps.map((step) => (
            <View key={step} style={styles.step}>
              <View style={[styles.dot, { borderColor: palette.line }]} />
              <Text color="ink2">{step}</Text>
            </View>
          ))}
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  body: { paddingHorizontal: Gutter, paddingBottom: 18 },
  hint: { textAlign: 'center', marginTop: 18 },
  thumbs: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, justifyContent: 'center', marginTop: 18 },
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
  checking: { flex: 1, alignItems: 'center', paddingTop: 70, paddingHorizontal: Gutter },
  checkingIcon: {
    width: 72,
    height: 72,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 18,
  },
  steps: { marginTop: 28, gap: 14, width: '100%', maxWidth: 300 },
  step: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  dot: { width: 24, height: 24, borderRadius: 12, borderWidth: 2 },
});
