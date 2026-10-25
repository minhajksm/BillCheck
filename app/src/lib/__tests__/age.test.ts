import { describe, expect, it } from '@jest/globals';

import { ageOn } from '../age';

describe('age from a date of birth', () => {
  const today = new Date(2026, 2, 14); // 14 March 2026

  it('counts a birthday only once it has come', () => {
    expect(ageOn('1958-03-15', today)).toBe(67);
    expect(ageOn('1958-03-14', today)).toBe(68);
    expect(ageOn('1958-01-01', today)).toBe(68);
  });

  it('is nothing for a date that is not one', () => {
    for (const input of ['', '14/03/1958', '1958-3-14', '1958-02-30', '2027-01-01', '1850-01-01']) {
      expect({ input, age: ageOn(input, today) }).toEqual({ input, age: undefined });
    }
  });

  it('is 0 in the first year', () => {
    expect(ageOn('2026-01-01', today)).toBe(0);
  });
});
