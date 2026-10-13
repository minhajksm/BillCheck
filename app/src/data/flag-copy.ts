/**
 * Turning a flag's facts into words.
 *
 * The API sends numbers and a reference, never a sentence, so the question a
 * family reads is composed here in their own language. Every flag must be able
 * to show what it was checked against — that is the rule the product rests on,
 * so nothing in here can produce a flag without its reference.
 */

import type { TFunction } from 'i18next';

import type { Flag, LineItem } from './types';
import { formatINR } from '@/lib/format';

/** `reference_detail` carries strings, since the API keeps money exact. */
const num = (flag: Flag, key: string): number => Number(flag.referenceDetail[key] ?? 0);
const str = (flag: Flag, key: string): string => String(flag.referenceDetail[key] ?? '');

/** "vial" -> the translated word, falling back to a neutral "units". */
export function unitWord(t: TFunction, unit: string): string {
  const key = `flags.unit${unit.charAt(0).toUpperCase()}${unit.slice(1)}`;
  const translated = t(key, { defaultValue: '' });
  return translated || t('flags.unitDefault');
}

export type FlagCopy = {
  /** The chip: the kind while open, the outcome once answered. */
  tag: string;
  /** One line under the item name. */
  short: string;
  /** Why this was flagged at all. */
  why: string;
  /** What to say at the billing desk. */
  ask: string;
  /** What the amount beside the reference means, e.g. "At MRP". */
  referenceLabel: string;
};

/** A flag the reader noticed rather than one a price list decided. */
export const isReaderFlag = (flag: Flag): boolean => flag.referenceSource === 'reader';

export function flagTag(t: TFunction, flag: Flag): string {
  if (flag.status === 'corrected') return t('flags.tagCorrected');
  if (flag.status === 'explained') return t('flags.tagExplained');
  if (isReaderFlag(flag)) return t('flags.tagNoticed');
  switch (flag.kind) {
    case 'above_mrp':
      return t('flags.tagAboveMrp');
    case 'duplicate':
      return t('flags.tagDuplicate');
    case 'quantity':
      return t('flags.tagQuantity');
    default:
      // Reader kinds are handled above; this keeps the switch total.
      return t('flags.tagNoticed');
  }
}

export function flagCopy(t: TFunction, flag: Flag, item?: LineItem): FlagCopy {
  const tag = flagTag(t, flag);
  if (isReaderFlag(flag)) return readerCopy(t, flag, tag, item);

  switch (flag.kind) {
    case 'above_mrp': {
      const unit = unitWord(t, str(flag, 'unit'));
      const billed = formatINR(num(flag, 'unit_price_billed'));
      const reference = formatINR(num(flag, 'unit_price_reference'));
      const difference = formatINR(num(flag, 'unit_price_billed') - num(flag, 'unit_price_reference'));
      // The NPPA ceiling is the legal maximum; the printed MRP is a different
      // argument to make at the counter, so the wording differs.
      const nppa = flag.referenceSource === 'nppa';
      return {
        tag,
        short: t(nppa ? 'flags.shortAboveMrpNppa' : 'flags.shortAboveMrpMrp', { billed, reference, unit }),
        why: t(nppa ? 'flags.whyAboveMrpNppa' : 'flags.whyAboveMrpMrp', { difference, unit }),
        ask: t('flags.askAboveMrp'),
        referenceLabel: t(nppa ? 'flags.referenceAtCeiling' : 'flags.referenceAtMrp'),
      };
    }
    case 'duplicate': {
      const detail = str(flag, 'repeated_detail') || item?.detail || '';
      return {
        tag,
        short: t('flags.shortDuplicate', { detail }),
        why: t('flags.whyDuplicate', { detail }),
        ask: t('flags.askDuplicate', { detail }),
        referenceLabel: t('flags.referenceOneEntry'),
      };
    }
    case 'quantity': {
      const unit = unitWord(t, str(flag, 'unit'));
      const usual = str(flag, 'usual_max_per_day');
      return {
        tag,
        short: t('flags.shortQuantity', { usual, unit }),
        why: t('flags.whyQuantity'),
        ask: t('flags.askQuantity', { unit }),
        referenceLabel: t('flags.referenceForUsual', { usual, unit }),
      };
    }
    default:
      // Reader kinds return above.
      return readerCopy(t, flag, tag, item);
  }
}

/**
 * Copy for something the reader noticed.
 *
 * These have no published reference behind them, so every one of them says so,
 * and none claims an amount it can't defend. The wording stays a question even
 * where the rows confirmed the claim, because the figures it rests on were
 * read off a photograph.
 */
