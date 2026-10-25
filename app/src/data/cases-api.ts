/**
 * Talking to the API about cases, bills and flags.
 *
 * The API speaks snake_case, the app speaks camelCase. Mapping happens here
 * and nowhere else, so screens only ever see the types in `types.ts`.
 */

import { apiFetch, API_URL, ApiError, type ApiErrorCode } from '@/lib/api';
import type { Bill, Case, Check, DailyBill, Flag, LineItem, Member, Payment } from './types';

type ApiMember = { id: string; name: string; is_you: boolean };

type ApiDailyBill = {
  id: string;
  date: string;
  item_count: number;
  total: number;
  flag_count: number;
  open_flag_count: number;
};

type ApiCase = {
  id: string;
  title: string;
  hospital_name: string;
  hospital_area: string;
  patient_name: string;
  ip_number: string;
  bed: string | null;
  admitted_on: string | null;
  closed_on: string | null;
  members: ApiMember[];
  is_owner: boolean;
  bills: ApiDailyBill[];
  recovered_amount: number;
};

type ApiLineItem = {
  id: string;
  position: number;
  name: string;
  detail: string | null;
  quantity: number | null;
  amount: number;
  net_amount: number | null;
  category: LineItem['category'];
};

type ApiFlag = {
  id: string;
  position: number;
  line_item_id: string | null;
  kind: Flag['kind'];
  level: Flag['level'];
  status: Flag['status'];
  billed: number;
  reference_amount: number;
  reference_source: string;
  reference_detail: Record<string, string | number>;
  excess: number;
};

type ApiCheck = {
  kind: Check['kind'];
  status: Check['status'];
  amount?: number | null;
  expected?: number | null;
  printed?: number | null;
  checked?: number | null;
  of?: number | null;
  count?: number | null;
  percent?: number | null;
  uniform?: boolean | null;
  positions?: number[];
};

type ApiBill = {
  id: string;
  case_id: string;
  date: string;
  page_count: number;
  subtotal: number;
  discount: number | null;
  total: number;
  // Missing from an API older than the arithmetic checks.
  checks?: ApiCheck[];
  payments?: Payment[];
  paid?: number | null;
  balance?: number | null;
  line_items: ApiLineItem[];
  flags: ApiFlag[];
};

const toMember = (m: ApiMember): Member => ({
  id: m.id,
  name: m.name,
  isYou: m.is_you,
});

const toDailyBill = (b: ApiDailyBill): DailyBill => ({
  id: b.id,
  date: b.date,
  itemCount: b.item_count,
  total: b.total,
  flagCount: b.flag_count,
  openFlagCount: b.open_flag_count,
});

export const toCase = (c: ApiCase): Case => ({
  id: c.id,
  title: c.title,
  hospital: { name: c.hospital_name, area: c.hospital_area },
  patient: { name: c.patient_name, ipNumber: c.ip_number, bed: c.bed ?? '' },
  admittedOn: c.admitted_on ?? undefined,
  closedOn: c.closed_on ?? undefined,
  members: c.members.map(toMember),
  isOwner: c.is_owner,
  bills: c.bills.map(toDailyBill),
  recoveredAmount: c.recovered_amount,
});

const toLineItem = (i: ApiLineItem): LineItem => ({
  id: i.id,
  position: i.position,
  name: i.name,
  detail: i.detail ?? undefined,
  quantity: i.quantity ?? undefined,
  amount: i.amount,
  netAmount: i.net_amount ?? undefined,
  category: i.category,
});

const toFlag = (f: ApiFlag): Flag => ({
  id: f.id,
  position: f.position,
  lineItemId: f.line_item_id ?? undefined,
  kind: f.kind,
  level: f.level,
  status: f.status,
  billed: f.billed,
  referenceAmount: f.reference_amount,
  referenceSource: f.reference_source,
  referenceDetail: f.reference_detail ?? {},
  excess: f.excess,
});

const toCheck = (c: ApiCheck): Check => ({
  kind: c.kind,
  status: c.status,
  amount: c.amount ?? undefined,
  expected: c.expected ?? undefined,
  printed: c.printed ?? undefined,
  checked: c.checked ?? undefined,
  of: c.of ?? undefined,
  count: c.count ?? undefined,
  percent: c.percent ?? undefined,
  uniform: c.uniform ?? undefined,
  positions: c.positions ?? [],
});

export const toBill = (b: ApiBill): Bill => ({
  id: b.id,
  caseId: b.case_id,
  date: b.date,
  pageCount: b.page_count,
  subtotal: b.subtotal,
  discount: b.discount ?? undefined,
  total: b.total,
  checks: (b.checks ?? []).map(toCheck),
  payments: b.payments ?? [],
  paid: b.paid ?? undefined,
  balance: b.balance ?? undefined,
  lineItems: b.line_items.map(toLineItem),
  flags: b.flags.map(toFlag),
});

export type NewCase = {
  title: string;
  hospitalName: string;
  hospitalArea: string;
  patientName: string;
  ipNumber: string;
  bed?: string;
  admittedOn: string;
};

export async function listCases(token: string): Promise<Case[]> {
  const cases = await apiFetch<ApiCase[]>('/cases', { token });
  return cases.map(toCase);
}

export async function readCase(token: string, caseId: string): Promise<Case> {
  return toCase(await apiFetch<ApiCase>(`/cases/${caseId}`, { token }));
}

export async function createCase(token: string, body: NewCase): Promise<Case> {
  const created = await apiFetch<ApiCase>('/cases', {
    method: 'POST',
    token,
    body: {
      title: body.title,
      hospital_name: body.hospitalName,
      hospital_area: body.hospitalArea,
      patient_name: body.patientName,
      ip_number: body.ipNumber,
      bed: body.bed || null,
      admitted_on: body.admittedOn,
    },
  });
  return toCase(created);
}

