import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import { Stack } from 'expo-router';
import { act, fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { Image } from 'react-native';

import BillReportScreen from '@/app/bills/[billId]';
import ScanScreen from '@/app/cases/[caseId]/scan';
import FileScreen from '@/app/file';
import YourCasesScreen from '@/app/index';
import MemberScreen from '@/app/members/[memberId]';
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
type PickedFile = { canceled: boolean; assets: { uri: string; name: string; mimeType?: string }[] };

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
  file: FileScreen,
  'members/[memberId]': MemberScreen,
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
  fireEvent.press(await screen.findByText('Scan or upload bill'));
  fireEvent.press(await screen.findByText('Take a photo'));
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
    // One button: the camera, the gallery and the phone's files are chosen after the tap.
    expect(screen.getByText('Scan or upload bill')).toBeVisible();
  });

  it('opens the camera on the tap, with no screen in between', async () => {
    mockCamera.mockResolvedValue(PICKED);
    renderRouter(routes, { initialUrl: '/' });

    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Take a photo'));

    await waitFor(() => expect(mockCamera).toHaveBeenCalledTimes(1));
  });

  it('carries the page through to the scan screen', async () => {
    mockCamera.mockResolvedValue(PICKED);
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Take a photo'));

    // Staged, counted, and ready to check: the page is not photographed twice.
    expect(await screen.findByText('1 page added. Add the next page, or check the bill.')).toBeVisible();
    expect(screen.getByText('Check bill')).toBeVisible();
  });

  it('stays put when the picker is cancelled', async () => {
    mockCamera.mockResolvedValue({ canceled: true, assets: [] });
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Take a photo'));

    await waitFor(() => expect(mockCamera).toHaveBeenCalled());
    expect(screen.getByText('Have a hospital bill?')).toBeVisible();
  });

  /** Signed in, and the bill on the home screen read: on to "whose is it?". */
  async function readFromHome() {
    mockCamera.mockResolvedValue(PICKED);
    const server = installFakeApi();
    server.users.set('+919876543210', { id: 'u1', phone: '+919876543210', name: 'Rohan Sharma' });
    server.sessions.set('saved-token', '+919876543210');
    resetTokenStore('saved-token');
    return server;
  }

  async function checkFromHome() {
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Take a photo'));
    fireEvent.press(await screen.findByText('Check bill'));
    return screen.findByText('Whose bill is this?');
  }

  it('reads the bill, then asks whose it is, offering the name it prints', async () => {
    const server = await readFromHome();

    expect(await checkFromHome()).toBeVisible();
    expect(server.calls).toContain('POST /bills');
    expect(screen.getByText('The page says: Ramesh Sharma')).toBeVisible();
    // Nobody is picked for them: "Ramesh Sharma" is neither "Papa" nor
    // "Mummy" as far as anything here can tell.
    expect(screen.getByRole('radio', { name: 'Papa' })).not.toBeChecked();
    expect(screen.getByRole('radio', { name: 'Mummy' })).not.toBeChecked();
  });

  it('files it under someone already there, then shows the report', async () => {
    const server = await readFromHome();
    await checkFromHome();

    fireEvent.press(screen.getByText('Papa'));
    await act(async () => fireEvent.press(screen.getByText('Continue')));

    expect(await screen.findByText('Bill total')).toBeVisible();
    expect(server.cases[0].member).toEqual({ id: 'm-papa', name: 'Papa' });
  });

  it('adds someone new by the name on the bill', async () => {
    const server = await readFromHome();
    await checkFromHome();

    fireEvent.press(screen.getByText('Someone new'));
    expect(screen.getByDisplayValue('Ramesh Sharma')).toBeVisible();
    await act(async () => fireEvent.press(screen.getByText('Continue')));

    expect(await screen.findByText('Bill total')).toBeVisible();
    expect(server.members.map((m) => m.name)).toContain('Ramesh Sharma');
    expect(server.cases[0].member?.name).toBe('Ramesh Sharma');
  });

  it('picks the member the bill names, where there is one', async () => {
    const server = await readFromHome();
    server.members[0].name = 'RAMESH  sharma';

    await checkFromHome();

    expect(screen.getByRole('radio', { name: 'RAMESH  sharma' })).toBeChecked();
  });

  it('asks for a choice rather than guessing', async () => {
    const server = await readFromHome();
    await checkFromHome();

    await act(async () => fireEvent.press(screen.getByText('Continue')));

    expect(await screen.findByText('Choose someone, or add someone new.')).toBeOnTheScreen();
    expect(server.cases[0].member).toBeNull();
  });

  it('needs no question when the bill was scanned from a member', async () => {
    const server = await readFromHome();
    renderRouter(routes, { initialUrl: '/members/m-papa' });
    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Take a photo'));
    fireEvent.press(await screen.findByText('Check bill'));

    expect(await screen.findByText('Bill total')).toBeVisible();
    expect(server.cases[0].member).toEqual({ id: 'm-papa', name: 'Papa' });
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
    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Take a photo'));
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
    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Take a photo'));
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
    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Take a photo'));
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

  it('still lets an admission be started by hand, from the member', async () => {
    renderRouter(routes, { initialUrl: '/members/m-papa' });

    // For anyone setting a case up before the first bill arrives.
    expect(await screen.findByText('Add an admission by hand')).toBeVisible();
  });
});

