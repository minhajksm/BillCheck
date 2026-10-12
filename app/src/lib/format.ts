/**
 * Formats rupees with Indian digit grouping: 142380 -> "₹1,42,380".
 * Done by hand so output doesn't depend on the device's Intl data.
 * Whole rupees print without decimals; anything with paise prints two places.
 */
export function formatINR(amount: number): string {
  const sign = amount < 0 ? '-' : '';
  const abs = Math.abs(amount);
  const hasPaise = Math.round(abs * 100) % 100 !== 0;
  const [whole, paise] = abs.toFixed(hasPaise ? 2 : 0).split('.');

  const lastThree = whole.slice(-3);
  const rest = whole.slice(0, -3);
  const grouped = rest ? `${rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',')},${lastThree}` : lastThree;

  return `${sign}₹${grouped}${paise ? `.${paise}` : ''}`;
}

export type CalendarDate = { year: number; month: number; day: number };

/**
 * Parses a "YYYY-MM-DD" string as a calendar date. Avoids `new Date()` so a
 * bill dated 11 Oct never shows as 10 Oct because of the device's time zone.
 */
export function parseCalendarDate(iso: string): CalendarDate {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) {
    throw new Error(`Expected a YYYY-MM-DD date, got "${iso}"`);
  }
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
}

/** Initials for an avatar: "Rohan Sharma" -> "RS". */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts;
  return letters.map((p) => p[0]?.toUpperCase() ?? '').join('');
}
