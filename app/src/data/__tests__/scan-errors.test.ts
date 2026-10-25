import { describe, expect, it } from '@jest/globals';

import i18n from '@/i18n';
import { ApiError, type ApiErrorCode } from '@/lib/api';

import { scanErrorMessage, scanErrorTitle } from '../scan-errors';

const t = i18n.t.bind(i18n);
const message = (code: ApiErrorCode, status = 400) => scanErrorMessage(t, new ApiError(code, status), 12);

describe('scanErrorMessage', () => {
  it('tells each failure apart', () => {
    expect(message('network', 0)).toMatch(/internet/);
    expect(message('page_too_large', 413)).toMatch(/too large/);
    expect(message('unsupported_page', 415)).toMatch(/JPEG or PNG/);
    expect(message('too_many_pages')).toBe('A bill can have up to 12 pages. Remove some and check them as a second bill.');
    expect(message('upload_limit', 429)).toMatch(/tomorrow/);
    expect(message('unreadable_bill', 422)).toMatch(/better light/);
  });

  it('only blames the light when the bill really could not be read', () => {
    const codes: ApiErrorCode[] = ['network', 'page_too_large', 'unsupported_page', 'too_many_pages', 'upload_limit', 'unknown'];
    for (const code of codes) expect(message(code)).not.toMatch(/better light/);
  });

  it('treats a bare 413 from a proxy as too large', () => {
    expect(message('unknown', 413)).toMatch(/too large/);
  });

  it('falls back to a general message', () => {
    expect(scanErrorMessage(t, new Error('boom'), 12)).toMatch(/Something went wrong/);
  });
});

describe('a page that reads fine and is something else', () => {
  const wrong = (code: ApiErrorCode, document?: string) => new ApiError(code, 422, undefined, document);

  it('says what it looks like, by its own title, and where it does belong', () => {
    const error = wrong('not_a_lab_report', 'OB 2/3 Trimester Scan Report');

    expect(scanErrorTitle(t, error, 'lab')).toBe("This doesn't look like a lab report");
    expect(scanErrorMessage(t, error, 12)).toMatch(/^It looks like “OB 2\/3 Trimester Scan Report”\./);
    expect(scanErrorMessage(t, error, 12)).toMatch(/Scan or upload bill/);
  });

  it('still says something useful with no title to quote', () => {
    const error = wrong('not_a_bill');

    expect(scanErrorTitle(t, error, 'bill')).toBe("This doesn't look like a hospital bill");
    expect(scanErrorMessage(t, error, 12)).toMatch(/^FairCare checks itemised hospital bills/);
  });

  it('never tells them to retake a photo that was fine', () => {
    for (const code of ['not_a_bill', 'not_a_lab_report'] as const) {
      expect(scanErrorMessage(t, wrong(code, 'Discharge Summary'), 12)).not.toMatch(/better light|try again/i);
    }
  });

  it('heads any other failure as a failure to check or explain', () => {
    expect(scanErrorTitle(t, new ApiError('unreadable_bill', 422), 'bill')).toBe("Couldn't check this bill");
    expect(scanErrorTitle(t, new ApiError('network', 0), 'lab')).toBe("Couldn't explain this report");
  });
});
