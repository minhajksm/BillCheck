/**
 * The phone field holds just the 10 national digits; "+91" is shown as a
 * fixed prefix. These helpers keep that state clean whatever gets typed
 * or pasted.
 */

/** Keeps the 10 national digits from whatever was typed or pasted. */
export function nationalDigits(input: string): string {
  let digits = input.replace(/\D/g, '');
  if (input.trim().startsWith('+91') || (digits.length === 12 && digits.startsWith('91'))) {
    digits = digits.slice(2);
  } else if (digits.length === 11 && digits.startsWith('0')) {
    digits = digits.slice(1);
  }
  return digits.slice(0, 10);
}

/** Indian mobile numbers are 10 digits starting with 6, 7, 8, or 9. */
export function isValidMobile(digits: string): boolean {
  return /^[6-9]\d{9}$/.test(digits);
}

/** "9876543210" or "+919876543210" -> "+91 98765 43210". */
export function formatPhone(phone: string): string {
  const digits = nationalDigits(phone);
  return digits.length === 10 ? `+91 ${digits.slice(0, 5)} ${digits.slice(5)}` : phone;
}
