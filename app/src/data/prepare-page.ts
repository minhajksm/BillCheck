/**
 * Getting a photographed page ready to upload.
 *
 * A phone camera shoots 12 MP or more, but Claude reads a page at most 2,576px
 * on its long edge, and a whole request is capped at 32 MB. Sending the full
 * photo only makes the upload slow on hospital mobile data, and can push a
 * many-page bill past the cap, where it fails as "couldn't be read". So every
 * page is scaled down to what will actually be read, and saved as JPEG,
 * which also turns an iPhone HEIC photo into something the reader accepts.
 */

import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';

import type { ScannedPage } from './cases-api';

/** The longest edge Claude reads a page at. Anything above it is wasted upload. */
export const MAX_EDGE = 2576;
/** JPEG quality: small enough to upload quickly, sharp enough for small print. */
const QUALITY = 0.8;

/** The resize to apply, or null when the photo is already small enough. */
export function targetSize(width: number, height: number): { width: number } | { height: number } | null {
  if (!width || !height || Math.max(width, height) <= MAX_EDGE) return null;
  // Give only the long edge; the short one follows the photo's own shape.
  return width >= height ? { width: MAX_EDGE } : { height: MAX_EDGE };
}

type PickedImage = { uri: string; width: number; height: number };

/**
 * Scales and re-encodes one page. If that fails, the original photo is sent
 * as it is: a larger upload is better than losing the page.
 */
export async function preparePage(image: PickedImage, pageNumber: number, fallback: ScannedPage): Promise<ScannedPage> {
  const context = ImageManipulator.manipulate(image.uri);
  try {
    const size = targetSize(image.width, image.height);
    if (size) context.resize(size);
    const rendered = await context.renderAsync();
    try {
      const saved = await rendered.saveAsync({ compress: QUALITY, format: SaveFormat.JPEG });
      return { uri: saved.uri, name: `page-${pageNumber}.jpg`, type: 'image/jpeg' };
    } finally {
      rendered.release();
    }
  } catch {
    return fallback;
  } finally {
    context.release();
  }
}
