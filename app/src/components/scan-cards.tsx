import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { Radius } from '@/constants/theme';
import type { ScannedPage } from '@/data/cases-api';
import { stagePages } from '@/data/page-inbox';
import { usePagePicker } from '@/hooks/use-page-picker';
import { usePalette } from '@/hooks/use-palette';

import { Button } from './button';
import { Text } from './text';

/**
 * The way in to checking a bill.
 *
 * A family arrives holding a bill, not wanting to fill in a form about an
 * admission they are living through. Everything a case needs -- the hospital,
 * the patient, the IP number, the admission date -- is printed on the page in
 * their hand, so the bill opens the case.
 *
 * From the home screen there is no member yet: the bill is read first and the
 * family then says whose it is, with the name printed on it offered. From a
 * member's screen, it is theirs from the start.
 *
 * The picker opens here, on the tap, so nothing stands between wanting a bill
 * checked and photographing it. The pages go to the scan screen, where the
 * rest of a multi-page bill is added.
 */
export function CheckABill({ memberId, compact = false }: { memberId?: string; compact?: boolean }) {
  const { t } = useTranslation();
  const palette = usePalette();
  const picker = usePagePicker();

  const pick = async (choose: () => Promise<ScannedPage[]>) => {
    const pages = await choose();
    // Cancelled: they are still where they were.
    if (pages.length === 0) return;
    stagePages(pages);
    router.push(memberId ? { pathname: '/scan', params: { memberId } } : '/scan');
  };

  return (
    <View
      style={[
        styles.card,
        compact && styles.compact,
        { backgroundColor: palette.indigoSoft, borderColor: palette.line },
      ]}>
      {compact ? null : (
        <>
          <Text weight="bold" style={styles.title}>
            {t('home.checkBillTitle')}
          </Text>
          <Text color="ink2">{t('home.checkBillBody')}</Text>
        </>
      )}
      <View style={[styles.buttons, compact && styles.buttonsCompact]}>
        <Button
          icon="camera"
          label={t('home.photographBill')}
          loading={picker.preparing}
          onPress={() => void pick(picker.takePhoto)}
        />
        <Button
          variant="secondary"
          icon="upload"
          label={t('home.uploadBill')}
          onPress={() => void pick(picker.choosePages)}
        />
      </View>
    </View>
  );
}

/**
 * The other page a family is handed in hospital.
 *
 * Under the bill, not beside it: the bill is what this app is for, and this
 * is the second thing it does. Its own consent comes first -- the one given
 * at sign-up covers bills -- so until it is given, either button goes there.
 */
export function CheckALabReport({
  consented,
  memberId,
  compact = false,
}: {
  consented: boolean;
  memberId?: string;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const palette = usePalette();
  const picker = usePagePicker();
  const params = memberId ? { memberId } : {};

  const pick = async (choose: () => Promise<ScannedPage[]>) => {
    if (!consented) {
      router.push({ pathname: '/lab/consent', params });
      return;
    }
    const pages = await choose();
    if (pages.length === 0) return;
    stagePages(pages);
    router.push({ pathname: '/lab/new', params });
  };

  return (
    <View
      style={[
        styles.card,
        compact && styles.compact,
        { backgroundColor: palette.card, borderColor: palette.line },
      ]}>
      {compact ? null : (
        <>
          <Text weight="bold" style={styles.title}>
            {t('lab.cardTitle')}
          </Text>
          <Text color="ink2">{t('lab.cardBody')}</Text>
        </>
      )}
      <View style={[styles.buttons, compact && styles.buttonsCompact]}>
        <Button
          variant="secondary"
          icon="camera"
          label={t('lab.photograph')}
          loading={picker.preparing}
          onPress={() => void pick(picker.takePhoto)}
        />
        <Button
          variant="secondary"
          icon="upload"
          label={t('lab.upload')}
          onPress={() => void pick(picker.choosePages)}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginTop: 18,
    borderWidth: 1,
    borderRadius: Radius.card,
    paddingHorizontal: 16,
    paddingVertical: 16,
    gap: 6,
  },
  compact: { marginTop: 10, paddingVertical: 12 },
  title: { fontSize: 16, lineHeight: 22 },
  buttons: { marginTop: 10, gap: 10 },
  buttonsCompact: { marginTop: 0 },
});
