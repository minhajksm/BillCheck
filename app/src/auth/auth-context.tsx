import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { ApiError, apiFetch } from '@/lib/api';

import { tokenStore } from './token-store';

export type User = { id: string; phone: string; name: string };

/** Which button started the flow on the welcome screen. Only changes the copy. */
export type AuthMode = 'signup' | 'login';

type LoggedIn = { status: 'logged_in'; token: string; expires_at: string; user: User };
type SignupRequired = { status: 'signup_required'; signup_token: string; expires_at: string };
type OtpRequestResponse = { expires_in_seconds: number; resend_after_seconds: number };

type AuthState =
  | { status: 'loading' }
  /** While signing in: the 10 digits being verified, and the sign-up token once verified. */
  | { status: 'signedOut'; phone: string | null; signupToken: string | null }
  | { status: 'signedIn'; user: User; token: string };

type AuthContextValue = {
  state: AuthState;
  /** Sends a code to +91 and the 10 digits. Resolves with the resend wait in seconds. */
  requestOtp: (phone: string) => Promise<number>;
  /** Checks the code for the number from requestOtp. Signs in an existing user,
   * or returns 'signupRequired' for a new number. */
  verifyOtp: (code: string) => Promise<'signedIn' | 'signupRequired'>;
  /** Finishes sign-up for a just-verified number. */
  completeSignup: (name: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>');
  return value;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' });

  // Restore a saved session on launch.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const token = await tokenStore.get().catch(() => null);
      if (!token) {
        if (!cancelled) setState({ status: 'signedOut', phone: null, signupToken: null });
        return;
      }
      try {
        const user = await apiFetch<User>('/auth/me', { token });
        if (!cancelled) setState({ status: 'signedIn', user, token });
      } catch (error) {
        // Only forget the token if the server rejected it. If the API is
        // unreachable, the user signs in again but the token stays.
        if (error instanceof ApiError && error.status === 401) await tokenStore.clear();
        if (!cancelled) setState({ status: 'signedOut', phone: null, signupToken: null });
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

  const logout = useCallback(async () => {
    const token = state.status === 'signedIn' ? state.token : null;
    // Sign out locally even if the server can't be reached.
    await apiFetch('/auth/logout', { method: 'POST', token }).catch(() => undefined);
    await tokenStore.clear();
    setState({ status: 'signedOut', phone: null, signupToken: null });
  }, [state]);

  const value = useMemo(
    () => ({ state, requestOtp, verifyOtp, completeSignup, logout }),
    [state, requestOtp, verifyOtp, completeSignup, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
