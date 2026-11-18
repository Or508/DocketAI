"use client";

import { useEffect, useState } from "react";

import { ApiError, api, type OrganizationProfile } from "@/lib/api";

function officeMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "הפעולה נכשלה. בדקו את החיבור ונסו שוב.";
  if (error.status === 502) return "לא ניתן להגיע לשירות המשרד.";
  if (error.message === "Unknown profession.") return "המקצוע הזה אינו זמין.";
  return "הפעולה נכשלה.";
}

export function OfficePanel() {
  const [office, setOffice] = useState<OrganizationProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .organization()
      .then((next) => {
        if (!cancelled) setOffice(next);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(officeMessage(reason));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function chooseProfession(profession: string) {
    if (!office || profession === office.profession.key) return;
    setBusy(true);
    setError(null);
    try {
      setOffice(await api.setProfession(profession));
    } catch (reason) {
      setError(officeMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function setReading(enabled: boolean) {
    setBusy(true);
    setError(null);
    try {
      setOffice(await api.setAiReading(enabled));
    } catch (reason) {
      setError(officeMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-lg border border-ink/15 bg-white p-5">
      <h2 className="font-serif text-2xl">מקצוע המשרד</h2>
      <p className="mt-2 text-sm text-mist">המקצוע קובע אילו תהליכים נפתחים, ואיך המסכים קוראים לאדם ולתיק.</p>
      {office ? (
        <>
          <label className="mt-4 block text-sm font-semibold" htmlFor="office-profession">
            מקצוע
            <select
              id="office-profession"
              className="mt-2 h-11 w-full rounded-md border border-line bg-white px-3 text-base text-ink"
              value={office.profession.key}
              disabled={busy}
              onChange={(event) => void chooseProfession(event.target.value)}
            >
              {office.professions.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label_he}
                </option>
              ))}
            </select>
          </label>
          <p className="mt-2 text-sm text-mist">
            במסכים: {office.profession.client_term_he}, {office.profession.case_term_he}.
          </p>
          <label className="mt-4 flex items-start gap-3 text-sm font-semibold">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4"
              checked={office.ai_reading_enabled}
              disabled={busy}
              onChange={(event) => void setReading(event.target.checked)}
            />
            <span>
              קריאת מסמכים ב-AI
              <span className="mt-1 block font-normal text-mist">כבוי: מסמכים של המשרד לא נשלחים למודל. מה שכבר נקרא נשאר.</span>
            </span>
          </label>
        </>
      ) : (
        <p className="mt-4 text-sm text-mist">{error ? "" : "טוענים את פרטי המשרד…"}</p>
      )}
      {error ? (
        <p className="mt-3 text-sm font-medium text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
