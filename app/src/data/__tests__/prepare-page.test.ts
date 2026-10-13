import { describe, expect, it, jest } from '@jest/globals';

import { MAX_EDGE, preparePage, targetSize } from '../prepare-page';

const mockSaveAsync = jest.fn(async () => ({ uri: 'file:///resized.jpg', width: MAX_EDGE, height: 1932 }));
const mockResize = jest.fn();
let mockRenderFails = false;

jest.mock('expo-image-manipulator', () => ({
  SaveFormat: { JPEG: 'jpeg' },
  ImageManipulator: {
    manipulate: () => ({
      resize: mockResize,
      release: jest.fn(),
      renderAsync: async () => {
        if (mockRenderFails) throw new Error('could not decode');
        return { saveAsync: mockSaveAsync, release: jest.fn() };
      },
    }),
  },
}));

describe('targetSize', () => {
  it('scales a large photo down on its long edge', () => {
    expect(targetSize(4000, 3000)).toEqual({ width: MAX_EDGE });
    expect(targetSize(3000, 4000)).toEqual({ height: MAX_EDGE });
  });

  it('leaves a photo that is already small enough', () => {
    expect(targetSize(MAX_EDGE, 1900)).toBeNull();
    expect(targetSize(1200, 1600)).toBeNull();
  });

  it('leaves a photo whose size is unknown', () => {
    expect(targetSize(0, 0)).toBeNull();
  });
});

describe('preparePage', () => {
  const fallback = { uri: 'file:///original.heic', name: 'IMG_1.heic', type: 'image/heic' };

  it('resizes and saves the page as JPEG', async () => {
    mockRenderFails = false;
    const page = await preparePage({ uri: fallback.uri, width: 4000, height: 3000 }, 2, fallback);
    expect(mockResize).toHaveBeenCalledWith({ width: MAX_EDGE });
    expect(mockSaveAsync).toHaveBeenCalledWith({ compress: 0.8, format: 'jpeg' });
    expect(page).toEqual({ uri: 'file:///resized.jpg', name: 'page-2.jpg', type: 'image/jpeg' });
  });

  it('sends the original photo if it cannot be processed', async () => {
    mockRenderFails = true;
    const page = await preparePage({ uri: fallback.uri, width: 4000, height: 3000 }, 1, fallback);
    expect(page).toBe(fallback);
  });
});
