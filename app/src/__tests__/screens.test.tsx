import { afterAll, beforeEach, describe, expect, it, jest } from '@jest/globals';
import { Stack } from 'expo-router';
import { fireEvent, renderRouter, screen } from 'expo-router/testing-library';

import CaseDashboardScreen from '@/app/cases/[caseId]';
import HomeScreen from '@/app/index';
import MemberScreen from '@/app/members/[memberId]';
import { AuthProvider, useAuth } from '@/auth/auth-context';
import { ToastProvider } from '@/components/toast';
import i18n, { SUPPORTED_LANGUAGES } from '@/i18n';
import { installFakeApi } from '@/test-utils/fake-api';
import { resetTokenStore } from '@/test-utils/memory-token-store';

jest.mock('@/auth/token-store', () => jest.requireActual('@/test-utils/memory-token-store'));
// The real icon loads its font asynchronously, which only adds act() noise here.
jest.mock('@expo/vector-icons/Feather', () => () => null);

function TestLayout() {
  return (
    <AuthProvider>
      <ToastProvider>
        <Navigator />
      </ToastProvider>
    </AuthProvider>
  );
}

/** Like the real root layout, waits for the saved session before showing screens. */
function Navigator() {
  const { state } = useAuth();
  return state.status === 'loading' ? null : <Stack screenOptions={{ headerShown: false }} />;
}

const routes = {
  _layout: TestLayout,
  index: HomeScreen,
  'members/[memberId]': MemberScreen,
  'cases/[caseId]': CaseDashboardScreen,
};

/** Renders and waits for the screen to appear once the session is restored. */
async function render(initialUrl: string, ready: string | RegExp) {
  const router = renderRouter(routes, { initialUrl });
  await screen.findByText(ready);
  return router;
}

// Start each test signed in as Rohan.
beforeEach(() => {
  const server = installFakeApi();
  server.users.set('+919876543210', { id: 'u1', phone: '+919876543210', name: 'Rohan Sharma' });
  server.sessions.set('saved-token', '+919876543210');
  resetTokenStore('saved-token');
});

describe('home, members and their admissions', () => {
  afterAll(() => i18n.changeLanguage('en'));

  it('greets the signed-in person and lists who they look after', async () => {
    await render('/', 'Welcome, Rohan');
    expect(screen.getByText('Papa')).toBeVisible();
    // Papa's admission has no discharge yet, and two open questions.
    expect(screen.getByText('In hospital now')).toBeVisible();
    expect(screen.getByText('2 to ask')).toBeVisible();
    expect(screen.getByText('Mummy')).toBeVisible();
    expect(screen.getAllByText('1 admission')).toHaveLength(2);
  });

  it('opens a member, with who follows them and their admissions', async () => {
    const router = await render('/', 'Papa');
    fireEvent.press(screen.getByText('Papa'));

    expect(router.getPathname()).toBe('/members/m-papa');
    expect(await screen.findByText('Rohan (you) and Anita follow Papa')).toBeVisible();
    expect(screen.getByText("Papa's admission")).toBeVisible();
    expect(screen.getByText('Admitted 9 Oct')).toBeVisible();
  });

  it('opens the case dashboard from the member', async () => {
    const router = await render('/members/m-papa', "Papa's admission");
    fireEvent.press(screen.getByText("Papa's admission"));

    expect(router.getPathname()).toBe('/cases/papa-admission');
    expect(await screen.findByText('Running total')).toBeVisible();
    expect(screen.getByText('₹73,890')).toBeVisible();
    expect(screen.getByText('10 Oct bill')).toBeVisible();
    expect(screen.getByText('37 items, ₹31,400')).toBeVisible();
  });

  it('opens a closed case, so its reports and its delete button stay reachable', async () => {
    const router = await render('/members/m-mummy', 'Discharged 13 Mar 2026');
    expect(screen.getByText('₹3,200 recovered')).toBeVisible();
    fireEvent.press(screen.getByText("Mummy's cataract surgery"));

    // A closed admission is done, not archived: the bills stay readable, and
    // deleting the case is only possible from inside it.
    expect(router.getPathname()).toBe('/cases/mummy-cataract');
    expect(await screen.findByText('Lotus Eye Clinic, Thane')).toBeVisible();
    expect(screen.getByLabelText('Case details')).toBeVisible();
  });

  it('shows whose admission it is on the case, and goes to them', async () => {
    const router = await render('/cases/papa-admission', '₹73,890');
    fireEvent.press(screen.getByText('Papa'));
    expect(router.getPathname()).toBe('/members/m-papa');
  });

  it('shows a message for an unknown case', async () => {
    await render('/cases/nope', "We couldn't find this case.");
    expect(screen.getByText("We couldn't find this case.")).toBeVisible();
  });

  it.each(SUPPORTED_LANGUAGES)('renders both screens in %s without raw keys', async (lng) => {
    await i18n.changeLanguage(lng);
    await render('/cases/papa-admission', '₹73,890');
    expect(
      screen.queryByText(
        /^(case|home|common|caseStatus|dates|auth|report|ask|flags|scan|newCase|message|members|file)\./,
      ),
    ).toBeNull();
    expect(screen.getByText('₹73,890')).toBeVisible();
  });

  it.each(SUPPORTED_LANGUAGES)('renders the home and member screens in %s without raw keys', async (lng) => {
    await i18n.changeLanguage(lng);
    const router = await render('/', 'Papa');
    expect(screen.queryByText(/^[a-zA-Z]+\.[a-zA-Z_]+$/)).toBeNull();
    fireEvent.press(screen.getByText('Papa'));
    await screen.findByText("Papa's admission");
    expect(router.getPathname()).toBe('/members/m-papa');
    expect(screen.queryByText(/^[a-zA-Z]+\.[a-zA-Z_]+$/)).toBeNull();
  });

  it('uses Hindi copy when the language is Hindi', async () => {
    await i18n.changeLanguage('hi');
    await render('/members/m-papa', '9 अक्टू॰ को भर्ती');
    expect(screen.getByText('9 अक्टू॰ को भर्ती')).toBeVisible();
  });
});
