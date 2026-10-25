/** Dates are calendar dates in "YYYY-MM-DD" form. Amounts are whole rupees. */

export type Member = {
  id: string;
  name: string;
  isYou: boolean;
};

export type DailyBill = {
  id: string;
  date: string;
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
  /** Missing where the bill printed no admission date and nobody has said. */
  admittedOn?: string;
  closedOn?: string;
  members: Member[];
  /** Whether you started this case. Only you can delete it. */
  isOwner: boolean;
  /** Oldest first. */
  bills: DailyBill[];
  recoveredAmount: number;
};

/**
 * What kind of charge a line is, as the reader classified it while reading
 * the bill. The report groups by this. Must match `CATEGORY_ORDER` in
 * `api/analysis.py`; `api/tests/test_categories.py` checks that it does.
 */
export type LineCategory =
  | 'room_and_nursing'
  | 'professional_fees'
  | 'procedure_or_ot'
  | 'investigation'
  | 'pharmacy_drug'
  | 'consumable_disposable'
  | 'implant_device'
  | 'equipment_charge'
  | 'non_medical'
  | 'unclassified';

/** One row of the itemized bill, as printed. */
export type LineItem = {
  id: string;
  position: number;
  name: string;
  detail?: string;
  quantity?: number;
  /** Gross, as the line prints it. */
  amount: number;
  /** The same line after the bill's discount, where it prints one. */
  netAmount?: number;
  category: LineCategory;
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
  // A line charging more than its own quantity x rate. Raised by the API's
  // arithmetic, never by the reader.
  | 'line_math'
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

/**
 * One sum on the bill, worked out by the API from the bill's own figures.
 * Only the fields its kind uses are set. Must match `CheckOut` in
 * `api/models.py`.
 */
export type Check = {
  kind: 'lines' | 'subtotal' | 'discount' | 'payable' | 'rounding' | 'paid' | 'balance';
  /** "mismatch": the bill asks for more than its own numbers give. "note": never a question. */
  status: 'ok' | 'mismatch' | 'note';
  amount?: number;
  expected?: number;
  printed?: number;
  checked?: number;
  of?: number;
  count?: number;
  percent?: number;
  /** For a discount: the same rate taken off every line. */
  uniform?: boolean;
  /** The lines a "lines" check found over quantity x rate, as the bill numbers them. */
  positions: number[];
};

/** A deposit, advance or receipt, as the bill lists it. */
export type Payment = { date: string; mode: string; amount: number };

/** One day's bill with everything on it. */
export type Bill = {
  id: string;
  caseId: string;
  date: string;
  pageCount: number;
  /** What the lines come to, before any discount. */
  subtotal: number;
  /** The discount the bill prints across the whole of it, where it prints one. */
  discount?: number;
  /** What the hospital is asking for: the sub-total less the discount. */
  total: number;
  /** The bill's own arithmetic. Empty on bills read before it was checked. */
  checks: Check[];
  payments: Payment[];
  /** What has been paid, where the bill or its deposits say. */
  paid?: number;
  /** Still due. 0 is "nothing left to pay"; missing, the bill doesn't say. */
  balance?: number;
  lineItems: LineItem[];
  flags: Flag[];
};
