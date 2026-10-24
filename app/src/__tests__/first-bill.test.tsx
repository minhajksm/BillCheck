import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import { Stack } from 'expo-router';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { Image } from 'react-native';

import BillReportScreen from '@/app/bills/[billId]';
import ScanScreen from '@/app/cases/[caseId]/scan';
import YourCasesScreen from '@/app/index';
import FirstScanScreen from '@/app/scan';
import { AuthProvider } from '@/auth/auth-context';
import i18n from '@/i18n';
import { ToastProvider } from '@/components/toast';
import { Colors } from '@/constants/theme';
import { installFakeApi } from '@/test-utils/fake-api';
import { resetTokenStore } from '@/test-utils/memory-token-store';

jest.mock('@/auth/token-store', () => jest.requireActual('@/test-utils/memory-token-store'));
jest.mock('@expo/vector-icons/Feather', () => () => null);

/** What a picker hands back: either a cancellation or the chosen assets. */
type Picked = {
  canceled: boolean;
  assets: { uri: string; fileName: string; mimeType: string }[];
};

/** What the document picker hands back for a PDF. */
type PickedFile = { canceled: boolean; assets: { uri: string; name: string }[] };

// Prefixed `mock` so the factories below may reach them: jest hoists
// `jest.mock` above the file, and only these names are allowed through.
const mockCamera = jest.fn<() => Promise<Picked>>();
const mockLibrary = jest.fn<() => Promise<Picked>>();

jest.mock('expo-image-picker', () => ({
  requestCameraPermissionsAsync: () => Promise.resolve({ granted: true }),
  launchCameraAsync: () => mockCamera(),
  launchImageLibraryAsync: () => mockLibrary(),
}));

const mockDocument = jest.fn<() => Promise<PickedFile>>();

jest.mock('expo-document-picker', () => ({
  getDocumentAsync: () => mockDocument(),
}));

jest.mock('@/data/prepare-page', () => ({
  // The real one re-encodes through expo-image-manipulator. What it produces
  // is a ScannedPage, and that is all these tests need.
  preparePage: (_asset: unknown, number: number, page: unknown) => Promise.resolve(page),
}));

function TestLayout() {
  return (
    <AuthProvider>
      <ToastProvider>
        <Stack screenOptions={{ headerShown: false }} />
      </ToastProvider>
    </AuthProvider>
  );
}

const routes = {
  _layout: TestLayout,
  index: YourCasesScreen,
  scan: FirstScanScreen,
  'cases/[caseId]/scan': ScanScreen,
  'bills/[billId]': BillReportScreen,
};

/** One page, as the picker would hand it back. */
const PICKED: Picked = {
  canceled: false,
  assets: [
    {
      uri: 'file:///bill-page-1.jpg',
      fileName: 'page-1.jpg',
      mimeType: 'image/jpeg',
    },
  ],
};

beforeEach(async () => {
  await i18n.changeLanguage('en');
  const server = installFakeApi();
  server.users.set('+919876543210', {
    id: 'u1',
    phone: '+919876543210',
    name: 'Rohan Sharma',
  });
  server.sessions.set('saved-token', '+919876543210');
  resetTokenStore('saved-token');
  mockCamera.mockReset();
  mockLibrary.mockReset();
  mockDocument.mockReset();
});

/** The scan screen with one page already on it. */
async function withOnePage() {
  mockCamera.mockResolvedValue(PICKED);
  renderRouter(routes, { initialUrl: '/' });
  fireEvent.press(await screen.findByText('Photograph bill'));
  await screen.findByText('Check bill');
}

/**
 * Checking a bill before there is a case for it.
 *
 * This is the first thing a signed-in family can do, and the reason is in the
 * bill itself: the hospital, the patient, the IP number and the admission date
 * are all printed on the page they are already holding, so a form asking for
 * them is asking twice.
 */
