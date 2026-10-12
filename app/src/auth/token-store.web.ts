const KEY = 'billcheck.session';

/**
 * Web has no secure store, so the browser build keeps the token in
 * localStorage. Fine for testing in a browser; the phone app uses
 * token-store.ts instead.
 */
export const tokenStore = {
  get: async () => {
    try {
      return window.localStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  set: async (token: string) => {
    try {
      window.localStorage.setItem(KEY, token);
    } catch {
      // Storage blocked (private mode): stay signed in for this tab only.
    }
  },
  clear: async () => {
    try {
      window.localStorage.removeItem(KEY);
    } catch {
      // Nothing stored.
    }
  },
};
