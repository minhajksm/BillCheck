import type { ScannedPage } from './cases-api';

/**
 * Pages picked on one screen and read on the next.
 *
 * The home screen offers "Photograph bill" as the first thing a family sees,
 * so the picker opens there -- but the pages are staged and checked on the
 * scan screen, where more pages can be added and removed. Router params carry
 * strings, not file handles, so they come across here instead.
 *
 * Deliberately a single slot, and emptied by whoever takes it: this is a
 * handoff between two screens in one gesture, not a store. A second tap on the
 * home screen replaces what the first one left.
 */
let waiting: ScannedPage[] = [];

export function stagePages(pages: ScannedPage[]): void {
  waiting = pages;
}

/** The staged pages, and empties the slot. */
export function takeStagedPages(): ScannedPage[] {
  const staged = waiting;
  waiting = [];
  return staged;
}
