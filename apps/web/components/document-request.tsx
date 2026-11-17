"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { israeliMobile, whatsAppUrl } from "@/lib/dispatch";
import { applyOfficeTemplate } from "@/lib/office-settings";
import { useOfficeSettings } from "@/lib/use-office-settings";

export function DocumentRequest({
  caseId,
  clientName,
  phone,
  processTitle,
  embedded = false,
}: {
  caseId: string;
  clientName: string;
  phone: string;
  processTitle: string;
  embedded?: boolean;
}) {
  const settings = useOfficeSettings();
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mobile = israeliMobile(phone);

  async function createLink() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`/api/cases/${caseId}/intake-link`, { method: "POST" });
      if (response.status === 401) {
        window.location.assign(`/login?next=${encodeURIComponent(`/cases/${caseId}`)}`);
        return;
      }
      if (!response.ok) {
        setError(response.status === 502 ? "לא ניתן להגיע לשירות המשרד." : "לא ניתן ליצור קישור העלאה.");
        return;
      }
      const link = uploadLink(await response.json());
      if (!link) {
        setError("הקישור לא חזר מהמשרד.");
        return;
      }
      setUrl(link);
      setNotice("נוצר קישור להעלאת מסמכים.");
    } catch {
      setError("לא ניתן ליצור קישור העלאה.");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!url || !navigator.clipboard) return;
    await navigator.clipboard.writeText(url);
    setNotice("הקישור הועתק.");
  }

  const message = url
    ? applyOfficeTemplate(settings.intakeTemplate, { client_name: clientName, process_title: processTitle, link: url }, settings)
    : "";

  return (
    <section className={embedded ? "border-t border-ink/10 pt-4" : "rounded-lg border border-ink/15 bg-white p-5 shadow-card"}>
      <h3 className={embedded ? "text-sm font-bold text-tide" : "font-serif text-2xl"}>בקש מסמכים מהלקוח (קישור העלאה מהנייד)</h3>
      <p className="mt-1 text-sm text-ink">שולחים ללקוח קישור להעלאת תעודת זהות, ארנונה או אישור בנק ישירות לתיק.</p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button type="button" disabled={busy} onClick={() => void createLink()}>
          {busy ? "יוצרים קישור…" : url ? "קישור העלאה חדש" : "בקש מסמכים מהלקוח (קישור העלאה מהנייד)"}
        </Button>
        {url ? (
          <Button type="button" variant="outline" onClick={() => void copy()}>
            העתק קישור העלאה
          </Button>
        ) : null}
        {url && mobile ? (
          <Button asChild variant="outline">
            <a href={whatsAppUrl(mobile, message)} target="_blank" rel="noopener noreferrer">
              שלח בקשה ב-WhatsApp
            </a>
          </Button>
        ) : null}
      </div>
      {url && !mobile ? <p className="mt-3 text-sm text-clay">אין מספר נייד ישראלי בתיק, ולכן אי אפשר לפתוח את וואטסאפ. אפשר להעתיק את הקישור.</p> : null}
      {url ? (
        <p dir="auto" className="mt-3 break-all rounded-md border border-ink/10 bg-[#fbf8f2] px-3 py-2 text-sm">
          {url}
        </p>
      ) : null}
      {notice ? <p className="mt-3 text-sm font-semibold text-[#0d4a2e]">{notice}</p> : null}
      {error ? (
        <p className="mt-3 text-sm font-medium text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function uploadLink(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const record = body as Record<string, unknown>;
  for (const key of ["url", "upload_url", "link"]) {
    if (typeof record[key] === "string" && record[key]) return absolute(record[key] as string);
  }
  if (typeof record.token === "string" && record.token) return absolute(`/upload/${record.token}`);
  return null;
}

function absolute(value: string) {
  if (value.startsWith("http://") || value.startsWith("https://")) return value;
  if (typeof window === "undefined") return value;
  return new URL(value, window.location.origin).toString();
}
