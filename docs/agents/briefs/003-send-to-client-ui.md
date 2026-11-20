Status: done
For: cursor

# Brief 003: "שליחה ללקוח" — send the link by email or WhatsApp, and show the reminders

Do not edit: `apps/api/**`, `apps/web/app/api/**` (the office proxy already allows these routes), and everything listed in brief 001.

Claude built the API (all office routes, through the usual office proxy `/api/office/...`):

| Method and path | Body | Returns |
|---|---|---|
| `POST /cases/{id}/outreach/send` | `{ purpose: "intake" \| "signing", channel: "email" \| "whatsapp", email?: string, phone?: string, reminders: boolean }` | `OutreachSent` (201) |
| `GET /cases/{id}/outreach` | – | `OutreachState` |
| `PUT /cases/{id}/outreach/reminders` | `{ enabled: boolean }` | `OutreachState` |
| `POST /cases/{id}/outreach/remind` | – | `OutreachSent` (a reminder now, with the same link) |
| `GET /outreach/due` | – | `DueReminder[]` (WhatsApp reminders whose time has come) |

```ts
type OutreachMessage = { id: string; purpose: "intake" | "signing"; kind: "first" | "reminder";
  channel: "email" | "whatsapp"; recipient: string; status: "sent" | "failed" | "handed_to_office";
  error: string | null; created_at: string };
type OutreachSent = { message: OutreachMessage; url: string; whatsapp_url: string | null; next_reminder_at: string | null };
type OutreachState = { email: string | null; phone: string | null; phone_display: string | null;
  purpose: "intake" | "signing" | null; channel: "email" | "whatsapp" | null; reminders_enabled: boolean;
  reminders_sent: number; next_reminder_at: string | null; stopped_reason: string | null;
  email_available: boolean; messages: OutreachMessage[] };
type DueReminder = { case_id: string; case_name: string; client_name: string | null;
  purpose: "intake" | "signing"; phone_display: string; due_at: string };
```

How it behaves (no need to re-check in the UI, the API enforces it):
- Every send creates a **new** link and the case's previous link of that kind stops working, exactly like the existing link buttons.
- Email goes out at once. WhatsApp returns `whatsapp_url`: opening it shows WhatsApp with the client and the message ready; the office presses send in WhatsApp.
- Reminders: by default after 2 and 5 days, 09:00–20:00 Israel time, never on Saturday. Email reminders go out by themselves.
  WhatsApp reminders appear in `GET /outreach/due`; the office sends each one with `POST .../remind` and opens the returned `whatsapp_url`.
- Reminders stop by themselves: `stopped_reason` is `done` (client handed in everything / signed), `case_signed`, `link_replaced`,
  `link_closed` (expired), `turned_off`, or `schedule_done`.
- Errors come back with a Hebrew `detail` (bad email/phone 400, email not set up 409, too many messages today 429). Show it as is.

## 1. "שליחה ללקוח" in the case workspace (`apps/web/app/cases/**` / its components)
A button near the existing link actions that opens a small dialog:
- **מה שולחים:** "בקשת מסמכים" (`intake`) or "טופס לחתימה" (`signing`). Default: `signing` when the case is ready to sign, otherwise `intake`.
- **איך:** "אימייל" / "וואטסאפ". If `email_available` is false, disable email with the note "שליחת אימייל לא הוגדרה בשרת".
- Email or mobile field, prefilled from `GET .../outreach` (`email`, `phone_display`).
- Checkbox "לשלוח תזכורות אוטומטיות" (on by default).
- On send: for WhatsApp, `window.open(whatsapp_url, "_blank", "noopener,noreferrer")` right in the click handler (so the browser does not block it).
  Then a short confirmation: "נשלח באימייל ל-…" or "וואטסאפ נפתח עם ההודעה. לחצו שם על שליחה.", with a copy-link button for `url`.

## 2. Reminder status on the case
A small block (near the timeline is fine): who it went to and how, "תזכורת הבאה: <date, Israel time>" or why reminders stopped
(Hebrew labels: done → "הלקוח השלים", case_signed → "התיק נחתם", link_replaced → "נוצר קישור חדש", link_closed → "הקישור פג",
turned_off → "התזכורות כובו", schedule_done → "כל התזכורות נשלחו"), a toggle for `PUT .../reminders`, a "לשלוח תזכורת עכשיו" button
(`POST .../remind`; open `whatsapp_url` when present), and the list of `messages` (kind, channel, recipient, status, time; show `error` on failed ones).

## 3. WhatsApp reminders waiting, on the dashboard (`components/dashboard.tsx`)
If `GET /outreach/due` returns anything, a quiet card "תזכורות לשליחה בוואטסאפ (N)" listing case name, client, phone, purpose,
with a button per row: `POST /cases/{id}/outreach/remind`, open its `whatsapp_url`, then refresh the list.

## Checks
- `npx tsc --noEmit -p apps/web`
- Rebuild and restart port 3000.
- With the API on port 8000 and `EMAIL_BACKEND=outbox` (the default), an email send writes an `.eml` file under `apps/api/data/outbox/`.

## When done
Set the first line to `Status: done` and add an entry at the top of `docs/agents/status.md`.

## Answers
(Claude answers questions from `status.md` here.)
