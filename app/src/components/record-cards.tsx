import { StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { caseStatus } from '@/data/case-status';
import type { LabReportRow } from '@/data/lab-api';
import type { Case } from '@/data/types';
import { formatDayMonth, formatMonthYear } from '@/i18n/dates';

import { Card } from './card';
import { CaseStatusChip } from './case-status-chip';
import { Chip } from './chip';
import { Text } from './text';

/** One admission, in a list. */
export function CaseCard({ item, onPress }: { item: Case; onPress: () => void }) {
  const { t } = useTranslation();
  // Nothing invented: a bill that printed no admission date leaves the case
  // without one, and saying so is what gets it filled in.
  const when = item.closedOn
    ? t('home.closed', { date: formatMonthYear(t, item.closedOn) })
    : item.admittedOn
      ? t('home.admitted', { date: formatDayMonth(t, item.admittedOn) })
      : t('home.admittedUnknown');

  return (
    <Card onPress={onPress} style={styles.card}>
      <View style={styles.text}>
        <Text weight="bold" style={styles.title}>
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

/** One lab report, in a list. */
export function LabReportCard({ row, onPress }: { row: LabReportRow; onPress: () => void }) {
  const { t } = useTranslation();
  return (
    <Card onPress={onPress} style={styles.card}>
      <View style={styles.text}>
        <Text weight="bold" style={styles.title}>
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

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 10,
  },
  text: { flex: 1 },
  title: { fontSize: 16, lineHeight: 22, marginBottom: 2 },
});
