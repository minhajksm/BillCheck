import { beforeAll, describe, expect, it } from '@jest/globals';

import i18n from '@/i18n';
import { SAMPLE_BILL, SAMPLE_CASE } from '@/test-utils/fake-api';
import { toBill, toCase } from '../cases-api';
import { composeMessage, openFlags } from '../message';
import type { Bill } from '../types';

const item = toCase(SAMPLE_CASE as never);
const bill = (): Bill => toBill(structuredClone(SAMPLE_BILL) as never);

beforeAll(async () => {
  await i18n.changeLanguage('en');
});

describe('the message to the billing desk', () => {
  it('names the patient and asks about every open flag', () => {
    const message = composeMessage(i18n.getFixedT('en'), item, bill());

    expect(message).toContain('Ramesh Sharma');
    expect(message).toContain('IP no. 20841');
    expect(message).toContain('1. Inj. Meropenem 1g is billed at ₹2,950 per vial. The listed MRP for it is ₹1,840. Could you show me the MRP printed on the pack?');
    expect(message).toContain('2. 80 pairs of Surgical gloves are billed for one day.');
    expect(message).toContain('Please share a corrected bill or an explanation.');
  });

  it('asks, and never accuses', () => {
    const message = composeMessage(i18n.getFixedT('en'), item, bill()) ?? '';

    for (const word of ['fraud', 'cheat', 'illegal', 'scam', 'overcharging you', 'wrong']) {
      expect(message.toLowerCase()).not.toContain(word);
    }
    expect(message).toContain('Could you help me understand');
  });

  it('leaves out questions the hospital has already answered', () => {
    const answered = bill();
    answered.flags[0].status = 'corrected';
    const message = composeMessage(i18n.getFixedT('en'), item, answered) ?? '';

    expect(message).not.toContain('Meropenem');
    expect(message).toContain('Surgical gloves');
    expect(message).toContain('1. 80 pairs');
  });

  it('returns nothing when every question is settled', () => {
    const settled = bill();
    settled.flags.forEach((flag) => (flag.status = 'explained'));

    expect(openFlags(settled)).toHaveLength(0);
    expect(composeMessage(i18n.getFixedT('en'), item, settled)).toBeNull();
  });

  it.each([
    ['hi', 'मैं मरीज़ Ramesh Sharma', 'धन्यवाद'],
    ['mr', 'मी रुग्ण Ramesh Sharma', 'धन्यवाद'],
  ])('is written in %s when that language is picked', (language, opening, closing) => {
    const message = composeMessage(i18n.getFixedT(language), item, bill()) ?? '';

    // The sentence is translated; the patient's name is not. It has to match
    // the admission slip the billing desk is holding.
    expect(message).toContain(opening);
    expect(message).toContain(closing);
    // Amounts keep Indian digit grouping whatever the language.
    expect(message).toContain('₹2,950');
  });

  it('does not change the app language when composing in another one', () => {
    composeMessage(i18n.getFixedT('mr'), item, bill());
    expect(i18n.language).toBe('en');
  });
});

describe('questions the reader noticed', () => {
  const readerFlag = (kind: string, extra: Record<string, string> = {}) => ({
    id: `f-${kind}`,
    position: 9,
    line_item_id: 'li-1',
    kind,
    level: 'amber',
    status: 'open',
    billed: 6500,
    reference_amount: 0,
    reference_source: 'reader',
    reference_detail: { confidence: 'medium', ...extra },
    excess: 0,
  });

  const withReader = (kind: string, extra: Record<string, string> = {}): Bill => {
    const raw = structuredClone(SAMPLE_BILL) as never as { flags: unknown[] };
    raw.flags = [readerFlag(kind, extra)];
    return toBill(raw as never);
  };

  it('asks about an item the reader noticed', () => {
    const message = composeMessage(i18n.getFixedT('en'), item, withReader('non_medical_item')) ?? '';
    expect(message).toContain("Room rent, twin sharing doesn't look like part of the treatment");
  });

  it('never claims a reference it does not have', () => {
    const message = composeMessage(i18n.getFixedT('en'), item, withReader('unit_price_high')) ?? '';

    expect(message).toContain('Could you explain what the charge for');
    for (const word of ['MRP', 'NPPA', 'ceiling', 'listed']) {
      expect(message).not.toContain(word);
    }
  });

  it('puts the arithmetic in the message when the rows were checked', () => {
    const message =
      composeMessage(
        i18n.getFixedT('en'),
        item,
        withReader('total_mismatch', { summed: '38290', stated: '42490' }),
      ) ?? '';

    expect(message).toContain('add up to ₹38,290');
    expect(message).toContain('total shows ₹42,490');
  });

  it.each(['hi', 'mr'])('asks in %s too', (language) => {
    const message = composeMessage(i18n.getFixedT(language), item, withReader('non_medical_item')) ?? '';
    expect(message).not.toMatch(/doesn't look like part of the treatment/);
    expect(message.length).toBeGreaterThan(40);
  });
});
