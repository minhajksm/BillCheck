/**
 * What to tell the family when a bill can't be checked.
 *
 * Each failure has its own fix (find signal, retake one page, split the bill),
 * so one catch-all "try better light" sends people to fix the wrong thing.
 */

import type { TFunction } from 'i18next';

import { ApiError } from '@/lib/api';

/** The heading over the message: which kind of failure this is. */
export function scanErrorTitle(t: TFunction, error: unknown, kind: 'bill' | 'lab'): string {
  if (error instanceof ApiError && error.code === 'not_a_bill') return t('scan.notABillTitle');
  if (error instanceof ApiError && error.code === 'not_a_lab_report')
    return t('lab.errors.notALabReportTitle');
  return kind === 'lab' ? t('lab.errors.title') : t('scan.errorTitle');
}

export function scanErrorMessage(t: TFunction, error: unknown, maxPages: number): string {
  if (!(error instanceof ApiError)) return t('scan.errorUnknown');
  switch (error.code) {
    // The pages were fine and are something else, so the advice is where
    // this page does belong -- never to take the photo again. The page's own
    // title is quoted where the reader found one.
    case 'not_a_bill':
      return error.document ? t('scan.notABillNamed', { document: error.document }) : t('scan.notABill');
    case 'not_a_lab_report':
      return error.document
        ? t('lab.errors.notALabReportNamed', { document: error.document })
        : t('lab.errors.not_a_lab_report');
    case 'network':
      return t('scan.errorNetwork');
    case 'page_too_large':
      return t('scan.errorTooLarge');
    case 'empty_page':
    case 'unsupported_page':
      return t('scan.errorUnsupported');
    case 'too_many_pages':
      return t('scan.errorTooMany', { max: maxPages });
    case 'upload_limit':
      return t('scan.errorLimit');
    case 'unreadable_bill':
      return t('scan.failed');
    // A lab report fails the same ways a bill does, bar these two.
    case 'unreadable_lab_report':
      return t('lab.errors.unreadable_lab_report');
    case 'lab_consent_required':
      return t('lab.errors.lab_consent_required');
    default:
      // A proxy in front of the API can refuse a big upload with its own 413.
      return error.status === 413 ? t('scan.errorTooLarge') : t('scan.errorUnknown');
  }
}
