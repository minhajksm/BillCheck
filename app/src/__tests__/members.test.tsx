import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import { Stack } from 'expo-router';
import { act, fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { Share } from 'react-native';

import HomeScreen from '@/app/index';
import MemberScreen from '@/app/members/[memberId]';
import JoinMemberScreen from '@/app/members/join';
import NewMemberScreen from '@/app/members/new';
import { AuthProvider, useAuth } from '@/auth/auth-context';
import { ToastProvider } from '@/components/toast';
import i18n from '@/i18n';
import { installFakeApi } from '@/test-utils/fake-api';
import { ageOn } from '@/lib/age';
import { resetTokenStore } from '@/test-utils/memory-token-store';

jest.mock('@/auth/token-store', () => jest.requireActual('@/test-utils/memory-token-store'));
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

function Navigator() {
  const { state } = useAuth();
  return state.status === 'loading' ? null : <Stack screenOptions={{ headerShown: false }} />;
}

const routes = {
  _layout: TestLayout,
  index: HomeScreen,
  'members/new': NewMemberScreen,
  'members/join': JoinMemberScreen,
  'members/[memberId]': MemberScreen,
};

let server: ReturnType<typeof installFakeApi>;

beforeEach(async () => {
  await i18n.changeLanguage('en');
  server = installFakeApi();
  server.users.set('+919876543210', { id: 'u1', phone: '+919876543210', name: 'Rohan Sharma' });
  server.sessions.set('saved-token', '+919876543210');
  resetTokenStore('saved-token');
});

describe('adding someone to look after', () => {
  it('asks only for a name, then opens them', async () => {
    const router = renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Add a member'));

    fireEvent.changeText(await screen.findByLabelText('Name'), 'Aaji');
    await act(async () => fireEvent.press(screen.getByText('Add member')));

    expect(await screen.findByText('Only you follow Aaji')).toBeVisible();
    expect(router.getPathname()).toBe('/members/m-3');
    expect(screen.getByText(/No admissions yet/)).toBeVisible();
  });

  it('needs a name', async () => {
    renderRouter(routes, { initialUrl: '/members/new' });
    // Straight to this screen: the saved session is restored first.
    await screen.findByText('Add a member', {}, { timeout: 5000 });
    await act(async () => fireEvent.press(await screen.findByText('Add member')));

    expect(await screen.findByText('Fill this in to continue.')).toBeVisible();
    expect(server.members).toHaveLength(2);
  });
});

describe('family follow the person', () => {
  it('makes an invite code, offers the share sheet, and shows the code too', async () => {
    const share = jest.spyOn(Share, 'share').mockResolvedValue({ action: 'sharedAction' });
    renderRouter(routes, { initialUrl: '/members/m-papa' });

    const invite = await screen.findByText('Invite family', {}, { timeout: 5000 });
    await act(async () => fireEvent.press(invite));

    expect(await screen.findByText('code-m-papa')).toBeVisible();
    expect(share).toHaveBeenCalledWith({ message: expect.stringContaining('code-m-papa') });
    expect(share.mock.calls[0][0]).toEqual({ message: expect.stringContaining('Follow Papa on BillCheck') });
  });

  it('still shows the code where there is no share sheet', async () => {
    jest.spyOn(Share, 'share').mockRejectedValue(new Error('not supported'));
    renderRouter(routes, { initialUrl: '/members/m-papa' });

    const invite = await screen.findByText('Invite family', {}, { timeout: 5000 });
    await act(async () => fireEvent.press(invite));

    expect(await screen.findByText('code-m-papa')).toBeVisible();
    expect(screen.queryByText(/Couldn't make an invite code/)).toBeNull();
  });

  it('joins with the code and opens the person', async () => {
    server.lastInvite = 'code-m-papa';
    const router = renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Join with a code from family'));

    fireEvent.changeText(await screen.findByLabelText('Invite code'), '  code-m-papa \n');
    await act(async () => fireEvent.press(screen.getByText('Join')));

    await waitFor(() => expect(router.getPathname()).toBe('/members/m-papa'));
    expect(server.calls).toContain('POST /members/join');
  });

  it('says plainly when a code no longer works', async () => {
    renderRouter(routes, { initialUrl: '/members/join' });

    fireEvent.changeText(await screen.findByLabelText('Invite code'), 'expired-code');
    await act(async () => fireEvent.press(screen.getByText('Join')));

    expect(await screen.findByText(/That code has expired or was withdrawn/)).toBeVisible();
  });
});

describe('deleting, or leaving', () => {
  it('deletes the person only after saying what goes with them', async () => {
    const router = renderRouter(routes, { initialUrl: '/members/m-papa' });

    fireEvent.press(await screen.findByText('Delete Papa'));
    expect(screen.getByText(/every admission, bill and lab report under them/)).toBeVisible();
    await act(async () => fireEvent.press(screen.getByText('Yes, delete')));

    await waitFor(() => expect(router.getPathname()).toBe('/'));
    expect(server.members.map((m) => m.id)).toEqual(['m-mummy']);
  });

  it('offers someone who did not add them only to stop following', async () => {
    server.members[0].is_owner = false;
    renderRouter(routes, { initialUrl: '/members/m-papa' });

    expect(await screen.findByText('Stop following Papa')).toBeVisible();
    expect(screen.queryByText('Delete Papa')).toBeNull();
  });
});

describe("a member's details", () => {
  it('takes a date of birth, mobile, email and address, and shows the age as it is typed', async () => {
    renderRouter(routes, { initialUrl: '/members/new' });
    fireEvent.changeText(await screen.findByLabelText('Name', {}, { timeout: 5000 }), 'Aaji');
    fireEvent.changeText(screen.getByLabelText('Date of birth (optional)'), '1958-03-14');

    const age = ageOn('1958-03-14', new Date());
    expect(screen.getByText(`Age ${age}`)).toBeVisible();

    fireEvent.changeText(screen.getByLabelText('Mobile number (optional)'), '98765 43210');
    fireEvent.changeText(screen.getByLabelText('Email (optional)'), 'Aaji@Example.com');
    fireEvent.changeText(screen.getByLabelText('Address (optional)'), '12 Example Road, Pune');
    await act(async () => fireEvent.press(screen.getByText('Add member')));

    expect(await screen.findByText(`Age ${age} · Born 14 Mar 1958`)).toBeVisible();
    expect(screen.getByText('+91 98765 43210')).toBeVisible();
    expect(screen.getByText('aaji@example.com')).toBeVisible();
    expect(screen.getByText('12 Example Road, Pune')).toBeVisible();
    expect(server.members[2]).toMatchObject({ phone: '+919876543210', date_of_birth: '1958-03-14' });
  });

  it('needs only the name', async () => {
    renderRouter(routes, { initialUrl: '/members/new' });
    fireEvent.changeText(await screen.findByLabelText('Name', {}, { timeout: 5000 }), 'Aaji');
    await act(async () => fireEvent.press(screen.getByText('Add member')));

    expect(await screen.findByText('Add date of birth, phone, email or address')).toBeVisible();
    expect(server.members[2]).toMatchObject({ date_of_birth: null, phone: null, email: null, address: null });
  });

  it('refuses what plainly is not a date, a mobile or an email, and saves nothing', async () => {
    renderRouter(routes, { initialUrl: '/members/new' });
    fireEvent.changeText(await screen.findByLabelText('Name', {}, { timeout: 5000 }), 'Aaji');
    fireEvent.changeText(screen.getByLabelText('Date of birth (optional)'), '14/03/1958');
    fireEvent.changeText(screen.getByLabelText('Mobile number (optional)'), '12345');
    fireEvent.changeText(screen.getByLabelText('Email (optional)'), 'aaji');
    await act(async () => fireEvent.press(screen.getByText('Add member')));

    expect(screen.getByText('Use the form YYYY-MM-DD, with a date in the past.')).toBeVisible();
    expect(screen.getByText('Enter a 10-digit mobile number.')).toBeVisible();
    expect(screen.getByText('Enter an email address like name@example.com.')).toBeVisible();
    expect(server.members).toHaveLength(2);
  });

  it('edits what is there, and clears what is emptied', async () => {
    Object.assign(server.members[0], { phone: '+919876543210', email: 'papa@example.com' });
    renderRouter(routes, { initialUrl: '/members/m-papa' });
    fireEvent.press(await screen.findByLabelText('Edit details', {}, { timeout: 5000 }));

    expect(await screen.findByDisplayValue('9876543210')).toBeVisible();
    fireEvent.changeText(screen.getByDisplayValue('papa@example.com'), '');
    fireEvent.changeText(screen.getByLabelText('Date of birth (optional)'), '1952-08-01');
    await act(async () => fireEvent.press(screen.getByText('Save')));

    await waitFor(() => expect(server.members[0].date_of_birth).toBe('1952-08-01'));
    expect(server.members[0]).toMatchObject({ name: 'Papa', phone: '+919876543210', email: null });
  });

  it('shows the age on the home screen', async () => {
    server.members[0].date_of_birth = '1958-03-14' as unknown as null;
    renderRouter(routes, { initialUrl: '/' });

    const age = ageOn('1958-03-14', new Date());
    expect(await screen.findByText(`Age ${age} · 1 admission`, {}, { timeout: 5000 })).toBeVisible();
  });
});
