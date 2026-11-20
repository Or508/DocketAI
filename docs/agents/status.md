# Status log

Newest entry first. Format and rules: [README.md](README.md).

## 2026-11-20 14:55 · claude · brief 005 review + live check · done
- Brief 005 matches: the dashboard line uses `WHATSAPP_FALLBACK` once; a failed status refresh says "התזכורת נשלחה, אבל הסטטוס לא התעדכן.". `tsc` passed.
- Live on port 3000 with a temporary login (now removed), demo case "דנה כהן (דוגמה)":
  WhatsApp send → popup blocked, the dialog showed the fallback sentence and a "פתיחת וואטסאפ" link to `wa.me/972500000000` with the Hebrew message and
  the upload link (`target=_blank`, `rel=noopener noreferrer`); "שליחה" was gone after the send. Message times now show Israel time (13:14, 14:49).
  "לשלוח תזכורת עכשיו" on a finished intake showed the API's "הלקוח כבר השלים את מה שהתבקש." as is.
- Not checked live: the dashboard WhatsApp card (needs a WhatsApp reminder whose time has come). Code reviewed only.
- Note: links in messages use `PUBLIC_WEB_URL` (`http://localhost:3000` here); production needs the real address.
- Questions: none

## 2026-11-20 14:42 · cursor · brief 005 · done
- The dashboard WhatsApp line is now "{case}: אם וואטסאפ לא נפתח, לחצו על פתיחת וואטסאפ." using the shared `WHATSAPP_FALLBACK` text. If a case reminder is sent but reloading its status fails, the block says "התזכורת נשלחה, אבל הסטטוס לא התעדכן."
- Files: apps/web/components/client-outreach.tsx, apps/web/components/dashboard.tsx
- Checks: `npx tsc --noEmit -p apps/web` passed; `npm run build -w web` passed; port 3000 restarted with `next start -p 3000` and `/login` returns 200. Port 8000 was not touched.
- Not done: no signed-in click. Nothing was committed.
- Questions: none

## 2026-11-20 14:40 · claude · brief 004 review · done → brief 005 opened for Cursor
- Read the diff of client-outreach.tsx and dashboard.tsx: the WhatsApp fallback link is in all three places, the dialog cannot send twice,
  and the reminder button and switch wait for a first send. All as brief 004 asked.
- Checks: `npx tsc --noEmit -p apps/web` passed.
- Found: the dashboard line repeats itself (my wording in brief 004), and the case reminder block still reports a failed refresh as a failed action.
  Both are in brief 005.
- Not done: a signed-in click (needs a temporary login; asking the user).
- Questions: none

## 2026-11-20 14:27 · cursor · brief 004 · done
- WhatsApp sends still call `window.open`, and also show a "פתיחת וואטסאפ" link with "אם וואטסאפ לא נפתח, לחצו על פתיחת וואטסאפ." in the dialog, the case reminder button, and the dashboard. The dashboard keeps the last sent reminder, with that link, until it is dismissed or the page reloads. After a successful send the dialog hides "שליחה". The reminder button and switch stay disabled until something has been sent. A dashboard refresh that fails after a successful remind says "התזכורת נשלחה, אבל הרשימה לא התעדכנה."
- Files: apps/web/components/client-outreach.tsx, apps/web/components/dashboard.tsx
- Checks: `npx tsc --noEmit -p apps/web` passed; `npm run build -w web` passed; port 3000 restarted with `next start -p 3000` and `/login` returns 200. Port 8000 was not touched.
- Not done: no signed-in click, so the popup fallback was not exercised in the browser. Nothing was committed.
- Questions: none

## 2026-11-20 13:50 · claude · times shown 2 hours early · done
- Every time column now uses `UtcDateTime` (`app/models/columns.py`): it writes UTC and always reads back with the UTC zone.
  On SQLite the API used to send `2026-11-20T11:14:10` with no offset, so browsers showed UTC as Israel time. Now it sends
  `…+00:00`, and every screen (dashboard, case, reminders, log) shows the right time with no web change. Postgres is unaffected.
- Files: apps/api/app/models/columns.py and the 11 model files (`DateTime(timezone=True)` → `UtcDateTime()`); tests/test_utc_times.py (new, 2).
- Checks: full suite 427 passed; API restarted on port 8000; the demo case's time reads back as `2026-11-19T21:18:17+00:00` (23:18 Israel time).
- Questions: none

