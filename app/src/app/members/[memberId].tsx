import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { Share, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { AppHeader, IconButton } from '@/components/app-header';
import { Avatar } from '@/components/avatar';
import { Button } from '@/components/button';
import { Icon, type IconName } from '@/components/icon';
import { CaseCard, LabReportCard } from '@/components/record-cards';
import { CheckABill, CheckALabReport } from '@/components/scan-cards';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useToast } from '@/components/toast';
import { Radius } from '@/constants/theme';
import { createInvite, deleteMember, readMember, stopFollowing, type Member } from '@/data/members-api';
import { useAsync } from '@/hooks/use-async';
import { usePalette } from '@/hooks/use-palette';
import { formatDate } from '@/i18n/dates';
import { formatPhone } from '@/lib/phone';

/**
 * One person, and everything kept about them: their admissions and their lab
 * reports. Family follow the person, so an invite from here shows them every
 * stay and every report, including the ones still to come.
 */
export default function MemberScreen() {
  const { memberId } = useLocalSearchParams<{ memberId: string }>();
  const { t } = useTranslation();
  const { state } = useAuth();
  const token = state.status === 'signedIn' ? state.token : null;

  const load = useCallback(async () => {
    if (!token) throw new Error('signed out');
    return readMember(token, memberId);
  }, [token, memberId]);
  const loaded = useAsync(load);

  // A bill just checked or a report just explained should be listed the
  // moment we come back.
  const { reload } = loaded;
  useFocusEffect(useCallback(() => void reload(), [reload]));

  if (state.status !== 'signedIn') return null;
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
        <Text style={styles.notFound}>{t('members.notFound')}</Text>
        <Button variant="secondary" label={t('common.goHome')} onPress={() => router.replace('/')} />
      </Screen>
    );
  }
  return (
    <MemberView
      member={loaded.value}
      token={state.token}
      userId={state.user.id}
      labConsent={state.user.lab_consent === true}
    />
  );
}

function MemberView({
  member,
  token,
  userId,
  labConsent,
}: {
  member: Member;
  token: string;
  userId: string;
  labConsent: boolean;
}) {
  const { t } = useTranslation();
  const palette = usePalette();
  const toast = useToast();
  const [inviting, setInviting] = useState(false);
  const [code, setCode] = useState<string | null>(null);

  const invite = async () => {
    setInviting(true);
    let made: string;
    try {
      made = (await createInvite(token, member.id)).code;
      setCode(made);
    } catch {
      toast(t('members.inviteFailed'));
      return;
    } finally {
      setInviting(false);
    }
    try {
      // The phone's own share sheet: WhatsApp is where families already talk.
      await Share.share({ message: t('members.inviteMessage', { name: member.name, code: made }) });
    } catch {
      // No share sheet (a browser without one): the code is on screen to copy.
    }
  };

  const header = (
    <AppHeader
      title={member.name}
      showBack
      right={
        <IconButton
          icon="edit-2"
          label={t('members.editDetails')}
          onPress={() => router.push({ pathname: '/members/new', params: { memberId: member.id } })}
        />
      }
    />
  );

  return (
    <Screen header={header}>
      <Details member={member} />
      <Followers member={member} />
      <Button
        variant="secondary"
        icon="user-plus"
        label={t('members.invite')}
        loading={inviting}
        onPress={invite}
      />
      {code ? (
        <View style={[styles.code, { backgroundColor: palette.soft, borderColor: palette.line }]}>
          <Text variant="small" color="ink2">
            {t('members.codeShown')}
          </Text>
          <Text weight="bold" selectable style={styles.codeText}>
            {code}
          </Text>
        </View>
      ) : null}

      <Text variant="small" weight="semibold" color="ink2" style={styles.sectionTitle}>
        {t('members.scanTitle')}
      </Text>
      <CheckABill memberId={member.id} compact />
      <CheckALabReport consented={labConsent} memberId={member.id} compact />

      <Text variant="small" weight="semibold" color="ink2" style={styles.sectionTitle}>
        {t('members.admissions')}
      </Text>
      {member.cases.length === 0 ? (
        <Text color="ink2" style={styles.empty}>
          {t('members.noAdmissions')}
        </Text>
      ) : null}
      {member.cases.map((item) => (
        <CaseCard
          key={item.id}
          item={item}
          onPress={() => router.push({ pathname: '/cases/[caseId]', params: { caseId: item.id } })}
        />
      ))}
      <Button
        variant="quiet"
        icon="plus"
        label={t('members.addAdmission')}
        onPress={() => router.push({ pathname: '/cases/new', params: { memberId: member.id } })}
      />

      <Text variant="small" weight="semibold" color="ink2" style={styles.sectionTitle}>
        {t('members.labReportsTitle')}
      </Text>
      {member.labReports.length === 0 ? (
        <Text color="ink2" style={styles.empty}>
          {t('members.noLabReports')}
        </Text>
      ) : null}
      {member.labReports.map((row) => (
        <LabReportCard
          key={row.id}
          row={row}
          onPress={() => router.push({ pathname: '/lab/[reportId]', params: { reportId: row.id } })}
        />
      ))}

      <Leave member={member} token={token} userId={userId} />
    </Screen>
  );
}

