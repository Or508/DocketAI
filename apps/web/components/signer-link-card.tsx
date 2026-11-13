"use client";

import type { SigningLinkRead } from "@docketai/shared-types";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { hebrewOfficeError } from "@/lib/hebrew";

function when(value: string) {
  return new Intl.DateTimeFormat("he-IL", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Jerusalem",
  }).format(new Date(value));
}

export function SignerLinkCard({ caseId }: { caseId: string }) {
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
      await api.revokeSigningLink(caseId);
      setFreshUrl(null);
      await load();
    } catch (error) {
      setNote(hebrewOfficeError(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-lg border-2 border-tide bg-white shadow-card">
      <div className="border-b border-line px-4 py-4">
        <h2 className="font-serif text-2xl">שליחה לאישור וחתימת לקוח</h2>
        <p className="mt-2 text-sm leading-6 text-ink">הלקוח בודק את הפרטים האישיים וחותם. הוא לא ממלא את הטופס.</p>
      </div>
      <div className="space-y-3 px-4 py-4 text-sm">
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
            <Button type="button" variant="outline" onClick={() => void copy()}>
              העתקת הקישור
            </Button>
          </div>
        ) : null}
        {note ? <p className="text-clay">{note}</p> : null}
        <div className="flex flex-wrap gap-2">
          <Button type="button" className="w-full" onClick={() => void create()} disabled={busy}>
            {freshUrl ? "קישור חדש" : "יצירת קישור לחתימה"}
          </Button>
          {link?.state === "open" ? (
            <Button type="button" variant="danger" onClick={() => void revoke()} disabled={busy}>
              ביטול הקישור
            </Button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
