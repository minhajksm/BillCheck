import * as SecureStore from 'expo-secure-store';

const KEY = 'faircare.session';

/** The session token lives in the Android Keystore / iOS Keychain. */
export const tokenStore = {
  get: () => SecureStore.getItemAsync(KEY),
  set: (token: string) => SecureStore.setItemAsync(KEY, token),
  clear: () => SecureStore.deleteItemAsync(KEY),
};
