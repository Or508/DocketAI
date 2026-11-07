"use client";

import type { PortalView } from "@docketai/shared-types";
import { useCallback, useEffect, useRef, useState } from "react";

import { ChatPanel } from "@/components/chat-panel";
import { FieldVerification } from "@/components/field-verification";
import { IntegrityPanel } from "@/components/integrity-panel";
import { PdfCanvas } from "@/components/pdf-preview";
import { SignatureForm, SigningModal } from "@/components/signing-modal";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { portalApi, portalCertificateUrl, portalDownloadUrl, portalPreviewUrl } from "@/lib/portal-api";

const RECORDING =
  "We record the signing time, your IP address and your browser details on the certificate.";

type Step = 1 | 2 | 3 | 4;

const STEP_LABELS = ["Check details", "Review", "Sign", "Done"] as const;

function derivedStep(view: PortalView): Step {
  if (view.state === "completed") return 4;
  if (view.ready_to_sign && !view.waiting_on_office) return 2;
  return 1;
}

function focusField(id: string) {
  const node = document.getElementById(id);
  if (!node) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  node.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
  node.focus();
}

export function PortalViewScreen({ token }: { token: string }) {
  const [view, setView] = useState<PortalView | null>(null);
  const [inactive, setInactive] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [liveReply, setLiveReply] = useState<string | null>(null);
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
      setNotice(error instanceof Error ? error.message : "The form could not be loaded.");
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
        // The form changed since the signer reviewed it. Send them back to review
        // the new version; signing straight away would reuse the fresh digest unseen.
        setNotice(error.message);
        setSigning(false);
        setStep(2);
        await load();
        return;
      }
      setNotice(error instanceof Error ? error.message : "The form could not be signed.");
    } finally {
      setBusy(false);
    }
  }

  if (inactive) {
    return (
      <main className="mx-auto max-w-lg px-4 py-16">
        <h1 className="font-serif text-3xl">This link is no longer active</h1>
      </main>
    );
  }

  if (!view) {
    return (
      <main className="mx-auto max-w-lg px-4 py-16">
        <p className="text-sm text-mist">{notice ?? "Loading the form."}</p>
      </main>
    );
  }

  const total = view.process.required_fields.length;
  const done = total - view.missing_fields.length;

  return (
    <main className="mx-auto flex min-w-0 max-w-3xl flex-col gap-5 overflow-x-clip px-4 py-8">
      <header>
        <p className="text-[11px] uppercase tracking-[0.18em] text-tide">Signing</p>
        <h1 className="font-serif text-4xl" dir="auto">
          {view.process.name}
        </h1>
        {view.client_name ? (
          <p className="mt-2 text-lg" dir="auto">
            {view.client_name}
          </p>
        ) : null}
      </header>
      <nav aria-label="Progress" className="grid grid-cols-4 gap-1 text-center text-[11px] leading-4">
        {STEP_LABELS.map((label, index) => {
          const number = (index + 1) as Step;
          const current = step === number;
          return (
            <p key={label} className={current ? "font-medium text-tide" : "text-mist"} aria-current={current ? "step" : undefined}>
              {number}. {label}
            </p>
          );
        })}
      </nav>
      {notice ? <p className="text-sm text-clay">{notice}</p> : null}
      {step === 1 ? (
        <div className="flex flex-col gap-5 pb-28">
          <FieldVerification
            process={view.process}
            field_values={view.field_values}
            busy={busy}
            onSave={async (key, value) => {
              setBusy(true);
              setNotice(null);
              try {
                setView(await portalApi.setField(token, key, value));
              } catch (error) {
                setNotice(error instanceof Error ? error.message : "That value could not be saved.");
              } finally {
                setBusy(false);
              }
            }}
          />
          <details className="rounded-lg border border-line bg-[#fbf8f2]">
            <summary className="flex min-h-11 cursor-pointer items-center px-4 text-sm">
              Prefer to type? Chat with the clerk
            </summary>
            <div className="px-2 pb-2">
              <ChatPanel
                workspace={view}
                busy={busy}
                liveReply={liveReply}
                onSend={async (message) => {
                  setBusy(true);
                  setLiveReply("");
                  setNotice(null);
                  try {
                    setView(await portalApi.streamChat(token, message, setLiveReply));
                  } catch (error) {
                    setNotice(error instanceof Error ? error.message : "The message could not be sent.");
                  } finally {
                    setBusy(false);
                    setLiveReply(null);
                  }
                }}
              />
            </div>
          </details>
          {view.waiting_on_office ? (
            <p className="text-sm leading-6">The office is finishing your documents. Check back soon.</p>
          ) : null}
          <div className="sticky bottom-0 z-10 -mx-4 border-t border-line bg-[#f3efe6]/95 px-4 py-3">
            <p className="mb-2 text-sm text-mist">
              {done} of {total} done
            </p>
            <Button
              type="button"
              className="min-h-11 w-full"
              onClick={() => {
                const missing = view.missing_fields[0];
                if (missing) {
                  focusField(`field-${missing.key}`);
                  return;
                }
                if (view.ready_to_sign) setStep(2);
              }}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
      {step === 2 ? (
        <section className="min-w-0 rounded-lg border border-line bg-white/80 shadow-card">
          <div className="border-b border-line px-4 py-4">
            <p className="text-[11px] uppercase tracking-[0.18em] text-tide">Draft</p>
            <h2 className="font-serif text-2xl">Form preview</h2>
          </div>
          <div className="min-w-0 overflow-hidden px-4 py-4">
            <PdfCanvas url={portalPreviewUrl(token)} refreshKey={view.review_digest ?? ""} />
          </div>
          <div className="flex flex-col gap-2 px-4 pb-4">
            <Button type="button" variant="outline" className="min-h-11 w-full" onClick={() => setStep(1)}>
              Back
            </Button>
            <Button type="button" className="min-h-11 w-full" disabled={!view.ready_to_sign} onClick={() => setStep(3)}>
              Looks right
            </Button>
          </div>
        </section>
      ) : null}
      {step === 3 ? (
        <section className="rounded-lg border border-line bg-white/80 p-4 shadow-card">
          <p className="text-[11px] uppercase tracking-[0.18em] text-tide">Sign</p>
          <h2 className="font-serif text-2xl">Sign the form</h2>
          <div className="mt-4 md:hidden">
            <SignatureForm busy={busy} consentLabel={view.consent_text} notice={RECORDING} onSign={sign} />
          </div>
          <div className="mt-4 hidden md:block">
            <Button type="button" className="min-h-11 w-full" onClick={() => setSigning(true)} disabled={busy}>
              Sign
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
            Back
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
