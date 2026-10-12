import { jest } from '@jest/globals';

/**
 * An in-memory stand-in for api/'s auth endpoints, installed as global.fetch.
 * Mirrors the real responses closely enough to drive the screens in tests.
 */
export function installFakeApi() {
  const server = {
    users: new Map<string, { id: string; phone: string; name: string }>(),
    codes: new Map<string, string>(),
    signupTokens: new Map<string, string>(),
    sessions: new Map<string, string>(),
    lastCode: '',
    nextCode: '123456',
    calls: [] as string[],
  };

  const json = (status: number, body?: unknown) =>
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  const fail = (status: number, code: string) => json(status, { detail: { code, message: code } });

  const login = (phone: string) => {
    const token = `token-${phone}-${server.sessions.size}`;
    server.sessions.set(token, phone);
    return { status: 'logged_in', token, expires_at: '2026-11-11T00:00:00Z', user: server.users.get(phone) };
  };

  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input)).pathname;
    const method = init?.method ?? 'GET';
    server.calls.push(`${method} ${path}`);
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    const auth = (init?.headers as Record<string, string> | undefined)?.Authorization?.replace('Bearer ', '');

    switch (`${method} ${path}`) {
      case 'POST /auth/otp/request':
        server.lastCode = server.nextCode;
        server.codes.set(body.phone, server.lastCode);
        return json(202, { expires_in_seconds: 300, resend_after_seconds: 30 });
      case 'POST /auth/otp/verify': {
        if (server.codes.get(body.phone) !== body.code) return fail(400, 'otp_invalid');
        server.codes.delete(body.phone);
        if (server.users.has(body.phone)) return json(200, login(body.phone));
        const signupToken = `signup-${body.phone}`;
        server.signupTokens.set(signupToken, body.phone);
        return json(200, { status: 'signup_required', signup_token: signupToken, expires_at: '' });
      }
      case 'POST /auth/signup': {
        const phone = server.signupTokens.get(body.signup_token);
        if (!phone) return fail(400, 'signup_token_invalid');
        if (body.consent !== true) return json(422, { detail: [] });
        server.signupTokens.delete(body.signup_token);
        server.users.set(phone, { id: `u-${phone}`, phone, name: body.name });
        return json(201, login(phone));
      }
      case 'GET /auth/me': {
        const phone = auth && server.sessions.get(auth);
        return phone ? json(200, server.users.get(phone)) : fail(401, 'not_authenticated');
      }
      case 'POST /auth/logout':
        if (auth) server.sessions.delete(auth);
        return json(204);
      default:
        return fail(404, 'unknown');
    }
  });

  global.fetch = fetchMock as typeof fetch;
  return server;
}
