import type { TFunction } from 'i18next';
import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/auth-context';
import { Avatar } from '@/components/avatar';
import { Button } from '@/components/button';
import { Checkbox } from '@/components/checkbox';
import { FormScreen } from '@/components/form-screen';
import { Icon } from '@/components/icon';
import {
  MemberFields,
  memberDetails,
  memberValues,
  validateMember,
  type MemberErrors,
  type MemberValues,
} from '@/components/member-fields';
import { Text } from '@/components/text';
import { useToast } from '@/components/toast';
import { Radius } from '@/constants/theme';
import { fileCase, readCase, type FileUnder } from '@/data/cases-api';
import { fileLabReport, readLabReport } from '@/data/lab-api';
import { listMembers } from '@/data/members-api';
import type { MemberSummary, SuggestedMember } from '@/data/types';
import { useAsync } from '@/hooks/use-async';
import { usePalette } from '@/hooks/use-palette';
import { formatDate } from '@/i18n/dates';
import { formatPhone } from '@/lib/phone';

type Kind = 'bill' | 'lab';

/** "Ramesh  sharma" and "Ramesh Sharma" are the same person on two printers. */
const same = (a: string, b: string) =>
  a.trim().replace(/\s+/g, ' ').toLocaleLowerCase() === b.trim().replace(/\s+/g, ' ').toLocaleLowerCase();

/**
 * Whose is this? Asked right after a scan made before choosing anyone.
 *
 * The page has been read by now, so the name it prints is offered: picked
 * already where it matches someone they follow, and as the name for someone
 * new otherwise. Once they answer, the rest goes on as before -- the bill's
 * report, or the lab report's explanation.
 *
 * Leaving without answering loses nothing: the scan waits on the home screen,
 * seen by nobody else, until they come back to it.
 *
 * `kind` and `id` say what is being filed: a bill's case, or a lab report.
 * `billId`, for a bill, is the report to open once it is filed.
 */
export default function FileScreen() {
  const { kind, id, billId } = useLocalSearchParams<{ kind: Kind; id: string; billId?: string }>();
  const { t } = useTranslation();
  const { state } = useAuth();
  const token = state.status === 'signedIn' ? state.token : null;

  const load = useCallback(async () => {
    if (!token) throw new Error('signed out');
    const [members, page] = await Promise.all([
      listMembers(token),
      kind === 'lab'
        ? readLabReport(token, id).then((report) => ({
            name: report.patientName,
            suggested: report.suggestedMember,
          }))
        : readCase(token, id).then((item) => ({ name: item.patient.name, suggested: item.suggestedMember })),
    ]);
    return { members, onPage: page.name, suggested: page.suggested };
  }, [token, kind, id]);
  const loaded = useAsync(load);

  if (!token) return null;
  if (loaded.status !== 'ready') {
    return (
      <FormScreen title={kind === 'lab' ? t('file.titleLab') : t('file.titleBill')}>
        {loaded.status === 'error' ? (
          <>
            <Text color="ink2">{t('common.loadFailed')}</Text>
            <Button variant="secondary" label={t('common.tryAgain')} onPress={loaded.reload} />
          </>
        ) : (
          <Text color="ink2">{t('common.loading')}</Text>
        )}
      </FormScreen>
    );
  }
  return (
    <Choose
      token={token}
      kind={kind}
      id={id}
      billId={billId}
      members={loaded.value.members}
      onPage={loaded.value.onPage}
      suggested={loaded.value.suggested}
    />
  );
}

