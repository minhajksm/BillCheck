# BillSaathi

A mobile app that helps Indian families check hospital bills during and after an admission. Users photograph itemized bills, the app flags likely overcharges (above MRP, duplicates, unusual quantities), and helps them ask the hospital polite, specific questions.

The clickable prototype is in `docs/prototype.html`. Treat it as the source of truth for screens, copy, and flow.

## Stack

- `app/`: React Native with Expo (SDK 57), TypeScript, Expo Router. Android first.
- `api/`: Python 3.12+, FastAPI, managed with uv.
- Database: PostgreSQL (local via Docker, see below).
- `data/`: reference price lists (NPPA ceiling prices, CGHS rates). Anonymized samples only.

## Commands

- App: `cd app && npx expo run:android` (development build; Expo Go doesn't support SDK 57)
- API: `cd api && uv run uvicorn main:app --reload` (docs at http://localhost:8000/docs)
- DB: `docker start billsaathi-db`
- From the Android emulator, the API is at `http://10.0.2.2:8000`

## MVP scope

1. Cases: a case is one hospital admission, shared with family members.
2. Scan: capture or upload multi-page bills (camera and PDF).
3. Audit: OCR the bill, structure line items, check against MRP, NPPA ceiling prices, duplicates, and quantity norms.
4. Report: flags with two levels. Red for clear issues (above MRP, duplicate). Amber for "worth asking" (unusual quantity).
5. Action: generate a message to the billing desk in English, Hindi, or Marathi. Track each flag as open, corrected, or explained. Track amount recovered.

Out of scope for now: medical necessity review, pre-admission estimates, insurance claim explainer, hospital comparisons.

## Rules that always apply

- API keys (Claude API, OCR) live only in `api/.env`. Never put secrets in the mobile app.
- Never commit real hospital bills or patient data. Use `data/samples/` with anonymized bills, and keep `data/private/` gitignored.
- Flags are questions, not verdicts. UI copy must never accuse a hospital of fraud.
- Every flag must show its reasoning and the reference it was checked against.
- All user-facing strings go through i18n (`en`, `hi`, `mr`). No hardcoded copy in components.
- Currency is INR, formatted with Indian digit grouping (₹1,42,380).
- Treat health data as sensitive under India's DPDP framework: explicit consent, minimal retention.

## Conventions

- TypeScript strict mode in `app/`. Type hints and Pydantic models in `api/`.
- Small, focused pull requests, one feature each.
- Write tests for the audit logic in `api/` (price matching, duplicate detection) before UI polish.

## Current milestone

The full scan loop: take a photo in the app, upload it to `POST /bills`, return structured line items, and show them on screen.
