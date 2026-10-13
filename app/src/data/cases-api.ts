/**
 * Talking to the API about cases, bills and flags.
 *
 * The API speaks snake_case, the app speaks camelCase. Mapping happens here
 * and nowhere else, so screens only ever see the types in `types.ts`.
 */

import { apiFetch, API_URL, ApiError, type ApiErrorCode } from '@/lib/api';
import type { Bill, Case, DailyBill, Flag, LineItem, Member } from './types';

type ApiMember = { id: string; name: string; is_you: boolean };

type ApiDailyBill = {
  id: string;
  date: string;
  day: number;
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
  admitted_on: string;
  closed_on: string | null;
  day_of_stay: number;
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

type ApiBill = {
  id: string;
  case_id: string;
  date: string;
  day: number;
  page_count: number;
  total: number;
  line_items: ApiLineItem[];
  flags: ApiFlag[];
};

const toMember = (m: ApiMember): Member => ({ id: m.id, name: m.name, isYou: m.is_you });

const toDailyBill = (b: ApiDailyBill): DailyBill => ({
  id: b.id,
  date: b.date,
  day: b.day,
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
  admittedOn: c.admitted_on,
  dayOfStay: c.day_of_stay,
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

export const toBill = (b: ApiBill): Bill => ({
  id: b.id,
  caseId: b.case_id,
  date: b.date,
  day: b.day,
  pageCount: b.page_count,
  total: b.total,
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
export async function createInvite(token: string, caseId: string): Promise<{ code: string; expiresAt: string }> {
  const invite = await apiFetch<{ id: string; code: string; expires_at: string }>(`/cases/${caseId}/invites`, {
    method: 'POST',
    token,
  });
  return { code: invite.code, expiresAt: invite.expires_at };
}

/** Joins with a code from a family member. The code goes in the body, never the URL. */
export async function joinCase(token: string, code: string): Promise<Case> {
  return toCase(await apiFetch<ApiCase>('/cases/join', { method: 'POST', token, body: { code } }));
}

export async function readBill(token: string, billId: string): Promise<Bill> {
  return toBill(await apiFetch<ApiBill>(`/bills/${billId}`, { token }));
}

export async function setFlagStatus(token: string, flagId: string, status: Flag['status']): Promise<Flag> {
  return toFlag(
    await apiFetch<ApiFlag>(`/flags/${flagId}`, { method: 'PATCH', token, body: { status } }),
  );
}

/** One page of a bill, ready to upload. */
export type ScannedPage = { uri: string; name: string; type: string };

/**
 * Uploads the photographed pages. Multipart, so it doesn't go through
 * `apiFetch`, which sends JSON.
 */
export async function uploadBill(
  token: string,
  caseId: string,
  pages: ScannedPage[],
  billDate?: string,
): Promise<Bill> {
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

  let response: Response;
  try {
    response = await fetch(`${API_URL}/cases/${caseId}/bills`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
  } catch {
    throw new ApiError('network', 0);
  }

  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (data as { detail?: { code?: unknown } } | null)?.detail;
    const code = typeof detail?.code === 'string' ? detail.code : 'unknown';
    throw new ApiError(code as ApiErrorCode, response.status);
  }
  return toBill(data as ApiBill);
}
