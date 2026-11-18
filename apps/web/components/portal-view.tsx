"use client";

import type { FieldSpec, PortalView } from "@docketai/shared-types";
import { useCallback, useEffect, useRef, useState } from "react";

import { IntegrityPanel } from "@/components/integrity-panel";
import { PdfCanvas } from "@/components/pdf-preview";
import { SignatureForm, SigningModal } from "@/components/signing-modal";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { FIELD_LABEL, processLabel } from "@/lib/filing";
import { hebrewOfficeError, PORTAL_CONSENT_HE } from "@/lib/hebrew";
import { portalApi, portalCertificateUrl, portalDownloadUrl, portalPreviewUrl } from "@/lib/portal-api";

const RECORDING = "נרשמים מועד החתימה, כתובת הרשת ופרטי הדפדפן על גבי אישור החתימה.";
const REVIEW_AGAIN = "המשרד עדכן פרט בטופס בהסכמתך – אנא עבור על הטופס המעודכן לפני החתימה";

type Step = 1 | 2 | 3 | 4;

const STEP_LABELS = ["בדיקת פרטים והסברים", "צפייה בטופס המלא", "חתימה דיגיטלית", "אישור והורדה"] as const;

function derivedStep(view: PortalView): Step {
  if (view.state === "completed") return 4;
  if (view.ready_to_sign && !view.waiting_on_office) return 2;
  return 1;
}