function Choose({
  token,
  kind,
  id,
  billId,
  members,
  onPage,
  suggested,
}: {
  token: string;
  kind: Kind;
  id: string;
  billId?: string;
  members: MemberSummary[];
  onPage: string;
  suggested?: SuggestedMember;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const matched = onPage ? members.find((member) => same(member.name, onPage)) : undefined;
  // Nothing is picked for them unless the page says who: guessing between
  // "Papa" and "Mummy" would file a bill under the wrong person.
  const [choice, setChoice] = useState<string | 'new' | null>(
    matched ? matched.id : members.length === 0 ? 'new' : null,
  );
  // Someone new starts as the page describes them, every field editable.
  const [newMember, setNewMember] = useState<MemberValues>(
    memberValues({ ...suggested, name: suggested?.name || onPage }),
  );
  const [errors, setErrors] = useState<MemberErrors>({});
  // For someone already there: whether to add what the page shows to theirs.
  const [addFromPage, setAddFromPage] = useState(true);
  const [saving, setSaving] = useState(false);

  const fromPage = pageDetails(suggested);
  const chosen = members.find((member) => member.id === choice);

  const submit = async () => {
    let answer: FileUnder;
    if (choice === 'new') {
      const found = validateMember(newMember, t);
      setErrors(found);
      if (Object.keys(found).length > 0) return;
      const { name, ...details } = memberDetails(newMember);
      answer = { newMemberName: name, details };
    } else if (choice) {
      answer = { memberId: choice, details: addFromPage && fromPage ? fromPage : undefined };
    } else {
      toast(t('file.pickOne'));
      return;
    }
    setSaving(true);
    try {
      if (kind === 'lab') {
        await fileLabReport(token, id, answer);
        router.replace({ pathname: '/lab/[reportId]', params: { reportId: id } });
      } else {
        await fileCase(token, id, answer);
        router.replace(
          billId
            ? { pathname: '/bills/[billId]', params: { billId } }
            : { pathname: '/cases/[caseId]', params: { caseId: id } },
        );
      }
    } catch {
      setSaving(false);
      toast(t('file.failed'));
    }
  };

  return (
    <FormScreen
      title={kind === 'lab' ? t('file.titleLab') : t('file.titleBill')}
      subtitle={
        <>
          <Text color="ink2">{t('file.subtitle')}</Text>
          {onPage ? (
            <Text weight="semibold" style={styles.onPage}>
              {t('home.onPage', { name: onPage })}
            </Text>
          ) : null}
        </>
      }
      footer={<Button label={t('file.continue')} loading={saving} onPress={submit} />}>
      <View accessibilityRole="radiogroup" style={styles.options}>
        {members.map((member) => (
          <Option
            key={member.id}
            label={member.name}
            selected={choice === member.id}
            onPress={() => setChoice(member.id)}
          />
        ))}
        <Option
          label={t('file.someoneNew')}
          selected={choice === 'new'}
          isNew
          onPress={() => setChoice('new')}
        />
      </View>

      {choice === 'new' ? (
        <MemberFields
          values={newMember}
          errors={errors}
          onChange={setNewMember}
          ageHint={suggested?.age !== undefined ? t('file.pageAge', { age: suggested.age }) : undefined}
        />
      ) : null}

      {chosen && fromPage ? (
        <View style={styles.fromPage}>
          <Checkbox
            checked={addFromPage}
            onChange={setAddFromPage}
            label={t('file.addToMember', { name: chosen.name })}
          />
          <View style={styles.fromPageList}>
            {pageLines(t, fromPage).map((line) => (
              <Text key={line} variant="small" color="ink2">
                {line}
              </Text>
            ))}
            <Text variant="faint">{t('file.addToMemberNote', { name: chosen.name })}</Text>
          </View>
        </View>
      ) : null}
    </FormScreen>
  );
}

/** What the page printed that a member can hold, or nothing. */
function pageDetails(suggested?: SuggestedMember): FileUnder['details'] {
  if (!suggested) return undefined;
  const { dateOfBirth, phone, email, address } = suggested;
  return dateOfBirth || phone || email || address ? { dateOfBirth, phone, email, address } : undefined;
}

function pageLines(t: TFunction, details: NonNullable<FileUnder['details']>): string[] {
  return [
    details.dateOfBirth ? t('members.born', { date: formatDate(t, details.dateOfBirth) }) : null,
    details.phone ? formatPhone(details.phone) : null,
    details.email ?? null,
    details.address ?? null,
  ].filter((line): line is string => line !== null);
}

function Option({
  label,
  selected,
  isNew = false,
  onPress,
}: {
  label: string;
  selected: boolean;
  /** "Someone new" has no initials to show. */
  isNew?: boolean;
  onPress: () => void;
}) {
  const palette = usePalette();
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      accessibilityLabel={label}
      onPress={onPress}
      style={[
        styles.option,
        {
          backgroundColor: selected ? palette.indigoSoft : palette.card,
          borderColor: selected ? palette.indigo : palette.line,
        },
      ]}>
      {isNew ? (
        <View style={[styles.newIcon, { backgroundColor: palette.soft }]}>
          <Icon name="user-plus" size={15} color="ink2" />
        </View>
      ) : (
        <Avatar name={label} />
      )}
      <Text weight="semibold" style={styles.optionLabel}>
        {label}
      </Text>
      <Icon name={selected ? 'check-circle' : 'circle'} size={20} color={selected ? 'indigo' : 'ink3'} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  onPage: { marginTop: 8 },
  fromPage: { marginTop: 6, gap: 6 },
  fromPageList: { paddingLeft: 34, gap: 2 },
  options: { gap: 8 },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderWidth: 1,
    borderRadius: Radius.card,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  optionLabel: { flex: 1 },
  newIcon: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
});
