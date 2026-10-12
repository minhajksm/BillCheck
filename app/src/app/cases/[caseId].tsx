import { router, useLocalSearchParams } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { AppHeader, IconButton } from '@/components/app-header';
import { Avatar } from '@/components/avatar';
import { Banner } from '@/components/banner';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { Chip } from '@/components/chip';
import { Icon } from '@/components/icon';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useToast } from '@/components/toast';
import { billStatus, caseStatus, latestBill, runningTotal, type CaseStatus } from '@/data/case-status';
import { findCase } from '@/data/placeholder';
import type { Case, DailyBill } from '@/data/types';
import { usePalette } from '@/hooks/use-palette';
import { formatDayMonth } from '@/i18n/dates';
import { formatINR } from '@/lib/format';

export default function CaseDashboardScreen() {
  const { caseId } = useLocalSearchParams<{ caseId: string }>();
  const item = findCase(caseId);
  const { t } = useTranslation();

  if (!item) {
    return (
      <Screen header={<AppHeader title="" showBack />}>
        <Text style={styles.notFound}>{t('case.notFound')}</Text>
        <Button variant="secondary" label={t('common.goHome')} onPress={() => router.replace('/')} />
      </Screen>
    );
  }
  return <CaseDashboard item={item} />;
}

function CaseDashboard({ item }: { item: Case }) {
  const { t } = useTranslation();
  const palette = usePalette();
  const toast = useToast();
  const status = caseStatus(item);
  const latest = latestBill(item);
  // Bills are newest first on screen, as in the prototype.
  const bills = [...item.bills].reverse();

  const header = (
    <AppHeader
      title={item.title}
      showBack
      right={<IconButton icon="users" label={t('case.inviteFamily')} onPress={() => toast(t('case.inviteSoon'))} />}
    />
  );

  return (
    <Screen header={header}>
      <Text color="ink2">{t('common.place', { name: item.hospital.name, area: item.hospital.area })}</Text>
      <Text variant="faint" style={styles.patient}>
        {t('case.patientLine', item.patient)}
      </Text>

      <Followers item={item} />

      <View style={styles.metrics}>
        <Metric label={t('case.runningTotal', { day: latest?.day ?? item.dayOfStay })} value={formatINR(runningTotal(item))} />
        <Metric label={t('case.sinceYesterday')} value={`+${formatINR(latest?.total ?? 0)}`} />
      </View>
      {item.recoveredAmount > 0 ? (
        <View style={[styles.metric, styles.recovered, { backgroundColor: palette.greenSoft }]}>
          <Text variant="faint" color="green">
            {t('case.recoveredSoFar')}
          </Text>
          <Text variant="metric" weight="bold" color="green">
            {formatINR(item.recoveredAmount)}
          </Text>
        </View>
      ) : null}

      <StatusBanner status={status} onAsk={() => toast(t('case.reportSoon'))} />

      <Text variant="small" weight="semibold" color="ink2" style={styles.sectionTitle}>
        {t('case.dailyBills')}
      </Text>
      <Card style={styles.list}>
        {bills.map((bill, i) => (
          <BillRow key={bill.id} bill={bill} first={i === 0} />
        ))}
      </Card>

      <View style={styles.cta}>
        <MainAction status={status} />
      </View>
    </Screen>
  );
}

