import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import { render, screen } from '@testing-library/react-native';

import { ReadingBill } from '@/components/reading-bill';
import i18n from '@/i18n';

jest.mock('@expo/vector-icons/Feather', () => () => null);

/**
 * The waiting screen, and what moves it on.
 *
 * The point of these: two of the three steps are driven by the upload itself,
 * and only the last is a guess. A screen that claims to know more than it does
 * is worse than a spinner, because a family trusts it.
 */
function reading(sent: number, pages = 1) {
  return render(<ReadingBill sent={sent} pages={pages} />);
}

beforeEach(async () => {
  await i18n.changeLanguage('en');
});

describe('while the bill is read', () => {
  it('counts the pages up from the upload itself', () => {
    reading(0.42, 3);
    expect(screen.getByText('Sending 3 pages · 42%')).toBeVisible();
  });

  it('moves to the reading when the last byte lands', () => {
    const view = reading(0.9);
    expect(screen.getByText('Sending 1 page · 90%')).toBeVisible();

    view.rerender(<ReadingBill sent={1} pages={1} />);

    // Not a timer: the upload finishing is what moved it.
    expect(screen.queryByText(/· 90%/)).toBeNull();
    expect(screen.getByText('Sending the pages')).toBeVisible();
  });

  it('says how many pages it is reading', () => {
    reading(1, 3);
    // Known: it is what the family photographed.
    expect(screen.getByText('Reading every line of 3 pages')).toBeVisible();
  });

  it('never claims to know which page it is on', () => {
    reading(1, 3);
    // The pages go up in one request and are read together, so there is no
    // page 2 to be on. A count that looked busier would be made up.
    expect(screen.queryByText(/of 3$/)).toBeNull();
    expect(screen.queryByText(/[Pp]age 2/)).toBeNull();
  });

  it('does not count a single page at the family', () => {
    reading(1);
    // "Reading every line of 1 page" tells them nothing they can't see.
    expect(screen.getByText('Reading every line of the bill')).toBeVisible();
  });

  it('names all three steps from the start', () => {
    reading(0);
    // A family can see what is coming, not just what is happening.
    expect(screen.getByText('Sending the pages')).toBeVisible();
    expect(screen.getByText('Reading every line of the bill')).toBeVisible();
    expect(screen.getByText('Checking the charges against price lists')).toBeVisible();
  });

  it('never says how long is left', () => {
    reading(1);
    // Nothing here knows how far through the reading is, and a bar stalled at
    // 90% is worse than no bar.
    expect(screen.getByText('This usually takes under a minute. Keep the app open.')).toBeVisible();
    // No percentage anywhere once the pages are up: the reading's own
    // progress is not something this app can see.
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it('tells a screen reader which step it is on', () => {
    reading(1);
    expect(screen.getByLabelText('Reading every line of the bill')).toBeTruthy();
  });
});