export function PortalViewScreen({ token }: { token: string }) {
  const [view, setView] = useState<PortalView | null>(null);
  const [inactive, setInactive] = useState(false);
  const [revoked, setRevoked] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [signing, setSigning] = useState(false);
  const [step, setStep] = useState<Step>(1);
  const [previewStamp, setPreviewStamp] = useState("");
  const synced = useRef(false);

  const load = useCallback(async () => {
    try {
      const next = await portalApi.view(token);
      setView(next);
      setInactive(false);
      setRevoked(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 410) {
        setRevoked(true);
        setInactive(false);
        setView(null);
        return;
      }
      if (error instanceof ApiError && error.status === 404) {
        setInactive(true);
        setRevoked(false);
        setView(null);
        return;
      }
      setNotice(hebrewOfficeError(error));
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!view) return;
    const next = derivedStep(view);
    if (!synced.current) {
      synced.current = true;
      setStep(next);
      return;
    }
    if (next === 4) setStep(4);
    else if (next === 1) setStep(1);
  }, [view]);

  async function sign(png: string) {
    if (!view?.review_digest) return;
    setBusy(true);
    setNotice(null);
    try {
      const next = await portalApi.sign(token, {
        signature_png_base64: png,
        review_digest: view.review_digest,
        consent: true,
      });
      setSigning(false);
      setStep(4);
      setView(next);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setSigning(false);
        setStep(2);
        setNotice(REVIEW_AGAIN);
        await load();
        return;
      }
      setNotice(hebrewOfficeError(error));
    } finally {
      setBusy(false);
    }
  }

  if (revoked) {
    return (
      <main className="mx-auto max-w-lg px-4 py-16">
        <h1 className="font-serif text-3xl">קישור החתימה בוטל על ידי המשרד לצורך עדכון פרטים. אנא פנה למשרד לקבלת קישור מעודכן.</h1>
      </main>
    );
  }

  if (inactive) {
    return (
      <main className="mx-auto max-w-lg px-4 py-16">
        <h1 className="font-serif text-3xl">הקישור הזה כבר לא פעיל</h1>
      </main>
    );
  }

  if (!view) {
    return (
      <main className="mx-auto max-w-lg px-4 py-16">
        <p className="text-sm text-ink">{notice ?? "טוען את הטופס."}</p>
      </main>
    );
  }

  const ready = view.ready_to_sign && !view.waiting_on_office;

  return (
    <main className="mx-auto flex min-w-0 max-w-3xl flex-col gap-5 overflow-x-clip px-4 py-8">
      <header>
        <p className="text-sm font-semibold text-tide">חתימת לקוח</p>
        <h1 className="font-serif text-4xl">{processLabel(view.process.name, view.process.name)}</h1>
        {view.client_name ? <p className="mt-2 text-lg">{view.client_name}</p> : null}
      </header>
      <ol aria-label="התקדמות החתימה" className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
        {(
          [
            ["1", "בדיקת פרטים וטופס"],
            ["2", "חתימה על המסמך"],
            ["3", "אישור וחותם דיגיטלי"],
          ] as const
        ).map(([number, label]) => {
          const phase = step <= 2 ? 1 : step === 3 ? 2 : 3;
          const current = String(phase) === number;
          const done = phase > Number(number);
          return (
            <li
              key={number}
              className={`rounded-md border px-3 py-2 text-center font-semibold ${current ? "border-tide bg-tide text-white" : done ? "border-moss bg-[#e7f5ee] text-[#0d4a2e]" : "border-ink/15 bg-white text-ink"}`}
              aria-current={current ? "step" : undefined}
            >
              {number}. {label}
            </li>
          );
        })}
      </ol>
      <nav aria-label="שלבי החתימה" className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        {STEP_LABELS.map((label, index) => {
          const number = (index + 1) as Step;
          const current = step === number;
          return (
            <p
              key={label}
              className={`rounded-md border px-2 py-2 text-center font-semibold leading-5 ${current ? "border-tide bg-tide text-white" : "border-ink/15 bg-white text-ink"}`}
              aria-current={current ? "step" : undefined}
            >
              {number}. {label}
            </p>
          );
        })}
      </nav>
      {notice ? (
        <p
          className={`rounded-md border px-4 py-3 text-sm font-semibold ${
            notice.startsWith("המסמך התקבל")
              ? "border-moss bg-[#e7f3ea] text-[#145c38]"
              : "border-amberink bg-[#fbf3e4] text-[#4a3208]"
          }`}
          role={notice.startsWith("המסמך התקבל") ? "status" : "alert"}
        >
          {notice}
        </p>
      ) : null}
      {step === 1 ? (
        <section className="rounded-lg border border-ink/15 bg-white p-6 shadow-card">
          <h2 className="font-serif text-3xl">בדיקת פרטים והסברים</h2>
          <p className="mt-3 text-sm leading-7">
            אלה הפרטים האישיים שנרשמו בטופס, והמקום בטופס שבו כל פרט נכתב. אין כאן מה להקליד.
          </p>
          {view.state === "open" ? (
            <ClientUpload
              busy={busy}
              onUpload={async (documentType, file) => {
                setBusy(true);
                setNotice(null);
                try {
                  const next = await portalApi.uploadDocument(token, documentType, file);
                  if (next) setView(next);
                  else await load();
                  setPreviewStamp(String(Date.now()));
                  setNotice("המסמך התקבל. הטופס עודכן לפי הקובץ החדש.");
                } catch (error) {
                  setNotice(hebrewOfficeError(error));
                } finally {
                  setBusy(false);
                }
              }}
            />
          ) : null}
          <ul className="mt-4 space-y-3">
            {view.process.required_fields.map((field) => (
              <li key={field.key} className="rounded-md border border-ink/10 px-3 py-3">
                <p className="font-semibold">{FIELD_LABEL[field.key] ?? field.label_he ?? field.label}</p>
                <p className="mt-1 text-sm" dir="auto">
                  {view.field_values[field.key] || "עדיין ריק"}
                </p>
                <p className="mt-1 text-sm text-ink">{explain(field)}</p>
              </li>
            ))}
          </ul>
          <Button type="button" className="mt-6 min-h-11 w-full" disabled={!ready} onClick={() => setStep(2)}>
            {ready ? "המשך לצפייה בטופס" : "הטופס עוד לא מוכן"}
          </Button>
        </section>
      ) : null}
      {step === 2 ? (
        <section className="min-w-0 rounded-lg border border-ink/15 bg-white shadow-card">
          <div className="border-b border-ink/10 px-4 py-4">
            <h2 className="font-serif text-2xl">צפייה בטופס המלא</h2>
          </div>
          <div className="min-w-0 overflow-hidden px-4 py-4">
            <details className="mb-4 rounded-md border border-ink/10 bg-[#fbf8f2] px-3 py-3" open>
              <summary className="cursor-pointer font-semibold">סיכום הפרטים שמולאו עבורך בטופס</summary>
              <ul className="mt-3 grid gap-2">
                {view.process.required_fields.map((field) => (
                  <li key={field.key} className="text-sm">
                    <span className="font-semibold">{FIELD_LABEL[field.key] ?? field.label_he ?? field.label}: </span>
                    <span dir="auto">{view.field_values[field.key] || "עדיין ריק"}</span>
                  </li>
                ))}
              </ul>
            </details>
            <PdfCanvas url={portalPreviewUrl(token)} refreshKey={`${view.review_digest ?? ""}:${previewStamp}`} />
          </div>
          <div className="flex flex-col gap-2 px-4 pb-4">
            <Button type="button" variant="outline" className="min-h-11 w-full" onClick={() => setStep(1)}>
              חזרה לפרטים
            </Button>
            <Button type="button" className="min-h-11 w-full" disabled={!ready} onClick={() => setStep(3)}>
              המשך לחתימה
            </Button>
          </div>
        </section>
      ) : null}
      {step === 3 ? (
        <section className="rounded-lg border border-ink/15 bg-white p-4 shadow-card">
          <h2 className="font-serif text-2xl">חתימה דיגיטלית</h2>
          <div className="mt-4 md:hidden">
            <SignatureForm busy={busy} consentLabel={PORTAL_CONSENT_HE} notice={RECORDING} alert={notice} onSign={sign} />
          </div>
          <div className="mt-4 hidden md:block">
            <Button type="button" className="min-h-11 w-full" onClick={() => setSigning(true)} disabled={busy}>
              חתימה
            </Button>
            <SigningModal
              open={signing}
              busy={busy}
              consentLabel={PORTAL_CONSENT_HE}
              notice={RECORDING}
              alert={notice}
              onOpenChange={setSigning}
              onSign={sign}
            />
          </div>
          <Button type="button" variant="outline" className="mt-4 min-h-11 w-full" onClick={() => setStep(2)}>
            חזרה לטופס
          </Button>
        </section>
      ) : null}
      {step === 4 && view.seal ? (
        <IntegrityPanel
          seal={view.seal}
          downloadExpiresAt={view.download_expires_at}
          signedPdfUrl={portalDownloadUrl(token)}
          certificateUrl={portalCertificateUrl(token)}
        />
      ) : null}
    </main>
  );
}

