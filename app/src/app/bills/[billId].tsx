import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { Modal, Pressable, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { AppHeader, IconButton } from '@/components/app-header';
import { Banner } from '@/components/banner';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { Chip } from '@/components/chip';
import { Icon } from '@/components/icon';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useToast } from '@/components/toast';
import { Gutter, Radius } from '@/constants/theme';
import { readBill, readCase, setFlagStatus } from '@/data/cases-api';
import { flagAmountLine, flagCopy, flagTag } from '@/data/flag-copy';
import type { Bill, Case, Flag, LineItem } from '@/data/types';
import { useAsync } from '@/hooks/use-async';
import { usePalette } from '@/hooks/use-palette';
import { formatDayMonth } from '@/i18n/dates';
import { formatINR } from '@/lib/format';

/**
 * The bill report: what was flagged, and what the bill looks like with the
 * flags marked on it.
 *
 * Two views of one thing. The flag list is for acting on; the marked bill is
 * for holding up at the counter beside the hospital's own copy.
 */
export default function BillReportScreen() {
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
        <Text color="ink2">{t('common.loadFailed')}</Text>
        <Button variant="secondary" label={t('common.tryAgain')} onPress={loaded.reload} />
      </Screen>
    );
  }

  return (
    <Report
      bill={loaded.value.bill}
      item={loaded.value.item}
      token={token ?? ''}
      onChanged={loaded.reload}
    />
  );
}

