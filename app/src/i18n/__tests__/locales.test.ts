import { describe, expect, it } from '@jest/globals';

import en from '../locales/en.json';
import hi from '../locales/hi.json';
import mr from '../locales/mr.json';

type Tree = { [key: string]: string | string[] | Tree };

function flatten(tree: Tree, prefix = ''): Record<string, string | string[]> {
  return Object.entries(tree).reduce<Record<string, string | string[]>>((out, [key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string' || Array.isArray(value)) out[path] = value;
    else Object.assign(out, flatten(value, path));
    return out;
  }, {});
}

const variables = (value: string | string[]) =>
  [...String(value).matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort();

const english = flatten(en);

describe.each([
  ['hi', hi],
  ['mr', mr],
])('%s translations', (_, locale) => {
  const translated = flatten(locale);

  it('has exactly the same keys as English', () => {
    expect(Object.keys(translated).sort()).toEqual(Object.keys(english).sort());
  });

  it('uses the same {{variables}} as English', () => {
    for (const [key, value] of Object.entries(english)) {
      expect({ key, vars: variables(translated[key]) }).toEqual({ key, vars: variables(value) });
    }
  });

  it('has no empty strings', () => {
    for (const [key, value] of Object.entries(translated)) {
      expect({ key, empty: String(value).trim() === '' }).toEqual({ key, empty: false });
    }
  });

  it('names all twelve months', () => {
    expect(locale.dates.monthsShort).toHaveLength(12);
    expect(locale.dates.monthsLong).toHaveLength(12);
  });
});
