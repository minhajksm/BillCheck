/**
 * Talking to the API about cases, bills and flags.
 *
 * The API speaks snake_case, the app speaks camelCase. Mapping happens here
 * and nowhere else, so screens only ever see the types in `types.ts`.
 */

import { apiFetch, API_URL, ApiError, type ApiErrorCode } from '@/lib/api';
import { deviceHeaders } from '@/lib/device';
import type {
  Bill,
  Case,
  Check,
  DailyBill,
  Flag,
  Follower,
  LineItem,
  MemberRef,
  Payment,
  SuggestedMember,
} from './types';

export type ApiFollower = { id: string; name: string; is_you: boolean };

type ApiDailyBill = {
  id: string;
  date: string;
  item_count: number;
  total: number;
  flag_count: number;
  open_flag_count: number;
};

export type ApiSuggestedMember = {
  name: string;
  date_of_birth: string | null;
  age: number | null;
  phone: string | null;
  email: string | null;
  address: string | null;
};

export const toSuggested = (s: ApiSuggestedMember | null | undefined): SuggestedMember | undefined =>
  s
    ? {
        name: s.name,
        dateOfBirth: s.date_of_birth ?? undefined,
        age: s.age ?? undefined,
        phone: s.phone ?? undefined,
        email: s.email ?? undefined,
        address: s.address ?? undefined,
      }
    : undefined;

export type ApiCase = {
  id: string;
  title: string;
  hospital_name: string;
  hospital_area: string;
  patient_name: string;
  ip_number: string;
  bed: string | null;
  admitted_on: string | null;
  closed_on: string | null;
  member: MemberRef | null;
  suggested_member?: ApiSuggestedMember | null;
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

export const toFollower = (f: ApiFollower): Follower => ({
  id: f.id,
  name: f.name,
  isYou: f.is_you,
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
  member: c.member ?? undefined,
  suggestedMember: toSuggested(c.suggested_member),
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
  /** The discharge date, where it is known. Empty while still in hospital. */
  dischargedOn?: string;
};

export async function listCases(token: string): Promise<Case[]> {
  const cases = await apiFetch<ApiCase[]>('/cases', { token });
  return cases.map(toCase);
}

export async function readCase(token: string, caseId: string): Promise<Case> {
  return toCase(await apiFetch<ApiCase>(`/cases/${caseId}`, { token }));
}

/** Opens an admission by hand, under a member. */
export async function createCase(token: string, memberId: string, body: NewCase): Promise<Case> {
  const created = await apiFetch<ApiCase>('/cases', {
    method: 'POST',
    token,
    body: {
      member_id: memberId,
      title: body.title,
      hospital_name: body.hospitalName,
      hospital_area: body.hospitalArea,
      patient_name: body.patientName,
      ip_number: body.ipNumber,
      bed: body.bed || null,
      admitted_on: body.admittedOn,
      closed_on: body.dischargedOn || null,
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
      closed_on: body.dischargedOn || null,
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

/**
 * Whose a scan is: someone already there, or someone new, usually named as
 * the page names them. Exactly one.
 */
export type FileUnder = ({ memberId: string } | { newMemberName: string }) & {
  /**
   * Details accepted from the page. Someone new takes them all; someone
   * already there gains only what they don't have yet.
   */
  details?: Omit<SuggestedMember, 'name' | 'age'>;
};

export const fileUnderBody = (answer: FileUnder) => ({
  ...('memberId' in answer ? { member_id: answer.memberId } : { new_member_name: answer.newMemberName }),
  ...(answer.details
    ? {
        details: {
          date_of_birth: answer.details.dateOfBirth ?? null,
          phone: answer.details.phone ?? null,
          email: answer.details.email ?? null,
          address: answer.details.address ?? null,
        },
      }
    : {}),
});

/** Says whose admission this is. Family following that member see it from now on. */
export async function fileCase(token: string, caseId: string, answer: FileUnder): Promise<Case> {
  return toCase(
    await apiFetch<ApiCase>(`/cases/${caseId}/member`, {
      method: 'POST',
      token,
      body: fileUnderBody(answer),
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
  fields: Record<string, string | undefined> = {},
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
  for (const [name, value] of Object.entries(fields)) {
    if (value) form.append(name, value);
  }

  // XHR rather than fetch, for one reason: `upload.onprogress`. Reading a bill
  // takes most of a minute and the screen says which part it is on, so the one
  // part that can be measured -- the pages going up -- is measured rather than
  // guessed at. fetch reports nothing until the whole response is back.
  return new Promise<unknown>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', `${API_URL}${path}`);
    request.setRequestHeader('Authorization', `Bearer ${token}`);
    // Uploads are what the daily allowance counts, per phone where it can.
    for (const [name, value] of Object.entries(deviceHeaders())) request.setRequestHeader(name, value);

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
        const detail = (data as { detail?: { code?: unknown; document?: unknown } } | null)?.detail;
        const code = typeof detail?.code === 'string' ? detail.code : 'unknown';
        const document =
          typeof detail?.document === 'string' && detail.document ? detail.document : undefined;
        reject(new ApiError(code as ApiErrorCode, request.status, undefined, document));
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
  fields: Record<string, string | undefined>,
  onProgress?: OnProgress,
): Promise<Bill> {
  return toBill((await sendPages(token, path, pages, fields, onProgress)) as ApiBill);
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
  return postPages(token, `/cases/${caseId}/bills`, pages, { bill_date: billDate }, onProgress);
}

/**
 * Checks a bill with no case behind it, and opens one from what the bill says.
 *
 * The way in for someone holding a bill and nothing else: the hospital, the
 * admission date, the patient and the IP number are all printed on it. The
 * case comes back on `bill.caseId`, and the family can correct its details
 * whenever they like.
 *
 * Scanned from a member, the case is theirs. Without one it waits to be
 * filed with `fileCase`, so the patient name on the bill can be offered.
 */
export async function checkFirstBill(
  token: string,
  pages: ScannedPage[],
  memberId?: string,
  onProgress?: OnProgress,
): Promise<Bill> {
  return postPages(token, '/bills', pages, { member_id: memberId }, onProgress);
}
