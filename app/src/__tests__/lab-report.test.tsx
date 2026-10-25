import { afterAll, beforeEach, describe, expect, it, jest } from '@jest/globals';
import { Stack } from 'expo-router';
import { act, fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import LabReportScreen from '@/app/lab/[reportId]';
import LabConsentScreen from '@/app/lab/consent';
import NewLabReportScreen from '@/app/lab/new';
import FileScreen from '@/app/file';
import HomeScreen from '@/app/index';
import MemberScreen from '@/app/members/[memberId]';
import { AuthProvider } from '@/auth/auth-context';
import { ToastProvider } from '@/components/toast';
import { Colors } from '@/constants/theme';
import i18n from '@/i18n';
import { installFakeApi, SAMPLE_LAB } from '@/test-utils/fake-api';
import { resetTokenStore } from '@/test-utils/memory-token-store';

jest.mock('@/auth/token-store', () => jest.requireActual('@/test-utils/memory-token-store'));
jest.mock('@expo/vector-icons/Feather', () => () => null);

type Picked = { canceled: boolean; assets: { uri: string; fileName: string; mimeType: string }[] };
const mockCamera = jest.fn<() => Promise<Picked>>();

jest.mock('expo-image-picker', () => ({
  requestCameraPermissionsAsync: () => Promise.resolve({ granted: true }),
  launchCameraAsync: () => mockCamera(),
  launchImageLibraryAsync: () => mockCamera(),
}));
jest.mock('@/data/prepare-page', () => ({
  preparePage: (_asset: unknown, _number: number, page: unknown) => Promise.resolve(page),
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
  index: HomeScreen,
  file: FileScreen,
  'members/[memberId]': MemberScreen,
  'lab/consent': LabConsentScreen,
  'lab/new': NewLabReportScreen,
  'lab/[reportId]': LabReportScreen,
};

const PICKED: Picked = {
  canceled: false,
  assets: [{ uri: 'file:///report-page-1.jpg', fileName: 'report-1.jpg', mimeType: 'image/jpeg' }],
};

let server: ReturnType<typeof installFakeApi>;

/** A signed-in person, with or without lab reports agreed to. */
function signedIn(labConsent: boolean) {
  server.users.set('+919876543210', {
    id: 'u1',
    phone: '+919876543210',
    name: 'Rohan Sharma',
    lab_consent: labConsent,
  });
  server.sessions.set('saved-token', '+919876543210');
  resetTokenStore('saved-token');
}

beforeEach(async () => {
  await i18n.changeLanguage('en');
  server = installFakeApi();
  mockCamera.mockReset();
  mockCamera.mockResolvedValue(PICKED);
});

afterAll(() => i18n.changeLanguage('en'));

describe('starting from the home screen', () => {
  it('offers it under the bill, as the second thing the app does', async () => {
    signedIn(true);
    renderRouter(routes, { initialUrl: '/' });

    expect(await screen.findByText('Got a lab report?')).toBeVisible();
    expect(screen.getByText('Scan or upload report')).toBeVisible();
  });

  it('asks for its own consent first, because sign-up consent covers bills', async () => {
    signedIn(false);
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload report'));

    expect(await screen.findByText('Before your first lab report')).toBeVisible();
    expect(mockCamera).not.toHaveBeenCalled();
    // The one thing to hear before reading an explanation of your results.
    expect(screen.getByText(/We don't diagnose, and we don't replace your doctor/)).toBeVisible();
  });

  it('records the consent only once it is ticked, then goes on to the report', async () => {
    signedIn(false);
    renderRouter(routes, { initialUrl: '/lab/consent' });

    const go = await screen.findByRole('button', { name: 'Continue' });
    expect(go).toBeDisabled();
    fireEvent.press(screen.getByRole('checkbox'));
    await act(async () => fireEvent.press(go));

    expect(await screen.findByText('Explain a lab report')).toBeVisible();
    expect(server.calls).toContain('POST /lab-reports/consent');
    expect(server.users.get('+919876543210')?.lab_consent).toBe(true);
  });

  it('cannot be reached around the consent', async () => {
    signedIn(false);
    renderRouter(routes, { initialUrl: '/lab/new' });

    expect(await screen.findByText('Before your first lab report')).toBeVisible();
  });
});

describe('explaining a report', () => {
  /** Started from Papa, so it is his from the start and opens straight away. */
  async function explainOne() {
    signedIn(true);
    renderRouter(routes, { initialUrl: '/members/m-papa' });
    fireEvent.press(await screen.findByText('Scan or upload report'));
    fireEvent.press(await screen.findByText('Take a photo'));
    await screen.findByText('Explain a lab report');
    await act(async () => fireEvent.press(await screen.findByText('Explain report')));
  }

  it('leads with explaining it once there is a page', async () => {
    signedIn(true);
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload report'));
    fireEvent.press(await screen.findByText('Take a photo'));

    const explain = await screen.findByRole('button', { name: 'Explain report' });
    expect(explain).toHaveStyle({ backgroundColor: Colors.light.indigo });
  });

  it("shows each result as printed, against the report's own range", async () => {
    await explainOne();

    expect(await screen.findByText('Sample Diagnostics')).toBeVisible();
    expect(screen.getByText('Haemoglobin')).toBeVisible();
    expect(screen.getByText('9.8 g/dL')).toBeVisible();
    expect(screen.getByText('Report range: 12.0 - 15.0')).toBeVisible();
    expect(screen.getByText('Below the report’s range')).toBeVisible();
    expect(screen.getByText(/carries oxygen in the blood/)).toBeVisible();
  });

  it('says plainly when the report prints no range, rather than supplying one', async () => {
    await explainOne();

    expect(await screen.findByText('Negative')).toBeVisible();
    expect(screen.getByText('No range printed')).toBeVisible();
  });

  it('ends with what to ask the doctor, and that this is not a diagnosis', async () => {
    await explainOne();

    expect(await screen.findByText('Questions for your doctor')).toBeVisible();
    expect(screen.getByText('1. What does the haemoglobin result mean?')).toBeVisible();
    expect(screen.getByText(/It is not a diagnosis/)).toBeVisible();
  });

  it('keeps the pages when it cannot be read, so a retry is one tap', async () => {
    signedIn(true);
    server.failUpload = 'unreadable_lab_report';
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload report'));
    fireEvent.press(await screen.findByText('Take a photo'));
    await act(async () => fireEvent.press(await screen.findByText('Explain report')));

    expect(await screen.findByText(/This report couldn't be read/)).toBeOnTheScreen();
    expect(screen.getByLabelText('Remove page 1')).toBeVisible();
  });
});

describe('a page that is not a lab report', () => {
  it('says what it looks like and keeps the pages, rather than blaming the photo', async () => {
    signedIn(true);
    server.failUpload = 'not_a_lab_report';
    server.failUploadDocument = 'OB 2/3 Trimester Scan Report';
    renderRouter(routes, { initialUrl: '/members/m-papa' });
    fireEvent.press(await screen.findByText('Scan or upload report'));
    fireEvent.press(await screen.findByText('Take a photo'));
    await act(async () => fireEvent.press(await screen.findByText('Explain report')));

    expect(await screen.findByText("This doesn't look like a lab report")).toBeVisible();
    expect(screen.getByText(/It looks like “OB 2\/3 Trimester Scan Report”/)).toBeVisible();
    expect(screen.queryByText(/better light/)).toBeNull();
    expect(screen.getByLabelText('Remove page 1')).toBeVisible();
  });

  it('clears the message once the pages change', async () => {
    signedIn(true);
    server.failUpload = 'not_a_lab_report';
    renderRouter(routes, { initialUrl: '/members/m-papa' });
    fireEvent.press(await screen.findByText('Scan or upload report'));
    fireEvent.press(await screen.findByText('Take a photo'));
    await act(async () => fireEvent.press(await screen.findByText('Explain report')));
    await screen.findByText("This doesn't look like a lab report");

    fireEvent.press(screen.getByLabelText('Remove page 1'));

    expect(screen.queryByText("This doesn't look like a lab report")).toBeNull();
  });
});

describe('the two languages', () => {
  beforeEach(() => {
    signedIn(true);
    server.labReports.push(structuredClone(SAMPLE_LAB));
  });

  it('switches the explanation and leaves the figures exactly as printed', async () => {
    renderRouter(routes, { initialUrl: '/lab/lab-1' });
    await screen.findByText(/carries oxygen in the blood/);

    fireEvent.press(screen.getByRole('tab', { name: 'हिंदी' }));

    expect(screen.getByText(/खून में ऑक्सीजन ले जाता है/)).toBeVisible();
    expect(screen.getByText('दो में से एक नतीजा रिपोर्ट पर छपी सीमा से बाहर है।')).toBeVisible();
    expect(screen.getByText('9.8 g/dL')).toBeVisible();
    expect(screen.getByText('Haemoglobin')).toBeVisible();
    expect(screen.queryByText(/carries oxygen in the blood/)).toBeNull();
  });

  it('opens in Hindi on a Hindi phone', async () => {
    await i18n.changeLanguage('hi');
    renderRouter(routes, { initialUrl: '/lab/lab-1' });

    expect(await screen.findByText(/खून में ऑक्सीजन ले जाता है/)).toBeVisible();
  });
});

describe('a report the lab marked urgent', () => {
  it('says to show it to a doctor today, and no more than that', async () => {
    signedIn(true);
    server.labReports.push({ ...structuredClone(SAMPLE_LAB), urgent: true });
    renderRouter(routes, { initialUrl: '/lab/lab-1' });

    expect(await screen.findByText('Show this report to a doctor today')).toBeVisible();
  });

  it('shows nothing of the kind on one it did not mark', async () => {
    signedIn(true);
    server.labReports.push(structuredClone(SAMPLE_LAB));
    renderRouter(routes, { initialUrl: '/lab/lab-1' });

    await screen.findByText('Sample Diagnostics');
    expect(screen.queryByText('Show this report to a doctor today')).toBeNull();
  });
});

describe('whose report it is', () => {
  it('is theirs from the start when started from a member', async () => {
    signedIn(true);
    renderRouter(routes, { initialUrl: '/members/m-papa' });
    fireEvent.press(await screen.findByText('Scan or upload report'));
    fireEvent.press(await screen.findByText('Take a photo'));
    await act(async () => fireEvent.press(await screen.findByText('Explain report')));

    expect(await screen.findByText('Sample Diagnostics')).toBeVisible();
    expect(server.labReports[0].member).toEqual({ id: 'm-papa', name: 'Papa' });
  });

  it('is asked once it is read, when started from the home screen', async () => {
    signedIn(true);
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload report'));
    fireEvent.press(await screen.findByText('Take a photo'));
    await act(async () => fireEvent.press(await screen.findByText('Explain report')));

    // The name the report prints is offered for someone new.
    expect(await screen.findByText('Whose lab report is this?')).toBeVisible();
    expect(screen.getByText('The page says: TEST PATIENT')).toBeVisible();
    fireEvent.press(screen.getByText('Mummy'));
    await act(async () => fireEvent.press(screen.getByText('Continue')));

    expect(await screen.findByText('Sample Diagnostics')).toBeVisible();
    expect(server.labReports[0].member).toEqual({ id: 'm-mummy', name: 'Mummy' });
  });
});

describe('who the report is about, offered from the page', () => {
  it('fills someone new in with the name and says the age the report printed', async () => {
    signedIn(true);
    renderRouter(routes, { initialUrl: '/' });
    fireEvent.press(await screen.findByText('Scan or upload report'));
    fireEvent.press(await screen.findByText('Take a photo'));
    await act(async () => fireEvent.press(await screen.findByText('Explain report')));

    fireEvent.press(await screen.findByText('Someone new'));
    expect(screen.getByDisplayValue('TEST PATIENT')).toBeVisible();
    expect(screen.getByText('The page gives their age as 45.')).toBeVisible();
  });
});

describe('keeping it', () => {
  it("lists it under the member's lab reports to open again", async () => {
    signedIn(true);
    server.labReports.push({ ...structuredClone(SAMPLE_LAB), member: { id: 'm-papa', name: 'Papa' } });
    renderRouter(routes, { initialUrl: '/members/m-papa' });

    expect(await screen.findByText('Lab reports')).toBeVisible();
    expect(screen.getByText('1 result outside the report’s range')).toBeVisible();
    fireEvent.press(screen.getByText('Sample Diagnostics'));
    expect(await screen.findByText('Report range: 12.0 - 15.0')).toBeVisible();
  });

  it('can be deleted for good, after saying so', async () => {
    signedIn(true);
    server.labReports.push(structuredClone(SAMPLE_LAB));
    renderRouter(routes, { initialUrl: '/lab/lab-1' });

    fireEvent.press(await screen.findByText('Delete this report'));
    expect(screen.getByText(/deletes the report and its explanation for good/)).toBeVisible();
    await act(async () => fireEvent.press(screen.getByText('Yes, delete it')));

    await waitFor(() => expect(server.labReports).toEqual([]));
    expect(server.calls).toContain('DELETE /lab-reports/lab-1');
  });
});
