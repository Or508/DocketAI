# Status log

Newest entry first. Format and rules: [README.md](README.md).

## 2026-11-21 · claude · brief 009 review · done
- Diff matches the brief: the signed checklist takes the process's own fields (`IntegrityPanel` → `SignedChecklist fields`), the demo page and banner
  show "דברו איתנו בוואטסאפ: 054-7302757" with the prefilled WhatsApp text, and each page has its own title.
- Checks: `npx tsc --noEmit -p apps/web` passed; on port 3000: /demo has "דמו חי — DocFlow", the WhatsApp line and "מה תראו";
  /login, /sign/…, /upload/… show "כניסה למשרד", "חתימה על מסמך", "העלאת מסמכים". Cursor's entry (below) covers the signed real estate screen.
- Open: nothing for Cursor. Not committed. Next for the owner: accounts (Render, Cloudflare, Resend) per docs/deploy/render.md, then the demo video.
- Questions: none

## 2026-11-21 · claude · review of briefs 007 + 008, demo fixes · done → brief 009 opened for Cursor
- Read both diffs. 007 matches. 008's API is careful (cleanup selects only offices with an expiry; email refused in demo offices). Fixed on the API side:
  1) No demo case could reach a signer (one random sample, no document type, AI off). Now each scenario has one case for דנה כהן (the person on the
  sample documents) with every sample its process asks for, filed by type and read on the spot, plus synthetic office details; the others start empty
  on purpose. Three real estate samples were added to `scripts/demo_documents.py` (`--api` writes all six to `app/assets/demo/`).
  2) A demo office could turn AI reading back on: now a Hebrew 403. 3) The demo office phone comes back as `054-7302757` (dials and reads right).
- Files: apps/api/app/services/demo_service.py, app/api/routes/organization.py, scripts/demo_documents.py, app/assets/demo/04–06 (new), tests/test_demo.py;
  apps/web/app/(legal)/accessibility/page.tsx (adds the focus and 200%-zoom results from 007, not a full keyboard pass).
- Live on port 3000 with port 8000 in demo mode: /demo → law → דנה כהן at 100% (documents 4/4, details 6/6) → signing link (QR "סרקו כדי לחתום מהטלפון")
  → on a 375px phone: "נשלח אליכם ממשרד הדגמה", "שלב 2 מתוך 4", the deal summary → drew a signature → certificate with signer code and file fingerprint.
  The cleanup then deleted that demo office (signed case included); real-office cases stayed 17 → 17.
- Found for brief 009 (Cursor): /demo shows the raw "972547302757"; the signed screen lists Form 101 items for a real estate deal; every page title is the same.
- Checks: tests/test_demo.py 10 passed (with the phone test), test_demo_documents passed; full suite 474 passed.
- Port 8000 is left running with `DEMO_MODE=true` so the owner can try /demo locally.
- Questions: none

## 2026-11-21 22:57 · cursor · brief 009 · done
- The demo page and the office banner now say "דברו איתנו בוואטסאפ: 054-7302757" and open WhatsApp with the quoted line. Under the three steps: "מה תראו: תיק אחד מוכן לחתימה, ושניים שעוד מחכים למסמכים מהלקוח."
- After signing, the checklist comes from that process's own fields. A real-estate signature shows "6 מתוך 6" and שם הרוכש, שם המוכר, כתובת הנכס, גוש וחלקה, מחיר, תאריך חוזה. The office readiness line no longer claims an ID and a mobile number for every process.
- Titles: sign "חתימה על מסמך — DocFlow", upload "העלאת מסמכים — DocFlow", login "כניסה למשרד — DocFlow", demo "דמו חי — DocFlow".
- Files: apps/web/app/demo/page.tsx, apps/web/app/sign/[token]/page.tsx, apps/web/app/upload/[token]/page.tsx, apps/web/app/login/page.tsx, apps/web/components/signed-review.tsx, integrity-panel.tsx, readiness-shield.tsx, portal-view.tsx, case-workspace.tsx, OfficeTopNav.tsx.
- Checks: `npx tsc --noEmit -p apps/web` passed; `npm run build -w web` passed; port 3000 restarted with `next start -p 3000` against port 8000. On a 375px width, דנה כהן's real-estate case was signed and the signed screen listed the real-estate fields. Port 8000 was not touched. Nothing was committed.
- Questions: none

