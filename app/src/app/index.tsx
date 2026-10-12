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
import { useToast } from '@/components/toast';
import { Radius } from '@/constants/theme';
import { caseStatus } from '@/data/case-status';
import { listCases } from '@/data/cases-api';
import type { Case } from '@/data/types';
import { useAsync } from '@/hooks/use-async';
import { usePalette } from '@/hooks/use-palette';
import { formatDayMonth, formatMonthYear } from '@/i18n/dates';
import { formatPhone } from '@/lib/phone';

export default function YourCasesScreen() {
  const { t } = useTranslation();
  const palette = usePalette();
  const toast = useToast();
  const { state, logout } = useAuth();
  const [accountOpen, setAccountOpen] = useState(false);
  const token = state.status === 'signedIn' ? state.token : null;

  const loadCases = useCallback(async () => (token ? listCases(token) : []), [token]);
  const cases = useAsync(loadCases);
  // Coming back from a scan, the case's chip should already be up to date.
  const { reload } = cases;
  useFocusEffect(useCallback(() => void reload(), [reload]));

  // The root layout only shows this screen to signed-in people.
  if (state.status !== 'signedIn') return null;
  const { user } = state;

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
          <Avatar name={user.name} />
        </Pressable>
      }
    />
  );

  return (
    <Screen header={header}>
      {accountOpen ? (
        <Card style={styles.account}>
          <Text weight="bold">{user.name}</Text>
          <Text variant="small" color="ink2">
            {t('auth.signedInAs', { phone: formatPhone(user.phone) })}
          </Text>
          <Button variant="secondary" icon="log-out" label={t('auth.logOut')} onPress={logout} />
        </Card>
      ) : null}
      <Text variant="hello" weight="bold" style={styles.hello}>
        {t('home.greeting', { name: user.name.split(' ')[0] })}
      </Text>
      <Text color="ink2">{t('home.intro')}</Text>

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
          onPress={() =>
            c.closedOn
              ? toast(t('home.closedCaseToast'))
              : router.push({ pathname: '/cases/[caseId]', params: { caseId: c.id } })
          }
        />
      ))}

      <Button
        variant="secondary"
        icon="plus"
        label={t('home.startNewCase')}
        onPress={() => router.push('/cases/new')}
      />

      <View style={[styles.tip, { borderColor: palette.line }]}>
        <Text weight="bold">{t('home.planningTitle')}</Text>
        <Text color="ink2">{t('home.planningBody')}</Text>
        <Chip tone="grey" label={t('home.nextVersion')} />
      </View>
    </Screen>
  );
}

function CaseCard({ item, onPress }: { item: Case; onPress: () => void }) {
  const { t } = useTranslation();
  const when = item.closedOn
    ? t('home.closed', { date: formatMonthYear(t, item.closedOn) })
    : t('home.admitted', { date: formatDayMonth(t, item.admittedOn), day: item.dayOfStay });

  return (
    <Card onPress={onPress} style={styles.case}>
      <View style={styles.caseText}>
        <Text weight="bold" style={styles.caseTitle}>
          {item.title}
        </Text>
        <Text color="ink2">{t('common.place', { name: item.hospital.name, area: item.hospital.area })}</Text>
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
