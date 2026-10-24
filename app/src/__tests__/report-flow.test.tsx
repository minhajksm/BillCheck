import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import { Stack } from 'expo-router';
import type { ReactTestInstance } from 'react-test-renderer';
import { fireEvent, renderRouter, screen, waitFor, within } from 'expo-router/testing-library';

import AskScreen from '@/app/bills/[billId]/ask';
import BillReportScreen from '@/app/bills/[billId]';
import CaseDashboardScreen from '@/app/cases/[caseId]';
import YourCasesScreen from '@/app/index';
import { AuthProvider, useAuth } from '@/auth/auth-context';
import { ToastProvider } from '@/components/toast';
import { Colors } from '@/constants/theme';
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

let server: ReturnType<typeof installFakeApi>;

beforeEach(() => {
  server = installFakeApi();
  server.users.set('+919876543210', {
    id: 'u1',
    phone: '+919876543210',
    name: 'Rohan Sharma',
  });
  server.sessions.set('saved-token', '+919876543210');
  resetTokenStore('saved-token');
});

/**
 * The element a node sits inside, skipping the component wrappers.
 *
 * `.parent` walks the React tree, so from the sheet's own heading it lands on
 * our `Text` component before the view that heading is laid out in.
 */
function hostParent(node: ReactTestInstance): ReactTestInstance {
  let found = node.parent;
  while (found && typeof found.type !== 'string') found = found.parent;
  if (!found) throw new Error('no element around this node');
  return found;
}

/** The report opens on the marked bill, so the summary is a tab away. */
async function openFlags() {
  fireEvent.press(await screen.findByText('Bill summary'));
}

