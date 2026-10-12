import type { Case, DailyBill } from './types';

/**
 * Where a case stands today. Drives the chip on "Your cases", and the banner
 * and main button on the case dashboard.
 */
export type CaseStatus =
  | { kind: 'closed'; recoveredAmount: number }
  | { kind: 'needsTodaysBill' }
  | { kind: 'toAsk'; openFlagCount: number }
  | { kind: 'upToDate' };

export function latestBill(c: Case): DailyBill | undefined {
  return c.bills[c.bills.length - 1];
}

export function hasTodaysBill(c: Case): boolean {
  return latestBill(c)?.day === c.dayOfStay;
}

export function openFlagCount(c: Case): number {
  return c.bills.reduce((sum, b) => sum + b.openFlagCount, 0);
}

export function caseStatus(c: Case): CaseStatus {
  if (c.closedOn) return { kind: 'closed', recoveredAmount: c.recoveredAmount };
  const open = openFlagCount(c);
  if (open > 0) return { kind: 'toAsk', openFlagCount: open };
  if (!hasTodaysBill(c)) return { kind: 'needsTodaysBill' };
  return { kind: 'upToDate' };
}

export function runningTotal(c: Case): number {
  return c.bills.reduce((sum, b) => sum + b.total, 0);
}

export type BillStatus = 'toAsk' | 'settled' | 'looksFine';

export function billStatus(b: DailyBill): BillStatus {
  if (b.openFlagCount > 0) return 'toAsk';
  if (b.flagCount > 0) return 'settled';
  return 'looksFine';
}
