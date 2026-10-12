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