function Report({
  bill,
  item,
  token,
  onChanged,
}: {
  bill: Bill;
  item: Case;
  token: string;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [view, setView] = useState<'flags' | 'bill'>('flags');
  const [openFlag, setOpenFlag] = useState<Flag | null>(null);

  const open = bill.flags.filter((flag) => flag.status === 'open');
  const recovered = bill.flags
    .filter((flag) => flag.status === 'corrected')
    .reduce((sum, flag) => sum + flag.excess, 0);
  const overcharge = open.reduce((sum, flag) => sum + flag.excess, 0);
  const items = new Map(bill.lineItems.map((row) => [row.id, row]));

  return (
    <Screen header={<AppHeader title={t('report.title', { day: bill.day })} showBack />}>
      <Summary open={open.length} total={bill.lineItems.length} overcharge={overcharge} recovered={recovered} />

      {bill.flags.length > 0 ? (
        <Segmented
          options={[
            { value: 'flags', label: t('report.tabFlags') },
            { value: 'bill', label: t('report.tabBill') },
          ]}
          value={view}
          onChange={setView}
        />
      ) : null}

      {bill.flags.length === 0 ? (
        <Banner tone="green" icon="check" title={t('report.nothingFlagged')} body={t('report.nothingFlaggedBody')} />
      ) : view === 'flags' ? (
        <FlagList bill={bill} items={items} onOpen={setOpenFlag} />
      ) : (
        <MarkedBill bill={bill} item={item} onOpen={setOpenFlag} />
      )}

      <Text variant="faint" style={styles.fine}>
        {t('report.fine')}
      </Text>

      <View style={styles.cta}>
        {open.length > 0 ? (
          <Button
            label={t('report.askBillingDesk')}
            onPress={() => router.push({ pathname: '/bills/[billId]/ask', params: { billId: bill.id } })}
          />
        ) : (
          <Button variant="secondary" label={t('report.backToCase')} onPress={() => router.back()} />
        )}
      </View>

      <FlagSheet
        flag={openFlag}
        item={openFlag?.lineItemId ? items.get(openFlag.lineItemId) : undefined}
        token={token}
        onClose={() => setOpenFlag(null)}
        onChanged={onChanged}
      />
    </Screen>
  );
}

function Summary({
  open,
  total,
  overcharge,
  recovered,
}: {
  open: number;
  total: number;
  overcharge: number;
  recovered: number;
}) {
  const { t } = useTranslation();
  const palette = usePalette();
  const settled = open === 0;

  return (
    <View style={[styles.summary, { backgroundColor: palette.card, borderColor: palette.line }]}>
      <Text variant="small" color="ink2">
        {settled ? t('report.allSettled') : t('report.possibleOvercharge')}
      </Text>
      <Text variant="big" weight="bold" color={settled ? 'green' : 'ink'}>
        {formatINR(settled ? recovered : overcharge)}
      </Text>
      <Text color="ink2">
        {settled ? t('report.recoveredOnBill') : t('report.needALook', { count: open, total })}
      </Text>
    </View>
  );
}

function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  const palette = usePalette();
  return (
    <View style={[styles.segmented, { backgroundColor: palette.soft }]} accessibilityRole="tablist">
      {options.map((option) => {
        const on = option.value === value;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="tab"
            accessibilityState={{ selected: on }}
            onPress={() => onChange(option.value)}
            style={[styles.segment, on && { backgroundColor: palette.card, borderColor: palette.line }]}>
            <Text weight="semibold" color={on ? 'ink' : 'ink2'}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function FlagList({
  bill,
  items,
  onOpen,
}: {
  bill: Bill;
  items: Map<string, LineItem>;
  onOpen: (flag: Flag) => void;
}) {
  const { t } = useTranslation();
  const palette = usePalette();
  const flagged = new Set(bill.flags.map((flag) => flag.lineItemId));
  const untouched = bill.lineItems.filter((row) => !flagged.has(row.id)).length;

  return (
    <View>
      {bill.flags.map((flag) => {
        const item = flag.lineItemId ? items.get(flag.lineItemId) : undefined;
        const copy = flagCopy(t, flag, item);
        const amountLine = flagAmountLine(t, flag);
        return (
          <Pressable
            key={flag.id}
            accessibilityRole="button"
            onPress={() => onOpen(flag)}
            style={[
              styles.flag,
              { backgroundColor: palette.card, borderColor: palette.line },
              flag.status !== 'open' && styles.resolved,
            ]}>
            <Marker position={flag.position} level={flag.level} />
            <View style={styles.flagBody}>
              <Text weight="bold">{item?.name ?? ''}</Text>
              <Text color="ink2" variant="small">
                {copy.short}
              </Text>
              {amountLine ? <Text variant="faint">{amountLine}</Text> : null}
            </View>
            <Chip tone={chipTone(flag)} label={flagTag(t, flag)} />
          </Pressable>
        );
      })}
      {untouched > 0 ? (
        <View style={styles.okRow}>
          <Icon name="check" size={18} color="green" />
          <Text color="green">{t('report.othersInRange', { count: untouched })}</Text>
        </View>
      ) : null}
    </View>
  );
}

function MarkedBill({
  bill,
  item,
  onOpen,
}: {
  bill: Bill;
  item: Case;
  onOpen: (flag: Flag) => void;
}) {
  const { t } = useTranslation();
  const palette = usePalette();
  const byItem = new Map(bill.flags.filter((f) => f.lineItemId).map((f) => [f.lineItemId as string, f]));

  return (
    <Card style={styles.paper}>
      <View style={[styles.billHead, { borderBottomColor: palette.line }]}>
        <Text weight="bold">{item.hospital.name}</Text>
        <Text variant="faint">{t('report.billHeader', { date: formatDayMonth(t, bill.date) })}</Text>
        <Text variant="faint">
          {t('report.patientLine', { ip: item.patient.ipNumber, patient: item.patient.name })}
        </Text>
      </View>

      {bill.lineItems.map((row) => {
        const flag = byItem.get(row.id);
        const content = (
          <>
            <View style={styles.billName}>
              <Text variant="small">{row.name}</Text>
              {row.detail ? <Text variant="faint">{row.detail}</Text> : null}
            </View>
            <Text variant="small" style={flag?.status === 'corrected' && styles.struck}>
              {formatINR(row.amount)}
            </Text>
          </>
        );
        if (!flag) {
          return (
            <View key={row.id} style={[styles.billRow, { borderBottomColor: palette.line }]}>
              {content}
            </View>
          );
        }
        return (
          <Pressable
            key={row.id}
            accessibilityRole="button"
            accessibilityLabel={`${flag.position}: ${row.name}`}
            onPress={() => onOpen(flag)}
            style={[
              styles.billRow,
              { borderBottomColor: palette.line },
              flag.status === 'open' && { backgroundColor: palette.marigoldSoft },
            ]}>
            {content}
          </Pressable>
        );
      })}

      <View style={styles.billTotal}>
        <Text weight="bold">{t('report.billTotal')}</Text>
        <Text weight="bold">{formatINR(bill.total)}</Text>
      </View>
    </Card>
  );
}

function Marker({ position, level }: { position: number; level: Flag['level'] }) {
  const palette = usePalette();
  const color = level === 'red' ? palette.red : palette.marigoldInk;
  return (
    <View style={[styles.marker, { borderColor: color }]}>
      <Text variant="faint" weight="bold" style={{ color }}>
        {position}
      </Text>
    </View>
  );
}

function chipTone(flag: Flag): 'red' | 'amber' | 'green' | 'grey' {
  if (flag.status === 'corrected') return 'green';
  if (flag.status === 'explained') return 'grey';
  return flag.level === 'red' ? 'red' : 'amber';
}

/** The detail sheet: why this was flagged, what to ask, and what happened. */
function FlagSheet({
  flag,
  item,
  token,
  onClose,
  onChanged,
}: {
  flag: Flag | null;
  item?: LineItem;
  token: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const palette = usePalette();
  const toast = useToast();
  const [saving, setSaving] = useState(false);

  if (!flag) return null;
  const copy = flagCopy(t, flag, item);

  const mark = async (status: Flag['status']) => {
    setSaving(true);
    try {
      await setFlagStatus(token, flag.id, status);
      onClose();
      onChanged();
      toast(
        status === 'corrected'
          ? t('report.toastCorrected', { amount: formatINR(flag.excess) })
          : status === 'explained'
            ? t('report.toastExplained')
            : t('report.toastReopened'),
      );
    } catch {
      toast(t('auth.errors.network'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.scrim} accessibilityLabel={t('common.back')} onPress={onClose} />
      <View style={[styles.sheet, { backgroundColor: palette.app }]}>
        <View style={styles.sheetTop}>
          <Chip tone={chipTone(flag)} label={flagTag(t, flag)} />
          <IconButton icon="x" label={t('common.back')} onPress={onClose} />
        </View>

        <Text variant="title" weight="bold" accessibilityRole="header">
          {item?.name ?? ''}
        </Text>

        <View style={styles.numbers}>
          <Figure label={t('flags.billed')} value={formatINR(flag.billed)} />
          <Figure label={copy.referenceLabel} value={formatINR(flag.referenceAmount)} />
          <Figure label={t('flags.difference')} value={formatINR(flag.excess)} />
        </View>

        <Text weight="semibold" style={styles.sheetHeading}>
          {t('report.whyFlagged')}
        </Text>
        <Text color="ink2">{copy.why}</Text>

        <Text weight="semibold" style={styles.sheetHeading}>
          {t('report.whatToAsk')}
        </Text>
        <Text color="ink2">{copy.ask}</Text>

        <Text weight="semibold" style={styles.sheetHeading}>
          {t('report.whatHappened')}
        </Text>
        {flag.status === 'open' ? (
          <View style={styles.sheetButtons}>
            <Button label={t('report.markCorrected')} loading={saving} onPress={() => mark('corrected')} />
            <Button
              variant="secondary"
              label={t('report.markExplained')}
              loading={saving}
              onPress={() => mark('explained')}
            />
          </View>
        ) : (
          <View style={styles.sheetButtons}>
            <Text color="ink2">
              {flag.status === 'corrected' ? t('report.correctedNote') : t('report.explainedNote')}
            </Text>
            <Button variant="secondary" label={t('report.reopen')} loading={saving} onPress={() => mark('open')} />
          </View>
        )}
      </View>
    </Modal>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  const palette = usePalette();
  return (
    <View style={[styles.figure, { backgroundColor: palette.card, borderColor: palette.line }]}>
      <Text variant="faint" color="ink2">
        {label}
      </Text>
      <Text weight="bold">{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  summary: { borderWidth: 1, borderRadius: Radius.card, padding: 16, marginBottom: 14, alignItems: 'flex-start' },
  segmented: { flexDirection: 'row', borderRadius: 12, padding: 3, gap: 3, marginBottom: 14 },
  segment: { flex: 1, paddingVertical: 7, borderRadius: 9, alignItems: 'center', borderWidth: 0 },
  flag: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'flex-start',
    borderWidth: 1,
    borderRadius: Radius.card,
    padding: 13,
    marginBottom: 10,
  },
  resolved: { opacity: 0.72 },
  flagBody: { flex: 1, gap: 1 },
  marker: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  okRow: { flexDirection: 'row', gap: 10, alignItems: 'center', paddingVertical: 6 },
  paper: { padding: 14 },
  billHead: { borderBottomWidth: 1, paddingBottom: 10, marginBottom: 4 },
  billRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    gap: 10,
    paddingVertical: 6,
    paddingHorizontal: 4,
    borderBottomWidth: 1,
    borderRadius: 2,
  },
  billName: { flex: 1 },
  struck: { textDecorationLine: 'line-through' },
  billTotal: { flexDirection: 'row', justifyContent: 'space-between', paddingTop: 10, paddingHorizontal: 4 },
  fine: { marginTop: 14, lineHeight: 18 },
  cta: { marginTop: 18, gap: 10 },
  scrim: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(14,16,32,0.45)' },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '88%',
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    padding: Gutter,
    paddingBottom: 24,
  },
  sheetTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  numbers: { flexDirection: 'row', gap: 8, marginVertical: 12 },
  figure: { flex: 1, borderWidth: 1, borderRadius: 12, padding: 8 },
  sheetHeading: { marginTop: 14, marginBottom: 2 },
  sheetButtons: { gap: 8, marginTop: 8 },
});