## 2026-11-20 13:20 · claude · brief 003 live check · done
- Signed in on port 3000 with a temporary login (now removed) and used the demo case "דנה כהן (דוגמה)".
  Email: the dialog said "נשלח באימייל ל-…", and an `.eml` with the right recipient, subject and `/upload/…` link was written (deleted after).
  WhatsApp: the API returned the message as `handed_to_office`, but the popup was blocked, which confirms brief 004 item 1.
- Found in the API (Claude's side, not fixed yet): on SQLite, times come back without a time zone (`2026-11-20T11:14:10`), so the
  screens show UTC, 2 hours early. This hits every screen, not just reminders (the dashboard too).
- Note: an intake request on a case with no missing documents stops reminders at once ("הלקוח השלים"). That is by design.
- The test messages stay in the demo case's history.
- Questions: none

## 2026-11-20 13:30 · claude · brief 003 review · done → brief 004 opened for Cursor
- Read Cursor's diff (client-outreach.tsx, case-workspace.tsx, dashboard.tsx, lib/api.ts): the types match the API schema, the Hebrew labels
  match the brief, and the API's `detail` reaches the screen as is.
- Checks: `npx tsc --noEmit -p apps/web` passed; `tests/test_outreach.py` 16 passed; API restarted on port 8000.
- Found: WhatsApp `window.open` comes after an await and can be blocked (Safari), with no link to fall back on; the dialog can send twice
  and break the link the client just got; reminder buttons are active before anything was sent; on the dashboard, a failed refresh shows as a failed send.
  All four are in brief 004.
- Not done: a signed-in click through the screen. Creating a temporary login was refused by the permission check; waiting on the user.
- Questions: none

## 2026-11-20 13:08 · cursor · brief 003 · done
- The case screen has "שליחה ללקוח" (intake or signing, email or WhatsApp, reminders) and a "סטטוס תזכורות" block. The dashboard shows "תזכורות לשליחה בוואטסאפ (N)" when `GET /outreach/due` returns rows; each row reminds and opens `whatsapp_url`. API `detail` is shown as returned. WhatsApp uses `window.open` in the click handler after the POST.
- Files: apps/web/components/client-outreach.tsx, apps/web/components/case-workspace.tsx, apps/web/components/dashboard.tsx, apps/web/lib/api.ts
- Checks: `npx tsc --noEmit -p apps/web` passed; `npm run build -w web` passed; port 3000 restarted with `next start -p 3000` and `/cases` redirects to login. Port 8000 was not touched.
- Not done: no signed-in click through the dialog or the dashboard card, so no `.eml` was written and WhatsApp was not opened. The API suite was not run. Nothing was committed.
- Questions: none

## 2026-11-20 00:30 · claude · client messages API · done → brief 003 opened for Cursor
- Send a fresh intake or signing link by email (sent now) or WhatsApp (a wa.me link the office opens). Reminders after 2 and 5 days,
  09:00–20:00 Israel time, never Saturday; they stop by themselves when the client finishes, the case is signed, or the link is
  replaced or expires. Email reminders go out from a loop in the API (claimed per row, so two processes never double-send);
  WhatsApp reminders wait in `GET /outreach/due`. Cap: 10 messages per case per day. The raw link token for reminders is sealed
  with the server key (`mfa.key` / `MFA_SECRET_KEY`), never stored in clear.
- Files: apps/api/app/{domain/outreach.py, models/outreach.py, schemas/outreach.py, services/outreach_service.py,
  services/email_sender.py, api/routes/outreach.py} (new); config.py, compat.py (creates the two new tables), main.py, router.py,
  enums.py, workers/runner.py; tests/test_outreach.py (new, 16), tests/test_tenancy.py (new routes in the 404 list);
  apps/web/app/api/office/[...path]/route.ts (`outreach/due` allowed); .env.example.
- Checks: full suite 424 passed + the tenancy list fix (33 passed in the affected files); tsc passed; proxy test passed; API restarted, tables created.
- Not done: SMS (needs a provider account) and automatic WhatsApp (needs Meta's business API). Alembic has no migration for
  this or for the recent intake/MFA tables; the schema is created by `compat.py`.
- Questions: none

## 2026-11-19 23:55 · claude · embedding model · done
- The label memory now embeds with `gemini-embedding-001` at 768 dimensions (`EMBEDDING_MODEL` default, `.env`, `.env.example`).
  Each model and size gets its own Qdrant collection (`docket_labels__gemini_embedding_001_768`), so old vectors are never
  searched with new ones. The old `docket_labels` collection, if one exists, is no longer read.
- Files: apps/api/app/core/config.py, apps/api/app/services/gemini_client.py, apps/api/app/services/learning_store.py,
  apps/api/tests/test_embeddings.py (new), apps/api/tests/test_tenancy.py (stub settings), .env.example
- Checks: one live call returned a 768-value vector; full suite 408 passed + the one fixed tenancy test; API on port 8000 restarted.
- Questions: none

## 2026-11-19 23:25 · claude · brief 002 live check · done
- Clicked "תיק לדוגמה" on port 3000 against the API on port 8000, signed in with a temporary login (now removed).
  The case opened with all three files in their drawers, nothing to review, 9 of 10 details filled; only the phone is left.
- Found on the way (fixed 23:55, see the entry above): Gemini returns 404 for `EMBEDDING_MODEL=text-embedding-004` (retired), so label memory
  (Qdrant few-shot) is not stored. Classification itself still works.
- Questions: none

## 2026-11-19 23:20 · claude · brief 002 review · done
- Reviewed brief 002: the demo button uploads each sample with its drawer type, as the API test pins. No open briefs.
- Checks: `npx tsc --noEmit -p apps/web` passed; port 3000 serves `/how-it-works` with the security headers, and `/` redirects to login when signed out.
- Not yet done: a click on the button against a running API (port 8000) with a signed-in office. Nothing is committed.
- Questions: none

## 2026-11-19 23:13 · cursor · brief 002 · done
- The demo button now uploads each sample PDF on its own with its drawer type (`id_copy`, `proof_of_address`, `bank_confirmation`) and no longer classifies from `gap.unrecognized`. Case name, client name, progress label, and Hebrew error are unchanged.
- Files: apps/web/components/dashboard.tsx
- Checks: `npx tsc --noEmit -p apps/web` passed; `npm run build -w web` passed; port 3000 restarted with `next start -p 3000`. Port 8000 was not touched.
- Questions: none

## 2026-11-19 22:20 · claude · brief 001 review · progress
- Reviewed Cursor's brief 001. Links on login and the office bar: good. Port 3000 serves `/how-it-works`, the sample PDFs and the new security headers.
- One bug in the demo button: on a real server the files are still in `gap.in_progress` when the button looks for `unrecognized`, so nothing is classified when there is no AI. Opened brief 002 with the fix.
- Added an API test for the demo sequence (`test_the_dashboard_demo_case_fills_the_form_with_no_ai`).
- Checks: `tests/test_demo_documents.py` 4 passed, `npx tsc --noEmit -p apps/web` passed.
- Questions: none

## 2026-11-19 22:01 · cursor · brief 001 · done
- Login and the office bar link to `/how-it-works`. The dashboard has a "תיק לדוגמה" button that opens a Form 101 demo case, loads the blank form, uploads the three sample PDFs, and classifies any that stay unrecognized. Rebuilt the web app and started it on port 3000.
- Files: apps/web/app/login/page.tsx, apps/web/components/login-form.tsx, apps/web/components/OfficeTopNav.tsx, apps/web/components/dashboard.tsx
- Checks: `npx tsc --noEmit -p apps/web` passed; `npm run build -w web` passed; `next start -p 3000` is serving. The login link opens `/how-it-works`. Port 8000 was not running and was left untouched, so the demo button was not clicked through a signed-in case.
- Questions: none

## 2026-11-19 21:55 · claude · brief 001 · progress
- Opened brief 001 for Cursor: links to `/how-it-works`, a "תיק לדוגמה" button on the dashboard, rebuild of port 3000.
- Already done by Claude, uncommitted: per-address rate limiting and login lockout per address (`apps/api`), security headers
  (`apps/web/next.config.ts`), visitor address forwarded by the login, intake and verify proxies, public page `/how-it-works`,
  three sample PDFs in `apps/web/public/demo`.
- Checks: `pytest -o addopts=""` 401 passed (+3 sample-file tests), `npx tsc --noEmit -p apps/web` passed, `/how-it-works` and headers checked on a preview server (port 3100, now stopped).
- Questions: none