describe('the bill report', () => {
  it('opens on the marked bill, not the flag list', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });

    // What a family does with this screen is hold it up beside the hospital's
    // own copy, so the bill is what it opens on.
    expect(await screen.findByText('City Care Hospital')).toBeVisible();
    expect(screen.getByText('Bill total')).toBeVisible();
    expect(screen.queryByText('1 other item is within range')).toBeNull();
  });

  it('puts the marked bill before the flags', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    const tabs = await screen.findAllByRole('tab');

    expect(tabs).toHaveLength(2);
    expect(tabs[0]).toHaveTextContent('Marked bill');
    expect(tabs[1]).toHaveTextContent('Bill summary');
  });

  it('shows what was flagged, with the reference each was checked against', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    await openFlags();

    expect(await screen.findByText('Inj. Meropenem 1g')).toBeVisible();
    // The reference is on screen, not just the verdict.
    expect(screen.getByText('Billed ₹2,950 a vial. The listed MRP is ₹1,840.')).toBeVisible();
    expect(screen.getByText('Above MRP')).toBeVisible();

    expect(screen.getByText('Surgical gloves')).toBeVisible();
    expect(screen.getByText('Worth asking')).toBeVisible();

    // The headline is the bill's own total; what is over a reference is a
    // line under it, and says what it means rather than standing alone.
    expect(screen.getByText(/₹11,760 above the references/)).toBeVisible();
  });

  it('says the rest of the bill is fine, rather than leaving it unsaid', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    await openFlags();
    expect(await screen.findByText('1 other item is within range')).toBeVisible();
  });

  it('never calls a flag a verdict', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    await screen.findByText('Inj. Meropenem 1g');

    expect(screen.getByText(/Flags are questions, not verdicts/)).toBeVisible();
  });

  it('opens a flag and explains why it was raised', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    await openFlags();
    fireEvent.press(await screen.findByText('Inj. Meropenem 1g'));

    expect(await screen.findByText("Why it's flagged")).toBeVisible();
    expect(screen.getByText(/Legal Metrology/)).toBeVisible();
    expect(screen.getByText('What to ask')).toBeVisible();
    expect(
      screen.getByText(/Ask the hospital pharmacy to show you the MRP and batch details printed on the pack/),
    ).toBeVisible();
    // The item and what it was billed for it, and nothing more: a tile
    // reading "At MRP ₹11,040" beside it read as our own figure for the
    // line, which is not what a reference price is.
    const sheet = within(hostParent(screen.getByRole('header', { name: 'Inj. Meropenem 1g' })));
    expect(sheet.getByText('₹17,700')).toBeVisible();
    expect(sheet.queryByText('₹11,040')).toBeNull();
    expect(sheet.queryByText('At MRP')).toBeNull();
  });

  it('says which line of the bill a flag is about', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    await openFlags();
    fireEvent.press(await screen.findByText('Inj. Meropenem 1g'));

    // A family reads this with the hospital's own copy in front of them, so
    // the explanation names the line as the bill numbers it.
    expect(await screen.findByText(/Legal Metrology rules. \(Line 5\)/)).toBeVisible();
  });

  it('records that the hospital corrected a charge', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    await openFlags();
    fireEvent.press(await screen.findByText('Inj. Meropenem 1g'));
    fireEvent.press(await screen.findByText('Hospital corrected it'));

    await waitFor(() => expect(screen.getByText('Corrected')).toBeVisible());
    // Both now: what the hospital put right, and what is still open.
    expect(screen.getByText(/₹6,660 recovered so far/)).toBeVisible();
    expect(screen.getByText(/₹5,100 above the references/)).toBeVisible();
  });

  it('shows the bill as the hospital printed it', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });

    expect(await screen.findByText('City Care Hospital')).toBeVisible();
    expect(screen.getByText('Room rent, twin sharing')).toBeVisible();
    expect(screen.getByText('Bill total')).toBeVisible();
    // Once at the top as the headline, once at the foot of the bill itself.
    expect(screen.getAllByText('₹42,490')).toHaveLength(2);
  });

  it('keeps the rows in the order the bill prints them', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    await screen.findByText('Room rent, twin sharing');

    // A family reads down this beside the hospital's own copy, so the line
    // they are looking at has to be where they are looking.
    const names = screen
      .getAllByText(/Room rent, twin sharing|Inj\. Meropenem 1g|Surgical gloves/)
      .map((node) => String(node.props.children));
    expect(names).toEqual(['Room rent, twin sharing', 'Inj. Meropenem 1g', 'Surgical gloves']);

    // And each row is numbered as the bill numbers it: 1, 5 and 10 here,
    // because the sample is three rows out of eleven.
    expect(screen.getAllByText(/^(1|5|10)$/).map((node) => Number(node.props.children))).toEqual([1, 5, 10]);
  });

  it('keeps every line of the bill on screen', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });

    // A line that quietly isn't here is the one failure this screen cannot
    // have: it is the family's own bill.
    for (const name of ['Room rent, twin sharing', 'Inj. Meropenem 1g', 'Surgical gloves']) {
      expect(await screen.findByText(name)).toBeVisible();
    }
  });

  it('says what each kind of charge came to', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    await screen.findByText('City Care Hospital');

    // Over on the summary tab with the questions, not under the bill: the
    // marked bill is the family's own copy, line for line, and nothing else.
    expect(screen.queryByText('Where it went')).toBeNull();
    await openFlags();
    expect(await screen.findByText('Where it went')).toBeVisible();
    expect(screen.getByText('Room and nursing')).toBeVisible();
    expect(screen.getByText('Medicines')).toBeVisible();
    expect(screen.getByText('Consumables')).toBeVisible();
    expect(screen.queryByText('Implants and devices')).toBeNull();
  });

  it('lets a flagged line on the bill be opened', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    fireEvent.press(await screen.findByText('Inj. Meropenem 1g'));

    expect(await screen.findByText("Why it's flagged")).toBeVisible();
  });

  it('colours a line for its own level, not every flagged line alike', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });

    // Both were painted amber, so a line the sheet then opened as a red
    // "Duplicate" was striped as though it were only worth asking about.
    expect(await screen.findByLabelText('1: Inj. Meropenem 1g')).toHaveStyle({
      backgroundColor: Colors.light.redSoft,
    });
    expect(screen.getByLabelText('2: Surgical gloves')).toHaveStyle({
      backgroundColor: Colors.light.marigoldSoft,
    });
  });

  it('stands for the worst flag when one line carries two', async () => {
    const bill = server.bills[0];
    bill.flags.push({
      ...structuredClone(bill.flags[1]),
      id: 'f-second',
      position: 3,
      line_item_id: 'li-5',
    });
    renderRouter(routes, { initialUrl: '/bills/b-day3' });

    // The amber one is listed last, and used to win the line by arriving last.
    expect(await screen.findByLabelText('1: Inj. Meropenem 1g')).toHaveStyle({
      backgroundColor: Colors.light.redSoft,
    });
  });
});

