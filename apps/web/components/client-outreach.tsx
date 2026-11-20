"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  ApiError,
  api,
  type OutreachChannel,
  type OutreachMessage,
  type OutreachPurpose,
  type OutreachState,
} from "@/lib/api";

const PURPOSE_LABEL: Record<OutreachPurpose, string> = {
  intake: "בקשת מסמכים",
  signing: "טופס לחתימה",
};

const CHANNEL_LABEL: Record<OutreachChannel, string> = {
  email: "אימייל",
  whatsapp: "וואטסאפ",
};

const KIND_LABEL: Record<OutreachMessage["kind"], string> = {
  first: "שליחה",
  reminder: "תזכורת",
};

const STATUS_LABEL: Record<OutreachMessage["status"], string> = {
  sent: "נשלח",
  failed: "נכשל",
  handed_to_office: "נמסר למשרד",
};

const STOPPED_LABEL: Record<string, string> = {
  done: "הלקוח השלים",
  case_signed: "התיק נחתם",
  link_replaced: "נוצר קישור חדש",
  link_closed: "הקישור פג",
  turned_off: "התזכורות כובו",
  schedule_done: "כל התזכורות נשלחו",
};

function israelTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("he-IL", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Jerusalem",
  }).format(date);
}

function outreachError(reason: unknown) {
  if (reason instanceof ApiError && reason.message.trim()) return reason.message;
  return "הפעולה נכשלה.";
}

export const WHATSAPP_FALLBACK = "אם וואטסאפ לא נפתח, לחצו על פתיחת וואטסאפ.";

export function WhatsAppOpenLink({ href }: { href: string }) {
  return (
    <Button asChild variant="outline" size="sm">
      <a href={href} target="_blank" rel="noopener noreferrer">
        פתיחת וואטסאפ
      </a>
    </Button>
  );
}

export function SendToClientButton({
  caseId,
  readyToSign,
  onSent,
}: {
  caseId: string;
  readyToSign: boolean;
  onSent?: () => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button type="button" onClick={() => setOpen(true)}>
        שליחה ללקוח
      </Button>
      <SendToClientDialog
        caseId={caseId}
        readyToSign={readyToSign}
        open={open}
        onOpenChange={setOpen}
        onSent={onSent}
      />
    </>
  );
}