function Followers({ item }: { item: Case }) {
  const { t } = useTranslation();
  const you = item.members.find((m) => m.isYou);
  const others = item.members.filter((m) => !m.isYou);
  const youName = you?.name.split(' ')[0] ?? '';

  let label: string;
  if (others.length === 0) label = t('case.followersYouOnly');
  else if (others.length === 1) label = t('case.followersPair', { you: youName, other: others[0].name.split(' ')[0] });
  else label = t('case.followersMany', { you: youName, count: others.length });

  // The prototype shows up to two overlapping avatars.
  const shown = [you, ...others].filter((m) => m !== undefined).slice(0, 2);

  return (
    <View style={styles.followers}>
      {shown.map((m, i) => (
        <Avatar key={m.id} name={m.name} tone={i === 0 ? 'indigo' : 'green'} style={i > 0 && styles.overlap} />
      ))}
      <Text variant="faint" style={styles.followersLabel}>
        {label}
      </Text>
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  const palette = usePalette();
  return (
    <View style={[styles.metric, styles.metricHalf, { backgroundColor: palette.card, borderColor: palette.line }]}>
      <Text variant="faint" color="ink2">
        {label}
      </Text>
      <Text variant="metric" weight="bold">
        {value}
      </Text>
    </View>
  );
}

function StatusBanner({ status, onAsk }: { status: CaseStatus; onAsk: () => void }) {
  const { t } = useTranslation();
  switch (status.kind) {
    case 'needsTodaysBill':
      return <Banner tone="indigo" icon="file-text" title={t('case.bannerNotAddedTitle')} body={t('case.bannerNotAddedBody')} />;
    case 'toAsk':
      return (
        <Banner
          tone="amber"
          icon="alert-triangle"
          title={t('case.bannerToAskTitle', { count: status.openFlagCount })}
          body={t('case.bannerToAskBody')}
          onPress={onAsk}
        />
      );
    case 'upToDate':
      return <Banner tone="green" icon="check" title={t('case.bannerSettledTitle')} body={t('case.bannerSettledBody')} />;
    case 'closed':
      return null;
  }
}

function MainAction({ status }: { status: CaseStatus }) {
  const { t } = useTranslation();
  const toast = useToast();
  switch (status.kind) {
    case 'needsTodaysBill':
      return <Button icon="camera" label={t('case.addTodaysBill')} onPress={() => toast(t('case.scanSoon'))} />;
    case 'toAsk':
      return <Button label={t('case.askBillingDesk')} onPress={() => toast(t('case.askSoon'))} />;
    case 'upToDate':
      return (
        <Button
          variant="secondary"
          icon="camera"
          label={t('case.addTomorrowsBill')}
          onPress={() => toast(t('case.tomorrowToast'))}
        />
      );
    case 'closed':
      return null;
  }
}

function BillRow({ bill, first }: { bill: DailyBill; first: boolean }) {
  const { t } = useTranslation();
  const palette = usePalette();
  const toast = useToast();
  const status = billStatus(bill);

  const title = bill.day === 1 ? t('case.billAdmission', { day: bill.day }) : t('case.billInterim', { day: bill.day });
  const meta = t('case.billMeta', {
    date: formatDayMonth(t, bill.date),
    count: bill.itemCount,
    amount: formatINR(bill.total),
  });
  const onPress = () =>
    status === 'looksFine'
      ? toast(t('case.billAllInRange', { day: bill.day, count: bill.itemCount }))
      : toast(t('case.reportSoon'));

  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [
        styles.row,
        !first && { borderTopWidth: 1, borderTopColor: palette.line },
        pressed && { backgroundColor: palette.soft },
      ]}>
      <Icon name="file-text" color="ink3" />
      <View style={styles.rowText}>
        <Text weight="bold">{title}</Text>
        <Text variant="faint">{meta}</Text>
      </View>
      {status === 'toAsk' ? (
        <Chip tone="amber" label={t('caseStatus.toAsk', { count: bill.openFlagCount })} />
      ) : (
        <Chip tone="green" label={t(status === 'settled' ? 'case.billSettled' : 'case.billLooksFine')} />
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  notFound: { marginVertical: 16 },
  patient: { marginBottom: 12 },
  followers: { flexDirection: 'row', alignItems: 'center', marginBottom: 14 },
  overlap: { marginLeft: -8 },
  followersLabel: { marginLeft: 8, flex: 1 },
  metrics: { flexDirection: 'row', gap: 10 },
  metric: { borderRadius: 16, paddingHorizontal: 14, paddingVertical: 12 },
  metricHalf: { flex: 1, borderWidth: 1 },
  recovered: { marginTop: 10 },
  sectionTitle: { marginTop: 22, marginBottom: 8 },
  list: { overflow: 'hidden' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 13 },
  rowText: { flex: 1 },
  cta: { marginTop: 18, gap: 10 },
});
