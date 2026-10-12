import { useTranslation } from 'react-i18next';

import type { CaseStatus } from '@/data/case-status';
import { formatINR } from '@/lib/format';

import { Chip } from './chip';

export function CaseStatusChip({ status }: { status: CaseStatus }) {
  const { t } = useTranslation();
  switch (status.kind) {
    case 'closed':
      return status.recoveredAmount > 0 ? (
        <Chip tone="green" label={t('caseStatus.recovered', { amount: formatINR(status.recoveredAmount) })} />
      ) : (
        <Chip tone="grey" label={t('caseStatus.closed')} />
      );
    case 'needsTodaysBill':
      return <Chip tone="indigo" label={t('caseStatus.addTodaysBill')} />;
    case 'toAsk':
      return <Chip tone="amber" label={t('caseStatus.toAsk', { count: status.openFlagCount })} />;
    case 'upToDate':
      return <Chip tone="green" label={t('caseStatus.upToDate')} />;
  }
}