/**
 * What the family has said about this person. Only what is known is shown;
 * with nothing known yet, one quiet line says what can be added.
 */
function Details({ member }: { member: Member }) {
  const { t } = useTranslation();
  const palette = usePalette();
  const edit = () => router.push({ pathname: '/members/new', params: { memberId: member.id } });

  const rows: { icon: IconName; text: string }[] = [];
  if (member.dateOfBirth) {
    const born = t('members.born', { date: formatDate(t, member.dateOfBirth) });
    rows.push({
      icon: 'calendar',
      text: member.age !== undefined ? `${t('members.age', { age: member.age })} · ${born}` : born,
    });
  }
  if (member.phone) rows.push({ icon: 'phone', text: formatPhone(member.phone) });
  if (member.email) rows.push({ icon: 'mail', text: member.email });
  if (member.address) rows.push({ icon: 'map-pin', text: member.address });

  if (rows.length === 0) {
    return <Button variant="quiet" icon="plus" label={t('members.addDetails')} onPress={edit} />;
  }
  return (
    <View style={[styles.details, { backgroundColor: palette.card, borderColor: palette.line }]}>
      {rows.map((row) => (
        <View key={row.icon} style={styles.detailRow}>
          <Icon name={row.icon} size={16} color="ink3" />
          <Text variant="small" selectable style={styles.detailText}>
            {row.text}
          </Text>
        </View>
      ))}
    </View>
  );
}

/** Who else follows this person. */
function Followers({ member }: { member: Member }) {
  const { t } = useTranslation();
  const you = member.followers.find((f) => f.isYou);
  const others = member.followers.filter((f) => !f.isYou);
  const youName = you?.name.split(' ')[0] ?? '';
  const name = member.name;

  let label: string;
  if (others.length === 0) label = t('members.followersYouOnly', { name });
  else if (others.length === 1)
    label = t('members.followersPair', { you: youName, other: others[0].name.split(' ')[0], name });
  else label = t('members.followersMany', { you: youName, count: others.length, name });

  // Up to two overlapping avatars, as on the prototype's case screen.
  const shown = [you, ...others].filter((f) => f !== undefined).slice(0, 2);

  return (
    <View style={styles.followers}>
      {shown.map((f, i) => (
        <Avatar
          key={f.id}
          name={f.name}
          tone={i === 0 ? 'indigo' : 'green'}
          style={i > 0 && styles.overlap}
        />
      ))}
      <Text variant="faint" style={styles.followersLabel}>
        {label}
      </Text>
    </View>
  );
}

/**
 * Deleting the person, or no longer following them.
 *
 * Whoever added them can delete them, which takes every admission and
 * report away from the whole family. Anyone else can only stop following.
 * Either is confirmed first: there is no undo.
 */
function Leave({ member, token, userId }: { member: Member; token: string; userId: string }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const name = member.name;

  const go = async () => {
    setBusy(true);
    try {
      if (member.isOwner) await deleteMember(token, member.id);
      else await stopFollowing(token, member.id, userId);
      toast(member.isOwner ? t('members.deleted') : t('members.stopped', { name }));
      router.replace('/');
    } catch {
      setBusy(false);
      toast(t('members.deleteFailed'));
    }
  };

  return (
    <View style={styles.leave}>
      {confirming ? (
        <>
          <Text color="ink2">
            {member.isOwner
              ? t('members.confirmDelete', { name })
              : t('members.confirmStopFollowing', { name })}
          </Text>
          <Button
            variant="danger"
            label={
              member.isOwner ? t('members.confirmDeleteAction') : t('members.confirmStopFollowingAction')
            }
            loading={busy}
            onPress={go}
          />
          <Button variant="secondary" label={t('common.cancel')} onPress={() => setConfirming(false)} />
        </>
      ) : (
        <Button
          variant="danger"
          icon={member.isOwner ? 'trash-2' : 'user-minus'}
          label={member.isOwner ? t('members.delete', { name }) : t('members.stopFollowing', { name })}
          onPress={() => setConfirming(true)}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  notFound: { marginVertical: 16 },
  details: { borderWidth: 1, borderRadius: Radius.card, padding: 12, gap: 8, marginBottom: 12 },
  detailRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  detailText: { flex: 1 },
  followers: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  overlap: { marginLeft: -8 },
  followersLabel: { marginLeft: 8, flex: 1 },
  sectionTitle: { marginTop: 22, marginBottom: 8 },
  empty: { marginBottom: 6 },
  leave: { marginTop: 28, gap: 10 },
  code: { marginTop: 10, borderWidth: 1, borderRadius: Radius.card, padding: 12, gap: 2 },
  codeText: { fontSize: 18, letterSpacing: 0.5 },
});
