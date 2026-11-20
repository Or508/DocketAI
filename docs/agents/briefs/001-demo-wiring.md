Status: done
For: cursor

# Brief 001: wire the demo into the office screens

Claude already built (do not edit these): `apps/web/app/how-it-works/**`, `apps/web/public/demo/*.pdf`,
`apps/api/scripts/demo_documents.py`, `apps/api/**`, `apps/web/next.config.ts`, `apps/web/lib/server/client-ip.ts`.

- `/how-it-works` is a public explainer page (no login) with a click-through demo and three downloadable sample files.
- `/demo/01-teudat-zehut.pdf`, `/demo/02-arnona.pdf`, `/demo/03-ishur-bank.pdf` are invented documents for one employee,
  Dana Cohen (ID 100000009). The office's real reader fills 9 of the 10 Form 101 details from them. Only the phone is left
  for the clerk. A test pins this (`apps/api/tests/test_demo_documents.py`).

## 1. Links to the explainer
- `apps/web/app/login/page.tsx`: under the form, a quiet link "איך זה עובד?" → `/how-it-works`.
- `apps/web/components/OfficeTopNav.tsx`: an item "איך זה עובד" → `/how-it-works` (in the overflow/help area, not a main tab).

## 2. "תיק לדוגמה" button on the office dashboard (`components/dashboard.tsx`)
One click opens a ready-to-explore case using the existing office API through the office proxy:
1. `POST /cases` `{ "name": "טופס 101 — דוגמה", "process_key": "employee_onboarding", "client_name": "דנה כהן (דוגמה)" }` → `id`
2. `POST /cases/{id}/load-default-form`
3. Fetch the three `/demo/*.pdf` files in the browser and send them in one `POST /cases/{id}/upload` (multipart, field `files`).
4. If the case's `gap.unrecognized` still lists them (no AI key, or AI is off for the office), classify each with
   `POST /cases/{id}/classify-manual` `{ "document_id", "document_type" }`: `01-…` → `id_copy`, `02-…` → `proof_of_address`, `03-…` → `bank_confirmation`.
5. Navigate to `/cases/{id}`.
Show progress on the button ("פותח תיק לדוגמה…") and a Hebrew error if a step fails. The case name must say it is a demo.

## 3. Deploy
After merging, rebuild and restart port 3000 so the new security headers and `/how-it-works` are live.

## Checks
`npx tsc --noEmit -p apps/web`. The API suite already passes (`pytest -o addopts=""` in `apps/api`).

## When done
Set the first line to `Status: done` and add an entry at the top of `docs/agents/status.md`
(format in `docs/agents/README.md`). Commit Claude's uncommitted files together with yours, as usual.

## Answers
(Claude answers questions from `status.md` here.)
