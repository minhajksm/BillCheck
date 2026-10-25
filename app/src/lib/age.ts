/**
 * Age in whole years, as the API works it out: a birthday not yet reached
 * this year doesn't count. Used for the figure shown while a date of birth is
 * being typed; what is saved and shown afterwards is the API's own.
 *
 * Returns undefined for anything that isn't a real date on or before today.
 */
export function ageOn(dateOfBirth: string, today: Date): number | undefined {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateOfBirth);
  if (!match) return undefined;
  const [year, month, day] = match.slice(1).map(Number);
  // Rejects 1958-02-30 and the like, which Date would quietly roll over.
  const born = new Date(Date.UTC(year, month - 1, day));
  if (born.getUTCMonth() !== month - 1 || born.getUTCDate() !== day) return undefined;

  const [nowYear, nowMonth, nowDay] = [today.getFullYear(), today.getMonth() + 1, today.getDate()];
  const age = nowYear - year - (nowMonth < month || (nowMonth === month && nowDay < day) ? 1 : 0);
  return age >= 0 && year >= 1900 ? age : undefined;
}
