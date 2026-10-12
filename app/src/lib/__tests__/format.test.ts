import { describe, expect, it } from '@jest/globals';

import { formatINR, initials, parseCalendarDate } from '../format';

describe('formatINR', () => {
  it.each([
    [0, '₹0'],
    [950, '₹950'],
    [2500, '₹2,500'],
    [31400, '₹31,400'],
    [142380, '₹1,42,380'],
    [1000000, '₹10,00,000'],
    [12345678, '₹1,23,45,678'],
    [-6660, '-₹6,660'],
    [1840.5, '₹1,840.50'],
    [99.999, '₹100'],
  ])('formats %p as %p', (amount, expected) => {
    expect(formatINR(amount)).toBe(expected);
  });
});

describe('parseCalendarDate', () => {
  it('reads the date without shifting it by time zone', () => {
    expect(parseCalendarDate('2026-10-09')).toEqual({ year: 2026, month: 10, day: 9 });
  });

  it('rejects anything that is not YYYY-MM-DD', () => {
    expect(() => parseCalendarDate('9 Oct 2026')).toThrow();
  });
});

describe('initials', () => {
  it('uses the first and last name', () => {
    expect(initials('Rohan Sharma')).toBe('RS');
    expect(initials('Anita K. Sharma')).toBe('AS');
    expect(initials('anita')).toBe('A');
  });
});