describe('checking a bill from the home screen', () => {
  it('offers it before anything else on the screen', async () => {
    renderRouter(routes, { initialUrl: '/' });

    expect(await screen.findByText('Have a hospital bill?')).toBeVisible();
    expect(screen.getByText('Photograph bill')).toBeVisible();
    expect(screen.getByText('Upload photo or PDF')).toBeVisible();
  });

  it('opens the camera on the tap, with no screen in between', async () => {
    mockCamera.mockResolvedValue(PICKED);
    renderRouter(routes, { initialUrl: '/' });

    fireEvent.press(await screen.findByText('Photograph bill'));

    await waitFor(() => expect(mockCamera).toHaveBeenCalledTimes(1));
  });

  it('carries the page through to the scan screen', async () => {
    mockCamera.mockResolvedValue(PICKED);
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Photograph bill'));

    // Staged, counted, and ready to check: the page is not photographed twice.
    expect(await screen.findByText('1 page added. Add the next page, or check the bill.')).toBeVisible();
    expect(screen.getByText('Check bill')).toBeVisible();
  });

  it('stays put when the picker is cancelled', async () => {
    mockCamera.mockResolvedValue({ canceled: true, assets: [] });
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Photograph bill'));

    await waitFor(() => expect(mockCamera).toHaveBeenCalled());
    expect(screen.getByText('Have a hospital bill?')).toBeVisible();
  });

  it('reads the bill and opens a case from it', async () => {
    mockCamera.mockResolvedValue(PICKED);
    const server = installFakeApi();
    server.users.set('+919876543210', {
      id: 'u1',
      phone: '+919876543210',
      name: 'Rohan Sharma',
    });
    server.sessions.set('saved-token', '+919876543210');
    resetTokenStore('saved-token');

    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Photograph bill'));
    fireEvent.press(await screen.findByText('Check bill'));

    // Straight to the report, on the marked bill.
    expect(await screen.findByText('Bill total')).toBeVisible();
    expect(server.calls).toContain('POST /bills');
    // And the case it opened is the family's, not one they had to name.
    expect(server.cases[0].title).toBe('Ramesh Sharma');
  });

  it('shows the reading animation while the bill is read', async () => {
    mockCamera.mockResolvedValue(PICKED);
    const server = installFakeApi();
    server.users.set('+919876543210', { id: 'u1', phone: '+919876543210', name: 'Rohan Sharma' });
    server.sessions.set('saved-token', '+919876543210');
    resetTokenStore('saved-token');
    // The pages land and the reading never comes back: the minute a family
    // spends on this screen.
    server.stallUpload = true;

    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Photograph bill'));
    fireEvent.press(await screen.findByText('Check bill'));

    expect(await screen.findByText('Checking your bill')).toBeVisible();
    // It says which of the three it is on, rather than spinning: the read
    // takes most of a minute, and a spinner that long reads as a hung app.
    expect(screen.getByText('Reading every line of the bill')).toBeVisible();
    expect(screen.getByText('Checking the charges against price lists')).toBeVisible();
    // And it never promises how long: nothing here knows.
    expect(screen.getByText('This usually takes under a minute. Keep the app open.')).toBeVisible();
  });

  it('counts the pages up while they are still going', async () => {
    mockCamera.mockResolvedValue(PICKED);
    const server = installFakeApi();
    server.users.set('+919876543210', { id: 'u1', phone: '+919876543210', name: 'Rohan Sharma' });
    server.sessions.set('saved-token', '+919876543210');
    resetTokenStore('saved-token');
    // Held at half sent, so the first step is the one on screen.
    server.stallUpload = true;
    global.XMLHttpRequest = class {
      upload: { onprogress?: (event: ProgressEvent) => void } = {};
      open() {}
      setRequestHeader() {}
      send() {
        this.upload.onprogress?.({ lengthComputable: true, loaded: 37, total: 100 } as ProgressEvent);
      }
    } as unknown as typeof XMLHttpRequest;

    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Photograph bill'));
    fireEvent.press(await screen.findByText('Check bill'));

    // The one figure on the screen that is measured rather than estimated.
    expect(await screen.findByText('Sending 1 page · 37%')).toBeVisible();
  });

  it('keeps the pages when the read fails, so nothing is photographed twice', async () => {
    mockCamera.mockResolvedValue(PICKED);
    const server = installFakeApi();
    server.users.set('+919876543210', { id: 'u1', phone: '+919876543210', name: 'Rohan Sharma' });
    server.sessions.set('saved-token', '+919876543210');
    resetTokenStore('saved-token');
    server.failUpload = 'unreadable_bill';

    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Photograph bill'));
    fireEvent.press(await screen.findByText('Check bill'));

    // The toast fades in through Animated, which the test renderer does not
    // advance, so this asserts it was raised rather than that it has finished
    // appearing.
    expect(
      await screen.findByText(/This bill couldn't be read. Try again in better light/),
    ).toBeOnTheScreen();

    // The point of the test: the page is still staged, so a retry is one tap
    // and not another trip to the counter.
    expect(screen.getByText('1 page added. Add the next page, or check the bill.')).toBeVisible();
    expect(screen.getByText('Check bill')).toBeVisible();
  });

  it('still lets a case be started by hand', async () => {
    renderRouter(routes, { initialUrl: '/' });

    // For anyone setting a case up before the first bill arrives.
    expect(await screen.findByText('Start a new case')).toBeVisible();
  });
});

describe('the page waiting to be checked', () => {
  it('is the photograph itself, not a numbered box', async () => {
    await withOnePage();

    // A stamp-sized square with a "1" in it proved nothing about whether the
    // page is square in frame or the small print came out.
    const [preview] = screen.UNSAFE_getAllByType(Image);
    expect(preview.props.source).toEqual({ uri: 'file:///bill-page-1.jpg' });
    expect(preview.props.resizeMode).toBe('contain');
  });

  it('is still removable by tapping it', async () => {
    await withOnePage();

    fireEvent.press(screen.getByLabelText('Remove page 1'));
    expect(await screen.findByText(/Fit one page inside the frame/)).toBeVisible();
  });

  it('shows a PDF by name, having no picture to show', async () => {
    mockDocument.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file:///final-bill.pdf', name: 'final-bill.pdf' }],
    });
    renderRouter(routes, { initialUrl: '/scan' });
    fireEvent.press(await screen.findByText('Upload PDF'));

    expect(await screen.findByText('final-bill.pdf')).toBeVisible();
    expect(screen.UNSAFE_queryAllByType(Image)).toEqual([]);
  });
});

describe('what to do next on the scan screen', () => {
  it('leads with the camera while there is nothing to check', async () => {
    renderRouter(routes, { initialUrl: '/scan' });

    const photo = await screen.findByRole('button', { name: 'Take photo' });
    expect(photo).toHaveStyle({ backgroundColor: Colors.light.indigo });
    expect(screen.queryByText('Check bill')).toBeNull();
  });

  it('leads with checking the bill the moment there is one', async () => {
    await withOnePage();

    // "Check bill" used to be the fourth button down and the quietest of
    // them, under three ways to add another page.
    const check = screen.getByRole('button', { name: 'Check bill' });
    const photo = screen.getByRole('button', { name: 'Take photo' });
    expect(check).toHaveStyle({ backgroundColor: Colors.light.indigo });
    expect(photo).not.toHaveStyle({ backgroundColor: Colors.light.indigo });
  });
});