describe('a bill that discounts', () => {
  /** The Olive bill's shape: two money columns and three totals under them. */
  function discount() {
    Object.assign(server.bills[0], { subtotal: 42490, discount: 7490, total: 35000 });
  }

  it('leads with what the hospital is asking for, not the sum of the lines', async () => {
    discount();
    renderRouter(routes, { initialUrl: '/bills/b-day3' });

    // It used to lead with the gross, so a family holding a bill for 35,000
    // opened the report and read 42,490.
    const payable = await screen.findAllByText('₹35,000');
    expect(payable).toHaveLength(2); // the headline, and the foot of the ledger
    expect(payable[0]).toHaveStyle({ fontSize: 34 }); // `variant="big"`, the headline
    expect(screen.getByText('₹42,490 billed, less a ₹7,490 discount')).toBeVisible();
  });

  it('prints the ledger the bill prints, so the rows still add up', async () => {
    discount();
    renderRouter(routes, { initialUrl: '/bills/b-day3' });

    expect(await screen.findByText('Sub total')).toBeVisible();
    expect(screen.getByText('₹42,490')).toBeVisible();
    expect(screen.getByText('Discount')).toBeVisible();
    expect(screen.getByText('−₹7,490')).toBeVisible();
    expect(screen.getAllByText('Bill total').length).toBeGreaterThan(0);
  });

  it('says nothing about a discount on a bill that has none', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });

    expect(await screen.findByText('Bill total')).toBeVisible();
    expect(screen.queryByText('Sub total')).toBeNull();
    expect(screen.queryByText('Discount')).toBeNull();
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

describe('the report header', () => {
  it('leads with the bill, not with a figure the audit may not have', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });

    // The headline used to be the sum of what every open flag was over its
    // reference. The reader cannot produce that for the questions it raises
    // itself, so a bill flagged six times read "Possible overcharge / ₹0".
    expect(await screen.findByText('City Care Hospital')).toBeVisible();
    expect(screen.queryByText('Possible overcharge')).toBeNull();
    expect(screen.queryByText('₹0')).toBeNull();
  });

  it('counts lines, not flags, so the shape cannot exceed the bill', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    await screen.findByText('City Care Hospital');

    // Three rows, two of them flagged once each. Counting flags against rows
    // is what produced "10 of 9 items need a look" on a real bill, where two
    // flags had landed on one line.
    expect(screen.getByText('1 clear')).toBeVisible();
    expect(screen.getByText('1 to ask')).toBeVisible();
    expect(screen.getByText('1 fine')).toBeVisible();
  });

  it('describes the bar for a reader who cannot see it', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });

    expect(
      await screen.findByLabelText('1 clear issues, 1 worth asking about, 1 within range'),
    ).toBeVisible();
  });

  it('names the hospital and patient once, above the bill rather than on it', async () => {
    renderRouter(routes, { initialUrl: '/bills/b-day3' });
    await screen.findByText('City Care Hospital');

    // The marked bill is the family's own copy of the rows and nothing else.
    expect(screen.getAllByText('City Care Hospital')).toHaveLength(1);
    expect(screen.getByText('IP no. 20841, Ramesh Sharma')).toBeVisible();
  });
});
