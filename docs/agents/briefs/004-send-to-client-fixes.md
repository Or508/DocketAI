Status: done
For: cursor

# Brief 004: small fixes to "שליחה ללקוח" (after Claude's review of brief 003)

Do not edit: `apps/api/**`, `apps/web/app/api/**`, and everything listed in brief 001.
Files: `apps/web/components/client-outreach.tsx`, `apps/web/components/dashboard.tsx` only.

Brief 003 is good: types match the API, labels are right, `tsc` passes, the API tests (16) pass.
Four things to fix:

## 1. WhatsApp can be blocked by the browser: always show a link too
`window.open` runs after `await api.sendOutreach(...)`. Chrome allows that for about 5 seconds after the click;
Safari and iPhone often block it. When it is blocked, the office sees "וואטסאפ נפתח…" but nothing opened,
and in the dashboard the row disappears after the refresh, so there is no way back to that message.
- Keep the `window.open` call, but also show a real link next to the confirmation:
  `<a href={whatsapp_url} target="_blank" rel="noopener noreferrer">פתיחת וואטסאפ</a>` (styled as a button).
- Do this in all three places: the dialog, the "לשלוח תזכורת עכשיו" button in `OutreachStatus`, and the dashboard card.
- In the dashboard card, keep the last sent reminder visible after the refresh (a short line
  "<case name>: וואטסאפ נפתח. לא נפתח? <link>") until the office dismisses it or reloads the page.
- Change the wording to "אם וואטסאפ לא נפתח, לחצו על פתיחת וואטסאפ." next to the link.
- Confirmed live on 2026-11-20: a WhatsApp send from the dialog was blocked as a popup, and the dialog still said
  "וואטסאפ נפתח עם ההודעה" with no way to open it.

## 2. The dialog must not send twice by accident
After a send succeeds, the "שליחה" button stays active. A second click creates another new link and the link
the client just got stops working. After success, hide the "שליחה" button (leave "סגירה" and the copy-link button),
or change it to "שליחה מחדש" behind a one-line warning "הקישור שנשלח קודם יפסיק לעבוד."

## 3. Reminder buttons before anything was sent
In `OutreachStatus`, when `state.purpose` is `null` (nothing sent yet), disable "לשלוח תזכורת עכשיו" and the
reminders switch. Today they are clickable and only return an error from the API.

## 4. Dashboard: a failed refresh is not a failed send
In `DueWhatsAppReminders.send`, if `remindOutreach` succeeded but the following `load()` fails, the card says
"השליחה נכשלה." Catch the refresh separately and show "התזכורת נשלחה, אבל הרשימה לא התעדכנה." instead.

## Checks
- `npx tsc --noEmit -p apps/web`
- Rebuild and restart port 3000.
- Do not commit.

## When done
Set the first line to `Status: done` and add an entry at the top of `docs/agents/status.md`.

## Answers
(Claude answers questions from `status.md` here.)
