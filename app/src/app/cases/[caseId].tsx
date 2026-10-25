import type { TFunction } from 'i18next';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback } from 'react';
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
import { Radius } from '@/constants/theme';
import { useAuth } from '@/auth/auth-context';
import { billStatus, caseStatus, latestBill, runningTotal, type CaseStatus } from '@/data/case-status';
import { readCase } from '@/data/cases-api';
import type { Case, DailyBill } from '@/data/types';
import { useAsync } from '@/hooks/use-async';
import { usePalette } from '@/hooks/use-palette';
import { formatDate, formatDayMonth } from '@/i18n/dates';
import { formatINR } from '@/lib/format';

export default function CaseDashboardScreen() {
  const { caseId } = useLocalSearchParams<{ caseId: string }>();
  const { t } = useTranslation();
  const { state } = useAuth();
  const token = state.status === 'signedIn' ? state.token : null;

  const load = useCallback(async () => {
    if (!token) throw new Error('signed out');
    return readCase(token, caseId);
  }, [token, caseId]);
  const loaded = useAsync(load);

  // A bill added or a question answered should show the moment we come back.
  const { reload } = loaded;
  useFocusEffect(useCallback(() => void reload(), [reload]));

  if (loaded.status === 'loading') {
    return (
      <Screen header={<AppHeader title="" showBack />}>
        <Text color="ink2">{t('common.loading')}</Text>
      </Screen>
    );
  }
  if (loaded.status === 'error') {
    return (
      <Screen header={<AppHeader title="" showBack />}>
        <Text style={styles.notFound}>{t('case.notFound')}</Text>
        <Button variant="secondary" label={t('common.goHome')} onPress={() => router.replace('/')} />
      </Screen>
    );
  }
  return <CaseDashboard item={loaded.value} />;
}

function CaseDashboard({ item }: { item: Case }) {
  const { t } = useTranslation();
  const palette = usePalette();
  const status = caseStatus(item);
  const latest = latestBill(item);
  // Bills are newest first on screen, as in the prototype.
  const bills = [...item.bills].reverse();

  const header = (
    <AppHeader
      title={item.title}
      showBack
      right={
        <IconButton
          icon="edit-2"
          label={t('case.editDetails')}
          onPress={() => router.push({ pathname: '/cases/[caseId]/edit', params: { caseId: item.id } })}
        />
      }
    />
  );

  return (
    <Screen header={header}>
      <Text color="ink2">{t('common.place', { name: item.hospital.name, area: item.hospital.area })}</Text>
      <Text variant="faint">{t('case.patientLine', item.patient)}</Text>
      <Text variant="faint" style={styles.patient}>
        {stayLine(t, item)}
      </Text>

      {/* The one detail the checks need and a bill often doesn't print.
          Nothing is assumed in its place, so it is asked for here, where the
          rest of the admission details are corrected. */}
      {item.admittedOn === undefined ? (
        <Pressable
          accessibilityRole="button"
          onPress={() => router.push({ pathname: '/cases/[caseId]/edit', params: { caseId: item.id } })}
          style={[styles.needsDate, { backgroundColor: palette.soft, borderColor: palette.line }]}>
          <Icon name="calendar" size={18} color="ink2" />
          <View style={styles.needsDateText}>
            <Text variant="small" weight="semibold">
              {t('case.admissionDateMissing')}
            </Text>
            <Text variant="faint">{t('case.admissionDateWhy')}</Text>
          </View>
        </Pressable>
      ) : null}

      <Whose item={item} />

      <View style={styles.metrics}>
        <Metric label={t('case.runningTotal')} value={formatINR(runningTotal(item))} />
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

      <StatusBanner status={status} onAsk={() => openLatestReport(item)} />

      <Text variant="small" weight="semibold" color="ink2" style={styles.sectionTitle}>
        {t('case.dailyBills')}
      </Text>
      <Card style={styles.list}>
        {bills.map((bill, i) => (
          <BillRow key={bill.id} bill={bill} first={i === 0} />
        ))}
        {bills.length === 0 ? (
          <View style={styles.emptyBills}>
            <Text color="ink2">{t('case.noBillsYet')}</Text>
          </View>
        ) : null}
      </Card>

      <View style={styles.cta}>
        <MainAction status={status} item={item} />
      </View>
    </Screen>
  );
}