/**
 * Corrects the admission details. Only what is passed changes, so the screen
 * can send the whole form and the server keeps the rest.
 */
export async function updateCase(token: string, caseId: string, body: NewCase): Promise<Case> {
  const updated = await apiFetch<ApiCase>(`/cases/${caseId}`, {
    method: 'PATCH',
    token,
    body: {
      title: body.title,
      hospital_name: body.hospitalName,
      hospital_area: body.hospitalArea,
      patient_name: body.patientName,
      ip_number: body.ipNumber,
      bed: body.bed || null,
      admitted_on: body.admittedOn,
    },
  });
  return toCase(updated);
}

/**
 * Deletes the case and every bill under it, for everyone following it. Only
 * whoever started it can; there is no undo, so the screen confirms first.
 */
export async function deleteCase(token: string, caseId: string): Promise<void> {
  await apiFetch<void>(`/cases/${caseId}`, { method: 'DELETE', token });
}

/** A new invite code to share with family. Shown once; valid for 7 days. */
export async function createInvite(
  token: string,
  caseId: string,
): Promise<{ code: string; expiresAt: string }> {
  const invite = await apiFetch<{
    id: string;
    code: string;
    expires_at: string;
  }>(`/cases/${caseId}/invites`, {
    method: 'POST',
    token,
  });
  return { code: invite.code, expiresAt: invite.expires_at };
}

/** Joins with a code from a family member. The code goes in the body, never the URL. */
export async function joinCase(token: string, code: string): Promise<Case> {
  return toCase(
    await apiFetch<ApiCase>('/cases/join', {
      method: 'POST',
      token,
      body: { code },
    }),
  );
}

export async function readBill(token: string, billId: string): Promise<Bill> {
  return toBill(await apiFetch<ApiBill>(`/bills/${billId}`, { token }));
}

export async function setFlagStatus(token: string, flagId: string, status: Flag['status']): Promise<Flag> {
  return toFlag(
    await apiFetch<ApiFlag>(`/flags/${flagId}`, {
      method: 'PATCH',
      token,
      body: { status },
    }),
  );
}

/** One page of a bill, ready to upload. */
export type ScannedPage = { uri: string; name: string; type: string };

/** Told how much of the upload has gone, from 0 to 1. */
export type OnProgress = (sent: number) => void;

/**
 * Sends pages as multipart and resolves with the JSON that comes back.
 * Shared by bills and lab reports: both are pages going up to be read.
 */
export async function sendPages(
  token: string,
  path: string,
  pages: ScannedPage[],
  billDate?: string,
  onProgress?: OnProgress,
): Promise<unknown> {
  const form = new FormData();
  for (const page of pages) {
    if (page.uri.startsWith('blob:') || page.uri.startsWith('data:')) {
      // On web the picker hands back a blob URL, which FormData can't read.
      const blob = await fetch(page.uri).then((r) => r.blob());
      form.append('pages', blob, page.name);
    } else {
      // React Native's FormData takes the file descriptor itself.
      form.append('pages', { uri: page.uri, name: page.name, type: page.type } as unknown as Blob);
    }
  }
  if (billDate) form.append('bill_date', billDate);

  // XHR rather than fetch, for one reason: `upload.onprogress`. Reading a bill
  // takes most of a minute and the screen says which part it is on, so the one
  // part that can be measured -- the pages going up -- is measured rather than
  // guessed at. fetch reports nothing until the whole response is back.
  return new Promise<unknown>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', `${API_URL}${path}`);
    request.setRequestHeader('Authorization', `Bearer ${token}`);

    request.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable && event.total > 0) {
        onProgress(Math.min(1, event.loaded / event.total));
      }
    };
    // The last few bytes may not arrive as a progress event, and the reading
    // starts the moment they land.
    request.upload.onload = () => onProgress?.(1);

    request.onload = () => {
      let data: unknown = null;
      try {
        data = JSON.parse(request.responseText) as unknown;
      } catch {
        data = null;
      }
      if (request.status < 200 || request.status >= 300) {
        const detail = (data as { detail?: { code?: unknown } } | null)?.detail;
        const code = typeof detail?.code === 'string' ? detail.code : 'unknown';
        reject(new ApiError(code as ApiErrorCode, request.status));
        return;
      }
      resolve(data);
    };
    request.onerror = () => reject(new ApiError('network', 0));
    request.onabort = () => reject(new ApiError('network', 0));

    request.send(form);
  });
}

async function postPages(
  token: string,
  path: string,
  pages: ScannedPage[],
  billDate?: string,
  onProgress?: OnProgress,
): Promise<Bill> {
  return toBill((await sendPages(token, path, pages, billDate, onProgress)) as ApiBill);
}

/**
 * Uploads the photographed pages. Multipart, so it doesn't go through
 * `apiFetch`, which sends JSON.
 */
export async function uploadBill(
  token: string,
  caseId: string,
  pages: ScannedPage[],
  billDate?: string,
  onProgress?: OnProgress,
): Promise<Bill> {
  return postPages(token, `/cases/${caseId}/bills`, pages, billDate, onProgress);
}

/**
 * Checks a bill with no case behind it, and opens one from what the bill says.
 *
 * The way in for someone holding a bill and nothing else: the hospital, the
 * admission date, the patient and the IP number are all printed on it. The
 * case comes back on `bill.caseId`, and the family can correct its details
 * whenever they like.
 */
export async function checkFirstBill(
  token: string,
  pages: ScannedPage[],
  billDate?: string,
  onProgress?: OnProgress,
): Promise<Bill> {
  return postPages(token, '/bills', pages, billDate, onProgress);
}
