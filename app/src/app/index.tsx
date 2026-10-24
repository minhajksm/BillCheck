import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { AppHeader } from '@/components/app-header';
import { Avatar } from '@/components/avatar';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { CaseStatusChip } from '@/components/case-status-chip';
import { Chip } from '@/components/chip';
import { Logo } from '@/components/logo';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { Radius } from '@/constants/theme';
import { caseStatus } from '@/data/case-status';
import { listCases, type ScannedPage } from '@/data/cases-api';
import { listLabReports, type LabReportRow } from '@/data/lab-api';
import { stagePages } from '@/data/page-inbox';
import type { Case } from '@/data/types';
import { useAsync } from '@/hooks/use-async';
import { usePagePicker } from '@/hooks/use-page-picker';
import { usePalette } from '@/hooks/use-palette';
import { formatDayMonth, formatMonthYear } from '@/i18n/dates';
import { formatPhone } from '@/lib/phone';

export default function YourCasesScreen() {
  const { t } = useTranslation();
  const palette = usePalette();
  const { state, logout } = useAuth();
  const [accountOpen, setAccountOpen] = useState(false);
  const token = state.status === 'signedIn' ? state.token : null;

  const loadCases = useCallback(async () => (token ? listCases(token) : []), [token]);
  const cases = useAsync(loadCases);
  const loadLabReports = useCallback(async () => (token ? listLabReports(token) : []), [token]);
  const labReports = useAsync(loadLabReports);
  // Coming back from a scan, the case's chip should already be up to date,
  // and a report just explained (or deleted) should already be in the list.
  const { reload } = cases;
  const { reload: reloadLab } = labReports;
  useFocusEffect(
    useCallback(() => {
      reload();
      reloadLab();
    }, [reload, reloadLab]),
  );

  // The root layout only shows this screen to signed-in people.
  if (state.status !== 'signedIn') return null;
  const { user } = state;
  // A device-only account has no number, and was never asked for a name.
  const { phone } = user;

  const header = (
    <AppHeader
      title={
        <View style={styles.brand}>
          <Logo />
          <Text weight="bold" style={styles.brandName} accessibilityRole="header">
            {t('common.appName')}
          </Text>
        </View>
      }
      right={
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t('auth.account')}
          accessibilityState={{ expanded: accountOpen }}
          hitSlop={6}
          onPress={() => setAccountOpen((open) => !open)}>
          <Avatar name={user.name} label={t('auth.guest')} />
        </Pressable>
      }
    />
  );

  return (
    <Screen header={header}>
      {accountOpen ? (
        <Card style={styles.account}>
          {phone === null ? (
            // No log out: without a number there is nothing to sign back in
            // with, so the button would only throw the bills away.
            <>
              <Text weight="bold">{t('auth.deviceAccountTitle')}</Text>
              <Text variant="small" color="ink2">
                {t('auth.deviceAccountBody')}
              </Text>
            </>
          ) : (
            <>
              <Text weight="bold">{user.name}</Text>
              <Text variant="small" color="ink2">
                {t('auth.signedInAs', { phone: formatPhone(phone) })}
              </Text>
              <Button variant="secondary" icon="log-out" label={t('auth.logOut')} onPress={logout} />
            </>
          )}
        </Card>
      ) : null}
      <Text variant="hello" weight="bold" style={styles.hello}>
        {phone === null ? t('home.greetingNoName') : t('home.greeting', { name: user.name.split(' ')[0] })}
      </Text>
      <Text color="ink2">{t('home.intro')}</Text>

      <CheckABill />
      <CheckALabReport consented={user.lab_consent === true} />

      <Text variant="small" weight="semibold" color="ink2" style={styles.sectionTitle}>
        {t('home.yourCases')}
      </Text>
      {cases.status === 'loading' ? <Text color="ink2">{t('common.loading')}</Text> : null}
      {cases.status === 'error' ? (
        <Card style={styles.account}>
          <Text color="ink2">{t('common.loadFailed')}</Text>
          <Button variant="secondary" label={t('common.tryAgain')} onPress={cases.reload} />
        </Card>
      ) : null}
      {(cases.status === 'ready' ? cases.value : []).map((c) => (
        <CaseCard
          key={c.id}
          item={c}
          // A closed admission opens like any other: its reports stay
          // readable, and the only way to delete it is from inside it.
          onPress={() => router.push({ pathname: '/cases/[caseId]', params: { caseId: c.id } })}
        />
      ))}

      <Button
        variant="secondary"
        icon="plus"
        label={t('home.startNewCase')}
        onPress={() => router.push('/cases/new')}
      />

      {labReports.status === 'ready' && labReports.value.length > 0 ? (
        <>
          <Text variant="small" weight="semibold" color="ink2" style={styles.sectionTitle}>
            {t('lab.yourReports')}
          </Text>
          {labReports.value.map((row) => (
            <LabReportCard
              key={row.id}
              row={row}
              onPress={() => router.push({ pathname: '/lab/[reportId]', params: { reportId: row.id } })}
            />
          ))}
        </>
      ) : null}

      <View style={[styles.tip, { borderColor: palette.line }]}>
        <Text weight="bold">{t('home.planningTitle')}</Text>
        <Text color="ink2">{t('home.planningBody')}</Text>
        <Chip tone="grey" label={t('home.nextVersion')} />
      </View>
    </Screen>
  );
}

