// Hermes doesn't always ship Intl.PluralRules, which i18next needs for
// _one/_other keys. The polyfill is a no-op where the engine already has it.
import 'intl-pluralrules';

import { getLocales, useLocales } from 'expo-localization';
import { createInstance } from 'i18next';
import { useEffect } from 'react';
import { initReactI18next } from 'react-i18next';

import en from './locales/en.json';
import hi from './locales/hi.json';
import mr from './locales/mr.json';

export const SUPPORTED_LANGUAGES = ['en', 'hi', 'mr'] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

export const resources = {
  en: { translation: en },
  hi: { translation: hi },
  mr: { translation: mr },
} as const;

function isSupported(code: string | null | undefined): code is Language {
  return SUPPORTED_LANGUAGES.includes(code as Language);
}

/** First device language we support, in the user's order of preference. */
export function pickLanguage(languageCodes: (string | null)[]): Language {
  return languageCodes.find(isSupported) ?? 'en';
}

const i18n = createInstance();

i18n.use(initReactI18next).init({
  resources,
  lng: pickLanguage(getLocales().map((l) => l.languageCode)),
  fallbackLng: 'en',
  supportedLngs: SUPPORTED_LANGUAGES,
  // React already escapes text, and our strings never go into HTML.
  interpolation: { escapeValue: false },
  returnNull: false,
});

/**
 * Follows the device or per-app language (Android 13+ app language settings)
 * while the app is running.
 */
export function useDeviceLanguage() {
  const locales = useLocales();
  const language = pickLanguage(locales.map((l) => l.languageCode));

  useEffect(() => {
    if (i18n.language !== language) {
      i18n.changeLanguage(language);
    }
  }, [language]);
}

export default i18n;