const CLIENT_DRAWERS = [
  { id: "id_copy", label: "תעודת זהות" },
  { id: "proof_of_address", label: "חשבון ארנונה / כתובת" },
  { id: "bank_confirmation", label: "אישור ניהול חשבון" },
] as const;

function ClientUpload({
  busy,
  onUpload,
}: {
  busy: boolean;
  onUpload: (documentType: string, file: File) => Promise<void>;
}) {
  const [drawer, setDrawer] = useState<(typeof CLIENT_DRAWERS)[number]["id"]>("id_copy");
  return (
    <div className="mt-5 rounded-md border border-ink/15 bg-[#fbf8f2] p-4">
      <p className="font-semibold">העלאת מסמך מעודכן מהנייד (ת"ז / ארנונה / אישור בנק)</p>
      <label className="mt-3 block text-sm font-semibold" htmlFor="client-drawer">
        מגירה
      </label>
      <select
        id="client-drawer"
        className="mt-1 h-11 w-full rounded-md border border-ink/25 bg-white px-3 text-base"
        value={drawer}
        onChange={(event) => setDrawer(event.target.value as (typeof CLIENT_DRAWERS)[number]["id"])}
      >
        {CLIENT_DRAWERS.map((item) => (
          <option key={item.id} value={item.id}>
            {item.label}
          </option>
        ))}
      </select>
      <label className="mt-3 inline-flex min-h-11 cursor-pointer items-center rounded-md bg-ink px-3 text-sm font-semibold text-white">
        {busy ? "שולח…" : "צילום או קובץ"}
        <input
          className="sr-only"
          type="file"
          accept="image/*,application/pdf"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void onUpload(drawer, file);
          }}
        />
      </label>
    </div>
  );
}

function explain(field: FieldSpec) {
  const provenance = field.provenance;
  if (!provenance) return "הפרט נרשם בטופס.";
  return [provenance.form_he, provenance.section_he, provenance.purpose_he].filter(Boolean).join(" · ") || "הפרט נרשם בטופס.";
}
