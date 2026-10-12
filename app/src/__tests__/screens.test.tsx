import { afterAll, describe, expect, it, jest } from '@jest/globals';
import { Stack } from 'expo-router';
import { fireEvent, renderRouter, screen } from 'expo-router/testing-library';

import CaseDashboardScreen from '@/app/cases/[caseId]';
import YourCasesScreen from '@/app/index';
import { ToastProvider } from '@/components/toast';
import i18n, { SUPPORTED_LANGUAGES } from '@/i18n';

// The real icon loads its font asynchronously, which only adds act() noise here.
jest.mock('@expo/vector-icons/Feather', () => () => null);

function TestLayout() {
  return (
    <ToastProvider>
      <Stack screenOptions={{ headerShown: false }} />
    </ToastProvider>
  );
}

const routes = {
  _layout: TestLayout,
  index: YourCasesScreen,
  'cases/[caseId]': CaseDashboardScreen,
};

describe('Your cases', () => {
  afterAll(() => i18n.changeLanguage('en'));

  it('lists both placeholder cases with their status', () => {
    renderRouter(routes, { initialUrl: '/' });
    expect(screen.getByText('Namaste, Rohan')).toBeVisible();
    expect(screen.getByText("Papa's admission")).toBeVisible();
    expect(screen.getByText('Admitted 9 Oct, day 3')).toBeVisible();
    expect(screen.getByText("Add today's bill")).toBeVisible();
    expect(screen.getByText('Closed March 2026')).toBeVisible();
    expect(screen.getByText('₹3,200 recovered')).toBeVisible();
  });

  it('opens the case dashboard', () => {
    const router = renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(screen.getByText("Papa's admission"));
    expect(router.getPathname()).toBe('/cases/papa-admission');
    expect(screen.getByText('Running total, day 2')).toBeVisible();
    expect(screen.getByText('₹99,890')).toBeVisible();
    expect(screen.getByText('+₹31,400')).toBeVisible();
    expect(screen.getByText("Today's bill isn't added yet")).toBeVisible();
    expect(screen.getByText('Rohan (you) and Anita follow this case')).toBeVisible();
    expect(screen.getByText('10 Oct, 37 items, ₹31,400')).toBeVisible();
  });

  it('shows a message for an unknown case', () => {
    renderRouter(routes, { initialUrl: '/cases/nope' });
    expect(screen.getByText("We couldn't find this case.")).toBeVisible();
  });

  it.each(SUPPORTED_LANGUAGES)('renders both screens in %s without raw keys', async (lng) => {
    await i18n.changeLanguage(lng);
    renderRouter(routes, { initialUrl: '/cases/papa-admission' });
    expect(screen.queryByText(/^(case|home|common|caseStatus|dates)\./)).toBeNull();
    expect(screen.getByText('₹99,890')).toBeVisible();
  });

  it('uses Hindi copy when the language is Hindi', async () => {
    await i18n.changeLanguage('hi');
    renderRouter(routes, { initialUrl: '/' });
    expect(screen.getByText('नमस्ते, Rohan')).toBeVisible();
    expect(screen.getByText('9 अक्टू॰ को भर्ती, दिन 3')).toBeVisible();
  });
});
