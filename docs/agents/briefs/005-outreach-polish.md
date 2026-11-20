Status: done
For: cursor

# Brief 005: two one-line fixes after Claude's review of brief 004

Do not edit: `apps/api/**`, `apps/web/app/api/**`, and everything listed in brief 001.
Files: `apps/web/components/dashboard.tsx`, `apps/web/components/client-outreach.tsx` only.

Brief 004 is good: the fallback link, no double send, and disabled buttons all match the brief; `tsc` passes.

## 1. Dashboard: the WhatsApp line says the same thing twice
`DueWhatsAppReminders` shows "<case>: וואטסאפ נפתח. לא נפתח? אם וואטסאפ לא נפתח, לחצו על פתיחת וואטסאפ."
(brief 004 asked for both sentences; that was Claude's mistake). Make it:
`{held.caseName}: אם וואטסאפ לא נפתח, לחצו על פתיחת וואטסאפ.` (reuse the `WHATSAPP_FALLBACK` text from client-outreach.tsx; export it).

## 2. Case reminder block: a failed refresh is not a failed reminder
In `OutreachStatus.remindNow`, if `remindOutreach` succeeds but the following `load()` fails, the block says "הפעולה נכשלה."
Catch `load()` separately, as the dashboard now does, and show "התזכורת נשלחה, אבל הסטטוס לא התעדכן."

## Checks
- `npx tsc --noEmit -p apps/web`
- Rebuild and restart port 3000. Do not touch port 8000. Do not commit.

## When done
Set the first line to `Status: done` and add an entry at the top of `docs/agents/status.md`.

## Answers
(Claude answers questions from `status.md` here.)
