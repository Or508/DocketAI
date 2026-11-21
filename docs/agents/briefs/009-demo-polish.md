Status: done
For: cursor

# Brief 009: small fixes from Claude's live run of the demo

Claude ran the whole demo on port 3000 against port 8000 (`DEMO_MODE=true`): /demo → law office → דנה כהן's case at 100% →
signing link → signed on a 375px phone → certificate. Briefs 007 and 008 work. Claude also changed the API side
(see the newest Claude entry in `status.md`): each scenario now has one case ready for a signer, named דנה כהן to match the
sample documents, and the demo office's phone now comes back as `054-7302757`.

Do not edit: `apps/api/**`, `apps/web/app/api/**`, `apps/web/app/(legal)/**`.
Files: `apps/web/app/demo/page.tsx` (and its components), `apps/web/components/signed-review.tsx`, `apps/web/components/readiness-shield.tsx`,
`apps/web/components/integrity-panel.tsx`, and the `page.tsx`/`layout.tsx` of `app/sign/[token]`, `app/upload/[token]`, `app/login`, `app/demo` for titles.

## 1. The demo page shows the raw number
`/demo` shows "972547302757" as the link text. Show "דברו איתנו בוואטסאפ: 054-7302757" with the link
`https://wa.me/972547302757?text=` + encodeURIComponent("היי, ראיתי את הדמו של DocFlow ואשמח לשמוע עוד"). Use the same text on the demo banner's link.
Under the three steps add: "מה תראו: תיק אחד מוכן לחתימה, ושניים שעוד מחכים למסמכים מהלקוח."

## 2. The signed screen lists Form 101 items for every process
After signing a real estate deal, the client sees "✓ שם מלא ✓ מספר זהות ✓ כתובת ✓ טלפון נייד ✓ פרטי בנק" and "10 מתוך 10 שדות מולאו".
Those are Form 101 fields. Build the list from the process's own fields (`view.process.required_fields` with `FIELD_LABEL`/`label_he`, as step 1 does)
and count those; or, if that list is not available there, drop the item list and keep only "כל הפרטים מולאו + חתימה דיגיטלית הוטבעה".
Check the same component on the office side (`signed-review.tsx`, `readiness-shield.tsx`).

## 3. Page titles
Every page's browser title is "ארון תיוק ובקרת מסמכים". Screen readers and tabs read it first. Set `metadata.title`:
sign → "חתימה על מסמך — DocFlow", upload → "העלאת מסמכים — DocFlow", login → "כניסה למשרד — DocFlow", demo → "דמו חי — DocFlow".

## Checks
- `npx tsc --noEmit -p apps/web`; `npm run build -w web`; restart port 3000 with `next start -p 3000`. Do not touch port 8000. Do not commit.
- With port 8000 as it is now (demo on): start a demo, sign דנה כהן's real estate case on a phone width, and confirm the signed screen lists real estate details.
  Delete nothing by hand: demo offices expire on their own.

## When done
Set the first line to `Status: done` and add an entry at the top of `docs/agents/status.md`.

## Answers
(Claude answers questions from `status.md` here.)