/**
 * The way in, first thing on the screen.
 *
 * A family arrives holding a bill, not wanting to fill in a form about an
 * admission they are living through. Everything a case needs -- the hospital,
 * the patient, the IP number, the admission date -- is printed on the page in
 * their hand, so the bill opens the case and they correct it later if they
 * like. Starting a case by hand is still there, below their cases, for anyone
 * setting one up before the first bill arrives.
 *
 * The picker opens here, on the tap, so nothing stands between wanting a bill
 * checked and photographing it. The pages go to the scan screen, where the
 * rest of a multi-page bill is added.
 */
function CheckABill() {
  const { t } = useTranslation();
  const palette = usePalette();
  const picker = usePagePicker();

  const pick = async (choose: () => Promise<ScannedPage[]>) => {
    const pages = await choose();
    // Cancelled: they are still on their own cases, which is where they were.
    if (pages.length === 0) return;
    stagePages(pages);
    router.push('/scan');
  };

  return (
    <View style={[styles.checkBill, { backgroundColor: palette.indigoSoft, borderColor: palette.line }]}>
      <Text weight="bold" style={styles.checkBillTitle}>
        {t('home.checkBillTitle')}
      </Text>
      <Text color="ink2">{t('home.checkBillBody')}</Text>
      <View style={styles.checkBillButtons}>
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
function CheckALabReport({ consented }: { consented: boolean }) {
  const { t } = useTranslation();
  const palette = usePalette();
  const picker = usePagePicker();

  const pick = async (choose: () => Promise<ScannedPage[]>) => {
    if (!consented) {
      router.push('/lab/consent');
      return;
    }
    const pages = await choose();
    if (pages.length === 0) return;
    stagePages(pages);
    router.push('/lab/new');
  };

  return (
    <View style={[styles.checkBill, { backgroundColor: palette.card, borderColor: palette.line }]}>
      <Text weight="bold" style={styles.checkBillTitle}>
        {t('lab.cardTitle')}
      </Text>
      <Text color="ink2">{t('lab.cardBody')}</Text>
      <View style={styles.checkBillButtons}>
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

function LabReportCard({ row, onPress }: { row: LabReportRow; onPress: () => void }) {
  const { t } = useTranslation();
  return (
    <Card onPress={onPress} style={styles.case}>
      <View style={styles.caseText}>
        <Text weight="bold" style={styles.caseTitle}>
          {row.labName || t('lab.unnamedLab')}
        </Text>
        <Text color="ink2">
          {row.outsideRange > 0 ? t('lab.outsideRange', { count: row.outsideRange }) : t('lab.noneOutside')}
        </Text>
        {row.reportDate ? <Text variant="faint">{row.reportDate}</Text> : null}
      </View>
      {row.urgent ? <Chip tone="amber" label={t('lab.urgentTitle')} /> : null}
    </Card>
  );
}

function CaseCard({ item, onPress }: { item: Case; onPress: () => void }) {
  const { t } = useTranslation();
  // Nothing invented: a bill that printed no admission date leaves the case
  // without one, and saying so is what gets it filled in.
  const when = item.closedOn
    ? t('home.closed', { date: formatMonthYear(t, item.closedOn) })
    : item.admittedOn
      ? t('home.admitted', { date: formatDayMonth(t, item.admittedOn) })
      : t('home.admittedUnknown');

  return (
    <Card onPress={onPress} style={styles.case}>
      <View style={styles.caseText}>
        <Text weight="bold" style={styles.caseTitle}>
          {item.title}
        </Text>
        <Text color="ink2">
          {t('common.place', {
            name: item.hospital.name,
            area: item.hospital.area,
          })}
        </Text>
        <Text variant="faint">{when}</Text>
      </View>
      <CaseStatusChip status={caseStatus(item)} />
    </Card>
  );
}

const styles = StyleSheet.create({
  brand: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  brandName: { fontSize: 20, lineHeight: 26 },
  account: { padding: 16, gap: 8, marginBottom: 8 },
  hello: { marginTop: 6, marginBottom: 2 },
  sectionTitle: { marginTop: 22, marginBottom: 8 },
  checkBill: {
    marginTop: 18,
    borderWidth: 1,
    borderRadius: Radius.card,
    paddingHorizontal: 16,
    paddingVertical: 16,
    gap: 6,
  },
  checkBillTitle: { fontSize: 16, lineHeight: 22 },
  checkBillButtons: { marginTop: 10, gap: 10 },
  case: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 10,
  },
  caseText: { flex: 1 },
  caseTitle: { fontSize: 16, lineHeight: 22, marginBottom: 2 },
  tip: {
    marginTop: 22,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderRadius: Radius.card,
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 6,
  },
});
