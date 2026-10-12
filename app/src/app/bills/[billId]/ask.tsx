import * as Clipboard from 'expo-clipboard';
import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, Share, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { AppHeader } from '@/components/app-header';
import { Banner } from '@/components/banner';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { Icon } from '@/components/icon';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useToast } from '@/components/toast';
import { Radius } from '@/constants/theme';
import { readBill, readCase } from '@/data/cases-api';
import { composeMessage } from '@/data/message';
import type { Bill, Case } from '@/data/types';
import { useAsync } from '@/hooks/use-async';
import { usePalette } from '@/hooks/use-palette';
import { SUPPORTED_LANGUAGES, type Language } from '@/i18n';
import { formatINR } from '@/lib/format';

const LANGUAGE_NAMES: Record<Language, string> = { en: 'English', hi: 'हिंदी', mr: 'मराठी' };

/**
 * The message to the billing desk.
 *
 * The family picks the language they'll actually be speaking at the counter,
 * which may not be the one the app is in — so the picker here changes the
 * message, not the app.
 */
export default function AskScreen() {
  const { billId } = useLocalSearchParams<{ billId: string }>();
  const { t } = useTranslation();
  const { state } = useAuth();
  const token = state.status === 'signedIn' ? state.token : null;

  const load = useCallback(async () => {
    if (!token) throw new Error('signed out');
    const bill = await readBill(token, billId);
    return { bill, item: await readCase(token, bill.caseId) };
  }, [token, billId]);

  const loaded = useAsync(load);

  if (loaded.status !== 'ready') {
    return (
      <Screen header={<AppHeader title={t('ask.title')} showBack />}>
        <Text color="ink2">{loaded.status === 'loading' ? t('common.loading') : t('common.loadFailed')}</Text>
      </Screen>
    );
  }
  return <Ask bill={loaded.value.bill} item={loaded.value.item} />;
}

function Ask({ bill, item }: { bill: Bill; item: Case }) {
  const { t, i18n } = useTranslation();
  const toast = useToast();
  const palette = usePalette();
  const [language, setLanguage] = useState<Language>(i18n.language as Language);
  const [expanded, setExpanded] = useState<number | null>(null);

  // The message is composed in the chosen language, which may differ from the
  // app's. `getFixedT` gives that language's copy without switching the app.
  const message = composeMessage(i18n.getFixedT(language), item, bill);
  const recovered = bill.flags
    .filter((flag) => flag.status === 'corrected')
    .reduce((sum, flag) => sum + flag.excess, 0);

  const copy = async () => {
    if (!message) return;
    try {
      await Clipboard.setStringAsync(message);
      toast(t('ask.copied'));
    } catch {
      toast(t('ask.copyFailed'));
    }
  };

  const share = async () => {
    if (!message) return;
    try {
      await Share.share({ message });
    } catch {
      await copy();
    }
  };

  const steps = [
    { title: t('ask.esc1Title'), body: t('ask.esc1Body') },
    { title: t('ask.esc2Title'), body: t('ask.esc2Body') },
    { title: t('ask.esc3Title'), body: t('ask.esc3Body') },
  ];

  return (
    <Screen header={<AppHeader title={t('ask.title')} showBack />}>
      <Text color="ink2" style={styles.intro}>
        {t('ask.intro')}
      </Text>

      <View style={[styles.segmented, { backgroundColor: palette.soft }]} accessibilityRole="tablist">
        {SUPPORTED_LANGUAGES.map((code) => {
          const on = code === language;
          return (
            <Pressable
              key={code}
              accessibilityRole="tab"
              accessibilityState={{ selected: on }}
              accessibilityLabel={`${t('ask.language')}: ${LANGUAGE_NAMES[code]}`}
              onPress={() => setLanguage(code)}
              style={[styles.segment, on && { backgroundColor: palette.card }]}>
              <Text weight="semibold" color={on ? 'ink' : 'ink2'}>
                {LANGUAGE_NAMES[code]}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {message ? (
        <>
          <Card style={styles.message}>
            <Text selectable>{message}</Text>
          </Card>
          <View style={styles.actions}>
            <Button variant="secondary" icon="copy" label={t('ask.copy')} onPress={copy} />
            <Button icon="share-2" label={t('ask.share')} onPress={share} />
          </View>
        </>
      ) : (
        <Banner tone="green" icon="check" title={t('ask.nothingLeft')} body={t('ask.nothingLeftBody')} />
      )}

      <Text variant="small" weight="semibold" color="ink2" style={styles.sectionTitle}>
        {t('ask.ifNotResolved')}
      </Text>
      <Card>
        {steps.map((step, index) => (
          <View key={step.title} style={index > 0 && { borderTopWidth: 1, borderTopColor: palette.line }}>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ expanded: expanded === index }}
              onPress={() => setExpanded(expanded === index ? null : index)}
              style={styles.step}>
              <Text variant="faint" weight="semibold">
                {index + 1}
              </Text>
              <Text weight="medium" style={styles.stepTitle}>
                {step.title}
              </Text>
              <Icon name={expanded === index ? 'chevron-up' : 'chevron-down'} size={18} color="ink3" />
            </Pressable>
            {expanded === index ? (
              <Text color="ink2" variant="small" style={styles.stepBody}>
                {step.body}
              </Text>
            ) : null}
          </View>
        ))}
      </Card>

      <View style={[styles.recovered, { backgroundColor: palette.greenSoft }]}>
        <Text color="green">{t('ask.recoveredSoFar')}</Text>
        <Text color="green" weight="bold">
          {formatINR(recovered)}
        </Text>
      </View>

      <Button variant="secondary" label={t('ask.updateWhatHappened')} onPress={() => router.back()} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  intro: { marginBottom: 14 },
  segmented: { flexDirection: 'row', borderRadius: 12, padding: 3, gap: 3, marginBottom: 14 },
  segment: { flex: 1, paddingVertical: 7, borderRadius: 9, alignItems: 'center' },
  message: { padding: 16, marginBottom: 10 },
  actions: { flexDirection: 'row', gap: 10 },
  sectionTitle: { marginTop: 22, marginBottom: 8 },
  step: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 13 },
  stepTitle: { flex: 1 },
  stepBody: { paddingHorizontal: 16, paddingBottom: 14, paddingLeft: 40 },
  recovered: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 14,
    borderRadius: Radius.card,
    marginVertical: 18,
  },
});
