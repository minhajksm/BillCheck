import { jest } from '@jest/globals';

import { ageOn } from '@/lib/age';

/**
 * A flag as the API sends one. Written out rather than inferred from the two
 * samples below, so a test can add a kind they don't cover -- a finding about
 * the bill rather than a charge on it carries no `line_item_id`.
 */
type SampleFlag = {
  id: string;
  position: number;
  line_item_id: string | null;
  kind: string;
  level: string;
  status: string;
  billed: number;
  reference_amount: number;
  reference_source: string;
  reference_detail: Record<string, string>;
  excess: number;
};

/** A bill from the prototype, as the API would return it. */
export const SAMPLE_BILL = {
  id: 'b-day3',
  case_id: 'papa-admission',
  date: '2026-10-11',
  page_count: 1,
  subtotal: 42490,
  discount: null,
  total: 42490,
  checks: [] as Record<string, unknown>[],
  payments: [] as { date: string; mode: string; amount: number }[],
  paid: null as number | null,
  balance: null as number | null,
  line_items: [
    {
      id: 'li-1',
      position: 1,
      name: 'Room rent, twin sharing',
      detail: '1 day',
      quantity: null,
      amount: 6500,
      net_amount: null,
      category: 'room_and_nursing',
    },
    {
      id: 'li-5',
      position: 5,
      name: 'Inj. Meropenem 1g',
      detail: '6 vials',
      quantity: 6,
      amount: 17700,
      net_amount: null,
      category: 'pharmacy_drug',
    },
    {
      id: 'li-10',
      position: 10,
      name: 'Surgical gloves',
      detail: '80 pairs',
      quantity: 80,
      amount: 6800,
      net_amount: null,
      category: 'consumable_disposable',
    },
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
        line_numbers: '5',
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
      reference_detail: {
        unit: 'pair',
        quantity: '80',
        usual_max_per_day: '20',
        line_numbers: '10',
      },
      excess: 5100,
    },
  ] as SampleFlag[],
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
  member: { id: 'm-papa', name: 'Papa' } as { id: string; name: string } | null,
  is_owner: true,
  bills: [
    {
      id: 'b-day2',
      date: '2026-10-10',
      item_count: 37,
      total: 31400,
      flag_count: 0,
      open_flag_count: 0,
    },
    {
      id: 'b-day3',
      date: '2026-10-11',
      item_count: 3,
      total: 42490,
      flag_count: 2,
      open_flag_count: 2,
    },
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
  member: { id: 'm-mummy', name: 'Mummy' } as { id: string; name: string } | null,
  is_owner: true,
  bills: [
    {
      id: 'b-cat1',
      date: '2026-03-12',
      item_count: 18,
      total: 41200,
      flag_count: 2,
      open_flag_count: 0,
    },
  ],
  recovered_amount: 3200,
};

/** A lab report as the API returns it, explained. Sample data, not a real patient. */
export const SAMPLE_LAB = {
  id: 'lab-1',
  member: null as { id: string; name: string } | null,
  lab_name: 'Sample Diagnostics',
  patient_name: 'TEST PATIENT',
  report_date: '06/05/2025',
  page_count: 1,
  tests: [
    {
      name: 'Haemoglobin',
      value: '9.8',
      unit: 'g/dL',
      range: '12.0 - 15.0',
      status: 'low',
      explanation_en:
        'Haemoglobin carries oxygen in the blood. This result is below the range printed on the report.',
      explanation_hi: 'हीमोग्लोबिन खून में ऑक्सीजन ले जाता है। यह नतीजा रिपोर्ट पर छपी सीमा से कम है।',
    },
    {
      name: 'Malaria Antigen',
      value: 'Negative',
      unit: '',
      range: '',
      status: 'no_range',
      explanation_en: 'This test looks for signs of malaria in the blood.',
      explanation_hi: 'यह जाँच खून में मलेरिया के संकेत देखती है।',
    },
  ],
  summary_en: 'One of the two results is outside the range printed on the report.',
  summary_hi: 'दो में से एक नतीजा रिपोर्ट पर छपी सीमा से बाहर है।',
  questions_en: ['What does the haemoglobin result mean?'],
  questions_hi: ['हीमोग्लोबिन के नतीजे का क्या मतलब है?'],
  urgent: false,
  created_at: '2026-10-24T08:00:00Z',
};

