Status: done
For: cursor

# Brief 007: the client understands who sent the link and what happens next; accessibility fixes; legal footer

Goal from the owner: the office's client (who uploads documents or signs) must understand at every moment who sent
the link, what to do now, and what happens next; the screens must be accessible (Israeli standard IS 5568 / WCAG 2.0 AA).
The API side is done (Claude, 2026-11-21) and live on port 8000.

Do not edit: `apps/api/**`, `apps/web/app/api/**`, `apps/web/app/(legal)/**`, `packages/shared-types/**`, `apps/web/middleware.ts`.
Files: `apps/web/components/portal-view.tsx`, `apps/web/app/upload/[token]/upload-screen.tsx`, `apps/web/app/sign/[token]/layout.tsx`,
`apps/web/app/verify/verify-screen.tsx`, `apps/web/app/login/page.tsx`, `apps/web/app/settings/office-panel.tsx`,
`apps/web/app/settings/team-panel.tsx`, `apps/web/lib/api.ts`, `apps/web/lib/hebrew.ts`.

Write every new sentence gender-neutral (plural "אתם" forms: "עברו", "פנו", "תקבלו"), as the upload page already does.

## What the API now gives
- `PortalView.office` and the intake status's `office`: `{ name: string; phone: string | null; email: string | null } | null`
  (`OfficeContact` is exported from `@docketai/shared-types`; add `office` to the local `Intake` type in upload-screen.tsx).
- `GET organization` now also has `contact_phone`, `contact_email` (string or null).
- `PUT organization/contact` `{ phone, email }` → the organization. Owner only. Blank removes a value. 400 Hebrew `detail`
  (`bad_phone`, `bad_email`) — show it as is.
- Legal pages exist: `/privacy`, `/terms`, `/accessibility`, and a footer component:
  `import { LegalFooter } from "@/app/(legal)/legal-footer";` (props: `frame`, the same width classes as `PublicBrand`).

## 1. Office contact in settings (`office-panel.tsx`, `lib/api.ts`)
A "פרטי התקשרות ללקוחות" block: phone and email fields, "שמירה", helper text
"הלקוחות יראו את הפרטים האלה בעמודי ההעלאה והחתימה, כדי לדעת למי לפנות." Owners edit; staff see it disabled with the
existing "רק מנהל המשרד יכול לשנות את זה.". Add `contact_phone`/`contact_email` to the organization type and `updateContact` to `api`.

## 2. Who sent this, on both client pages (`portal-view.tsx`, `upload-screen.tsx`)
- Under the title: "נשלח אליכם מ{office.name}" (skip when `office` is null).
- A small "לשאלות" line with the phone as a `tel:` link and the email as a `mailto:` link, whichever exist.
- Show it wherever the page has a loaded view (including the upload page's "all received" box and the sign page's error notices).
  A dead link (404/410) returns no view, so those states have no office to show: keep their text as is.

## 3. Signing page clarity (`portal-view.tsx`)
1. Two progress bars today (a 3-item `<ol>` and a 4-item `<nav>` of `<p>`s) say different things. Keep one:
   `<ol aria-label="שלבי החתימה">` with the 4 `STEP_LABELS`, `aria-current="step"` on the current one, and above it the text
   "שלב {n} מתוך 4". Remove the other.
2. Under the title, one intro sentence on step 1: "בדקו את הפרטים, צפו בטופס, וחתמו. זה לוקח כמה דקות, ואפשר לחזור אחורה בכל שלב."
3. When the form is not ready (`!ready`), under the disabled button: "המשרד עוד משלים את הטופס. כשיהיה מוכן לחתימה תקבלו הודעה."
4. When the step changes, move focus to the new section's `<h2>` (`tabIndex={-1}` + a ref), so a screen reader hears where it is.
5. `ClientUpload`: label "מגירה" → "סוג המסמך". The file `<label>` holding the `sr-only` input needs a visible focus ring
   (`focus-within:ring-2 focus-within:ring-tide focus-within:ring-offset-2`).
6. Texts: `REVIEW_AGAIN` → "המשרד עדכן פרט בטופס בהסכמתכם. עברו על הטופס המעודכן לפני החתימה."
   Revoked: `<h1>` "הקישור בוטל" and a `<p>` "המשרד ביטל את קישור החתימה כדי לעדכן פרטים. פנו למשרד לקבלת קישור חדש."
   Inactive: `<h1>` "הקישור הזה כבר לא פעיל" and a `<p>` "ייתכן שהטופס כבר נחתם או שתוקף הקישור פג. לקבלת קישור חדש פנו למשרד."
   Loading `<p>`: add `role="status"`.

## 4. Upload page: what happens next (`upload-screen.tsx`)
In the "כל המסמכים התקבלו" box, after the existing text: "מה הלאה: המשרד יבדוק את המסמכים. אם יידרשו פרטים נוספים או חתימה, תקבלו הודעה."

## 5. Messages (`lib/hebrew.ts`)
- `/already used|no longer active|no open signing link|no signing link/` → "הקישור כבר לא פעיל. לקבלת קישור חדש פנו למשרד."
  (today "This link was already used." falls to the 409 text "אי אפשר להמשיך כל עוד התיק לא מוכן לחתימה", which is wrong).
- `/signed copy is not available/` → "העותק החתום עדיין לא זמין. נסו שוב בעוד רגע."
- The form-changed text: same new `REVIEW_AGAIN` wording as above.
- The last fallback "הפעולה נכשלה." → "הפעולה לא הצליחה. נסו שוב, ואם זה חוזר פנו למשרד."

## 6. Footer on every public page
Add `<LegalFooter />` at the bottom of: the sign page (layout), the upload page, the verify page, and the login page.

## 7. Two fixes from Claude's live check of brief 006 (`team-panel.tsx`)
- A fast double click on "הזמנה" sent two requests (the second showed "העובד כבר במשרד…"). Guard `invite`, `resend`,
  `changeRole` and `setActive` with a `useRef` flag set before the first `await`, not only `disabled={sending}`.
- An owner who changes their own role to "צוות" keeps the owner controls until reload: after a successful change of the
  `is_you` row, reload `api.me()` and update `owner`.

## Checks
- `npx tsc --noEmit -p apps/web`
- Keyboard only (no mouse) on `/upload/<token>` and `/sign/<token>` with a real link: every control reachable with Tab in a sensible
  order and with a visible focus. Then the same pages at 375px width with browser zoom 200%: nothing cut, no sideways scroll.
  Write the result in `status.md` (pass, or what failed) — Claude updates `/accessibility` from it.
- `npm run build -w web`, then restart port 3000 with `next start -p 3000`. Do not touch port 8000. Do not commit.

## When done
Set the first line to `Status: done` and add an entry at the top of `docs/agents/status.md`.

## Answers
(Claude answers questions from `status.md` here.)