/**
 * What the reader wrote about this flag, in the family's language.
 *
 * This is the one line on screen the reader writes rather than us: specific to
 * the bill, and so not reviewable the way the rest of the copy is. It is
 * written under the rules in the prompt -- what the page shows, no verdict, no
 * reference it doesn't have -- and an empty one falls back to our own wording,
 * so a reader that says nothing costs the family nothing.
 */
function readerWhy(t: TFunction, flag: Flag): string | null {
  const language = (t('common.languageCode') || 'en').slice(0, 2);
  return str(flag, `why_${language}`) || str(flag, 'why_en') || null;
}

function readerCopy(t: TFunction, flag: Flag, tag: string, item?: LineItem): FlagCopy {
  const written = writtenReaderCopy(t, flag, tag, item);
  const why = readerWhy(t, flag);
  // Only "why" is the reader's. The heading and the question a family repeats
  // at the counter stay ours, written once and translated once.
  return why ? { ...written, why } : written;
}

function writtenReaderCopy(t: TFunction, flag: Flag, tag: string, item?: LineItem): FlagCopy {
  const referenceLabel = t('flags.noticedBy');

  switch (flag.kind) {
    case 'total_mismatch':
      return {
        tag,
        short: t('flags.shortTotalMismatch', {
          summed: formatINR(num(flag, 'summed')),
          stated: formatINR(num(flag, 'stated')),
        }),
        why: t('flags.whyTotalMismatch', { difference: formatINR(num(flag, 'difference')) }),
        ask: t('flags.askTotalMismatch'),
        referenceLabel,
      };
    case 'duplicate_line': {
      const detail = str(flag, 'repeated_detail') || item?.detail || '';
      return {
        tag,
        short: t('flags.shortDuplicateLine', { detail }),
        why: t('flags.whyDuplicateLine'),
        ask: t('flags.askDuplicateLine'),
        referenceLabel,
      };
    }
    case 'date_outside_stay':
      return {
        tag,
        short: t('flags.shortDateOutsideStay', { rowDate: str(flag, 'row_date') }),
        why: t('flags.whyDateOutsideStay', { admittedOn: str(flag, 'admitted_on') }),
        ask: t('flags.askDateOutsideStay'),
        referenceLabel,
      };
    case 'unit_price_high': {
      // The reader's own estimate, shown as an expectation and never as a
      // reference. Without one, the line says only that it looks high.
      const expected = str(flag, 'expected');
      const unitPrice = str(flag, 'unit_price');
      return {
        tag,
        short:
          expected && unitPrice
            ? t('flags.shortUnitPriceHighExpected', {
                unitPrice: formatINR(Number(unitPrice)),
                expected: formatINR(Number(expected)),
              })
            : t('flags.shortUnitPriceHigh'),
        why: t('flags.whyUnitPriceHigh'),
        ask: t('flags.askUnitPriceHigh'),
        referenceLabel,
      };
    }
    case 'quantity_high':
      return {
        tag,
        short: t('flags.shortQuantityHigh'),
        why: t('flags.whyQuantityHigh'),
        ask: t('flags.askQuantityHigh'),
        referenceLabel,
      };
    case 'package_overlap':
      return {
        tag,
        short: t('flags.shortPackageOverlap'),
        why: t('flags.whyPackageOverlap'),
        ask: t('flags.askPackageOverlap'),
        referenceLabel,
      };
    case 'service_charge_on_room':
      return {
        tag,
        short: t('flags.shortServiceCharge'),
        why: t('flags.whyServiceCharge'),
        ask: t('flags.askServiceCharge'),
        referenceLabel,
      };
    case 'same_test_two_names':
      return {
        tag,
        short: t('flags.shortSameTestTwoNames'),
        why: t('flags.whySameTestTwoNames'),
        ask: t('flags.askSameTestTwoNames'),
        referenceLabel,
      };
    case 'non_medical_item':
      return {
        tag,
        short: t('flags.shortNonMedicalItem'),
        why: t('flags.whyNonMedicalItem'),
        ask: t('flags.askNonMedicalItem'),
        referenceLabel,
      };
    // A kind with no wording of its own yet. It must not borrow another
    // kind's: telling a family a tax line "isn't part of the treatment" is
    // simply false. This says only what we actually know — that we noticed it.
    default:
      return {
        tag,
        short: t('flags.shortNoticed'),
        why: t('flags.whyNoticed'),
        ask: t('flags.askNoticed'),
        referenceLabel,
      };
  }
}

/** The line under a flag in the list: what the difference means right now. */
export function flagAmountLine(t: TFunction, flag: Flag): string | null {
  // A judgment of degree has no defensible figure, so it shows none.
  if (flag.excess === 0) return null;
  const amount = formatINR(flag.excess);
  if (flag.status === 'corrected') return t('flags.recovered', { amount });
  if (flag.status === 'explained') return t('flags.explainedByHospital', { amount });
  return t('flags.overReference', { amount });
}