/** A member's optional details, as the API stores them. */
type Details = {
  date_of_birth: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
};
const NO_DETAILS: Details = { date_of_birth: null, phone: null, email: null, address: null };

/** The people the signed-in account follows, as GET /members/{id} answers minus what is under them. */
export const SAMPLE_MEMBERS = [
  {
    id: 'm-papa',
    name: 'Papa',
    ...NO_DETAILS,
    is_owner: true,
    followers: [
      { id: 'u1', name: 'Rohan Sharma', is_you: true },
      { id: 'u2', name: 'Anita Sharma', is_you: false },
    ],
  },
  {
    id: 'm-mummy',
    name: 'Mummy',
    ...NO_DETAILS,
    is_owner: true,
    followers: [{ id: 'u1', name: 'Rohan Sharma', is_you: true }],
  },
];

/** The details a request sent, phone and email as the real API normalises them. */
function pickDetails(body: Partial<Details>): Partial<Details> {
  const picked: Partial<Details> = {};
  for (const key of ['date_of_birth', 'phone', 'email', 'address'] as const) {
    if (key in body) picked[key] = body[key] || null;
  }
  if (picked.email) picked.email = picked.email.toLowerCase();
  return picked;
}

/** A field of a multipart upload, from whichever FormData the test runs with. */
function formField(body: unknown, name: string): string | undefined {
  const form = body as {
    get?: (name: string) => unknown;
    getParts?: () => { fieldName: string; string?: string }[];
  } | null;
  if (form?.get) return (form.get(name) as string | null) ?? undefined;
  return form?.getParts?.().find((part) => part.fieldName === name)?.string;
}

/**
 * An in-memory stand-in for api/, installed as global.fetch. Mirrors the real
 * responses closely enough to drive the screens in tests.
 */
