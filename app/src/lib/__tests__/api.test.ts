import { afterEach, describe, expect, it, jest } from '@jest/globals';

import { ApiError, apiFetch } from '../api';

const respond = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  jest.fn<typeof fetch>().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), { status, headers }),
  );

afterEach(() => {
  jest.restoreAllMocks();
});

describe('apiFetch', () => {
  it('sends JSON and the bearer token', async () => {
    const fetchMock = respond(200, { ok: true });
    global.fetch = fetchMock;
    await expect(apiFetch('/auth/me', { method: 'POST', body: { a: 1 }, token: 'tok' })).resolves.toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/auth\/me$/);
    expect(init?.headers).toEqual({ 'Content-Type': 'application/json', Authorization: 'Bearer tok' });
    expect(init?.body).toBe('{"a":1}');
  });

  it('reads the error code and Retry-After', async () => {
    global.fetch = respond(429, { detail: { code: 'otp_cooldown', message: '' } }, { 'Retry-After': '12' });
    const error = await apiFetch('/x').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: 'otp_cooldown', status: 429, retryAfterSeconds: 12 });
  });

  it('reports validation errors and unknown failures', async () => {
    global.fetch = respond(422, { detail: [{ msg: 'bad' }] });
    await expect(apiFetch('/x')).rejects.toMatchObject({ code: 'invalid_request' });
    global.fetch = respond(500, null);
    await expect(apiFetch('/x')).rejects.toMatchObject({ code: 'unknown' });
  });

  it('reports a network failure when the API is unreachable', async () => {
    global.fetch = jest.fn<typeof fetch>().mockRejectedValue(new TypeError('Network request failed'));
    await expect(apiFetch('/x')).rejects.toMatchObject({ code: 'network', status: 0 });
  });

  it('handles 204 No Content', async () => {
    global.fetch = respond(204, undefined);
    await expect(apiFetch('/auth/logout', { method: 'POST' })).resolves.toBeUndefined();
  });
});
