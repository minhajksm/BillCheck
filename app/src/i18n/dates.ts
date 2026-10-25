import type { TFunction } from 'i18next';

import { parseCalendarDate } from '@/lib/format';

/** "2026-10-09" -> "9 Oct" (or the Hindi/Marathi month name). */
export function formatDayMonth(t: TFunction, iso: string): string {
  const { day, month } = parseCalendarDate(iso);
  const months = t('dates.monthsShort', { returnObjects: true });
  return t('dates.dayMonth', { day, month: months[month - 1] });
}

/** "1958-03-14" -> "14 Mar 1958". For a date that may be years away. */
export function formatDate(t: TFunction, iso: string): string {
  const { year, month, day } = parseCalendarDate(iso);
  const months = t('dates.monthsShort', { returnObjects: true });
  return t('dates.dayMonthYear', { day, month: months[month - 1], year });
}

/** "2026-03-14" -> "March 2026". */
export function formatMonthYear(t: TFunction, iso: string): string {
  const { year, month } = parseCalendarDate(iso);
  const months = t('dates.monthsLong', { returnObjects: true });
  return t('dates.monthYear', { year, month: months[month - 1] });
}
