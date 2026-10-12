import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

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
import { currentUser, placeholderCases } from '@/data/placeholder';
import type { Case } from '@/data/types';
import { usePalette } from '@/hooks/use-palette';
import { formatDayMonth, formatMonthYear } from '@/i18n/dates';

export default function YourCasesScreen() {
  const { t } = useTranslation();
  const palette = usePalette();
  const toast = useToast();

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
      right={<Avatar name={currentUser.name} />}
    />
  );

  return (
    <Screen header={header}>
      <Text variant="hello" weight="bold" style={styles.hello}>
        {t('home.greeting', { name: currentUser.firstName })}
      </Text>
      <Text color="ink2">{t('home.intro')}</Text>

      <Text variant="small" weight="semibold" color="ink2" style={styles.sectionTitle}>
        {t('home.yourCases')}
      </Text>
      {placeholderCases.map((c) => (
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

      <Button variant="secondary" icon="plus" label={t('home.startNewCase')} onPress={() => toast(t('home.newCaseSoon'))} />

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
