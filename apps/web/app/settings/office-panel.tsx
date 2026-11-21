"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api, type OrganizationProfile } from "@/lib/api";

function officeMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "הפעולה נכשלה. בדקו את החיבור ונסו שוב.";
  if (error.status === 502) return "לא ניתן להגיע לשירות המשרד.";
  if (error.message === "Unknown profession.") return "המקצוע הזה אינו זמין.";
  if (error.message && error.message !== "Request failed") return error.message;
  return "הפעולה נכשלה.";
}

export function OfficePanel() {
  const [office, setOffice] = useState<OrganizationProfile | null>(null);
  const [staff, setStaff] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [contactError, setContactError] = useState<string | null>(null);
  const [contactSaved, setContactSaved] = useState(false);
  const [savingContact, setSavingContact] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.organization(), api.me()])
      .then(([next, me]) => {
        if (cancelled) return;
        setOffice(next);
        setStaff(me.role === "staff");
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(officeMessage(reason));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!office) return;
    setPhone(office.contact_phone ?? "");
    setEmail(office.contact_email ?? "");
  }, [office]);

  async function chooseProfession(profession: string) {
    if (!office || staff || profession === office.profession.key) return;
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
    if (staff) return;
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

  async function saveContact() {
    if (!office || staff || savingContact) return;
    setSavingContact(true);
    setContactError(null);
    setContactSaved(false);
    try {
      setOffice(await api.updateContact(phone.trim(), email.trim()));
      setContactSaved(true);
    } catch (reason) {
      setContactError(officeMessage(reason));
    } finally {
      setSavingContact(false);
    }
  }

  return (
    <section className="rounded-lg border border-ink/15 bg-white p-5">
      <h2 className="font-serif text-2xl">מקצוע המשרד</h2>
      <p className="mt-2 text-sm text-mist">המקצוע קובע אילו תהליכים נפתחים, ואיך המסכים קוראים לאדם ולתיק.</p>
      {staff ? <p className="mt-2 text-sm font-medium">רק מנהל המשרד יכול לשנות את זה.</p> : null}
      {office ? (
        <>
          <label className="mt-4 block text-sm font-semibold" htmlFor="office-profession">
            מקצוע
            <select
              id="office-profession"
              className="mt-2 h-11 w-full rounded-md border border-line bg-white px-3 text-base text-ink"
              value={office.profession.key}
              disabled={busy || staff}
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
              disabled={busy || staff}
              onChange={(event) => void setReading(event.target.checked)}
            />
            <span>
              קריאת מסמכים ב-AI
              <span className="mt-1 block font-normal text-mist">כבוי: מסמכים של המשרד לא נשלחים למודל. מה שכבר נקרא נשאר.</span>
            </span>
          </label>
          <div className="mt-6 border-t border-line pt-4">
            <h3 className="text-base font-semibold">פרטי התקשרות ללקוחות</h3>
            <p className="mt-2 text-sm text-mist">הלקוחות יראו את הפרטים האלה בעמודי ההעלאה והחתימה, כדי לדעת למי לפנות.</p>
            <label className="mt-4 block text-sm font-semibold" htmlFor="office-contact-phone">
              טלפון
              <Input
                id="office-contact-phone"
                className="mt-2"
                dir="ltr"
                type="tel"
                value={phone}
                disabled={busy || staff || savingContact}
                onChange={(event) => {
                  setContactSaved(false);
                  setPhone(event.target.value);
                }}
              />
            </label>
            <label className="mt-4 block text-sm font-semibold" htmlFor="office-contact-email">
              דוא״ל
              <Input
                id="office-contact-email"
                className="mt-2"
                dir="ltr"
                type="email"
                value={email}
                disabled={busy || staff || savingContact}
                onChange={(event) => {
                  setContactSaved(false);
                  setEmail(event.target.value);
                }}
              />
            </label>
            <Button type="button" className="mt-4" disabled={busy || staff || savingContact} onClick={() => void saveContact()}>
              שמירה
            </Button>
            {contactSaved ? (
              <p className="mt-3 text-sm font-semibold text-[#0d4a2e]" role="status">
                הפרטים נשמרו.
              </p>
            ) : null}
            {contactError ? (
              <p className="mt-3 text-sm font-medium text-clay" role="alert">
                {contactError}
              </p>
            ) : null}
          </div>
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
