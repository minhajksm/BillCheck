/**
 * The message to the billing desk.
 *
 * Built from the flags that are still open, in whichever of the three
 * languages the family picks — which is why it is composed here and not on the
 * server: every sentence in it is translated copy.
 *
 * It asks. It never accuses: each line states what the bill says and what the
 * reference says, and lets the hospital answer.
 */

import type { TFunction } from 'i18next';

import { isReaderFlag, unitWord } from './flag-copy';
import type { Bill, Case, Flag, LineItem } from './types';
import { formatINR } from '@/lib/format';

const num = (flag: Flag, key: string): number => Number(flag.referenceDetail[key] ?? 0);
const str = (flag: Flag, key: string): string => String(flag.referenceDetail[key] ?? '');

export function openFlags(bill: Bill): Flag[] {
  return bill.flags.filter((flag) => flag.status === 'open');
}

function line(t: TFunction, flag: Flag, item: LineItem | undefined): string {
  const name = item?.name ?? '';
  if (isReaderFlag(flag)) return readerLine(t, flag, name, item);
  switch (flag.kind) {
    case 'above_mrp':
      return t(flag.referenceSource === 'nppa' ? 'message.lineAboveMrpNppa' : 'message.lineAboveMrp', {
        name,
        billed: formatINR(num(flag, 'unit_price_billed')),
        reference: formatINR(num(flag, 'unit_price_reference')),
        unit: unitWord(t, str(flag, 'unit')),
      });
    case 'duplicate':
      return t('message.lineDuplicate', {
        name,
        detail: str(flag, 'repeated_detail') || item?.detail || '',
      });
    case 'quantity':
      return t('message.lineQuantity', {
        name,
        quantity: str(flag, 'quantity'),
        unit: unitWord(t, str(flag, 'unit')),
      });
    default:
      return readerLine(t, flag, name, item);
  }
}

/**
 * A line for something the reader noticed. These ask what the charge is,
 * without claiming a reference the hospital could be shown.
 */
function readerLine(t: TFunction, flag: Flag, name: string, item: LineItem | undefined): string {
  switch (flag.kind) {
    case 'total_mismatch':
      return t('message.lineTotalMismatch', {
        summed: formatINR(Number(str(flag, 'summed'))),
        stated: formatINR(Number(str(flag, 'stated'))),
      });
    case 'duplicate_line':
      return t('message.lineDuplicateLine', {
        name,
        detail: str(flag, 'repeated_detail') || item?.detail || '',
      });
    case 'non_medical_item':
      return t('message.lineNonMedicalItem', { name });
    case 'package_overlap':
      return t('message.linePackageOverlap', { name });
    case 'date_outside_stay':
      return t('message.lineDateOutsideStay', { name, rowDate: str(flag, 'row_date') });
    default:
      return t('message.lineNoticed', { name });
  }
}

/**
 * Returns the whole message, or null when nothing is left to ask — in which
 * case the screen shows "nothing left to ask" rather than an empty message.
 */
export function composeMessage(t: TFunction, item: Case, bill: Bill): string | null {
  const open = openFlags(bill);
  if (open.length === 0) return null;

  const items = new Map(bill.lineItems.map((row) => [row.id, row]));
  const numbered = open.map(
    (flag, index) => `${index + 1}. ${line(t, flag, flag.lineItemId ? items.get(flag.lineItemId) : undefined)}`,
  );

  return [
    t('message.opening', { patient: item.patient.name, ip: item.patient.ipNumber }),
    '',
    numbered.join('\n'),
    '',
    t('message.closing'),
  ].join('\n');
}
