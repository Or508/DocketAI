Status: done
For: cursor

# Brief 006: office team screen, joining by invitation, and "forgot my password"

The API side is done (Claude, 2026-11-21) and running on port 8000. An office can now invite colleagues,
give them a role, turn an account off, and anyone can reset a forgotten password by email. This brief adds the screens.

Do not edit: `apps/api/**`, `apps/web/app/api/**` (the proxies are done: `/api/office/team...` and `/api/account/...`),
`apps/web/middleware.ts`, and everything listed in brief 001.
Files: `apps/web/lib/api.ts`, `apps/web/app/settings/settings-screen.tsx`, `apps/web/app/settings/office-panel.tsx`,
`apps/web/app/settings/team-panel.tsx` (new), `apps/web/app/login/page.tsx`, `apps/web/app/forgot-password/page.tsx` (new),
`apps/web/app/join/[token]/page.tsx` (new), `apps/web/app/reset-password/[token]/page.tsx` (new).

Every error below comes back from the API with a Hebrew `detail`. Show it as it is (`detailFrom`), do not translate or replace it.

## API contract

Office (through `/api/office/...`, signed in):
- `GET /auth/me` now also has `role: "owner" | "staff"`.
- `GET team` → `Member[]`:
  `{ id, email, display_name, role: "owner"|"staff", status: "active"|"invited"|"invite_expired"|"inactive", is_you, mfa_enabled, created_at, invite_expires_at | null }`
- `POST team/invite` `{ email, display_name, role }` → 201 `{ member: Member, invite_url, email_sent: boolean, email_error: string|null }`. Owner only.
- `POST team/{id}/resend-invite` → same shape as invite. Owner only. The old link stops working.
- `PATCH team/{id}` `{ role?, is_active?, display_name? }` → `Member`. Owner only. Turning an account off signs it out at once.
- A staff member gets 403 "רק מנהל המשרד יכול לשנות את זה." on the three above and on `PUT organization/profession` and `PUT organization/ai-reading`.

Public (through `/api/account/...`, no session, all `POST` with JSON):
- `link` `{ token }` → `{ purpose: "invite"|"reset", email, display_name, organization_name, min_password_length }`, or 410 with `detail`.
- `invite/accept` `{ token, password }` → 204. 400 `code: "weak_password"`; 410 if the link no longer works.
- `password/forgot` `{ email }` → 202 `{ detail }`. Always the same answer, whatever the address.
- `password/reset` `{ token, password }` → 204. Same errors as accept. It signs that account out everywhere.

## 1. Settings: "צוות המשרד" panel (`team-panel.tsx`, added to `settings-screen.tsx`)
- A list of members: name, email, role ("מנהל/ת" for owner, "צוות" for staff), status
  ("פעיל", "ממתין להצטרפות", "פג תוקף ההזמנה", "כבוי"), "את/ה" next to `is_you`, and "אימות דו-שלבי" when `mfa_enabled`.
- Owners (`me.role === "owner"`) also get:
  - An invite form: email, name, role (default "צוות"), button "הזמנה". On success:
    if `email_sent`: "ההזמנה נשלחה ל-{email}.";
    if not: show `email_error`, then the `invite_url` with a "העתקת הקישור" button and a "שליחה בוואטסאפ" link
    (`https://wa.me/?text=` + the encoded url, `target=_blank`, `rel=noopener noreferrer`). Disable the button while sending.
  - Per row (not on their own row for turning off): "שליחת ההזמנה שוב" for `invited`/`invite_expired` (same result display),
    a role switch, and "כיבוי חשבון" / "הפעלה מחדש". Ask before turning off:
    "לכבות את החשבון של {name}? החשבון ינותק מיד, ואי אפשר יהיה להתחבר אליו עד שתפעילו אותו מחדש."
  - After any change, reload the list. Show a 409/400 `detail` beside the row.
- Staff see the list only, with "רק מנהל המשרד יכול להוסיף עובדים או לשנות הרשאות."

## 2. Office settings for staff (`office-panel.tsx`)
Profession and AI reading controls are disabled for staff, with the same sentence as above. Owners see no change.

## 3. Login page: a "שכחתי סיסמה" link under the password field, to `/forgot-password`.

## 4. `/forgot-password`
One email field and "שליחת קישור". After the call, always show the API's `detail` (it is the same for any address)
and a link back to `/login`. A 429 shows its `detail` as well.

## 5. `/join/[token]` and `/reset-password/[token]`
- On load, `POST /api/account/link { token }`. If it fails, or `purpose` is not this page's
  (`invite` for join, `reset` for reset), show the `detail` (or "הקישור כבר לא פעיל. אפשר לבקש קישור חדש.") and a link to `/login`.
- Join: title "הצטרפות ל{organization_name}", "שלום {display_name}", the email shown read-only.
  Reset: title "בחירת סיסמה חדשה", the email shown read-only.
- Password and repeat-password fields. Check in the page that they match and are at least `min_password_length`.
  Button "שמירת הסיסמה" (disabled while sending), then `invite/accept` or `password/reset`.
- Success: join "החשבון מוכן. אפשר להתחבר עכשיו."; reset "הסיסמה עודכנה. התחברו עם הסיסמה החדשה."; each with a button to `/login`.
- Both pages: `export const metadata = { referrer: "no-referrer" }` (or the equivalent in a layout), so the token never leaves in a Referer header.
  They are public: no office session, and they must not call any `/api/office/...` route.

## Checks
- `npx tsc --noEmit -p apps/web`
- `npm run build -w web`, then restart port 3000 with `next start -p 3000`. Do not touch port 8000. Do not commit.

## When done
Set the first line to `Status: done` and add an entry at the top of `docs/agents/status.md`.

## Answers
(Claude answers questions from `status.md` here.)