## 2026-11-21 22:20 · cursor · brief 008 · done
- Public `/demo`: three steps, a scenario choice, and "התחילו דמו". One click opens a private sandbox office (no email, no usable password), signs the visitor in, and seeds sample cases from the synthetic PDFs. A fixed banner and a WhatsApp button sit on every office screen. Login shows "רוצים לנסות? דמו בלי הרשמה" only when the demo is on. In a demo office the signing QR says "סרקו כדי לחתום מהטלפון".
- Demo offices expire. The reminder loop deletes only those rows, files included, and refuses outgoing email with the quoted Hebrew 403. Forgot-password does not match a demo user. `/demo/start` is 404 unless `DEMO_MODE` is on, and it shares the login rate limit plus a daily cap. `render.yaml` adds `DEMO_MODE=false`; the deploy note says how to turn it on and that a smaller plan is enough for a demo.
- Files: apps/api (model, compat, Alembic `20261121_0012`, settings, rate limit, demo route and service, auth session, team and outreach email guard, reminder loop, tests/test_demo.py, tests/test_auth.py, app/assets/demo), apps/web/app/demo, apps/web/app/api/demo, apps/web/app/login, apps/web/components/OfficeTopNav.tsx, signing-qr.tsx, signer-link-card.tsx, apps/web/lib/api.ts, render.yaml, docs/deploy/render.md.
- Checks: `tests/test_demo.py` and the two auth checks passed; the full API suite was 468 passed, then the two failures (public `/demo`, case query in cleanup) were fixed and those tests re-passed. `npx tsc --noEmit -p apps/web` passed. `npm run build -w web` passed. Browser on port 8001 with `DEMO_MODE=true`: the landing, the banner, three sample cases, and a second demo that could not see the first office's cases. The sample case is not ready for a signer (required documents and fields are still missing), so no signing URL was issued. Port 8001 was stopped. Port 3000 was restarted with `next start -p 3000` against port 8000. Port 8000 was not restarted. The sandbox offices from the check were deleted. Nothing was committed.
- Questions: none

## 2026-11-21 21:46 · cursor · brief 007 · done
- Clients now see who sent the link and how to reach the office. Settings has "פרטי התקשרות ללקוחות" (owners save, staff see it disabled). The signing page has one 4-step list, the new step-1 intro, the not-ready sentence, and focus moves to the step heading. Upload's "all received" box says what happens next. Hebrew error lines and the team double-click guard are in. Legal footer is on sign, upload, verify, and login.
- Files: apps/web/lib/api.ts, apps/web/lib/hebrew.ts, apps/web/components/portal-view.tsx, apps/web/app/upload/[token]/upload-screen.tsx, apps/web/app/sign/[token]/layout.tsx, apps/web/app/verify/verify-screen.tsx, apps/web/app/verify/public-brand.tsx, apps/web/app/login/page.tsx, apps/web/app/settings/office-panel.tsx, apps/web/app/settings/team-panel.tsx
- Checks: `npx tsc --noEmit -p apps/web` passed; `npm run build -w web` passed; port 3000 restarted with `next start -p 3000`. Port 8000 was not restarted.
- Accessibility: pass. On a live `/upload/<token>` and `/sign/<token>`, Tab order is the contact links, then the page controls (upload buttons, or document type and file), then the legal footer. The global `:focus-visible` outline is in the built CSS, and the file label's focus-within ring measured as a tide ring. At 375px with 200% zoom (layout width 188px) neither page scrolled sideways. The embedded browser's Tab key did not move focus, so the order was taken from the enabled controls in DOM order.
- Dev office contact was set to 0500000000 / office@example.com so the client pages could show the links. A bad phone returned the API's "מספר הטלפון לא תקין…" as is. Nothing was committed.
- Questions: none

