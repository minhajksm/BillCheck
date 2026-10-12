/** Drop-in for auth/token-store in tests: jest.mock('@/auth/token-store', () => require(...)). */
let saved: string | null = null;

export const tokenStore = {
  get: async () => saved,
  set: async (token: string) => {
    saved = token;
  },
  clear: async () => {
    saved = null;
  },
};

export function resetTokenStore(token: string | null = null) {
  saved = token;
}
