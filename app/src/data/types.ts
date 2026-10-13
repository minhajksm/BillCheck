/** Dates are calendar dates in "YYYY-MM-DD" form. Amounts are whole rupees. */

export type Member = {
  id: string;
  name: string;
  isYou: boolean;
};

export type DailyBill = {
  id: string;
  date: string;
  /** Day of the stay this bill covers. Day 1 is the admission day. */
  day: number;
  itemCount: number;
  total: number;
  /** Flags raised by the audit. */
  flagCount: number;
  /** Flags still open, not yet corrected or explained by the hospital. */
  openFlagCount: number;
};

export type Case = {
  id: string;
  title: string;
  hospital: { name: string; area: string };
  patient: { name: string; ipNumber: string; bed: string };
  admittedOn: string;
  /** Current day of the stay, counting the admission day as day 1. */
  dayOfStay: number;
  closedOn?: string;
  members: Member[];
  /** Oldest first. */
  bills: DailyBill[];
  recoveredAmount: number;
};

/** One row of the itemized bill, as printed. */
export type LineItem = {
  id: string;
  position: number;
  name: string;
  detail?: string;
  quantity?: number;
  amount: number;
};

export type FlagKind = 'above_mrp' | 'duplicate' | 'quantity';
export type FlagLevel = 'red' | 'amber';
export type FlagStatus = 'open' | 'corrected' | 'explained';

/**
 * A charge worth asking about. The API sends facts only; the copy a family
 * reads is composed here, in their own language.
 */
export type Flag = {
  id: string;
  position: number;
  lineItemId?: string;
  kind: FlagKind;
  level: FlagLevel;
  status: FlagStatus;
  billed: number;
  referenceAmount: number;
  referenceSource: string;
  /** The reference's own numbers: unit price, usual quantity, and so on. */
  referenceDetail: Record<string, string | number>;
  excess: number;
};

/** One day's bill with everything on it. */
export type Bill = {
  id: string;
  caseId: string;
  date: string;
  day: number;
  pageCount: number;
  total: number;
  lineItems: LineItem[];
  flags: Flag[];
};