describe('a page that is not a hospital bill', () => {
  it('says what it looks like, where it belongs, and keeps the pages', async () => {
    mockCamera.mockResolvedValue(PICKED);
    const server = installFakeApi();
    server.users.set('+919876543210', { id: 'u1', phone: '+919876543210', name: 'Rohan Sharma' });
    server.sessions.set('saved-token', '+919876543210');
    resetTokenStore('saved-token');
    server.failUpload = 'not_a_bill';
    server.failUploadDocument = 'Complete Blood Count';

    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Take a photo'));
    fireEvent.press(await screen.findByText('Check bill'));

    expect(await screen.findByText("This doesn't look like a hospital bill")).toBeVisible();
    expect(screen.getByText(/It looks like “Complete Blood Count”/)).toBeVisible();
    expect(screen.getByText(/use “Scan or upload report” instead/)).toBeVisible();
    expect(screen.getByText('Check bill')).toBeVisible();
  });
});

describe('one button for every way a page arrives', () => {
  it("offers the camera, the gallery and the phone's files after one tap", async () => {
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload bill'));

    expect(await screen.findByText('Take a photo')).toBeVisible();
    expect(screen.getByText('Choose from gallery')).toBeVisible();
    expect(screen.getByText('Choose a file')).toBeVisible();
    expect(screen.getByText('A PDF or a photo saved on the phone')).toBeVisible();
    // Nothing is opened until they choose.
    expect(mockCamera).not.toHaveBeenCalled();
    expect(mockLibrary).not.toHaveBeenCalled();
  });

  it('closes without picking anything when cancelled', async () => {
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Cancel'));

    await waitFor(() => expect(screen.queryByText('Take a photo')).toBeNull());
    expect(mockCamera).not.toHaveBeenCalled();
  });

  it('takes pages from the gallery', async () => {
    mockLibrary.mockResolvedValue(PICKED);
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Choose from gallery'));

    expect(await screen.findByText('1 page added. Add the next page, or check the bill.')).toBeVisible();
    expect(mockLibrary).toHaveBeenCalledTimes(1);
  });

  it("takes a photo saved in the phone's files, not only a PDF", async () => {
    mockDocument.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file:///Download/bill-photo.jpg', name: 'bill-photo.jpg', mimeType: 'image/jpeg' }],
    });
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Choose a file'));

    expect(await screen.findByText('1 page added. Add the next page, or check the bill.')).toBeVisible();
    // A photo, shown as one, rather than a PDF shown by name.
    const [preview] = screen.UNSAFE_getAllByType(Image);
    expect(preview.props.source).toEqual({ uri: 'file:///Download/bill-photo.jpg' });
  });
});

