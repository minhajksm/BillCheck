import { afterEach, describe, expect, it, jest } from '@jest/globals';
import { Platform } from 'react-native';

import { androidId, deviceHeaders } from '../device';

const mockGetAndroidId = jest.fn<() => string>();
// Hoisted above the imports by jest, so the module sees the mock.
jest.mock('expo-application', () => ({ getAndroidId: () => mockGetAndroidId() }));

const realOs = Platform.OS;
const onAndroid = (yes: boolean) => Object.defineProperty(Platform, 'OS', { value: yes ? 'android' : 'web' });

afterEach(() => {
  Object.defineProperty(Platform, 'OS', { value: realOs });
  mockGetAndroidId.mockReset();
});

describe('the Android ID sent with each request', () => {
  it("is the phone's own, on Android", () => {
    onAndroid(true);
    mockGetAndroidId.mockReturnValue('a1b2c3d4e5f60718');

    expect(androidId()).toBe('a1b2c3d4e5f60718');
    expect(deviceHeaders()).toEqual({ 'X-Android-Id': 'a1b2c3d4e5f60718' });
  });

  it('is not sent where there is none, so the API counts by account', () => {
    onAndroid(false);

    expect(deviceHeaders()).toEqual({});
    expect(mockGetAndroidId).not.toHaveBeenCalled();
  });

  it('never stops a request when it cannot be read', () => {
    onAndroid(true);
    mockGetAndroidId.mockImplementation(() => {
      throw new Error('no native module');
    });

    expect(deviceHeaders()).toEqual({});
  });
});
