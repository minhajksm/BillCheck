import { afterAll, beforeEach, describe, expect, it, jest } from '@jest/globals';
import { act, fireEvent, renderRouter, screen } from 'expo-router/testing-library';

import AuthLayout from '@/app/(auth)/_layout';
import NoAccountScreen from '@/app/(auth)/no-account';
import PhoneScreen from '@/app/(auth)/phone';
import ProfileScreen from '@/app/(auth)/profile';
import VerifyScreen from '@/app/(auth)/verify';
import WelcomeScreen from '@/app/(auth)/welcome';
import RootLayout from '@/app/_layout';
import CaseDashboardScreen from '@/app/cases/[caseId]';
import YourCasesScreen from '@/app/index';
import i18n from '@/i18n';
import { installFakeApi } from '@/test-utils/fake-api';
import { resetTokenStore, tokenStore } from '@/test-utils/memory-token-store';

jest.mock('@/auth/token-store', () => jest.requireActual('@/test-utils/memory-token-store'));
// The app follows the device language, so tests set that instead of calling i18n.
let mockDeviceLanguage = 'en';
jest.mock('expo-localization', () => ({
  getLocales: () => [{ languageCode: mockDeviceLanguage }],
  useLocales: () => [{ languageCode: mockDeviceLanguage }],
}));
// The real icon loads its font asynchronously, which only adds act() noise here.
jest.mock('@expo/vector-icons/Feather', () => () => null);

const routes = {
  _layout: RootLayout,
  index: YourCasesScreen,
  'cases/[caseId]': CaseDashboardScreen,
  '(auth)/_layout': AuthLayout,
  '(auth)/welcome': WelcomeScreen,
  '(auth)/no-account': NoAccountScreen,
  '(auth)/phone': PhoneScreen,
  '(auth)/verify': VerifyScreen,
  '(auth)/profile': ProfileScreen,
};

let server: ReturnType<typeof installFakeApi>;

beforeEach(async () => {
  mockDeviceLanguage = 'en';
  await i18n.changeLanguage('en');
  resetTokenStore();
  server = installFakeApi();
});

afterAll(() => i18n.changeLanguage('en'));

async function start(initialUrl = '/', ready: RegExp = /Create account|Welcome, /) {
  const router = renderRouter(routes, { initialUrl });
  await screen.findByText(ready);
  return router;
}

async function enterPhone(digits: string) {
  fireEvent.changeText(screen.getByLabelText('Mobile number'), digits);
  await act(async () => fireEvent.press(screen.getByText('Send code')));
  await screen.findByText('Enter the code');
}

async function enterCode(code: string) {
  await act(async () => fireEvent.changeText(screen.getByLabelText('6-digit code'), code));
}

describe('sign up', () => {
  it('takes a new number through code, name, and consent to the home screen', async () => {
    const router = await start();
    fireEvent.press(screen.getByText('Create account'));
    expect(await screen.findByText('Create your account')).toBeVisible();

    await enterPhone('98765 43210');
    expect(screen.getByText('We sent a 6-digit code to +91 98765 43210.')).toBeVisible();
    expect(server.calls).toContain('POST /auth/otp/request');

    await enterCode(server.lastCode);
    expect(await screen.findByText('A few details')).toBeVisible();

    fireEvent.changeText(screen.getByLabelText('Your name'), 'Anita Sharma');
    const create = screen.getByRole('button', { name: 'Create account' });
    expect(create).toBeDisabled();
    fireEvent.press(screen.getByRole('checkbox'));
    await act(async () => fireEvent.press(create));

    expect(await screen.findByText('Welcome, Anita')).toBeVisible();
    expect(router.getPathname()).toBe('/');
    expect(await tokenStore.get()).toMatch(/^token-/);
  });

  it('keeps the send button off until the number is a valid mobile', async () => {
    await start();
    fireEvent.press(screen.getByText('Create account'));
    await screen.findByText('Create your account');
    const field = screen.getByLabelText('Mobile number');

    fireEvent.changeText(field, '98765');
    expect(screen.getByRole('button', { name: 'Send code' })).toBeDisabled();

    fireEvent.changeText(field, '5876543210');
    expect(screen.getByText('Enter a 10-digit mobile number starting with 6, 7, 8, or 9.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Send code' })).toBeDisabled();
  });

  it('shows a wrong code and lets the person try again', async () => {
    await start();
    fireEvent.press(screen.getByText('Create account'));
    await screen.findByText('Create your account');
    await enterPhone('9876543210');

    await enterCode('000000');
    expect(await screen.findByText("That code isn't right. Check the SMS and try again.")).toBeVisible();

    await enterCode(server.lastCode);
    expect(await screen.findByText('A few details')).toBeVisible();
  });
});