/**
 * Whose admission this is, and the way to them. Family follow the person, so
 * inviting someone happens there, not here.
 */
function Whose({ item }: { item: Case }) {
  const { t } = useTranslation();
  const { member } = item;
  if (!member) {
    return (
      <Button
        variant="secondary"
        icon="user-check"
        label={t('file.titleBill')}
        onPress={() => router.push({ pathname: '/file', params: { kind: 'bill', id: item.id } })}
      />
    );
  }
  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => router.push({ pathname: '/members/[memberId]', params: { memberId: member.id } })}
      style={styles.followers}>
      <Avatar name={member.name} />
      <Text variant="small" weight="semibold" color="indigoInk" style={styles.followersLabel}>
        {member.name}
      </Text>
    </Pressable>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  const palette = usePalette();
  return (
    <View
      style={[
        styles.metric,
        styles.metricHalf,
        { backgroundColor: palette.card, borderColor: palette.line },
      ]}>
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
      return (
        <Banner
          tone="green"
          icon="check"
          title={t('case.bannerSettledTitle')}
          body={t('case.bannerSettledBody')}
        />
      );
    case 'closed':
      return null;
  }
}

/**
 * When the stay began and ended, as far as anyone has said. A missing
 * admission date is asked for just below, so it isn't repeated here.
 */
function stayLine(t: TFunction, item: Case): string {
  const parts = [
    item.admittedOn ? t('case.admittedOn', { date: formatDate(t, item.admittedOn) }) : null,
    item.closedOn
      ? t('case.dischargedOn', { date: formatDate(t, item.closedOn) })
      : item.admittedOn
        ? t('case.stillIn')
        : null,
  ];
  return parts.filter((part): part is string => part !== null).join(' · ');
}

/** Opens the newest bill that still has open questions, else the newest. */
function openLatestReport(item: Case) {
  const withOpen = [...item.bills].reverse().find((bill) => bill.openFlagCount > 0);
  const bill = withOpen ?? latestBill(item);
  if (bill) router.push({ pathname: '/bills/[billId]', params: { billId: bill.id } });
}

function scan(item: Case) {
  router.push({ pathname: '/cases/[caseId]/scan', params: { caseId: item.id } });
}

function MainAction({ status, item }: { status: CaseStatus; item: Case }) {
  const { t } = useTranslation();

  // A closed admission takes no more bills.
  if (status.kind === 'closed') return null;

  switch (status.kind) {
    case 'toAsk':
      // Asking about one bill and adding the next are both live during a
      // stay, and a family does them in either order. This used to be the ask
      // button alone, so the way to add a bill disappeared the moment one had
      // an open question — which is the usual state — and the only way on was
      // to start another case for the same admission.
      return (
        <>
          <Button label={t('case.askBillingDesk')} onPress={() => openLatestReport(item)} />
          <Button
            variant="secondary"
            icon="camera"
            label={t('case.addAnotherBill')}
            onPress={() => scan(item)}
          />
        </>
      );
    case 'upToDate':
      return (
        <Button
          variant="secondary"
          icon="camera"
          label={t('case.addAnotherBill')}
          onPress={() => scan(item)}
        />
      );
  }
}

function BillRow({ bill, first }: { bill: DailyBill; first: boolean }) {
  const { t } = useTranslation();
  const palette = usePalette();
  const status = billStatus(bill);

  const title = t('case.billOn', { date: formatDayMonth(t, bill.date) });
  const meta = t('case.billMeta', { count: bill.itemCount, amount: formatINR(bill.total) });
  const onPress = () => router.push({ pathname: '/bills/[billId]', params: { billId: bill.id } });

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
  needsDate: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderWidth: 1,
    borderRadius: Radius.card,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginTop: 12,
  },
  needsDateText: { flex: 1 },
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
  emptyBills: { padding: 16 },
  cta: { marginTop: 18, gap: 10 },
  headerActions: { flexDirection: 'row', gap: 4 },
});
