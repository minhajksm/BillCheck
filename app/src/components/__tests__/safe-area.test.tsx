/**
 * Every screen keeps clear of the system bars.
 *
 * A screen that leaves the bottom edge out looks right in a simulator and
 * wrong on a phone: Android's navigation bar sits over the last thing on the
 * page, which on most of these screens is the button the screen exists for.
 * It is visible, half covered, and does not respond to a tap. Nothing in
 * jsdom reproduces that -- there are no insets here -- so this checks the
 * decision rather than the pixels.
 */

import { describe, expect, it } from '@jest/globals';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const EDGES = /edges=\{\[([^\]]*)\]\}/g;

/** Every .tsx under src/, tests aside. No glob library: the only one on disk
 *  is there by way of something else's dependencies, and would go with it. */
function screens(dir = 'src'): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : screens(path);
    return entry.name.endsWith('.tsx') ? [path] : [];
  });
}

function safeAreaEdges(): { file: string; edges: string }[] {
  const found: { file: string; edges: string }[] = [];
  for (const file of screens()) {
    for (const match of readFileSync(file, 'utf8').matchAll(EDGES)) {
      found.push({ file, edges: match[1] });
    }
  }
  return found;
}

describe('safe-area edges', () => {
  it('are declared somewhere, or this test is checking nothing', () => {
    expect(safeAreaEdges().length).toBeGreaterThan(3);
  });

  it.each(safeAreaEdges())('$file keeps clear of the bottom bar', ({ edges }) => {
    expect(edges).toContain('bottom');
  });

  it.each(safeAreaEdges())('$file keeps clear of the status bar and notch', ({ edges }) => {
    expect(edges).toContain('top');
  });
});