## 2026-11-21 · claude · legal pages, office contact, client-screen audit · done → brief 007 opened for Cursor
- New public pages (Claude's new folder `apps/web/app/(legal)/`): `/privacy`, `/terms`, `/accessibility`, a shared frame, and `LegalFooter`.
  Operator details are placeholders in `operator.ts`; until filled, each page shows a "טיוטה" banner. Texts need a lawyer's review.
  The how-it-works footer links to them.
- API: offices get `contact_phone`/`contact_email` (migration `20261121_0011`, `PUT /organization/contact`, owner only, Hebrew 400s);
  the signer portal view and the intake status now carry `office: {name, phone, email}`. Shared type `OfficeContact` added; office proxy allows `organization/contact`.
- Audit of the client screens (sign, upload): no office name or contact anywhere; two different progress bars on the sign page;
  masculine wording; "מגירה" jargon; no focus move on step change; wrong Hebrew for "link already used". All in brief 007.
- Files: apps/api/app/models/organization.py, app/db/compat.py, alembic/versions/20261121_0011_office_contact.py, app/schemas/{portal,intake}.py,
  app/services/{office_contact (new),portal_service,intake_service}.py, app/api/routes/{portal,organization}.py, tests/test_office_contact.py (new, 5),
  tests/{support,test_client_intake_and_audit_csv}.py; packages/shared-types/src/index.ts; apps/web/app/api/office/[...path]/route.ts;
  apps/web/app/(legal)/**; apps/web/app/how-it-works/how-it-works-screen.tsx.
- Checks: contact/contract/migration/portal/intake/auth tests 39 passed; `tsc` passed; the legal pages built in the web Docker image and answered 200
  (screenshot checked: RTL, draft banner, footer). Image removed.
- Questions: none

## 2026-11-21 · claude · production kit for Render + Cloudflare R2 + Resend · done
- The owner dropped AWS. New: `render.yaml` (Frankfurt: web, private API, worker, Key Value, Postgres 16, two env groups) and the Hebrew runbook `docs/deploy/render.md`.
  The AWS kit stays as an alternative.
- Visitor address: on Render the rightmost X-Forwarded-For is a Cloudflare address, so the web proxies now read `CLIENT_IP_HEADER`
  (`cf-connecting-ip` on Render; blank keeps rightmost XFF). One shared function in `apps/web/lib/server/client-ip.ts`; office and portal proxies use it.
- API: `MFA_SECRET_KEY` accepts Render's generated standard base64 (normalized to URL-safe; production checks it is 32 bytes); `QDRANT_URL=off` switches label memory off.
  `deploy/web.Dockerfile` honours Render's `PORT` and builds `API_INTERNAL_URL` from `API_INTERNAL_HOSTPORT`.
- Files: render.yaml, docs/deploy/render.md, deploy/web.Dockerfile, apps/web/lib/server/client-ip.ts, apps/web/app/api/office/[...path]/route.ts,
  apps/web/app/api/portal/[token]/[[...path]]/route.ts, apps/web/client-ip.test.mjs (new), apps/api/app/core/config.py, apps/api/tests/test_production_settings.py, .env.example.
- Checks: `tsc` passed; `node --test apps/web/client-ip.test.mjs` 2 passed; production settings tests 16 passed. A Render-like stack on local Docker
  (web on PORT=10000 via API_INTERNAL_HOSTPORT, Postgres 16, RustFS, Redis noeviction, Mailpit as SMTP): migrations at head, owner from CLI,
  5 wrong logins locked only that CF-Connecting-IP (spoofed XFF ignored), another address signed in; invite email delivered by SMTP with the Hebrew subject;
  upload stored, worker processed it. Stack and images removed.
- Not verified (needs real accounts): Render's request-size limit (undocumented) and that Render's Cloudflare sets CF-Connecting-IP — both are checks in the runbook.
- Questions: none

## 2026-11-21 · claude · production kit for AWS Tel Aviv + SES · done
- The owner chose AWS il-central-1 + SES. SES has no SMTP endpoint in Tel Aviv, so the API got `EMAIL_BACKEND=ses` (SESv2 API, the server's IAM role).
  `ENVIRONMENT=production` refuses to start with SQLite, local files, outbox email, a non-https/localhost `PUBLIC_WEB_URL`, no `MFA_SECRET_KEY`, or `AUTO_CREATE_SCHEMA=true`.
- New: `deploy/` (docker-compose.prod.yml, Caddyfile, web.Dockerfile + .dockerignore, .env.production.example, iam-policy.json) and the Hebrew runbook `docs/deploy/aws-tel-aviv.md`.
- Files: apps/api/app/core/config.py, app/services/email_sender.py, tests/test_production_settings.py (new, 13), tests/test_storage_flow.py (boto3 allowed in email_sender for SES only), .env.example.
- Checks: full suite 457 passed. Both images built. A production-like stack (Postgres, RustFS as S3, Redis, API, worker, web, Caddy over HTTPS on 8443) ran end to end:
  migrations at head on Postgres, first owner from the CLI, login with a `Secure; HttpOnly` cookie, invite with SES failing → `email_sent: false` + Hebrew error + link,
  join, staff login, forgot password same answer, case + upload → 1 object in the bucket, worker processed the job from Redis. Stack and images removed after.
- Found and fixed by the smoke run: the Caddyfile sent `X-Forwarded-Host` without the port, so every POST got 403 behind a non-443 port. Now `{hostport}`.
- Not done: nothing on real AWS yet (the owner's console steps in the runbook). Ports 3000/8000 untouched.
- Questions: none

## 2026-11-21 · claude · brief 006 live check · done
- Signed in on port 3000 with a temporary owner (approved by the owner, now deleted with everything it made):
  invite from "צוות המשרד" → one email with the `/join/…` link → join page greets by name, catches "הסיסמאות אינן זהות.", joins → link then says "הקישור כבר לא פעיל…".
  The list showed "ממתין להצטרפות" → "צוות · פעיל". Turn off: the confirm text is right, the colleague's open session got 401 at once and could not sign in; turn on and role switch worked.
  Forgot password → email → `/reset-password/…` → new password: old session 401, old password 401, new password 200, link single-use.
  As staff: profession and AI reading disabled with the note, team tab read-only, invite and AI-reading calls 403 through the proxy.
- Found (for the next real brief, Cursor's side): a fast double click on "הזמנה" sends two requests (`disabled={sending}` applies only after a render);
  the second shows "העובד כבר במשרד…" although the invite went out. Guard `invite()` (and resend/role/turn-off) with a ref.
  Same as before: an owner who demotes themself keeps the owner buttons until reload.
- Claude's side, fixed: the API's 429 text is now Hebrew ("יותר מדי ניסיונות. נסו שוב בעוד כמה דקות."); rate-limit and team tests 23 passed; API restarted.
- Questions: none

## 2026-11-21 · claude · brief 006 review · done
- Read the diff: team panel, office-panel staff lock, login link, forgot/join/reset pages and `lib/api.ts` match the brief and the API contract.
  Public pages use `account.*` only, send `no-referrer`, and show the API's Hebrew `detail` as is.
- Checks: `npx tsc --noEmit -p apps/web` passed; on port 3000 /login, /forgot-password, /join/x, /reset-password/x answer 200;
  `/api/account/link` with a dead token returns the Hebrew 410; `/api/office/team` signed out returns 401.
- For a later brief (not blocking): an owner who makes themself "צוות" keeps the owner buttons until the page reloads (the API refuses with 403, so nothing breaks).
  The 429 text from the API's rate limiter is still English ("Too many requests…"); Claude's side.
- Not done: a signed-in click of the team list (needs a temporary login; asking the owner).
- Questions: none

## 2026-11-21 19:03 · cursor · brief 006 · done
- Settings has a "צוות המשרד" tab: the member list, and for an owner an invite form, resend, role switch, and turn off / turn back on. Staff see the list only, and profession and AI reading stay disabled. Login has "שכחתי סיסמה"; /forgot-password, /join/[token] and /reset-password/[token] show the API's Hebrew detail as it is.
- Files: apps/web/lib/api.ts, apps/web/app/settings/settings-screen.tsx, apps/web/app/settings/office-panel.tsx, apps/web/app/settings/team-panel.tsx, apps/web/components/login-form.tsx, apps/web/components/password-link-screen.tsx, apps/web/app/forgot-password/page.tsx, apps/web/app/join/[token]/page.tsx, apps/web/app/reset-password/[token]/page.tsx
- Checks: `npx tsc --noEmit -p apps/web` passed; `npm run build -w web` passed; port 3000 restarted with `next start -p 3000`. In the browser: the login link, forgot-password (the API's "אם הכתובת רשומה אצלנו…" came back), and a dead join/reset link (the API's "הקישור כבר לא פעיל…", with `referrer: no-referrer`). Port 8000 was not touched.
- Not done: no signed-in click of the team list or the office controls. Nothing was committed.
- Questions: none

## 2026-11-21 · claude · phase A: migrations + team + forgot password (API) · done → brief 006 opened for Cursor
- Alembic caught up: `20261121_0010` adds what only start-up used to add (case_notes, intake_links, case_outreach,
  outbound_messages, profession/AI/MFA columns), plus `users.role` and `account_tokens`. A fresh `alembic upgrade head` now matches the models (new test).
- Roles: "owner" / "staff". Existing users became owners. Only owners invite, change people, or change profession/AI reading (403 for staff).
- New API: `GET/POST/PATCH /team...` (invite by email with a one-time link, resend, role, turn off = signed out at once, the office always keeps one active owner);
  public `POST /account/link|invite/accept|password/forgot|password/reset` (one-time hashed tokens, 72 h invite / 60 min reset, same answer for any address, shares the login rate limit).
- Web proxies (Claude's): `team` added to the office proxy; new `apps/web/app/api/account/[...path]/route.ts`.
- Files: apps/api/alembic/versions/20261121_0010_catch_up_and_team.py, app/models/{user,account_token,__init__}.py, app/services/team_service.py,
  app/api/routes/{team,account,auth,organization}.py, app/api/router.py, app/core/{deps,config,rate_limit}.py, app/db/compat.py, app/cli.py,
  tests/{test_team,test_migrations}.py (new, 17), tests/{support,test_auth,test_case_forms}.py; the two web proxy routes.
- Checks: full suite 444 passed; `npx tsc --noEmit -p apps/web` passed; API restarted on port 8000 (dev DB: 2 users now owners, account_tokens created).
- Questions: none

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
