/**
 * Talking to the API about members: the people an account looks after, who
 * follows them, and what is waiting to be filed under one.
 */

import { apiFetch } from '@/lib/api';

import { toCase, toFollower, type ApiCase, type ApiFollower } from './cases-api';
import { toLabRow, type ApiLabReportRow, type LabReportRow } from './lab-api';
import type { Case, Follower, MemberSummary } from './types';

type ApiMemberSummary = {
  id: string;
  name: string;
  age: number | null;
  is_owner: boolean;
  followers: ApiFollower[];
  admission_count: number;
  open_admission_count: number;
  open_flag_count: number;
  lab_report_count: number;
};

type ApiMember = {
  id: string;
  name: string;
  date_of_birth: string | null;
  age: number | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  is_owner: boolean;
  followers: ApiFollower[];
  cases: ApiCase[];
  lab_reports: ApiLabReportRow[];
};

/**
 * What a family may know about someone they look after. Only the name is
 * needed; the rest is filled in where it is known.
 */
export type MemberDetails = {
  name: string;
  /** "YYYY-MM-DD". */
  dateOfBirth?: string;
  /** E.164, "+919876543210". */
  phone?: string;
  email?: string;
  address?: string;
};

/** A member, their details, and everything under them. */
export type Member = MemberDetails & {
  id: string;
  /** Whole years, worked out by the API from the date of birth. */
  age?: number;
  isOwner: boolean;
  followers: Follower[];
  /** Newest admission first. */
  cases: Case[];
  /** Newest first. */
  labReports: LabReportRow[];
};

/** What you scanned before choosing anyone, and haven't filed yet. */
export type Unfiled = { cases: Case[]; labReports: LabReportRow[] };

const toSummary = (m: ApiMemberSummary): MemberSummary => ({
  id: m.id,
  name: m.name,
  age: m.age ?? undefined,
  isOwner: m.is_owner,
  followers: m.followers.map(toFollower),
  admissionCount: m.admission_count,
  openAdmissionCount: m.open_admission_count,
  openFlagCount: m.open_flag_count,
  labReportCount: m.lab_report_count,
});

const toMember = (m: ApiMember): Member => ({
  id: m.id,
  name: m.name,
  dateOfBirth: m.date_of_birth ?? undefined,
  age: m.age ?? undefined,
  phone: m.phone ?? undefined,
  email: m.email ?? undefined,
  address: m.address ?? undefined,
  isOwner: m.is_owner,
  followers: m.followers.map(toFollower),
  cases: m.cases.map(toCase),
  labReports: m.lab_reports.map(toLabRow),
});

/** Everyone you follow, anyone in hospital now first. */
export async function listMembers(token: string): Promise<MemberSummary[]> {
  return (await apiFetch<ApiMemberSummary[]>('/members', { token })).map(toSummary);
}

export async function readMember(token: string, memberId: string): Promise<Member> {
  return toMember(await apiFetch<ApiMember>(`/members/${memberId}`, { token }));
}

/** Every field, an empty one sent as null so that editing can clear it. */
const detailsBody = (details: MemberDetails) => ({
  name: details.name,
  date_of_birth: details.dateOfBirth || null,
  phone: details.phone || null,
  email: details.email || null,
  address: details.address || null,
});

export async function createMember(token: string, details: MemberDetails): Promise<Member> {
  return toMember(
    await apiFetch<ApiMember>('/members', { method: 'POST', token, body: detailsBody(details) }),
  );
}

/** Saves the whole form: a field emptied is cleared. */
export async function updateMember(token: string, memberId: string, details: MemberDetails): Promise<Member> {
  return toMember(
    await apiFetch<ApiMember>(`/members/${memberId}`, { method: 'PATCH', token, body: detailsBody(details) }),
  );
}

/**
 * Deletes the member and every admission and report under them, for everyone
 * following. Only whoever added them can; there is no undo.
 */
export async function deleteMember(token: string, memberId: string): Promise<void> {
  await apiFetch<void>(`/members/${memberId}`, { method: 'DELETE', token });
}

/** Stops following. Whoever added the member can't. */
export async function stopFollowing(token: string, memberId: string, userId: string): Promise<void> {
  await apiFetch<void>(`/members/${memberId}/followers/${userId}/remove`, { method: 'POST', token });
}

/** A new invite code to share with family. Shown once; valid for 7 days. */
export async function createInvite(
  token: string,
  memberId: string,
): Promise<{ code: string; expiresAt: string }> {
  const invite = await apiFetch<{ id: string; code: string; expires_at: string }>(
    `/members/${memberId}/invites`,
    { method: 'POST', token },
  );
  return { code: invite.code, expiresAt: invite.expires_at };
}

/** Follows with a code from family. The code goes in the body, never the URL. */
export async function joinMember(token: string, code: string): Promise<Member> {
  return toMember(await apiFetch<ApiMember>('/members/join', { method: 'POST', token, body: { code } }));
}

export async function listUnfiled(token: string): Promise<Unfiled> {
  const unfiled = await apiFetch<{ cases: ApiCase[]; lab_reports: ApiLabReportRow[] }>('/unfiled', { token });
  return { cases: unfiled.cases.map(toCase), labReports: unfiled.lab_reports.map(toLabRow) };
}
