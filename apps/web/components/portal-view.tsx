"use client";

import type { FieldSpec, PortalView } from "@docketai/shared-types";
import { useCallback, useEffect, useRef, useState } from "react";

import { IntegrityPanel } from "@/components/integrity-panel";
import { PdfCanvas } from "@/components/pdf-preview";
import { SignatureForm, SigningModal } from "@/components/signing-modal";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { FIELD_LABEL } from "@/lib/filing";
import { hebrewOfficeError } from "@/lib/hebrew";
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
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [signing, setSigning] = useState(false);
  const [step, setStep] = useState<Step>(1);
  const synced = useRef(false);

  const load = useCallback(async () => {
    try {
      const next = await portalApi.view(token);
      setView(next);
      setInactive(false);
    } catch (error) {
      if (error instanceof ApiError && (error.status === 404 || error.status === 410)) {
        setInactive(true);
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
      setView(next);
      setSigning(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setNotice(REVIEW_AGAIN);
        setSigning(false);
        setStep(2);
        await load();
        return;
      }
      setNotice(hebrewOfficeError(error));
    } finally {
      setBusy(false);
    }
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
        <h1 className="font-serif text-4xl">{view.process.name}</h1>
        {view.client_name ? <p className="mt-2 text-lg">{view.client_name}</p> : null}
      </header>
      <nav aria-label="שלבי החתימה" className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        {STEP_LABELS.map((label, index) => {
          const number = (index + 1) as Step;
          const current = step === number;
          return (
            <p
              key={label}
              className={`rounded-md border-2 px-2 py-2 text-center font-semibold leading-5 ${current ? "border-tide bg-tide text-white" : "border-ink/15 bg-white text-ink"}`}
              aria-current={current ? "step" : undefined}
            >
              {number}. {label}
            </p>
          );
        })}
      </nav>
      {notice ? (
        <p className="rounded-md border-2 border-amberink bg-[#fbf3e4] px-4 py-3 text-sm font-semibold text-[#4a3208]" role="alert">
          {notice}
        </p>
      ) : null}
      {step === 1 ? (
        <section className="rounded-lg border-2 border-ink/15 bg-white p-6 shadow-card">
          <h2 className="font-serif text-3xl">בדיקת פרטים והסברים</h2>
          <p className="mt-3 text-sm leading-7">
            אלה הפרטים האישיים שנרשמו בטופס, והמקום בטופס שבו כל פרט נכתב. אין כאן מה להקליד.
          </p>
          <ul className="mt-4 space-y-3">
            {view.process.required_fields.map((field) => (
              <li key={field.key} className="rounded-md border-2 border-ink/10 px-3 py-3">
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
        <section className="min-w-0 rounded-lg border-2 border-ink/15 bg-white shadow-card">
          <div className="border-b-2 border-ink/10 px-4 py-4">
            <h2 className="font-serif text-2xl">צפייה בטופס המלא</h2>
          </div>
          <div className="min-w-0 overflow-hidden px-4 py-4">
            <PdfCanvas url={portalPreviewUrl(token)} refreshKey={view.review_digest ?? ""} />
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
        <section className="rounded-lg border-2 border-ink/15 bg-white p-4 shadow-card">
          <h2 className="font-serif text-2xl">חתימה דיגיטלית</h2>
          <div className="mt-4 md:hidden">
            <SignatureForm busy={busy} consentLabel={view.consent_text} notice={RECORDING} onSign={sign} />
          </div>
          <div className="mt-4 hidden md:block">
            <Button type="button" className="min-h-11 w-full" onClick={() => setSigning(true)} disabled={busy}>
              חתימה
            </Button>
            <SigningModal
              open={signing}
              busy={busy}
              consentLabel={view.consent_text}
              notice={RECORDING}
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

function explain(field: FieldSpec) {
  const provenance = field.provenance;
  if (!provenance) return "הפרט נרשם בטופס.";
  return [provenance.form_he, provenance.section_he, provenance.purpose_he].filter(Boolean).join(" · ") || "הפרט נרשם בטופס.";
}
