import { beforeAll, describe, expect, it } from '@jest/globals';

import i18n from '@/i18n';
import { flagCopy } from '../flag-copy';
import type { Flag, FlagKind } from '../types';

beforeAll(async () => {
  await i18n.changeLanguage('en');
});

const readerFlag = (kind: FlagKind): Flag =>
  ({
    id: `f-${kind}`,
    position: 1,
    lineItemId: 'li-1',
    kind,
    level: 'amber',
    status: 'open',
    billed: 6500,
    referenceAmount: 0,
    referenceSource: 'reader',
    referenceDetail: { confidence: 'medium' },
    excess: 0,
  }) as never as Flag;

describe('a kind with no wording of its own', () => {
  // The reader can report more kinds than the app has copy for. What it must
  // never do is borrow another kind's words: telling a family that a tax line
  // "isn't part of the treatment" is simply false, and it is the sentence they
  // would repeat at the counter.
  const borrowed = ['tax_on_exempt_item', 'icu_rate_on_ward_day', 'rounded_amounts'] as const;

  it.each(borrowed)('does not tell the family %s is not treatment', (kind) => {
    const copy = flagCopy(i18n.getFixedT('en'), readerFlag(kind));

    expect(copy.short).not.toMatch(/part of the treatment/i);
    expect(copy.short).toBe('This line is worth asking about.');
    expect(copy.ask).toBe('Ask the billing desk what this charge is for.');
  });

  it.each(['hi', 'mr'])('says so in %s too, never in English', (language) => {
    const copy = flagCopy(i18n.getFixedT(language), readerFlag('tax_on_exempt_item'));

    expect(copy.short).not.toMatch(/[a-z]{4}/i);
    expect(copy.short.length).toBeGreaterThan(10);
  });

  it('still words the kinds it does know specifically', () => {
    const copy = flagCopy(i18n.getFixedT('en'), readerFlag('non_medical_item'));
    expect(copy.short).toMatch(/part of the treatment/i);
  });
});
