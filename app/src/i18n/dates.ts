import type { TFunction } from 'i18next';

import { parseCalendarDate } from '@/lib/format';

/** "2026-10-09" -> "9 Oct" (or the Hindi/Marathi month name). */
export function formatDayMonth(t: TFunction, iso: string): string {
  const { day, month } = parseCalendarDate(iso);
  const months = t('dates.monthsShort', { returnObjects: true });
  return t('dates.dayMonth', { day, month: months[month - 1] });
}

/** "2026-03-14" -> "March 2026". */
export function formatMonthYear(t: TFunction, iso: string): string {
  const { year, month } = parseCalendarDate(iso);
  const months = t('dates.monthsLong', { returnObjects: true });
  return t('dates.monthYear', { year, month: months[month - 1] });
}
