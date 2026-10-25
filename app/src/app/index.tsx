import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { AppHeader } from '@/components/app-header';
import { Avatar } from '@/components/avatar';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { Chip } from '@/components/chip';
import { Icon } from '@/components/icon';
import { Logo } from '@/components/logo';
import { CheckABill, CheckALabReport } from '@/components/scan-cards';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { Radius } from '@/constants/theme';
import { listMembers, listUnfiled, type Unfiled } from '@/data/members-api';
import type { MemberSummary } from '@/data/types';
import { useAsync } from '@/hooks/use-async';
import { usePalette } from '@/hooks/use-palette';
import { formatPhone } from '@/lib/phone';

/**
 * Home: the way in to checking a bill or a report, and the people whose
 * bills and reports are kept here.
 */
export default function HomeScreen() {
  const { t } = useTranslation();
  const palette = usePalette();
  const { state, logout } = useAuth();
  const [accountOpen, setAccountOpen] = useState(false);
  const token = state.status === 'signedIn' ? state.token : null;

  const loadMembers = useCallback(async () => (token ? listMembers(token) : []), [token]);
  const members = useAsync(loadMembers);
  const loadUnfiled = useCallback(
    async (): Promise<Unfiled> => (token ? listUnfiled(token) : { cases: [], labReports: [] }),
    [token],
  );
  const unfiled = useAsync(loadUnfiled);
  // Coming back from a scan, a member's counts should already be up to date,
  // and something just filed should already have left the waiting list.
  const { reload } = members;
  const { reload: reloadUnfiled } = unfiled;
  useFocusEffect(
    useCallback(() => {
      reload();
      reloadUnfiled();
    }, [reload, reloadUnfiled]),
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

      {unfiled.status === 'ready' ? <WaitingToBeFiled unfiled={unfiled.value} /> : null}

      <Text variant="small" weight="semibold" color="ink2" style={styles.sectionTitle}>
        {t('home.yourMembers')}
      </Text>
      {members.status === 'loading' ? <Text color="ink2">{t('common.loading')}</Text> : null}
      {members.status === 'error' ? (
        <Card style={styles.account}>
          <Text color="ink2">{t('common.loadFailed')}</Text>
          <Button variant="secondary" label={t('common.tryAgain')} onPress={members.reload} />
        </Card>
      ) : null}
      {members.status === 'ready' && members.value.length === 0 ? (
        <Text color="ink2" style={styles.empty}>
          {t('home.membersEmpty')}
        </Text>
      ) : null}
      {(members.status === 'ready' ? members.value : []).map((member) => (
        <MemberCard
          key={member.id}
          member={member}
          onPress={() => router.push({ pathname: '/members/[memberId]', params: { memberId: member.id } })}
        />
      ))}

      <View style={styles.memberActions}>
        <Button
          variant="secondary"
          icon="user-plus"
          label={t('home.addMember')}
          onPress={() => router.push('/members/new')}
        />
        <Button
          variant="quiet"
          icon="users"
          label={t('home.joinWithCode')}
          onPress={() => router.push('/members/join')}
        />
      </View>

      <View style={[styles.tip, { borderColor: palette.line }]}>
        <Text weight="bold">{t('home.planningTitle')}</Text>
        <Text color="ink2">{t('home.planningBody')}</Text>
        <Chip tone="grey" label={t('home.nextVersion')} />
      </View>
    </Screen>
  );
}

/** Someone looked after, with what is under them at a glance. */
function MemberCard({ member, onPress }: { member: MemberSummary; onPress: () => void }) {
  const { t } = useTranslation();
  const counts = [
    member.age !== undefined ? t('members.age', { age: member.age }) : null,
    member.admissionCount > 0 ? t('members.admissions', { count: member.admissionCount }) : null,
    member.labReportCount > 0 ? t('members.labReports', { count: member.labReportCount }) : null,
  ].filter((part): part is string => part !== null);

  return (
    <Card onPress={onPress} style={styles.member}>
      <Avatar name={member.name} />
      <View style={styles.memberText}>
        <Text weight="bold" style={styles.memberName}>
          {member.name}
        </Text>
        {member.openAdmissionCount > 0 ? (
          <Text variant="small" weight="semibold" color="indigoInk">
            {t('members.inHospital')}
          </Text>
        ) : null}
        <Text variant="faint">{counts.length > 0 ? counts.join(' · ') : t('members.nothingYet')}</Text>
      </View>
      {member.openFlagCount > 0 ? (
        <Chip tone="amber" label={t('caseStatus.toAsk', { count: member.openFlagCount })} />
      ) : null}
    </Card>
  );
}

/**
 * Scans nobody has said whose they are yet.
 *
 * The app asks as soon as a scan is read, so this is normally empty. It is
 * where one lands if the app was closed before the answer, so it is never
 * lost and never seen by anyone else.
 */
function WaitingToBeFiled({ unfiled }: { unfiled: Unfiled }) {
  const { t } = useTranslation();
  const palette = usePalette();
  if (unfiled.cases.length === 0 && unfiled.labReports.length === 0) return null;

  const rows = [
    ...unfiled.cases.map((item) => ({
      key: `bill-${item.id}`,
      title: item.hospital.name
        ? t('home.unfiledBill', { hospital: item.hospital.name })
        : t('home.unfiledBillUnnamed'),
      name: item.patient.name,
      icon: 'file-text' as const,
      open: () => router.push({ pathname: '/file', params: { kind: 'bill', id: item.id } }),
    })),
    ...unfiled.labReports.map((row) => ({
      key: `lab-${row.id}`,
      title: row.labName ? t('home.unfiledLab', { lab: row.labName }) : t('home.unfiledLabUnnamed'),
      name: row.patientName,
      icon: 'activity' as const,
      open: () => router.push({ pathname: '/file', params: { kind: 'lab', id: row.id } }),
    })),
  ];

  return (
    <>
      <Text variant="small" weight="semibold" color="ink2" style={styles.sectionTitle}>
        {t('home.unfiledTitle')}
      </Text>
      {rows.map((row) => (
        <Pressable
          key={row.key}
          accessibilityRole="button"
          onPress={row.open}
          style={[styles.unfiled, { backgroundColor: palette.marigoldSoft, borderColor: palette.line }]}>
          <Icon name={row.icon} size={18} color="marigoldInk" />
          <View style={styles.memberText}>
            <Text weight="semibold">{row.title}</Text>
            {row.name ? <Text variant="faint">{t('home.onPage', { name: row.name })}</Text> : null}
          </View>
          <Icon name="chevron-right" size={18} color="ink3" />
        </Pressable>
      ))}
    </>
  );
}

const styles = StyleSheet.create({
  brand: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  brandName: { fontSize: 20, lineHeight: 26 },
  account: { padding: 16, gap: 8, marginBottom: 8 },
  hello: { marginTop: 6, marginBottom: 2 },
  sectionTitle: { marginTop: 22, marginBottom: 8 },
  empty: { marginBottom: 6 },
  member: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 10,
  },
  memberText: { flex: 1 },
  memberName: { fontSize: 16, lineHeight: 22 },
  memberActions: { gap: 6, marginTop: 4 },
  unfiled: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderWidth: 1,
    borderRadius: Radius.card,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 10,
  },
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