describe('who the bill is about, offered from the page', () => {
  async function readFromHome() {
    mockCamera.mockResolvedValue(PICKED);
    const server = installFakeApi();
    server.users.set('+919876543210', { id: 'u1', phone: '+919876543210', name: 'Rohan Sharma' });
    server.sessions.set('saved-token', '+919876543210');
    resetTokenStore('saved-token');
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload bill'));
    fireEvent.press(await screen.findByText('Take a photo'));
    fireEvent.press(await screen.findByText('Check bill'));
    await screen.findByText('Whose bill is this?');
    return server;
  }

  it('fills someone new in from the page, every field editable', async () => {
    const server = await readFromHome();
    fireEvent.press(screen.getByText('Someone new'));

    expect(screen.getByDisplayValue('Ramesh Sharma')).toBeVisible();
    expect(screen.getByDisplayValue('9876543210')).toBeVisible();
    expect(screen.getByDisplayValue('12 Example Road, Andheri, Mumbai 400058')).toBeVisible();
    // The age the bill printed is said, never turned into a date of birth.
    expect(screen.getByText('The page gives their age as 68.')).toBeVisible();
    expect(screen.getByLabelText('Date of birth (optional)')).toHaveDisplayValue('');

    await act(async () => fireEvent.press(screen.getByText('Continue')));

    expect(await screen.findByText('Bill total')).toBeVisible();
    const added = server.members.find((m) => m.name === 'Ramesh Sharma');
    expect(added).toMatchObject({
      phone: '+919876543210',
      address: '12 Example Road, Andheri, Mumbai 400058',
    });
  });

  it("offers to add the page's details to someone already there", async () => {
    const server = await readFromHome();
    fireEvent.press(screen.getByText('Papa'));

    const add = screen.getByRole('checkbox', { name: "Add what the page shows to Papa's details" });
    expect(add).toBeChecked();
    expect(screen.getByText('+91 98765 43210')).toBeVisible();
    expect(screen.getByText(/Nothing already saved is changed/)).toBeVisible();
    await act(async () => fireEvent.press(screen.getByText('Continue')));

    await screen.findByText('Bill total');
    expect(server.members[0]).toMatchObject({ name: 'Papa', phone: '+919876543210' });
  });

  it('adds nothing to them when told not to', async () => {
    const server = await readFromHome();
    fireEvent.press(screen.getByText('Papa'));
    fireEvent.press(screen.getByRole('checkbox', { name: "Add what the page shows to Papa's details" }));
    await act(async () => fireEvent.press(screen.getByText('Continue')));

    await screen.findByText('Bill total');
    expect(server.members[0]).toMatchObject({ phone: null, address: null });
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
    fireEvent.press(await screen.findByText('Add pages'));
    fireEvent.press(await screen.findByText('Choose a file'));

    expect(await screen.findByText('final-bill.pdf')).toBeVisible();
    expect(screen.UNSAFE_queryAllByType(Image)).toEqual([]);
  });
});

describe('what to do next on the scan screen', () => {
  it('leads with the camera while there is nothing to check', async () => {
    renderRouter(routes, { initialUrl: '/scan' });

    const photo = await screen.findByRole('button', { name: 'Add pages' });
    expect(photo).toHaveStyle({ backgroundColor: Colors.light.indigo });
    expect(screen.queryByText('Check bill')).toBeNull();
  });

  it('leads with checking the bill the moment there is one', async () => {
    await withOnePage();

    // "Check bill" used to be the fourth button down and the quietest of
    // them, under three ways to add another page.
    const check = screen.getByRole('button', { name: 'Check bill' });
    const photo = screen.getByRole('button', { name: 'Add another page' });
    expect(check).toHaveStyle({ backgroundColor: Colors.light.indigo });
    expect(photo).not.toHaveStyle({ backgroundColor: Colors.light.indigo });
  });
});
