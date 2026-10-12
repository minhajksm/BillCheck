import type { TFunction } from 'i18next';

import { ApiError } from '@/lib/api';

/** Turns an API failure into translated copy for the sign-in screens. */
export function authErrorMessage(t: TFunction, error: unknown): string {
  const code = error instanceof ApiError ? error.code : 'unknown';
  switch (code) {
    case 'otp_cooldown':
      return t('auth.errors.otp_cooldown');
    case 'otp_rate_limited':
      return t('auth.errors.otp_rate_limited');
    case 'otp_expired':
      return t('auth.errors.otp_expired');
    case 'otp_invalid':
      return t('auth.errors.otp_invalid');
    case 'otp_locked':
      return t('auth.errors.otp_locked');
    case 'sms_failed':
      return t('auth.errors.sms_failed');
    case 'signup_token_invalid':
      return t('auth.errors.signup_token_invalid');
    case 'account_exists':
      return t('auth.errors.account_exists');
    case 'network':
      return t('auth.errors.network');
    default:
      return t('auth.errors.unknown');
  }
}
