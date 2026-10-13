import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import { act, fireEvent, renderRouter, screen } from 'expo-router/testing-library';
import { Text } from 'react-native';

import CaseDashboardScreen from '@/app/cases/[caseId]';
import RootLayout from '@/app/_layout';
import YourCasesScreen from '@/app/index';
import i18n from '@/i18n';
import { installFakeApi } from '@/test-utils/fake-api';
import { resetTokenStore } from '@/test-utils/memory-token-store';

jest.mock('@/auth/token-store', () => jest.requireActual('@/test-utils/memory-token-store'));
jest.mock('expo-localization', () => ({
  getLocales: () => [{ languageCode: 'en' }],
  useLocales: () => [{ languageCode: 'en' }],
}));
jest.mock('@expo/vector-icons/Feather', () => () => null);

// The real scan screen pulls in the camera and the document picker, which this
// is not about. Only that we arrive there matters.
const ScanStub = () => <Text>Scan screen</Text>;

const routes = {
  _layout: RootLayout,
  index: YourCasesScreen,
  'cases/[caseId]': CaseDashboardScreen,
  'cases/[caseId]/scan': ScanStub,
};

let server: ReturnType<typeof installFakeApi>;

beforeEach(async () => {
  await i18n.changeLanguage('en');
  resetTokenStore();
  server = installFakeApi();
  server.sessions.set('saved-token', '+919876543210');
  resetTokenStore('saved-token');
});

async function openCase(caseId: string, ready: RegExp) {
  const router = renderRouter(routes, { initialUrl: `/cases/${caseId}` });
  await screen.findByText(ready);
  return router;
}

describe('adding another bill to the same admission', () => {
  // One admission runs for days and the bills arrive one at a time. Adding one
  // used to be the dashboard's only button, so it disappeared as soon as a
  // bill had an open question -- which is the usual state after a scan finds
  // anything -- and the only way on was to start a second case for the same
  // admission, re-entering every admission detail.
  it('offers it even while there are open questions', async () => {
    await openCase('papa-admission', /Ask the billing desk/);

    expect(screen.getByText('Ask the billing desk')).toBeVisible();
    expect(screen.getByText('Add another bill')).toBeVisible();
  });

  it('goes to the scan screen for the same case', async () => {
    const router = await openCase('papa-admission', /Add another bill/);

    await act(async () => fireEvent.press(screen.getByText('Add another bill')));

    expect(router.getPathname()).toBe('/cases/papa-admission/scan');
  });

  it('offers nothing more on a case that is closed', async () => {
    await openCase('mummy-cataract', /Mummy's cataract surgery/);

    expect(screen.queryByText('Add another bill')).toBeNull();
    expect(screen.queryByText("Add today's bill")).toBeNull();
  });
});
