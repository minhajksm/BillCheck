import * as Application from 'expo-application';
import { Platform } from 'react-native';

/**
 * The phone's Android ID, sent with every request as `X-Android-Id`.
 *
 * The API counts the daily upload allowance per phone with it, and notes
 * which phone an account last opened the app on. It survives clearing the
 * app's data and reinstalling, which an account made without signing in
 * does not. The API keeps only a keyed hash of it, never the ID.
 *
 * Null on the web and anywhere it can't be read: the API then counts by
 * account, as it always has.
 */
export function androidId(): string | null {
  if (Platform.OS !== 'android') return null;
  try {
    return Application.getAndroidId() || null;
  } catch {
    return null;
  }
}

/** The header to send, or none. */
export function deviceHeaders(): Record<string, string> {
  const id = androidId();
  return id ? { 'X-Android-Id': id } : {};
}
