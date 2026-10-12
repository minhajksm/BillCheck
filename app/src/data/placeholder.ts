import type { Case } from './types';

/**
 * Placeholder data matching docs/prototype.html, before today's bill is
 * scanned. Illustrative only: not a real hospital, patient, or price.
 * Replace with API data once cases are served by api/.
 */

export const currentUser = { id: 'u-rohan', name: 'Rohan Sharma', firstName: 'Rohan' };

export const placeholderCases: Case[] = [
  {
    id: 'papa-admission',
    title: "Papa's admission",
    hospital: { name: 'City Care Hospital', area: 'Andheri' },
    patient: { name: 'Ramesh Sharma', ipNumber: '20841', bed: '412' },
    admittedOn: '2026-10-09',
    dayOfStay: 3,
    members: [
      { id: 'u-rohan', name: 'Rohan Sharma', isYou: true },
      { id: 'u-anita', name: 'Anita Sharma', isYou: false },
    ],
    bills: [
      { id: 'b-day1', date: '2026-10-09', day: 1, itemCount: 24, total: 68490, flagCount: 0, openFlagCount: 0 },
      { id: 'b-day2', date: '2026-10-10', day: 2, itemCount: 37, total: 31400, flagCount: 0, openFlagCount: 0 },
    ],
    recoveredAmount: 0,
  },
  {
    id: 'mummy-cataract',
    title: "Mummy's cataract surgery",
    hospital: { name: 'Lotus Eye Clinic', area: 'Thane' },
    patient: { name: 'Sunita Sharma', ipNumber: '7712', bed: '6' },
    admittedOn: '2026-03-12',
    dayOfStay: 2,
    closedOn: '2026-03-13',
    members: [{ id: 'u-rohan', name: 'Rohan Sharma', isYou: true }],
    bills: [
      { id: 'b-cat1', date: '2026-03-12', day: 1, itemCount: 18, total: 41200, flagCount: 2, openFlagCount: 0 },
      { id: 'b-cat2', date: '2026-03-13', day: 2, itemCount: 9, total: 6350, flagCount: 0, openFlagCount: 0 },
    ],
    recoveredAmount: 3200,
  },
];

export function findCase(id: string): Case | undefined {
  return placeholderCases.find((c) => c.id === id);
}