function SendToClientDialog({
  caseId,
  readyToSign,
  open,
  onOpenChange,
  onSent,
}: {
  caseId: string;
  readyToSign: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSent?: () => void;
}) {
  const [purpose, setPurpose] = useState<OutreachPurpose>(readyToSign ? "signing" : "intake");
  const [channel, setChannel] = useState<OutreachChannel>("email");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [reminders, setReminders] = useState(true);
  const [emailAvailable, setEmailAvailable] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentUrl, setSentUrl] = useState<string | null>(null);
  const [sentNote, setSentNote] = useState<{
    channel: OutreachChannel;
    recipient: string;
    whatsappUrl: string | null;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setPurpose(readyToSign ? "signing" : "intake");
    setReminders(true);
    setError(null);
    setSentUrl(null);
    setSentNote(null);
    setCopied(false);
    setLoading(true);
    api
      .outreach(caseId)
      .then((state) => {
        if (cancelled) return;
        setEmail(state.email ?? "");
        setPhone(state.phone_display ?? "");
        setEmailAvailable(state.email_available);
        setChannel(state.email_available ? "email" : "whatsapp");
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setEmailAvailable(null);
        setError(outreachError(reason));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, caseId, readyToSign]);

  async function send() {
    if (sentNote) return;
    setBusy(true);
    setError(null);
    setSentUrl(null);
    setCopied(false);
    const chosen = channel;
    try {
      const sent = await api.sendOutreach(caseId, {
        purpose,
        channel: chosen,
        reminders,
        email: chosen === "email" ? email.trim() : undefined,
        phone: chosen === "whatsapp" ? phone.trim() : undefined,
      });
      if (chosen === "whatsapp" && sent.whatsapp_url) {
        window.open(sent.whatsapp_url, "_blank", "noopener,noreferrer");
      }
      setSentUrl(sent.url);
      setSentNote({ channel: chosen, recipient: sent.message.recipient, whatsappUrl: sent.whatsapp_url });
      onSent?.();
    } catch (reason) {
      setError(outreachError(reason));
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    if (!sentUrl) return;
    try {
      await navigator.clipboard.writeText(sentUrl);
      setCopied(true);
    } catch {
      setCopied(false);
      setError("לא ניתן להעתיק את הקישור.");
    }
  }

  const emailDisabled = emailAvailable === false;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(92vw,32rem)]" aria-describedby="send-to-client-lead">
        <DialogTitle>שליחה ללקוח</DialogTitle>
        <p id="send-to-client-lead" className="mt-1 text-sm text-mist">
          נשלח קישור חדש. קישור קודם מאותו סוג יפסיק לעבוד.
        </p>
        <form
          className="mt-5 space-y-5"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (sentNote) return;
            void send();
          }}
        >
          <fieldset className="space-y-2">
            <legend className="text-sm font-semibold text-ink">מה שולחים</legend>
            <div className="flex flex-wrap gap-2">
              <Choice
                name="outreach-purpose"
                checked={purpose === "intake"}
                onChange={() => setPurpose("intake")}
                label="בקשת מסמכים"
              />
              <Choice
                name="outreach-purpose"
                checked={purpose === "signing"}
                onChange={() => setPurpose("signing")}
                label="טופס לחתימה"
              />
            </div>
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-sm font-semibold text-ink">איך</legend>
            <div className="flex flex-wrap gap-2">
              <Choice
                name="outreach-channel"
                checked={channel === "email"}
                disabled={emailDisabled}
                onChange={() => setChannel("email")}
                label="אימייל"
              />
              <Choice
                name="outreach-channel"
                checked={channel === "whatsapp"}
                onChange={() => setChannel("whatsapp")}
                label="וואטסאפ"
              />
            </div>
            {emailDisabled ? <p className="text-sm text-clay">שליחת אימייל לא הוגדרה בשרת</p> : null}
          </fieldset>

          {channel === "email" ? (
            <label className="block text-sm font-semibold text-ink" htmlFor="outreach-email">
              אימייל
              <Input
                id="outreach-email"
                className="mt-1.5"
                dir="ltr"
                inputMode="email"
                autoComplete="email"
                value={email}
                disabled={emailDisabled || loading}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
          ) : (
            <label className="block text-sm font-semibold text-ink" htmlFor="outreach-phone">
              נייד
              <Input
                id="outreach-phone"
                className="mt-1.5"
                dir="ltr"
                inputMode="tel"
                autoComplete="tel"
                value={phone}
                disabled={loading}
                onChange={(event) => setPhone(event.target.value)}
              />
            </label>
          )}

          <label className="flex items-start gap-3 rounded-md bg-paper p-3 text-sm">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-[#0e4f49]"
              checked={reminders}
              onChange={(event) => setReminders(event.target.checked)}
            />
            <span className="font-semibold text-ink">לשלוח תזכורות אוטומטיות</span>
          </label>

          {loading ? <p className="text-sm text-mist">טוען פרטי קשר…</p> : null}
          {sentNote ? (
            <div className="space-y-2 rounded-md border border-line bg-[#f4faf6] px-3 py-3">
              <p className="text-sm font-semibold text-moss">
                {sentNote.channel === "email" ? (
                  <>
                    נשלח באימייל ל-<span dir="ltr">{sentNote.recipient}</span>
                  </>
                ) : (
                  WHATSAPP_FALLBACK
                )}
              </p>
              <div className="flex flex-wrap gap-2">
                {sentNote.whatsappUrl ? <WhatsAppOpenLink href={sentNote.whatsappUrl} /> : null}
                <Button type="button" variant="outline" onClick={() => void copyLink()}>
                  {copied ? "הקישור הועתק" : "העתק קישור"}
                </Button>
              </div>
            </div>
          ) : null}
          {error ? (
            <p className="text-sm font-medium text-clay" role="alert">
              {error}
            </p>
          ) : null}

          <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-4">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              סגירה
            </Button>
            {sentNote ? null : (
              <Button type="submit" disabled={busy || loading || (channel === "email" && emailDisabled)}>
                {busy ? "שולח…" : "שליחה"}
              </Button>
            )}
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Choice({
  name,
  checked,
  disabled = false,
  onChange,
  label,
}: {
  name: string;
  checked: boolean;
  disabled?: boolean;
  onChange: () => void;
  label: string;
}) {
  return (
    <label
      className={`inline-flex h-10 items-center gap-2 rounded-md border px-3 text-sm font-semibold ${
        disabled
          ? "cursor-not-allowed border-line text-mist opacity-60"
          : checked
            ? "border-tide bg-mint text-tide"
            : "border-line bg-white text-ink"
      }`}
    >
      <input type="radio" name={name} className="accent-[#0e4f49]" checked={checked} disabled={disabled} onChange={onChange} />
      {label}
    </label>
  );
}

export function OutreachStatus({ caseId, refreshKey = 0 }: { caseId: string; refreshKey?: number }) {
  const [state, setState] = useState<OutreachState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [openedWhatsApp, setOpenedWhatsApp] = useState<string | null>(null);
  const [busy, setBusy] = useState<"toggle" | "remind" | null>(null);

  const load = useCallback(async () => {
    setState(await api.outreach(caseId));
  }, [caseId]);

  useEffect(() => {
    let cancelled = false;
    api
      .outreach(caseId)
      .then((next) => {
        if (!cancelled) setState(next);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(outreachError(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, refreshKey]);

  async function toggle() {
    if (!state) return;
    setBusy("toggle");
    setError(null);
    setNotice(null);
    try {
      setState(await api.setOutreachReminders(caseId, !state.reminders_enabled));
    } catch (reason) {
      setError(outreachError(reason));
    } finally {
      setBusy(null);
    }
  }

  async function remindNow() {
    setBusy("remind");
    setError(null);
    setNotice(null);
    setOpenedWhatsApp(null);
    try {
      const sent = await api.remindOutreach(caseId);
      if (sent.whatsapp_url) window.open(sent.whatsapp_url, "_blank", "noopener,noreferrer");
      setOpenedWhatsApp(sent.whatsapp_url);
      if (!sent.whatsapp_url) setNotice("התזכורת נשלחה.");
    } catch (reason) {
      setError(outreachError(reason));
      setBusy(null);
      return;
    }
    try {
      await load();
    } catch {
      setNotice("התזכורת נשלחה, אבל הסטטוס לא התעדכן.");
    } finally {
      setBusy(null);
    }
  }

  const latest = state?.messages[0];
  const recipient = latest?.recipient ?? (state?.channel === "email" ? state.email : state?.phone_display);
  const nothingSent = !state?.purpose;

  return (
    <section className="rounded-lg border border-ink/15 bg-white p-4 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-serif text-xl">סטטוס תזכורות</h2>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-ink">תזכורות</span>
          <button
          type="button"
          role="switch"
          aria-checked={Boolean(state?.reminders_enabled)}
          aria-label="תזכורות אוטומטיות"
          disabled={nothingSent || busy !== null}
          onClick={() => void toggle()}
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-40 ${
            state?.reminders_enabled ? "bg-tide" : "bg-ink/20"
          }`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow ${
              state?.reminders_enabled ? "end-0.5" : "start-0.5"
            }`}
          />
        </button>
        </div>
      </div>

      {state ? (
        <div className="mt-3 space-y-2 text-sm">
          <p className="text-ink">
            {state.purpose && state.channel ? (
              <>
                {PURPOSE_LABEL[state.purpose]} · {CHANNEL_LABEL[state.channel]}
                {recipient ? (
                  <>
                    {" · "}
                    <span dir="ltr">{recipient}</span>
                  </>
                ) : null}
              </>
            ) : (
              "עדיין לא נשלח קישור ללקוח."
            )}
          </p>
          {state.next_reminder_at ? (
            <p className="font-semibold text-ink">תזכורת הבאה: {israelTime(state.next_reminder_at)}</p>
          ) : state.stopped_reason ? (
            <p className="font-semibold text-ink">{STOPPED_LABEL[state.stopped_reason] ?? state.stopped_reason}</p>
          ) : null}
        </div>
      ) : error ? null : (
        <p className="mt-3 text-sm text-mist">טוען…</p>
      )}

      <div className="mt-4">
        <Button type="button" variant="outline" disabled={nothingSent || busy !== null} onClick={() => void remindNow()}>
          {busy === "remind" ? "שולח…" : "לשלוח תזכורת עכשיו"}
        </Button>
      </div>

      {openedWhatsApp ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold text-moss">{WHATSAPP_FALLBACK}</p>
          <WhatsAppOpenLink href={openedWhatsApp} />
        </div>
      ) : null}
      {notice ? <p className="mt-3 text-sm font-semibold text-moss">{notice}</p> : null}
      {error ? (
        <p className="mt-3 text-sm font-medium text-clay" role="alert">
          {error}
        </p>
      ) : null}

      {state && state.messages.length > 0 ? (
        <ul className="mt-4 max-h-72 space-y-2 overflow-y-auto border-t border-ink/10 pt-3">
          {state.messages.map((message) => (
            <li key={message.id} className="rounded-md border border-line px-3 py-2 text-sm">
              <p className="text-ink">
                {KIND_LABEL[message.kind]} · {CHANNEL_LABEL[message.channel]} ·{" "}
                <span dir="ltr">{message.recipient}</span> · {STATUS_LABEL[message.status]} · {israelTime(message.created_at)}
              </p>
              {message.status === "failed" && message.error ? (
                <p className="mt-1 text-clay">{message.error}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
