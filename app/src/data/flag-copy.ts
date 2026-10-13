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

export function flagTag(t: TFunction, flag: Flag): string {
  if (flag.status === 'corrected') return t('flags.tagCorrected');
  if (flag.status === 'explained') return t('flags.tagExplained');
  switch (flag.kind) {
    case 'above_mrp':
      return t('flags.tagAboveMrp');
    case 'duplicate':
      return t('flags.tagDuplicate');
    case 'quantity':
      return t('flags.tagQuantity');
  }
}

export function flagCopy(t: TFunction, flag: Flag, item?: LineItem): FlagCopy {
  const tag = flagTag(t, flag);

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
  }
}

/** The line under a flag in the list: what the difference means right now. */
export function flagAmountLine(t: TFunction, flag: Flag): string {
  const amount = formatINR(flag.excess);
  if (flag.status === 'corrected') return t('flags.recovered', { amount });
  if (flag.status === 'explained') return t('flags.explainedByHospital', { amount });
  return t('flags.overReference', { amount });
}
