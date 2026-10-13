import { jest } from '@jest/globals';

/** The day 3 bill from the prototype, as the API would return it. */
export const SAMPLE_BILL = {
  id: 'b-day3',
  case_id: 'papa-admission',
  date: '2026-10-11',
  day: 3,
  page_count: 1,
  total: 42490,
  line_items: [
    { id: 'li-1', position: 1, name: 'Room rent, twin sharing', detail: '1 day', quantity: null, amount: 6500 },
    { id: 'li-5', position: 5, name: 'Inj. Meropenem 1g', detail: '6 vials', quantity: 6, amount: 17700 },
    { id: 'li-10', position: 10, name: 'Surgical gloves', detail: '80 pairs', quantity: 80, amount: 6800 },
  ],
  flags: [
    {
      id: 'f-mrp',
      position: 1,
      line_item_id: 'li-5',
      kind: 'above_mrp',
      level: 'red',
      status: 'open',
      billed: 17700,
      reference_amount: 11040,
      reference_source: 'mrp',
      reference_detail: {
        unit: 'vial',
        unit_price_billed: '2950.00',
        unit_price_reference: '1840.00',
        quantity: '6',
      },
      excess: 6660,
    },
    {
      id: 'f-gloves',
      position: 2,
      line_item_id: 'li-10',
      kind: 'quantity',
      level: 'amber',
      status: 'open',
      billed: 6800,
      reference_amount: 1700,
      reference_source: 'quantity_norm',
      reference_detail: { unit: 'pair', quantity: '80', usual_max_per_day: '20' },
      excess: 5100,
    },
  ],
};

/** One open case, as the API would return it. */
export const SAMPLE_CASE = {
  id: 'papa-admission',
  title: "Papa's admission",
  hospital_name: 'City Care Hospital',
  hospital_area: 'Andheri',
  patient_name: 'Ramesh Sharma',
  ip_number: '20841',
  bed: '412',
  admitted_on: '2026-10-09',
  closed_on: null,
  day_of_stay: 3,
  members: [
    { id: 'u1', name: 'Rohan Sharma', is_you: true },
    { id: 'u2', name: 'Anita Sharma', is_you: false },
  ],
  bills: [
    { id: 'b-day2', date: '2026-10-10', day: 2, item_count: 37, total: 31400, flag_count: 0, open_flag_count: 0 },
    { id: 'b-day3', date: '2026-10-11', day: 3, item_count: 3, total: 42490, flag_count: 2, open_flag_count: 2 },
  ],
  recovered_amount: 0,
};

/** A closed case, for the "reports stay saved" path. */
export const CLOSED_CASE = {
  id: 'mummy-cataract',
  title: "Mummy's cataract surgery",
  hospital_name: 'Lotus Eye Clinic',
  hospital_area: 'Thane',
  patient_name: 'Sunita Sharma',
  ip_number: '7712',
  bed: '6',
  admitted_on: '2026-03-12',
  closed_on: '2026-03-13',
  day_of_stay: 2,
  members: [{ id: 'u1', name: 'Rohan Sharma', is_you: true }],
  bills: [
    { id: 'b-cat1', date: '2026-03-12', day: 1, item_count: 18, total: 41200, flag_count: 2, open_flag_count: 0 },
  ],
  recovered_amount: 3200,
};

/**
 * An in-memory stand-in for api/, installed as global.fetch. Mirrors the real
 * responses closely enough to drive the screens in tests.
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
    cases: [structuredClone(SAMPLE_CASE), structuredClone(CLOSED_CASE)],
    bills: [structuredClone(SAMPLE_BILL)],
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
      case 'GET /cases':
        if (!auth || !server.sessions.has(auth)) return fail(401, 'not_authenticated');
        return json(200, server.cases);
      default: {
        if (!auth || !server.sessions.has(auth)) return fail(401, 'not_authenticated');

        const readCase = /^\/cases\/([^/]+)$/.exec(path);
        if (method === 'GET' && readCase) {
          const found = server.cases.find((c) => c.id === readCase[1]);
          return found ? json(200, found) : fail(404, 'case_not_found');
        }

        const readBill = /^\/bills\/([^/]+)$/.exec(path);
        if (method === 'GET' && readBill) {
          const found = server.bills.find((b) => b.id === readBill[1]);
          return found ? json(200, found) : fail(404, 'bill_not_found');
        }

        const patchFlag = /^\/flags\/([^/]+)$/.exec(path);
        if (method === 'PATCH' && patchFlag) {
          for (const bill of server.bills) {
            const flag = bill.flags.find((f) => f.id === patchFlag[1]);
            if (flag) {
              flag.status = body.status;
              return json(200, flag);
            }
          }
          return fail(404, 'flag_not_found');
        }

        return fail(404, 'unknown');
      }
    }
  });

  global.fetch = fetchMock as typeof fetch;
  return server;
}
