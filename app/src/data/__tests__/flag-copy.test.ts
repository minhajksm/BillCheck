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

describe("the reader's own explanation", () => {
  const withWhy = (detail: Record<string, string>): Flag =>
    ({
      ...readerFlag('nursing_billed_with_room'),
      referenceDetail: { confidence: 'medium', ...detail },
    }) as never as Flag;

  it('is what the family reads, in place of our wording', () => {
    const copy = flagCopy(i18n.getFixedT('en'), withWhy({ why_en: 'Nursing is billed separately here.' }));
    expect(copy.why).toBe('Nursing is billed separately here.');
  });

  it('is read in the language the family is using', () => {
    const detail = { why_en: 'In English.', why_hi: 'हिंदी में।', why_mr: 'मराठीत.' };
    expect(flagCopy(i18n.getFixedT('hi'), withWhy(detail)).why).toBe('हिंदी में।');
    expect(flagCopy(i18n.getFixedT('mr'), withWhy(detail)).why).toBe('मराठीत.');
  });

  it('falls back to our own wording when the reader wrote none', () => {
    const copy = flagCopy(i18n.getFixedT('en'), withWhy({}));
    expect(copy.why).toBe(
      'We noticed this while reading the bill. It may well be correct — the billing desk can tell you what it covers.',
    );
  });

  it('never replaces the question the family asks at the counter', () => {
    // The reader writes why. What they say out loud stays ours, written once
    // and translated once, so a reader that goes wrong cannot put words in
    // their mouth.
    const copy = flagCopy(i18n.getFixedT('en'), withWhy({ why_en: 'Something the reader wrote.' }));
    expect(copy.ask).toBe('Ask the billing desk what this charge is for.');
  });
});

describe('the lines a flag is about', () => {
  const onLines = (line_numbers: string): Flag =>
    ({
      ...readerFlag('duplicate_line'),
      referenceDetail: { confidence: 'medium', why_en: 'The same room charge appears twice.', line_numbers },
    }) as never as Flag;

  it('names a single line', () => {
    expect(flagCopy(i18n.getFixedT('en'), onLines('7')).why).toBe(
      'The same room charge appears twice. (Line 7)',
    );
  });

  it('names every line a duplicate is spread across', () => {
    expect(flagCopy(i18n.getFixedT('en'), onLines('2,4')).why).toBe(
      'The same room charge appears twice. (Lines 2 and 4)',
    );
    expect(flagCopy(i18n.getFixedT('en'), onLines('2,4,6')).why).toBe(
      'The same room charge appears twice. (Lines 2, 4 and 6)',
    );
  });

  it('says it in the language the family is using', () => {
    // A family holds the bill up beside this, so the line numbers have to
    // read as part of the sentence, not as an English aside.
    const written = 'The same room charge appears twice.';
    for (const language of ['hi', 'mr']) {
      const tail = flagCopy(i18n.getFixedT(language), onLines('2,4')).why.slice(written.length);
      expect(tail).toMatch(/2/);
      expect(tail).toMatch(/4/);
      expect(tail.replace(/[\d\s(),.]/g, '')).not.toMatch(/[a-z]/i);
    }
  });

  it('says nothing at all when the flag carries no lines', () => {
    // A flag without them is a flag we could not place on the page. Inventing
    // a line number would send a family to the wrong row at the counter.
    const copy = flagCopy(i18n.getFixedT('en'), onLines(''));
    expect(copy.why).toBe('The same room charge appears twice.');
  });
});
