"use client";

import type { CaseWorkspace, SigningLinkRead } from "@docketai/shared-types";
import { useCallback, useEffect, useState } from "react";

import { SigningQr } from "@/components/signing-qr";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { israeliMobile, mailUrl, signedMessage, whatsAppUrl } from "@/lib/dispatch";
import { dispatchFormTitle } from "@/lib/filing";
import { applyOfficeTemplate } from "@/lib/office-settings";
import { useOfficeSettings } from "@/lib/use-office-settings";
import { hebrewOfficeError } from "@/lib/hebrew";

const STORED_URL = "docket-sign-url:";

function storedUrl(caseId: string) {
  try {
    return sessionStorage.getItem(STORED_URL + caseId);
  } catch {
    return null;
  }
}

function rememberUrl(caseId: string, url: string) {
  try {
    sessionStorage.setItem(STORED_URL + caseId, url);
  } catch {
    /* Private mode can block storage. The address still shows once. */
  }
}

function forgetUrl(caseId: string) {
  try {
    sessionStorage.removeItem(STORED_URL + caseId);
  } catch {
    /* Storage may be unavailable. */
  }
}

function when(value: string) {
  return new Intl.DateTimeFormat("he-IL", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Jerusalem",
  }).format(new Date(value));
}

export function SignerLinkCard({
  caseId,
  clientName,
  phone,
  email,
  signed,
  waiting,
  verificationId,
  processKey,
  onRevoked,
  embedded = false,
}: {
  caseId: string;
  clientName: string;
  phone: string;
  email: string;
  signed: boolean;
  waiting: boolean;
  verificationId: string | null;
  processKey: string;
  onRevoked?: (workspace: CaseWorkspace) => void;
  embedded?: boolean;
}) {
  const [link, setLink] = useState<SigningLinkRead | null>(null);
  const [freshUrl, setFreshUrl] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setLink(await api.signingLink(caseId));
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setLink(null);
        return;
      }
      setNote(hebrewOfficeError(error));
    }
  }, [caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create() {
    setBusy(true);
    setNote(null);
    try {
      const created = await api.createSigningLink(caseId);
      setFreshUrl(created.url);
      rememberUrl(caseId, created.url);
      await load();
    } catch (error) {
      setNote(hebrewOfficeError(error));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!freshUrl) return;
    await navigator.clipboard.writeText(freshUrl);
    setNote("הקישור הועתק.");
  }

  async function revoke() {
    setBusy(true);
    setNote(null);
    try {
      const response = await fetch(`/api/cases/${caseId}/revoke-link`, { method: "POST" });
      if (response.status === 401) {
        window.location.assign(`/login?next=${encodeURIComponent(`/cases/${caseId}`)}`);
        return;
      }
      if (!response.ok) {
        setNote(response.status === 404 ? "אין קישור חתימה פתוח." : "לא ניתן לבטל את הקישור.");
        return;
      }
      const workspace = (await response.json()) as CaseWorkspace;
      setFreshUrl(null);
      forgetUrl(caseId);
      setLink(null);
      onRevoked?.(workspace);
    } catch {
      setNote("לא ניתן לבטל את הקישור.");
    } finally {
      setBusy(false);
    }
  }

  const reportedUrl = (() => {
    if (!link || !("url" in link)) return null;
    const value = (link as { url?: unknown }).url;
    return typeof value === "string" && value ? value : null;
  })();
  const signingUrl = reportedUrl || freshUrl || storedUrl(caseId);
  const settings = useOfficeSettings();
  const mobile = israeliMobile(phone);
  const formTitle = dispatchFormTitle(processKey);
  const readyText = signingUrl
    ? applyOfficeTemplate(settings.signingTemplate, { client_name: clientName, process_title: formTitle, link: signingUrl }, settings)
    : "";
  const signedText = verificationId ? signedMessage(clientName, verificationId, signingUrl) : "";
  const open = link?.state === "open" && Boolean(signingUrl);

  return (
    <section className={embedded ? "border-t border-ink/10 pt-4" : "rounded-lg border border-tide bg-white shadow-card"}>
      <div className={embedded ? "" : "border-b border-line px-4 py-4"}>
        <h3 className={embedded ? "text-sm font-bold text-tide" : "font-serif text-2xl"}>שליחה לאישור וחתימת לקוח</h3>
        <p className="mt-1 text-sm leading-6 text-ink">הלקוח בודק את הפרטים האישיים וחותם. הוא לא ממלא את הטופס.</p>
      </div>
      <div className={embedded ? "mt-3 space-y-3 text-sm" : "space-y-3 px-4 py-4 text-sm"}>
        {link ? (
          <p>
            {link.state === "open"
              ? `פתוח עד ${when(link.expires_at)}`
              : link.state === "completed"
                ? "הלקוח חתם."
                : "הקישור כבר לא פעיל."}
          </p>
        ) : (
          <p className="text-mist">עדיין אין קישור.</p>
        )}
        {freshUrl ? (
          <div className="space-y-2">
            <p className="text-xs text-mist">הכתובת מוצגת פעם אחת.</p>
            <p dir="auto" className="break-all rounded-md border border-line bg-white px-3 py-2">
              {freshUrl}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={() => void copy()}>
                העתק קישור
              </Button>
              <Button asChild>
                <a href={freshUrl} target="_blank" rel="noopener noreferrer">
                  פתח פורטל חתימה בטאב חדש ↗
                </a>
              </Button>
            </div>
          </div>
        ) : null}
        {open && signingUrl ? (
          <div className="flex flex-wrap items-start gap-4">
            <div className="min-w-[12rem] flex-1 space-y-2">
            {mobile ? (
              <Button asChild className="w-full">
                <a href={whatsAppUrl(mobile, readyText)} target="_blank" rel="noopener noreferrer">
                  שליחה ב-WhatsApp ללקוח
                </a>
              </Button>
            ) : (
              <Button type="button" className="w-full" disabled>
                שליחה ב-WhatsApp ללקוח
              </Button>
            )}
            <Button asChild variant="outline" className="w-full">
              <a href={mailUrl(email, `${formTitle} מוכן לבדיקה ולחתימה`, readyText)}>שליחה באימייל</a>
            </Button>
            {mobile ? null : <p className="text-clay">אין מספר נייד ישראלי בתיק, ולכן אי אפשר לפתוח את וואטסאפ.</p>}
            </div>
            <SigningQr value={signingUrl} />
          </div>
        ) : null}
        {signed && signedText ? (
          mobile ? (
            <Button asChild className="w-full">
              <a href={whatsAppUrl(mobile, signedText)} target="_blank" rel="noopener noreferrer">
                שלח אישור חתימה ב-WhatsApp
              </a>
            </Button>
          ) : (
            <Button type="button" className="w-full" disabled>
              שלח אישור חתימה ב-WhatsApp
            </Button>
          )
        ) : null}
        {note ? <p className="text-clay">{note}</p> : null}
        <div className="flex flex-wrap gap-2">
          <Button type="button" className="w-full" onClick={() => void create()} disabled={busy}>
            {freshUrl ? "קישור חדש" : "יצירת קישור לחתימה"}
          </Button>
          {link?.state === "open" || waiting ? (
            <Button type="button" variant="danger" onClick={() => void revoke()} disabled={busy}>
              בטל קישור חתימה והחזר לעריכה
            </Button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
