import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { ApiError, apiFetch } from '@/lib/api';

import { tokenStore } from './token-store';

/** `phone` is null for a device-only account, which has no number to sign in with.
 * `lab_consent` says whether lab reports have been agreed to: sign-up consent
 * covers bills only, so the app asks once before the first report. */
export type User = { id: string; phone: string | null; name: string; lab_consent?: boolean };

/** Which button started the flow on the welcome screen. Only changes the copy. */
export type AuthMode = 'signup' | 'login';

type LoggedIn = { status: 'logged_in'; token: string; expires_at: string; user: User };
type SignupRequired = { status: 'signup_required'; signup_token: string; expires_at: string };
type OtpRequestResponse = { expires_in_seconds: number; resend_after_seconds: number };
type Health = { status: string; anonymous_accounts: boolean };

type AuthState =
  | { status: 'loading' }
  /** While signing in: the 10 digits being verified, and the sign-up token once verified. */
  | { status: 'signedOut'; phone: string | null; signupToken: string | null }
  | { status: 'signedIn'; user: User; token: string };

type AuthContextValue = {
  state: AuthState;
  /** Whether this API lets people in without a phone number. Read at launch
   * from GET /health, so the welcome screen only offers what will work. */
  anonymousAllowed: boolean;
  /** Sends a code to +91 and the 10 digits. Resolves with the resend wait in seconds. */
  requestOtp: (phone: string) => Promise<number>;
  /** Checks the code for the number from requestOtp. Signs in an existing user,
   * or returns 'signupRequired' for a new number. */
  verifyOtp: (code: string) => Promise<'signedIn' | 'signupRequired'>;
  /** Finishes sign-up for a just-verified number. */
  completeSignup: (name: string) => Promise<void>;
  /** Opens a device-only account: no number, so nothing to sign in with later. */
  continueWithoutSignIn: () => Promise<void>;
  /** Records agreement to lab reports, and updates the signed-in user to match. */
  agreeToLabReports: () => Promise<void>;
  logout: () => Promise<void>;
};

const SIGNED_OUT = { status: 'signedOut', phone: null, signupToken: null } as const;

/**
 * How long launch waits to hear whether signing in is optional, before
 * drawing the welcome screen without the answer. A cold or unreachable API
 * must not hold the splash screen: the two sign-in buttons always work.
 *
 * Waiting this long is not the same as giving up. A Cloud Run instance waking
 * from idle takes longer than this, and the answer it then sends still
 * counts: the option appears on the welcome screen when it arrives. It used
 * to be thrown away, which hid the option for the whole of any launch that
 * happened to wake the server.
 */
const HEALTH_TIMEOUT_MS = 3000;

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>');
  return value;
}

async function restoreSession(): Promise<AuthState> {
  const token = await tokenStore.get().catch(() => null);
  if (!token) return SIGNED_OUT;
  try {
    const user = await apiFetch<User>('/auth/me', { token });
    return { status: 'signedIn', user, token };
  } catch (error) {
    // Only forget the token if the server rejected it. If the API is
    // unreachable, the user signs in again but the token stays.
    if (error instanceof ApiError && error.status === 401) await tokenStore.clear();
    return SIGNED_OUT;
  }
}

/** Whether the API lets people in without a number. Never rejects. */
async function askIfSignInIsOptional(): Promise<boolean> {
  try {
    const health = await apiFetch<Health>('/health');
    return health.anonymous_accounts === true;
  } catch (error) {
    // Offline, or an older API that doesn't answer this, so signing in it is.
    // Said out loud, because the only other sign is a button that isn't there.
    console.warn('Could not ask the API whether signing in is optional:', error);
    return false;
  }
}

/** The answer if it arrives within `ms`, or null if it is still on its way. */
async function within<T>(answer: Promise<T>, ms: number): Promise<T | null> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      answer,
      new Promise<null>((resolve) => {
        timer = setTimeout(() => resolve(null), ms);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' });
  const [anonymousAllowed, setAnonymousAllowed] = useState(false);

  // Restore a saved session on launch, and ask what the API allows.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const optional = askIfSignInIsOptional();
      const [allowed, restored] = await Promise.all([within(optional, HEALTH_TIMEOUT_MS), restoreSession()]);
      if (cancelled) return;
      setAnonymousAllowed(allowed ?? false);
      setState(restored);
      if (allowed === null) {
        // Too slow for launch, not too slow to count.
        const late = await optional;
        if (!cancelled) setAnonymousAllowed(late);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (body: LoggedIn) => {
    await tokenStore.set(body.token);
    setState({ status: 'signedIn', user: body.user, token: body.token });
  }, []);

  const requestOtp = useCallback(async (phone: string) => {
    const body = await apiFetch<OtpRequestResponse>('/auth/otp/request', {
      method: 'POST',
      body: { phone: `+91${phone}` },
    });
    setState({ status: 'signedOut', phone, signupToken: null });
    return body.resend_after_seconds;
  }, []);

  const verifyOtp = useCallback(
    async (code: string) => {
      const phone = state.status === 'signedOut' ? state.phone : null;
      if (!phone) throw new ApiError('otp_expired', 400);
      const body = await apiFetch<LoggedIn | SignupRequired>('/auth/otp/verify', {
        method: 'POST',
        body: { phone: `+91${phone}`, code },
      });
      if (body.status === 'logged_in') {
        await signIn(body);
        return 'signedIn' as const;
      }
      setState({ status: 'signedOut', phone, signupToken: body.signup_token });
      return 'signupRequired' as const;
    },
    [state, signIn],
  );

  const completeSignup = useCallback(
    async (name: string) => {
      const signupToken = state.status === 'signedOut' ? state.signupToken : null;
      if (!signupToken) throw new ApiError('signup_token_invalid', 400);
      const body = await apiFetch<LoggedIn>('/auth/signup', {
        method: 'POST',
        body: { signup_token: signupToken, name, consent: true },
      });
      await signIn(body);
    },
    [state, signIn],
  );

  const continueWithoutSignIn = useCallback(async () => {
    const body = await apiFetch<LoggedIn>('/auth/anonymous', { method: 'POST', body: { consent: true } });
    await signIn(body);
  }, [signIn]);

  const agreeToLabReports = useCallback(async () => {
    if (state.status !== 'signedIn') return;
    await apiFetch<void>('/lab-reports/consent', {
      method: 'POST',
      body: { consent: true },
      token: state.token,
    });
    setState({ ...state, user: { ...state.user, lab_consent: true } });
  }, [state]);

  const logout = useCallback(async () => {
    const token = state.status === 'signedIn' ? state.token : null;
    // Sign out locally even if the server can't be reached.
    await apiFetch('/auth/logout', { method: 'POST', token }).catch(() => undefined);
    await tokenStore.clear();
    setState(SIGNED_OUT);
  }, [state]);

  const value = useMemo(
    () => ({
      state,
      anonymousAllowed,
      requestOtp,
      verifyOtp,
      completeSignup,
      continueWithoutSignIn,
      agreeToLabReports,
      logout,
    }),
    [
      state,
      anonymousAllowed,
      requestOtp,
      verifyOtp,
      completeSignup,
      continueWithoutSignIn,
      agreeToLabReports,
      logout,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
