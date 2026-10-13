import { describe, expect, it } from '@jest/globals';

import { billStatus, caseStatus, runningTotal } from '../case-status';
import type { Case, DailyBill } from '../types';

const bill = (overrides: Partial<DailyBill>): DailyBill => ({
  id: 'b',
  date: '2026-10-11',
  day: 3,
  itemCount: 11,
  total: 42490,
  flagCount: 0,
  openFlagCount: 0,
  ...overrides,
});

/** The prototype's case on day 3, with days 1 and 2 already added. */
const papa: Case = {
  id: 'papa-admission',
  title: "Papa's admission",
  hospital: { name: 'City Care Hospital', area: 'Andheri' },
  patient: { name: 'Ramesh Sharma', ipNumber: '20841', bed: '412' },
  admittedOn: '2026-10-09',
  dayOfStay: 3,
  members: [{ id: 'u1', name: 'Rohan Sharma', isYou: true }],
  bills: [
    bill({ id: 'b-day1', date: '2026-10-09', day: 1, itemCount: 24, total: 68490 }),
    bill({ id: 'b-day2', date: '2026-10-10', day: 2, itemCount: 37, total: 31400 }),
  ],
  recoveredAmount: 0,
};

const closed: Case = {
  ...papa,
  id: 'mummy-cataract',
  closedOn: '2026-03-13',
  recoveredAmount: 3200,
};

const withBills = (bills: DailyBill[], extra: Partial<Case> = {}): Case => ({ ...papa, bills, ...extra });

describe('caseStatus', () => {
  it("asks for today's bill when the latest bill is from an earlier day", () => {
    expect(caseStatus(papa)).toEqual({ kind: 'needsTodaysBill' });
  });

  it('counts open flags across bills', () => {
    const c = withBills([...papa.bills, bill({ flagCount: 3, openFlagCount: 3 })]);
    expect(caseStatus(c)).toEqual({ kind: 'toAsk', openFlagCount: 3 });
  });

  it("is up to date once today's flags are settled", () => {
    const c = withBills([...papa.bills, bill({ flagCount: 3, openFlagCount: 0 })]);
    expect(caseStatus(c)).toEqual({ kind: 'upToDate' });
  });

  it('reports closed cases with their recovered amount', () => {
    expect(caseStatus(closed)).toEqual({ kind: 'closed', recoveredAmount: 3200 });
  });
});

describe('runningTotal', () => {
  it('matches the prototype day 2 total', () => {
    expect(runningTotal(papa)).toBe(99890);
  });
});

describe('billStatus', () => {
  it('separates open, settled, and clean bills', () => {
    expect(billStatus(bill({ flagCount: 2, openFlagCount: 1 }))).toBe('toAsk');
    expect(billStatus(bill({ flagCount: 2, openFlagCount: 0 }))).toBe('settled');
    expect(billStatus(bill({}))).toBe('looksFine');
  });
});