export function installFakeApi() {
  const server = {
    users: new Map<string, { id: string; phone: string | null; name: string; lab_consent?: boolean }>(),
    /** What GET /health answers, i.e. whether REQUIRE_SIGN_IN is off on the API. */
    anonymousAccounts: false,
    /** Set to a promise to hold GET /health until it settles: a server waking from cold. */
    healthWaitsFor: null as Promise<void> | null,
    codes: new Map<string, string>(),
    signupTokens: new Map<string, string>(),
    sessions: new Map<string, string>(),
    lastCode: '',
    nextCode: '123456',
    calls: [] as string[],
    cases: [structuredClone(SAMPLE_CASE), structuredClone(CLOSED_CASE)],
    bills: [structuredClone(SAMPLE_BILL)],
    /** Set to an error code to make the next bill upload fail with it. */
    failUpload: null as string | null,
    /** Set to hold an upload open, for testing what is shown while waiting. */
    stallUpload: false,
    labReports: [] as (typeof SAMPLE_LAB)[],
    members: structuredClone(SAMPLE_MEMBERS),
    /** The last invite code made, so a test can join with it. */
    lastInvite: '',
  };

  const labRow = (r: typeof SAMPLE_LAB) => ({
    id: r.id,
    lab_name: r.lab_name,
    patient_name: r.patient_name,
    report_date: r.report_date,
    member: r.member,
    test_count: r.tests.length,
    outside_range: r.tests.filter((test) => test.status === 'low' || test.status === 'high').length,
    urgent: r.urgent,
    created_at: r.created_at,
  });

  const memberOut = (m: (typeof server.members)[number]) => ({
    ...m,
    age: m.date_of_birth ? (ageOn(m.date_of_birth, new Date()) ?? null) : null,
    cases: server.cases.filter((c) => c.member?.id === m.id),
    lab_reports: server.labReports.filter((r) => r.member?.id === m.id).map(labRow),
  });

  /** Someone already there, or someone new: what POST .../member answers with. */
  const fileUnder = (body: { member_id?: string; new_member_name?: string }) => {
    if (body.member_id) {
      const found = server.members.find((m) => m.id === body.member_id);
      return found ? { id: found.id, name: found.name } : null;
    }
    const made = {
      id: `m-${server.members.length + 1}`,
      name: body.new_member_name ?? '',
      ...NO_DETAILS,
      is_owner: true,
      followers: [{ id: 'u1', name: 'Rohan Sharma', is_you: true }],
    };
    server.members.push(made);
    return { id: made.id, name: made.name };
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
    return {
      status: 'logged_in',
      token,
      expires_at: '2026-11-11T00:00:00Z',
      user: server.users.get(phone),
    };
  };

  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input)).pathname;
    const method = init?.method ?? 'GET';
    server.calls.push(`${method} ${path}`);
    // Only JSON bodies are parsed: the bill uploads are multipart, and
    // JSON.parse on a FormData throws before any route is reached.
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : ({} as Record<string, never>);
    const auth = (init?.headers as Record<string, string> | undefined)?.Authorization?.replace('Bearer ', '');

    switch (`${method} ${path}`) {
      case 'GET /health':
        if (server.healthWaitsFor) await server.healthWaitsFor;
        return json(200, { status: 'ok', anonymous_accounts: server.anonymousAccounts });
      case 'POST /auth/otp/request':
        server.lastCode = server.nextCode;
        server.codes.set(body.phone, server.lastCode);
        return json(202, {
          expires_in_seconds: 300,
          resend_after_seconds: 30,
        });
      case 'POST /auth/otp/verify': {
        if (server.codes.get(body.phone) !== body.code) return fail(400, 'otp_invalid');
        server.codes.delete(body.phone);
        if (server.users.has(body.phone)) return json(200, login(body.phone));
        const signupToken = `signup-${body.phone}`;
        server.signupTokens.set(signupToken, body.phone);
        return json(200, {
          status: 'signup_required',
          signup_token: signupToken,
          expires_at: '',
        });
      }
      case 'POST /auth/signup': {
        const phone = server.signupTokens.get(body.signup_token);
        if (!phone) return fail(400, 'signup_token_invalid');
        if (body.consent !== true) return json(422, { detail: [] });
        server.signupTokens.delete(body.signup_token);
        server.users.set(phone, { id: `u-${phone}`, phone, name: body.name });
        return json(201, login(phone));
      }
      case 'POST /auth/anonymous': {
        if (!server.anonymousAccounts) return fail(403, 'sign_in_required');
        if (body.consent !== true) return json(422, { detail: [] });
        // No number, so the key is one the device holds and nothing else.
        const phone = `device-${server.users.size}`;
        server.users.set(phone, { id: `u-${phone}`, phone: null, name: '' });
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

        // Lab reports: theirs only, and nothing read before they have agreed.
        const signedIn = server.users.get(server.sessions.get(auth) ?? '');
        if (method === 'POST' && path === '/lab-reports/consent') {
          if (body.consent !== true) return json(422, { detail: [] });
          if (signedIn) signedIn.lab_consent = true;
          return new Response(null, { status: 204 });
        }
        if (method === 'POST' && path === '/lab-reports') {
          if (!signedIn?.lab_consent) return fail(403, 'lab_consent_required');
          const memberId = formField(init?.body, 'member_id');
          const member = server.members.find((m) => m.id === memberId);
          const report = {
            ...structuredClone(SAMPLE_LAB),
            id: `lab-${server.labReports.length + 1}`,
            member: member ? { id: member.id, name: member.name } : null,
          };
          server.labReports.unshift(report);
          return json(201, report);
        }
        if (method === 'GET' && path === '/lab-reports') {
          return json(200, server.labReports.map(labRow));
        }
        const fileLab = /^\/lab-reports\/([^/]+)\/member$/.exec(path);
        if (method === 'POST' && fileLab) {
          const found = server.labReports.find((r) => r.id === fileLab[1]);
          const member = fileUnder(body);
          if (!found || !member) return fail(404, 'lab_report_not_found');
          found.member = member;
          return json(200, found);
        }

        // Members: the people this account follows.
        if (method === 'GET' && path === '/members') {
          return json(
            200,
            server.members.map((m) => {
              const cases = server.cases.filter((c) => c.member?.id === m.id);
              return {
                id: m.id,
                name: m.name,
                age: m.date_of_birth ? (ageOn(m.date_of_birth, new Date()) ?? null) : null,
                is_owner: m.is_owner,
                followers: m.followers,
                admission_count: cases.length,
                open_admission_count: cases.filter((c) => c.closed_on === null).length,
                open_flag_count: server.bills
                  .filter((b) => cases.some((c) => c.id === b.case_id))
                  .reduce((sum, b) => sum + b.flags.filter((f) => f.status === 'open').length, 0),
                lab_report_count: server.labReports.filter((r) => r.member?.id === m.id).length,
              };
            }),
          );
        }
        if (method === 'POST' && path === '/members') {
          const made = {
            id: `m-${server.members.length + 1}`,
            name: body.name,
            ...NO_DETAILS,
            ...pickDetails(body),
            is_owner: true,
            followers: [{ id: 'u1', name: 'Rohan Sharma', is_you: true }],
          };
          server.members.push(made);
          return json(201, memberOut(made));
        }
        if (method === 'POST' && path === '/members/join') {
          if (body.code !== server.lastInvite) return fail(404, 'invite_invalid');
          return json(200, memberOut(server.members[0]));
        }
        if (method === 'GET' && path === '/unfiled') {
          return json(200, {
            cases: server.cases.filter((c) => c.member === null),
            lab_reports: server.labReports.filter((r) => r.member === null).map(labRow),
          });
        }
        const invite = /^\/members\/([^/]+)\/invites$/.exec(path);
        if (method === 'POST' && invite) {
          server.lastInvite = `code-${invite[1]}`;
          return json(201, { id: 'inv-1', code: server.lastInvite, expires_at: '2026-11-01T00:00:00Z' });
        }
        const leave = /^\/members\/([^/]+)\/followers\/([^/]+)\/remove$/.exec(path);
        if (method === 'POST' && leave) {
          const at = server.members.findIndex((m) => m.id === leave[1]);
          if (at < 0) return fail(404, 'member_not_found');
          server.members.splice(at, 1);
          return new Response(null, { status: 204 });
        }
        const member = /^\/members\/([^/]+)$/.exec(path);
        if (member) {
          const at = server.members.findIndex((m) => m.id === member[1]);
          if (at < 0) return fail(404, 'member_not_found');
          if (method === 'GET') return json(200, memberOut(server.members[at]));
          if (method === 'PATCH') {
            Object.assign(
              server.members[at],
              { name: body.name ?? server.members[at].name },
              pickDetails(body),
            );
            return json(200, memberOut(server.members[at]));
          }
          if (method === 'DELETE') {
            if (!server.members[at].is_owner) return fail(403, 'not_member_owner');
            const gone = server.members[at].id;
            server.members.splice(at, 1);
            server.cases = server.cases.filter((c) => c.member?.id !== gone);
            return new Response(null, { status: 204 });
          }
        }
        const labReport = /^\/lab-reports\/([^/]+)$/.exec(path);
        if (labReport) {
          const at = server.labReports.findIndex((r) => r.id === labReport[1]);
          if (at < 0) return fail(404, 'lab_report_not_found');
          if (method === 'GET') return json(200, server.labReports[at]);
          if (method === 'DELETE') {
            server.labReports.splice(at, 1);
            return new Response(null, { status: 204 });
          }
        }

        const fileCase = /^\/cases\/([^/]+)\/member$/.exec(path);
        if (method === 'POST' && fileCase) {
          const found = server.cases.find((c) => c.id === fileCase[1]);
          const member = fileUnder(body);
          if (!found || !member) return fail(404, 'case_not_found');
          found.member = member;
          return json(200, found);
        }

        const readCase = /^\/cases\/([^/]+)$/.exec(path);
        if (method === 'GET' && readCase) {
          const found = server.cases.find((c) => c.id === readCase[1]);
          return found ? json(200, found) : fail(404, 'case_not_found');
        }

        const editCase = /^\/cases\/([^/]+)$/.exec(path);
        if (method === 'PATCH' && editCase) {
          const found = server.cases.find((c) => c.id === editCase[1]);
          if (!found) return fail(404, 'case_not_found');
          // Only what was sent changes, as the real endpoint does.
          Object.assign(found, body);
          return json(200, found);
        }
        if (method === 'DELETE' && editCase) {
          const at = server.cases.findIndex((c) => c.id === editCase[1]);
          if (at < 0) return fail(404, 'case_not_found');
          if (!server.cases[at].is_owner) return fail(403, 'not_case_owner');
          server.cases.splice(at, 1);
          return new Response(null, { status: 204 });
        }

        const readBill = /^\/bills\/([^/]+)$/.exec(path);
        if (method === 'GET' && readBill) {
          const found = server.bills.find((b) => b.id === readBill[1]);
          return found ? json(200, found) : fail(404, 'bill_not_found');
        }

        // Checking a bill with no case: the real endpoint reads the pages,
        // opens a case from what the bill says, and returns the bill on it.
        // From a member it is theirs; otherwise it waits to be filed.
        if (method === 'POST' && path === '/bills') {
          const memberId = formField(init?.body, 'member_id');
          const member = server.members.find((m) => m.id === memberId);
          const opened = {
            ...structuredClone(SAMPLE_CASE),
            id: `case-from-bill-${server.cases.length}`,
            title: 'Ramesh Sharma',
            member: member ? { id: member.id, name: member.name } : null,
            bills: [],
          };
          server.cases.unshift(opened);
          const bill = {
            ...structuredClone(SAMPLE_BILL),
            id: `bill-${server.bills.length + 1}`,
            case_id: opened.id,
          };
          server.bills.push(bill);
          return json(201, bill);
        }

        const addBill = /^\/cases\/([^/]+)\/bills$/.exec(path);
        if (method === 'POST' && addBill) {
          const found = server.cases.find((c) => c.id === addBill[1]);
          if (!found) return fail(404, 'case_not_found');
          const bill = {
            ...structuredClone(SAMPLE_BILL),
            id: `bill-${server.bills.length + 1}`,
            case_id: found.id,
          };
          server.bills.push(bill);
          return json(201, bill);
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

  /**
   * The bill uploads go through XMLHttpRequest, not fetch, because that is
   * the only way to see the upload's own progress. This routes them through
   * the same handler, and reports the progress a real upload would.
   */
  class FakeXhr {
    status = 0;
    responseText = '';
    upload: { onprogress?: (event: ProgressEvent) => void; onload?: () => void } = {};
    onload?: () => void;
    onerror?: () => void;
    onabort?: () => void;
    private method = 'GET';
    private url = '';
    private headers: Record<string, string> = {};

    open(method: string, url: string) {
      this.method = method;
      this.url = url;
    }

    setRequestHeader(name: string, value: string) {
      this.headers[name] = value;
    }

    send(body: unknown) {
      void (async () => {
        // Halfway, then done: enough for a screen that shows a percentage.
        this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 } as ProgressEvent);

        if (server.stallUpload) {
          // The pages land and the reading never comes back, which is the
          // minute a family spends on the waiting screen.
          this.upload.onprogress?.({ lengthComputable: true, loaded: 100, total: 100 } as ProgressEvent);
          this.upload.onload?.();
          return;
        }
        if (server.failUpload) {
          this.upload.onload?.();
          this.status = 422;
          this.responseText = JSON.stringify({ detail: { code: server.failUpload } });
          this.onload?.();
          return;
        }

        const response = await fetchMock(this.url, {
          method: this.method,
          headers: this.headers,
          body: body as BodyInit,
        });
        this.upload.onprogress?.({ lengthComputable: true, loaded: 100, total: 100 } as ProgressEvent);
        this.upload.onload?.();
        this.status = response.status;
        this.responseText = await response.text();
        this.onload?.();
      })();
    }
  }

  global.XMLHttpRequest = FakeXhr as unknown as typeof XMLHttpRequest;
  return server;
}
