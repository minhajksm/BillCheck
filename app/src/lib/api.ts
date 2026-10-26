import { Platform } from 'react-native';

/**
 * Where the API lives. Set EXPO_PUBLIC_API_URL to override, e.g. your
 * computer's LAN address when testing on a real phone.
 * Defaults: the Android emulator reaches the host at 10.0.2.2.
 */
export const API_URL =
  process.env.EXPO_PUBLIC_API_URL ??
  (Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000');

/** Error codes the API returns, plus "network" when it can't be reached. */
export type ApiErrorCode =
  | 'otp_cooldown'
  | 'otp_rate_limited'
  | 'otp_expired'
  | 'otp_invalid'
  | 'otp_locked'
  | 'sms_failed'
  | 'signup_token_invalid'
  | 'account_exists'
  | 'sign_in_required'
  | 'sign_in_off'
  | 'not_authenticated'
  | 'invalid_request'
  | 'page_too_large'
  | 'empty_page'
  | 'unsupported_page'
  | 'no_pages'
  | 'too_many_pages'
  | 'unreadable_bill'
  | 'upload_limit'
  | 'lab_consent_required'
  | 'lab_report_not_found'
  | 'unreadable_lab_report'
  // The pages read fine and are something else; `document` says what.
  | 'not_a_bill'
  | 'not_a_lab_report'
  | 'network'
  | 'unknown';

export class ApiError extends Error {
  constructor(
    readonly code: ApiErrorCode,
    readonly status: number,
    readonly retryAfterSeconds?: number,
    /** For a page that is the wrong kind of document: the title it prints, if any. */
    readonly document?: string,
  ) {
    super(code);
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  token?: string | null;
};

export async function apiFetch<T>(
  path: string,
  { method = 'GET', body, token }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('network', 0);
  }

  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (response.ok) return data as T;

  const retryAfter = Number(response.headers.get('Retry-After'));
  throw new ApiError(errorCode(response.status, data), response.status, retryAfter || undefined);
}

function errorCode(status: number, data: unknown): ApiErrorCode {
  if (status === 422) return 'invalid_request';
  const detail = (data as { detail?: { code?: unknown } } | null)?.detail;
  return typeof detail?.code === 'string' ? (detail.code as ApiErrorCode) : 'unknown';
}
