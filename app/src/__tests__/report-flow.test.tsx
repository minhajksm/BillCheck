import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import { Stack } from 'expo-router';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import AskScreen from '@/app/bills/[billId]/ask';
import BillReportScreen from '@/app/bills/[billId]';
import CaseDashboardScreen from '@/app/cases/[caseId]';
import YourCasesScreen from '@/app/index';
import { AuthProvider, useAuth } from '@/auth/auth-context';
import { ToastProvider } from '@/components/toast';
import { installFakeApi } from '@/test-utils/fake-api';
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
  index: YourCasesScreen,
  'cases/[caseId]': CaseDashboardScreen,
  'bills/[billId]': BillReportScreen,
  'bills/[billId]/ask': AskScreen,
};

beforeEach(() => {
  const server = installFakeApi();
  server.users.set('+919876543210', { id: 'u1', phone: '+919876543210', name: 'Rohan Sharma' });
  server.sessions.set('saved-token', '+919876543210');
  resetTokenStore('saved-token');
});

describe('the bill report', () => {
  it('shows what was flagged, with the reference each was checked against', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });

    expect(await screen.findByText('Inj. Meropenem 1g')).toBeVisible();
    // The reference is on screen, not just the verdict.
    expect(screen.getByText('Billed ₹2,950 a vial. The listed MRP is ₹1,840.')).toBeVisible();
    expect(screen.getByText('Above MRP')).toBeVisible();

    expect(screen.getByText('Surgical gloves')).toBeVisible();
    expect(screen.getByText('Worth asking')).toBeVisible();

    // The headline is what might be recoverable: 6660 + 5100.
    expect(screen.getByText('₹11,760')).toBeVisible();
  });

  it('says the rest of the bill is fine, rather than leaving it unsaid', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    expect(await screen.findByText('1 other item is within range')).toBeVisible();
  });

  it('never calls a flag a verdict', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    await screen.findByText('Inj. Meropenem 1g');

    expect(
      screen.getByText(/Flags are questions, not verdicts/),
    ).toBeVisible();
  });

  it('opens a flag and explains why it was raised', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    fireEvent.press(await screen.findByText('Inj. Meropenem 1g'));

    expect(await screen.findByText("Why it's flagged")).toBeVisible();
    expect(screen.getByText(/Legal Metrology/)).toBeVisible();
    expect(screen.getByText('What to ask')).toBeVisible();
    expect(screen.getByText(/Ask the hospital pharmacy to show you the MRP and batch details printed on the pack/)).toBeVisible();
    // Billed, reference and difference, side by side.
    expect(screen.getByText('₹17,700')).toBeVisible();
    expect(screen.getByText('₹11,040')).toBeVisible();
    expect(screen.getByText('₹6,660')).toBeVisible();
  });

  it('records that the hospital corrected a charge', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    fireEvent.press(await screen.findByText('Inj. Meropenem 1g'));
    fireEvent.press(await screen.findByText('Hospital corrected it'));

    await waitFor(() => expect(screen.getByText('Corrected')).toBeVisible());
    // One question left, so the headline drops to the gloves alone.
    expect(screen.getByText('₹5,100')).toBeVisible();
  });

  it('switches to the marked-up bill', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    fireEvent.press(await screen.findByText('Marked bill'));

    expect(await screen.findByText('City Care Hospital')).toBeVisible();
    expect(screen.getByText('Room rent, twin sharing')).toBeVisible();
    expect(screen.getByText('Bill total')).toBeVisible();
    expect(screen.getByText('₹42,490')).toBeVisible();
  });

  it('groups the marked bill by the kind of charge', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    fireEvent.press(await screen.findByText('Marked bill'));

    // One heading per kind of charge the bill actually has, and no others.
    expect(await screen.findByText('Room and nursing')).toBeVisible();
    expect(screen.getByText('Medicines')).toBeVisible();
    expect(screen.getByText('Consumables')).toBeVisible();
    expect(screen.queryByText('Implants and devices')).toBeNull();
    expect(screen.queryByText('Other charges')).toBeNull();
  });

  it('shows each group what its lines come to', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    fireEvent.press(await screen.findByText('Marked bill'));

    // The point of the grouping: the medicines alone are more than the room,
    // which is worth asking about even where no single line was flagged.
    // 17,700 is both the group's subtotal and its one line, so it appears
    // twice; the room's 6,500 likewise.
    expect(await screen.findAllByText('₹17,700')).toHaveLength(2);
    expect(screen.getAllByText('₹6,500')).toHaveLength(2);
  });

  it('keeps every line of the bill on screen', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    fireEvent.press(await screen.findByText('Marked bill'));

    // Grouping must not lose a row. A family holds this up beside the
    // hospital's own copy, so a line that quietly isn't here is the one
    // failure this screen cannot have.
    for (const name of ['Room rent, twin sharing', 'Inj. Meropenem 1g', 'Surgical gloves']) {
      expect(await screen.findByText(name)).toBeVisible();
    }
  });

  it('still lets a flagged line in a group be opened', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    fireEvent.press(await screen.findByText('Marked bill'));
    fireEvent.press(await screen.findByText('Inj. Meropenem 1g'));

    expect(await screen.findByText("Why it's flagged")).toBeVisible();
  });
});

describe('asking the billing desk', () => {
  it('offers the message in all three languages', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3/ask' });

    expect(await screen.findByText(/I'm reviewing the interim bill/)).toBeVisible();
    expect(screen.getByText('English')).toBeVisible();
    expect(screen.getByText('हिंदी')).toBeVisible();
    expect(screen.getByText('मराठी')).toBeVisible();
  });

  it('rewrites the message in the language the family will speak', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3/ask' });
    fireEvent.press(await screen.findByText('मराठी'));

    expect(await screen.findByText(/मी रुग्ण Ramesh Sharma/)).toBeVisible();
  });

  it('shows where to go if the hospital does not resolve it', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3/ask' });

    expect(await screen.findByText('Hospital grievance officer')).toBeVisible();
    expect(screen.getByText('Insurer or TPA')).toBeVisible();
    expect(screen.getByText('Consumer commission')).toBeVisible();
  });
});
