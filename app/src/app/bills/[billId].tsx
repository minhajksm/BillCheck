import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { Modal, Pressable, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

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
import { Gutter, Radius, type Palette } from '@/constants/theme';
import { readBill, readCase, setFlagStatus } from '@/data/cases-api';
import { flagAmountLine, flagCopy, flagTag } from '@/data/flag-copy';
import type { Bill, Case, Flag, LineCategory, LineItem } from '@/data/types';
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
    <Report bill={loaded.value.bill} item={loaded.value.item} token={token ?? ''} onChanged={loaded.reload} />
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
  // The marked bill opens first: what a family does with this screen is hold
  // it up beside the hospital's own copy, and the flags are marked on it. The
  // flag list is the worklist for afterwards.
  const [view, setView] = useState<'bill' | 'flags'>('bill');
  const [openFlag, setOpenFlag] = useState<Flag | null>(null);

  const open = bill.flags.filter((flag) => flag.status === 'open');
  const recovered = bill.flags
    .filter((flag) => flag.status === 'corrected')
    .reduce((sum, flag) => sum + flag.excess, 0);
  const overcharge = open.reduce((sum, flag) => sum + flag.excess, 0);
  const items = new Map(bill.lineItems.map((row) => [row.id, row]));

  return (
    <Screen header={<AppHeader title={t('report.title')} showBack />}>
      <ReportHeader bill={bill} item={item} overcharge={overcharge} recovered={recovered} />

      {bill.flags.length > 0 ? (
        <Segmented
          options={[
            { value: 'bill', label: t('report.tabBill') },
            { value: 'flags', label: t('report.tabSummary') },
          ]}
          value={view}
          onChange={setView}
        />
      ) : null}

      {bill.flags.length === 0 ? (
        <Banner
          tone="green"
          icon="check"
          title={t('report.nothingFlagged')}
          body={t('report.nothingFlaggedBody')}
        />
      ) : view === 'bill' ? (
        <MarkedBill bill={bill} item={item} onOpen={setOpenFlag} />
      ) : (
        <>
          <WhereItWent rows={bill.lineItems} total={bill.total} />
          <FlagList bill={bill} items={items} onOpen={setOpenFlag} />
        </>
      )}

      <Text variant="faint" style={styles.fine}>
        {t('report.fine')}
      </Text>

      <View style={styles.cta}>
        {open.length > 0 ? (
          <Button
            label={t('report.askBillingDesk')}
            onPress={() =>
              router.push({
                pathname: '/bills/[billId]/ask',
                params: { billId: bill.id },
              })
            }
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

/**
 * How a line stands, for the strip at the top. By line, not by flag: a row
 * can carry two of them, which is how "10 of 9 items need a look" happened.
 */
type Shape = { red: number; amber: number; fine: number };

function shapeOf(bill: Bill): Shape {
  const worst = new Map<string, Flag['level']>();
  for (const flag of bill.flags) {
    if (!flag.lineItemId || flag.status !== 'open') continue;
    if (flag.level === 'red' || !worst.has(flag.lineItemId)) worst.set(flag.lineItemId, flag.level);
  }
  const red = [...worst.values()].filter((level) => level === 'red').length;
  return { red, amber: worst.size - red, fine: bill.lineItems.length - worst.size };
}

/**
 * What the bill is, and what we make of it.
 *
 * The headline is the bill's own total, which is always true and is the
 * number a family already has in their head. It used to be the sum of what
 * every open flag was over its reference -- a figure the reader cannot
 * produce for the questions it raises itself, so a bill flagged six times
 * read "Possible overcharge / ₹0", which is the opposite of what it meant.
 * Money only appears below now, and only when there is a figure to show.
 */
function ReportHeader({
  bill,
  item,
  overcharge,
  recovered,
}: {
  bill: Bill;
  item: Case;
  overcharge: number;
  recovered: number;
}) {
  const { t } = useTranslation();
  const palette = usePalette();
  const shape = shapeOf(bill);
  const patient = item.patient.name
    ? t('report.patientLine', { ip: item.patient.ipNumber, patient: item.patient.name })
    : t('report.patientUnknown');

  return (
    <Card style={styles.header}>
      <View style={styles.headerTop}>
        <View style={styles.headerWho}>
          <Text weight="bold" numberOfLines={1}>
            {item.hospital.name}
          </Text>
          <Text variant="small" color="ink2">
            {patient}
          </Text>
        </View>
        <Chip tone="indigo" label={t('report.billHeader', { date: formatDayMonth(t, bill.date) })} />
      </View>

      <Text variant="big" weight="bold" style={styles.headerTotal}>
        {formatINR(bill.total)}
      </Text>
      <Text color="ink2">{t('report.billedAcross', { count: bill.lineItems.length })}</Text>

      <SeverityBar shape={shape} />

      <View style={styles.legend}>
        {shape.red > 0 ? (
          <LegendItem swatch={palette.red} color="red" label={t('report.legendRed', { count: shape.red })} />
        ) : null}
        {shape.amber > 0 ? (
          <LegendItem
            swatch={palette.marigold}
            color="marigoldInk"
            label={t('report.legendAmber', { count: shape.amber })}
          />
        ) : null}
        {shape.fine > 0 ? (
          <LegendItem
            swatch={palette.line}
            color="ink2"
            label={t('report.legendFine', { count: shape.fine })}
          />
        ) : null}
      </View>

      {/* Both, where both apply: what the hospital has already put right is
          not a reason to stop showing what is still open. */}
      {recovered > 0 || overcharge > 0 ? (
        <View style={styles.headerMoney}>
          {recovered > 0 ? (
            <Text variant="small" weight="semibold" color="green">
              {t('report.recoveredSoFar', { amount: formatINR(recovered) })}
            </Text>
          ) : null}
          {overcharge > 0 ? (
            <Text variant="small" color="ink2">
              {t('report.overReference', { amount: formatINR(overcharge) })}
            </Text>
          ) : null}
        </View>
      ) : null}
    </Card>
  );
}

/**
 * The shape of the bill in one bar: how much of it is in question at a
 * glance, before a word is read. Red and amber differ in lightness as well
 * as hue, so the split survives a colour-blind reader; the legend names the
 * counts in any case.
 */
function SeverityBar({ shape }: { shape: Shape }) {
  const { t } = useTranslation();
  const palette = usePalette();
  const total = shape.red + shape.amber + shape.fine;
  if (total === 0) return null;

  return (
    <View
      accessibilityRole="image"
      accessibilityLabel={t('report.barLabel', {
        red: shape.red,
        amber: shape.amber,
        fine: shape.fine,
      })}
      style={styles.bar}>
      {shape.red > 0 ? <View style={{ flex: shape.red, backgroundColor: palette.red }} /> : null}
      {shape.amber > 0 ? <View style={{ flex: shape.amber, backgroundColor: palette.marigold }} /> : null}
      {shape.fine > 0 ? <View style={{ flex: shape.fine, backgroundColor: palette.line }} /> : null}
    </View>
  );
}

function LegendItem({ swatch, color, label }: { swatch: string; color: keyof Palette; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendSwatch, { backgroundColor: swatch }]} />
      <Text variant="small" weight="semibold" color={color}>
        {label}
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
            style={[
              styles.segment,
              on && {
                backgroundColor: palette.card,
                borderColor: palette.line,
              },
            ]}>
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

/**
 * The categories in the order the summary strip shows them: where the money
 * usually goes first, the catch-all last. Mirrors `CATEGORY_ORDER` in
 * `api/analysis.py`, and `api/tests/test_categories.py` keeps the two in step.
 */
const CATEGORY_ORDER: LineCategory[] = [
  'room_and_nursing',
  'professional_fees',
  'procedure_or_ot',
  'investigation',
  'pharmacy_drug',
  'consumable_disposable',
  'implant_device',
  'equipment_charge',
  'non_medical',
  'unclassified',
];

/**
 * What each kind of charge came to, for the strip under the bill.
 *
 * The rows themselves stay in the bill's own order, so this is where the
 * shape of a bill shows: "the consumables came to more than the room" is a
 * question worth asking at a billing desk even where no single line was
 * flagged, and it is the same figure the reader's own structural check
 * measures. Only categories the bill actually has appear.
 */
function categoryTotals(rows: LineItem[]): { category: LineCategory; total: number }[] {
  const totals = new Map<LineCategory, number>();
  for (const row of rows) {
    // A category this build doesn't know about counts under the catch-all
    // rather than going missing: the strip has to add up to the bill.
    const category = CATEGORY_ORDER.includes(row.category) ? row.category : 'unclassified';
    totals.set(category, (totals.get(category) ?? 0) + row.amount);
  }
  return CATEGORY_ORDER.filter((category) => totals.has(category)).map((category) => ({
    category,
    total: totals.get(category) ?? 0,
  }));
}

function MarkedBill({ bill, item, onOpen }: { bill: Bill; item: Case; onOpen: (flag: Flag) => void }) {
  const { t } = useTranslation();
  const palette = usePalette();
  // A line can carry more than one flag, so the row has to stand for the
  // worst of them. Last-one-wins put an amber stripe on a line the sheet then
  // opened as a red duplicate.
  const byItem = new Map<string, Flag>();
  for (const flag of bill.flags) {
    if (!flag.lineItemId) continue;
    const shown = byItem.get(flag.lineItemId);
    if (!shown || severity(flag) < severity(shown)) byItem.set(flag.lineItemId, flag);
  }
  // The bill's own order, by the position the reader transcribed. A family
  // reads down this beside the hospital's copy, so any order but the printed
  // one makes them hunt for the line they are looking at.
  const rows = [...bill.lineItems].sort((a, b) => a.position - b.position);

  return (
    <Card style={styles.paper}>
      {rows.map((row) => {
        const flag = byItem.get(row.id);
        const content = (
          <>
            <Text variant="faint" color="ink3" style={styles.billNumber}>
              {row.position}
            </Text>
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
              // The same two colours as the legend above and the markers in
              // the flag list: red for a clear issue, amber for worth asking.
              flag.status === 'open' && {
                backgroundColor: flag.level === 'red' ? palette.redSoft : palette.marigoldSoft,
              },
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

/**
 * What each kind of charge came to.
 *
 * Above the questions rather than under the bill: it is the shape of the
 * bill, and "the medicines came to more than the room" is worth asking even
 * where no single line was flagged.
 */
function WhereItWent({ rows, total }: { rows: LineItem[]; total: number }) {
  const { t } = useTranslation();
  const palette = usePalette();
  const totals = categoryTotals(rows);

  return (
    <Card style={styles.whereItWent}>
      <Text variant="small" weight="semibold" color="ink2" accessibilityRole="header">
        {t('report.whereItWent')}
      </Text>
      <View style={styles.wentRows}>
        {totals.map((group) => (
          <View key={group.category} style={styles.wentRow}>
            <Text color="ink2" style={styles.wentLabel}>
              {t(`report.categories.${group.category}`)}
            </Text>
            <Text weight="semibold">{formatINR(group.total)}</Text>
          </View>
        ))}
      </View>
      <View style={[styles.wentTotal, { borderTopColor: palette.line }]}>
        <Text weight="bold">{t('report.billTotal')}</Text>
        <Text weight="bold">{formatINR(total)}</Text>
      </View>
    </Card>
  );
}

/**
 * Worst first, for a line with more than one flag: an open question before a
 * settled one, and within those a clear issue before one worth asking.
 */
function severity(flag: Flag): number {
  return (flag.status === 'open' ? 0 : 2) + (flag.level === 'red' ? 0 : 1);
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
  const insets = useSafeAreaInsets();
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
      {/* A Modal renders outside the screen's SafeAreaView, so its own insets
          are its own problem: without this the last button sits under
          Android's navigation bar, where it cannot be tapped. */}
      <View style={[styles.sheet, { backgroundColor: palette.app, paddingBottom: 24 + insets.bottom }]}>
        <View style={styles.sheetTop}>
          <Chip tone={chipTone(flag)} label={flagTag(t, flag)} />
          <IconButton icon="x" label={t('common.back')} onPress={onClose} />
        </View>

        <Text variant="title" weight="bold" accessibilityRole="header">
          {item?.name ?? ''}
        </Text>
        <Text variant="big" weight="bold" style={styles.sheetBilled}>
          {formatINR(flag.billed)}
        </Text>

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
            <Button
              variant="secondary"
              label={t('report.reopen')}
              loading={saving}
              onPress={() => mark('open')}
            />
          </View>
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  header: { padding: 16, marginBottom: 14 },
  headerTop: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
  headerWho: { flex: 1 },
  headerTotal: { marginTop: 14 },
  bar: { flexDirection: 'row', gap: 2, height: 10, borderRadius: 999, overflow: 'hidden', marginTop: 14 },
  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: 14, marginTop: 10 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendSwatch: { width: 9, height: 9, borderRadius: 2 },
  headerMoney: { marginTop: 10, gap: 2 },
  segmented: {
    flexDirection: 'row',
    borderRadius: 12,
    padding: 3,
    gap: 3,
    marginBottom: 14,
  },
  segment: {
    flex: 1,
    paddingVertical: 7,
    borderRadius: 9,
    alignItems: 'center',
    borderWidth: 0,
  },
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
  okRow: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'center',
    paddingVertical: 6,
  },
  paper: { padding: 14 },
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
  billNumber: { width: 20, textAlign: 'right' },
  billName: { flex: 1 },
  whereItWent: { padding: 14, marginBottom: 14 },
  wentRows: { marginTop: 8, gap: 5 },
  wentTotal: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 10,
    paddingTop: 10,
    borderTopWidth: 1,
  },
  wentRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    gap: 10,
  },
  wentLabel: { flex: 1 },
  struck: { textDecorationLine: 'line-through' },
  billTotal: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingTop: 10,
    paddingHorizontal: 4,
  },
  fine: { marginTop: 14, lineHeight: 18 },
  cta: { marginTop: 18, gap: 10 },
  scrim: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(14,16,32,0.45)',
  },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '88%',
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    padding: Gutter,
  },
  sheetTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sheetBilled: { marginTop: 2, marginBottom: 6 },
  sheetHeading: { marginTop: 14, marginBottom: 2 },
  sheetButtons: { gap: 8, marginTop: 8 },
});