describe('log in', () => {
  beforeEach(() => {
    server.users.set('+919876543210', { id: 'u1', phone: '+919876543210', name: 'Rohan Sharma' });
  });

  it('goes straight home for an existing account', async () => {
    await start();
    fireEvent.press(screen.getByText('Log in'));
    expect(await screen.findByText('Welcome back')).toBeVisible();
    await enterPhone('9876543210');
    await enterCode(server.lastCode);
    expect(await screen.findByText('Welcome, Rohan')).toBeVisible();
  });

  it('explains when a new number used "Log in"', async () => {
    server.users.clear();
    await start();
    fireEvent.press(screen.getByText('Log in'));
    await screen.findByText('Welcome back');
    await enterPhone('9876543210');
    await enterCode(server.lastCode);
    expect(
      await screen.findByText("There's no account with this number yet, so let's create one."),
    ).toBeVisible();
  });

  it('restores a saved session on launch', async () => {
    server.sessions.set('saved-token', '+919876543210');
    resetTokenStore('saved-token');
    await start();
    expect(screen.getByText('Welcome, Rohan')).toBeVisible();
  });

  it('drops a token the server no longer accepts', async () => {
    resetTokenStore('revoked-token');
    await start();
    expect(screen.getByText('Create account')).toBeVisible();
    expect(await tokenStore.get()).toBeNull();
  });

  it('keeps signed-out people away from the app screens', async () => {
    const router = await start('/cases/papa-admission');
    expect(screen.getByText('Create account')).toBeVisible();
    expect(router.getPathname()).not.toContain('/cases');
  });

  it('logs out from the account panel', async () => {
    server.sessions.set('saved-token', '+919876543210');
    resetTokenStore('saved-token');
    await start();
    fireEvent.press(screen.getByLabelText('Account'));
    expect(screen.getByText('Signed in as +91 98765 43210')).toBeVisible();
    await act(async () => fireEvent.press(screen.getByText('Log out')));
    expect(await screen.findByText('Create account')).toBeVisible();
    expect(await tokenStore.get()).toBeNull();
    expect(server.sessions.has('saved-token')).toBe(false);
  });
});

describe('without an account', () => {
  it('is not offered while the API requires signing in', async () => {
    await start();
    expect(screen.getByText('Create account')).toBeVisible();
    expect(screen.queryByText('Use it without an account')).toBeNull();
  });

  it('says what is given up, and only starts once that is agreed to', async () => {
    server.anonymousAccounts = true;
    await start();
    fireEvent.press(screen.getByText('Use it without an account'));

    expect(await screen.findByText('No account needed')).toBeVisible();
    // The trade has to be on screen before they agree to it.
    expect(screen.getByText('Your bills stay on this phone')).toBeVisible();

    const begin = screen.getByRole('button', { name: 'Start checking bills' });
    expect(begin).toBeDisabled();
    fireEvent.press(screen.getByRole('checkbox'));
    await act(async () => fireEvent.press(begin));

    // No name was asked for, so the greeting cannot use one.
    expect(await screen.findByText('Welcome')).toBeVisible();
    expect(server.calls).toContain('POST /auth/anonymous');
    expect(await tokenStore.get()).toMatch(/^token-/);
  });

  it('offers no log out, which would throw the bills away for good', async () => {
    server.anonymousAccounts = true;
    server.users.set('device-0', { id: 'u-device-0', phone: null, name: '' });
    server.sessions.set('saved-token', 'device-0');
    resetTokenStore('saved-token');
    await start('/', /Welcome/);

    fireEvent.press(screen.getByLabelText('Account'));
    expect(screen.getByText('No account on this phone')).toBeVisible();
    expect(screen.queryByText('Log out')).toBeNull();
  });

  it('sends people back to the welcome screen if the API has since closed it', async () => {
    const router = await start('/no-account');
    expect(router.getPathname()).toBe('/welcome');
  });
});

describe('in Hindi', () => {
  it('follows a Hindi device', async () => {
    mockDeviceLanguage = 'hi';
    await start('/', /खाता बनाएँ/);
    expect(screen.getByText('खाता बनाएँ')).toBeVisible();
    expect(screen.getByText('लॉग इन करें')).toBeVisible();
  });
});
