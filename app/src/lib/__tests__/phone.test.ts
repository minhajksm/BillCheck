import { describe, expect, it } from '@jest/globals';

import { formatPhone, isValidMobile, nationalDigits } from '../phone';

describe('nationalDigits', () => {
  it.each([
    ['98765 43210', '9876543210'],
    ['+91 98765-43210', '9876543210'],
    ['+919876543210', '9876543210'],
    ['919876543210', '9876543210'],
    ['09876543210', '9876543210'],
    ['98765432109999', '9876543210'],
    ['98a7', '987'],
  ])('keeps the 10 digits of %p', (input, expected) => {
    expect(nationalDigits(input)).toBe(expected);
  });
});

describe('isValidMobile', () => {
  it('accepts 10 digits starting with 6-9', () => {
    expect(isValidMobile('9876543210')).toBe(true);
    expect(isValidMobile('6000000000')).toBe(true);
  });

  it('rejects anything else', () => {
    expect(isValidMobile('5876543210')).toBe(false);
    expect(isValidMobile('987654321')).toBe(false);
    expect(isValidMobile('')).toBe(false);
  });
});

describe('formatPhone', () => {
  it('groups the number the way it is usually written', () => {
    expect(formatPhone('+919876543210')).toBe('+91 98765 43210');
    expect(formatPhone('9876543210')).toBe('+91 98765 43210');
  });
});
