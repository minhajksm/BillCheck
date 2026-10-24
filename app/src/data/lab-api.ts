import { apiFetch } from '@/lib/api';

import { sendPages, type OnProgress, type ScannedPage } from './cases-api';

/** Against the range the report itself prints, and nothing else. */
export type LabStatus = 'low' | 'high' | 'in_range' | 'no_range';

/** The two languages the reader writes in. Test names and numbers are never translated. */
export type LabLanguage = 'en' | 'hi';

export type LabTest = {
  name: string;
  value: string;
  unit: string;
  /** Exactly as printed. Empty where the report prints none. */
  range: string;
  status: LabStatus;
  explanation: Record<LabLanguage, string>;
};

export type LabReport = {
  id: string;
  labName: string;
  patientName: string;
  /** As printed. Never parsed: lab reports print dates every way there is. */
  reportDate: string;
  tests: LabTest[];
  summary: Record<LabLanguage, string>;
  questions: Record<LabLanguage, string[]>;
  /** The report itself marked a result critical. */
  urgent: boolean;
};

export type LabReportRow = {
  id: string;
  labName: string;
  reportDate: string;
  testCount: number;
  outsideRange: number;
  urgent: boolean;
};

type ApiLabTest = {
  name: string;
  value: string;
  unit: string;
  range: string;
  status: LabStatus;
  explanation_en: string;
  explanation_hi: string;
};

type ApiLabReport = {
  id: string;
  lab_name: string;
  patient_name: string;
  report_date: string;
  tests: ApiLabTest[];
  summary_en: string;
  summary_hi: string;
  questions_en: string[];
  questions_hi: string[];
  urgent: boolean;
};

type ApiLabReportRow = {
  id: string;
  lab_name: string;
  report_date: string;
  test_count: number;
  outside_range: number;
  urgent: boolean;
};

export const toLabReport = (r: ApiLabReport): LabReport => ({
  id: r.id,
  labName: r.lab_name,
  patientName: r.patient_name,
  reportDate: r.report_date,
  tests: r.tests.map((test) => ({
    name: test.name,
    value: test.value,
    unit: test.unit,
    range: test.range,
    status: test.status,
    explanation: { en: test.explanation_en, hi: test.explanation_hi },
  })),
  summary: { en: r.summary_en, hi: r.summary_hi },
  questions: { en: r.questions_en, hi: r.questions_hi },
  urgent: r.urgent,
});

const toRow = (r: ApiLabReportRow): LabReportRow => ({
  id: r.id,
  labName: r.lab_name,
  reportDate: r.report_date,
  testCount: r.test_count,
  outsideRange: r.outside_range,
  urgent: r.urgent,
});

export async function uploadLabReport(
  token: string,
  pages: ScannedPage[],
  onProgress?: OnProgress,
): Promise<LabReport> {
  return toLabReport((await sendPages(token, '/lab-reports', pages, undefined, onProgress)) as ApiLabReport);
}

export async function listLabReports(token: string): Promise<LabReportRow[]> {
  return (await apiFetch<ApiLabReportRow[]>('/lab-reports', { token })).map(toRow);
}

export async function readLabReport(token: string, id: string): Promise<LabReport> {
  return toLabReport(await apiFetch<ApiLabReport>(`/lab-reports/${id}`, { token }));
}

export async function deleteLabReport(token: string, id: string): Promise<void> {
  await apiFetch<void>(`/lab-reports/${id}`, { method: 'DELETE', token });
}
