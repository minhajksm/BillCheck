import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import { act, fireEvent, renderRouter, screen } from 'expo-router/testing-library';

import EditCaseScreen from '@/app/cases/[caseId]/edit';
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

const routes = {
  _layout: RootLayout,
  index: YourCasesScreen,
  'cases/[caseId]': CaseDashboardScreen,
  'cases/[caseId]/edit': EditCaseScreen,
};

let server: ReturnType<typeof installFakeApi>;

beforeEach(async () => {
  await i18n.changeLanguage('en');
  resetTokenStore();
  server = installFakeApi();
  // A signed-in session, as the sign-up flow would leave it.
  server.users.set('+919876543210', { id: 'u1', phone: '+919876543210', name: 'Rohan Sharma' });
  server.sessions.set('saved-token', '+919876543210');
  resetTokenStore('saved-token');
});

/** In through the dashboard, as a family would, so going back has somewhere
 * to go and the way in is exercised too. */
async function openEdit(caseId = 'papa-admission') {
  const router = renderRouter(routes, { initialUrl: `/cases/${caseId}` });
  await screen.findByText('Ask the billing desk');
  await act(async () => fireEvent.press(screen.getByLabelText('Case details')));
  await screen.findByText('Save changes');
  return router;
}

describe('correcting the admission details', () => {
  it('opens with what was entered at the counter', async () => {
    await openEdit();

    expect(screen.getByDisplayValue("Papa's admission")).toBeVisible();
    expect(screen.getByDisplayValue('City Care Hospital')).toBeVisible();
    expect(screen.getByDisplayValue('20841')).toBeVisible();
    expect(screen.getByDisplayValue('412')).toBeVisible();
  });

  it('saves a correction and goes back', async () => {
    const router = await openEdit();

    fireEvent.changeText(screen.getByDisplayValue('412'), '308');
    await act(async () => fireEvent.press(screen.getByText('Save changes')));

    expect(server.calls).toContain('PATCH /cases/papa-admission');
    expect(server.cases[0].bed).toBe('308');
    expect(router.getPathname()).not.toContain('/edit');
  });

  it('will not save a case with the patient name rubbed out', async () => {
    await openEdit();

    fireEvent.changeText(screen.getByDisplayValue('Ramesh Sharma'), '  ');
    await act(async () => fireEvent.press(screen.getByText('Save changes')));

    expect(screen.getByText('Fill this in to continue.')).toBeVisible();
    expect(server.calls).not.toContain('PATCH /cases/papa-admission');
  });

  it('will not save an admission date that is not a date', async () => {
    await openEdit();

    fireEvent.changeText(screen.getByDisplayValue('2026-10-09'), '9 Oct');
    await act(async () => fireEvent.press(screen.getByText('Save changes')));

    expect(screen.getByText('Use the form YYYY-MM-DD, e.g. 2026-10-09.')).toBeVisible();
    expect(server.calls).not.toContain('PATCH /cases/papa-admission');
  });
});

describe('the discharge date', () => {
  it('shows the stay on the case, still open until someone says otherwise', async () => {
    renderRouter(routes, { initialUrl: '/cases/papa-admission' });

    expect(await screen.findByText('Admitted 9 Oct 2026 · Still in hospital')).toBeVisible();
  });

  it('can be entered, and closes the stay', async () => {
    await openEdit();

    fireEvent.changeText(screen.getByLabelText('Discharged on (optional)'), '2026-10-12');
    await act(async () => fireEvent.press(screen.getByText('Save changes')));

    expect(server.cases[0].closed_on).toBe('2026-10-12');
  });

  it('will not end a stay before it began', async () => {
    await openEdit();

    fireEvent.changeText(screen.getByLabelText('Discharged on (optional)'), '2026-10-01');
    await act(async () => fireEvent.press(screen.getByText('Save changes')));

    expect(screen.getByText('This is before the admission date.')).toBeVisible();
    expect(server.calls).not.toContain('PATCH /cases/papa-admission');
  });

  it('cleared, says the patient is still in hospital', async () => {
    server.cases[0].closed_on = '2026-10-12' as unknown as null;
    // A discharged case offers no more questions or bills, so open it by its edit button.
    renderRouter(routes, { initialUrl: '/cases/papa-admission' });
    const details = await screen.findByLabelText('Case details');
    await act(async () => fireEvent.press(details));
    await screen.findByText('Save changes');

    expect(screen.getByDisplayValue('2026-10-12')).toBeVisible();
    fireEvent.changeText(screen.getByDisplayValue('2026-10-12'), '');
    await act(async () => fireEvent.press(screen.getByText('Save changes')));

    expect(server.cases[0].closed_on).toBeNull();
  });
});

describe('deleting a case', () => {
  // It takes the bills away from everyone following the case and cannot be
  // undone, so it asks first, in words, rather than deleting on one tap.
  it('asks before it does anything', async () => {
    await openEdit();

    await act(async () => fireEvent.press(screen.getByText('Delete this case')));

    expect(
      screen.getByText(
        "This deletes Papa's admission and every bill on it, for everyone following the case. It cannot be undone.",
      ),
    ).toBeVisible();
    expect(server.calls.some((call) => call.startsWith('DELETE'))).toBe(false);
  });

  it('can be backed out of', async () => {
    await openEdit();

    await act(async () => fireEvent.press(screen.getByText('Delete this case')));
    await act(async () => fireEvent.press(screen.getByText('Cancel')));

    expect(screen.getByText('Delete this case')).toBeVisible();
    expect(server.calls.some((call) => call.startsWith('DELETE'))).toBe(false);
  });

  it('deletes on the second press and goes home', async () => {
    const router = await openEdit();

    await act(async () => fireEvent.press(screen.getByText('Delete this case')));
    await act(async () => fireEvent.press(screen.getByText('Yes, delete it')));

    expect(server.calls).toContain('DELETE /cases/papa-admission');
    expect(server.cases.map((c) => c.id)).not.toContain('papa-admission');
    expect(router.getPathname()).toBe('/');
  });

  it('is not offered to someone who did not start the case', async () => {
    server.cases[0].is_owner = false;
    await openEdit();

    expect(screen.queryByText('Delete this case')).toBeNull();
    expect(screen.getByText('Save changes')).toBeVisible();
  });
});
