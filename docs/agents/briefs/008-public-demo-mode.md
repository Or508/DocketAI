Status: done
For: cursor

# Brief 008: a public demo anyone can try without signing up

Start this only after brief 007 is done. The owner (2026-11-21) gave this whole brief to Cursor, API included.

## Ownership for this brief only
- Yours for this brief: `apps/api/**` (the parts below), `apps/web/app/demo/**` (new), `apps/web/app/api/demo/**` (new),
  `apps/web/components/OfficeTopNav.tsx`, `apps/web/app/login/page.tsx`, `apps/web/lib/api.ts`, `render.yaml`, `docs/deploy/render.md`.
- Do not edit: `apps/web/app/(legal)/**`, `apps/web/middleware.ts`, other proxies under `apps/web/app/api/**`.
- Port 8000 stays Claude's: to try the API, run your own copy on port 8001
  (`apps/api/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8001` from `apps/api`) and stop it when done. Claude restarts 8000 after review.
- API tests: `apps/api/.venv/Scripts/python.exe -m pytest -o addopts="" -q` from `apps/api` (the full suite takes ~12 minutes; run the files you touched
  first, the full suite once at the end). Never open a second `TestClient(app)` in a test: its shutdown can hang. For a request without the office
  session use `tests.support.SignedOut`; for a signed-in user `tests.support.authenticate`. Follow `tests/test_team.py` and `tests/test_office_contact.py`.
- New columns need both an Alembic migration (copy the style of `alembic/versions/20261121_0011_office_contact.py`) and the same columns in
  `app/db/compat.py`. `tests/test_migrations.py` fails if the models and Alembic disagree.

## Why
DocFlow is the owner's showcase: a link (and a one-minute video) sent to prospective clients to show what the owner builds
(document automation, websites, CRMs). It runs on the owner's own Render account (`render.yaml`), at a Render address first
(`*.onrender.com`), later on the owner's own domain. The LOGIMAT site (logimat.co.il) is a friend's account: do not depend on it.

Contact shown in the demo: WhatsApp **972547302757** (the owner's own number). Brand line: "DocFlow" plus that contact;
do not use the LOGIMAT name unless the owner asks (shared brand, the friend runs that site).

## What the visitor gets
1. `/demo` (public, Claude's new folder): what DocFlow does in three steps, a choice of scenario
   (law office: real estate closing / dental clinic: consent forms / HR: Form 101), and "התחילו דמו".
2. One click: a fresh, private sandbox office is created for that visitor with ready sample cases (synthetic people, the PDFs in
   `apps/web/public/demo/`), and the visitor is signed in to it as its owner. No email, no password.
3. Everything works as in a real office: the case, the missing-documents view, filling, "send to client" (WhatsApp link only),
   and the signer's page on the visitor's phone (a QR code to the signing link).
4. A fixed banner on every office screen: "דמו · נמחק אוטומטית ב-{time} · לא להעלות מידע אמיתי" with "רוצים מערכת כזו לעסק? דברו איתנו"
   → `https://wa.me/972547302757?text=...`.

## API
- Settings: `DEMO_MODE` (bool, default false), `DEMO_TTL_HOURS` (24), `DEMO_STARTS_PER_IP_PER_DAY` (5), `DEMO_WHATSAPP` ("972547302757").
  `production_problems()` must still pass in demo mode (real Postgres, R2, etc.); demo orgs only change behavior inside them.
- `organizations.demo_expires_at` (nullable). Alembic `20261121_0012` + `db/compat.py`.
- `POST /demo/start` `{ scenario: "law" | "dental" | "hr" }` (public; 404 unless DEMO_MODE; login rate-limit bucket plus the per-IP daily cap):
  create the org (profession from the scenario, `ai_reading_enabled=False` so the demo costs nothing, contact = the WhatsApp number),
  an owner user with an unusable random password and a `@demo.invalid` email, seed 2–3 cases from server-side copies of the demo PDFs
  (`app/assets/demo/`, synthetic data only), and return a session token like `/auth/login` does.
- `GET /demo/info` → `{ enabled, whatsapp, ttl_hours }` (public).
- `/auth/me` gains `demo_expires_at` (null for real offices).
- Inside a demo org: refuse every outgoing email (outreach email, team invites) with a Hebrew 403 "בדמו אפשר לשלוח רק בוואטסאפ, כדי שלא יישלחו מיילים לאנשים אמיתיים.";
  WhatsApp hand-off links keep working; forgot-password never matches demo users (unusable `.invalid` emails).
- Cleanup: the reminder loop (or a sibling loop) deletes expired demo orgs every few minutes: each case through `CaseService.delete_case`
  (so stored files go too), then users, sessions, account tokens, the org. Real offices are never touched (only `demo_expires_at IS NOT NULL AND < now`).
- Tests: start creates an isolated signed-in office with cases; two visitors never see each other's cases; the daily cap; email refused in demo;
  cleanup deletes files and rows and leaves real offices alone; 404 when DEMO_MODE is off.

## Web
- `apps/web/app/demo/**`: the landing page above. Public (not in the middleware matcher), RTL, gender-neutral plural Hebrew, `LegalFooter` at the bottom.
- `apps/web/app/api/demo/[...path]/route.ts`: `start` (POST, same-origin check, `clientIpHeaders`) sets the `docket_session` cookie exactly like
  `apps/web/app/api/auth/login/route.ts`; `info` (GET) passes through. Copy the structure of `apps/web/app/api/account/[...path]/route.ts`.
- `OfficeTopNav.tsx`: the demo banner when `me.demo_expires_at` is set, with the WhatsApp link; a floating WhatsApp button on demo screens.
- `/login`: a "רוצים לנסות? דמו בלי הרשמה" link to `/demo` when `GET /api/demo/info` says enabled.
- In demo cases, make the QR code to the signing link prominent ("סרקו כדי לחתום מהטלפון").
- `render.yaml`: add `DEMO_MODE` to `docketflow-config` with value "false" and a comment; describe in `docs/deploy/render.md` how to switch it on
  and that smaller plans are fine for a demo.

## Checks
- The API tests above (the new ones, then the full suite once), `npx tsc --noEmit -p apps/web`.
- On your port-8001 API with `DEMO_MODE=true` and a `npm run build -w web` + port 3000 restart (with `API_INTERNAL_URL=http://127.0.0.1:8001` for that run,
  then restart 3000 normally against 8000 at the end): start a demo in the browser, see the banner and the sample cases, open the signing link,
  and check a second demo (another browser profile) cannot see the first one's cases.
- Do not commit.

## When done
Set the first line to `Status: done` and add an entry at the top of `docs/agents/status.md` with files, checks, and anything not done.

## Then
The demo video (brief 010): Playwright records the scenario from start to signed PDF, with Hebrew captions; script by Claude.

## Open from earlier (do not lose)
- Brief 007 (client clarity, accessibility, legal footer) is with Cursor. Its keyboard/zoom results update `/accessibility`.
- `apps/web/app/(legal)/operator.ts`: operator details are still placeholders; for a demo, the operator is the owner as a private person
  (name + contact email still needed from the owner).
- Nothing since 843ad7e is committed. Render deploys from `main`.
