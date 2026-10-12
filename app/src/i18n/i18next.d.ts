import 'i18next';

import type en from './locales/en.json';

// Types t() keys against the English file, so a typo or missing key fails tsc.
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: { translation: typeof en };
  }
}
