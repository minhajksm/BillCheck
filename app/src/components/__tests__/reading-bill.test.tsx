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
function reading(sent: number) {
  return render(<ReadingBill sent={sent} />);
}

beforeEach(async () => {
  await i18n.changeLanguage('en');
});

describe('while the bill is read', () => {
  it('counts the pages up from the upload itself', () => {
    reading(0.42);
    expect(screen.getByText('Sending the pages · 42%')).toBeVisible();
  });

  it('moves to the reading when the last byte lands', () => {
    const view = reading(0.9);
    expect(screen.getByText('Sending the pages · 90%')).toBeVisible();

    view.rerender(<ReadingBill sent={1} />);

    // Not a timer: the upload finishing is what moved it.
    expect(screen.queryByText(/Sending the pages ·/)).toBeNull();
    expect(screen.getByText('Sending the pages')).toBeVisible();
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
