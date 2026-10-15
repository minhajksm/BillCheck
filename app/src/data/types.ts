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
  /** Whether you started this case. Only you can delete it. */
  isOwner: boolean;
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

/** Checked against a published price list, so the reference can be shown. */
export type CitedFlagKind = 'above_mrp' | 'duplicate' | 'quantity';

/**
 * Noticed by the reader while reading the bill. Some were re-checked against
 * the rows; none has a published reference behind it, so none is ever red.
 */
export type ReaderFlagKind =
  // What the reader's analysis produces now: one kind, carrying its own rule,
  // the evidence it quoted and the sentence it wrote for the family.
  | 'analysis_finding'
  // Contradictions on the page. `date_outside_stay` is still raised by the
  // stay check the API makes itself. The rest are kinds older bills carry.
  | 'total_mismatch'
  | 'duplicate_line'
  | 'equipment_hours_exceed_stay'
  | 'date_outside_stay'
  | 'implant_without_identity'
  | 'rounded_amounts'
  | 'advance_not_deducted'
  // What an experienced eye notices. Nothing can confirm these.
  | 'unit_price_high'
  | 'branded_drug_margin'
  | 'capped_item_above_ceiling'
  | 'non_medical_item'
  | 'package_overlap'
  | 'nursing_billed_with_room'
  | 'service_charge_on_room'
  | 'quantity_high'
  | 'visits_in_one_day'
  | 'same_test_two_names'
  | 'same_drug_twice_sources'
  | 'room_rate_vs_ward'
  | 'icu_rate_on_ward_day'
  | 'tax_on_exempt_item';

export type FlagKind = CitedFlagKind | ReaderFlagKind;
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
