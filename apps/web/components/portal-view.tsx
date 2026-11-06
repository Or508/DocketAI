"use client";

import type { PortalView } from "@docketai/shared-types";
import { useCallback, useEffect, useState } from "react";

import { ChatPanel } from "@/components/chat-panel";
import { FieldVerification } from "@/components/field-verification";
import { PdfCanvas } from "@/components/pdf-preview";
import { SigningModal } from "@/components/signing-modal";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { portalApi, portalDownloadUrl, portalPreviewUrl } from "@/lib/portal-api";

function israelTime(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone: "Asia/Jerusalem",
  }).format(new Date(value));
}

function israelDate(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "long",
    timeZone: "Asia/Jerusalem",
  }).format(new Date(value));
}

export function PortalViewScreen({ token }: { token: string }) {
  const [view, setView] = useState<PortalView | null>(null);
  const [inactive, setInactive] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [liveReply, setLiveReply] = useState<string | null>(null);
  const [signing, setSigning] = useState(false);

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

  if (view.state === "completed") {
    return (
      <main className="mx-auto max-w-lg px-4 py-16">
        <h1 className="font-serif text-4xl">All set</h1>
        {view.signed_at ? (
          <p className="mt-4 text-sm leading-6">Signed {israelTime(view.signed_at)} Israel time.</p>
        ) : null}
        <a className="mt-6 inline-block text-sm underline" href={portalDownloadUrl(token)}>
          Download copy
        </a>
        {view.download_expires_at ? (
          <p className="mt-3 text-sm text-mist">The download ends on {israelDate(view.download_expires_at)}.</p>
        ) : null}
      </main>
    );
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-5 px-4 py-8">
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
      <section className="rounded-lg border border-line bg-white/80 shadow-card">
        <div className="border-b border-line px-4 py-4">
          <p className="text-[11px] uppercase tracking-[0.18em] text-tide">Draft</p>
          <h2 className="font-serif text-2xl">Form preview</h2>
        </div>
        <div className="px-4 py-4">
          <PdfCanvas url={portalPreviewUrl(token)} refreshKey={view.review_digest ?? ""} />
        </div>
      </section>
      {notice ? <p className="text-sm text-clay">{notice}</p> : null}
      {view.waiting_on_office ? (
        <p className="text-sm leading-6">The office is finishing your documents. Check back soon.</p>
      ) : (
        <Button type="button" disabled={!view.ready_to_sign || busy} onClick={() => setSigning(true)}>
          Review and sign
        </Button>
      )}
      <SigningModal
        open={signing}
        busy={busy}
        consentLabel={view.consent_text}
        onOpenChange={setSigning}
        onSign={async (png) => {
          if (!view.review_digest) return;
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
              setNotice(error.message);
              await load();
              return;
            }
            setNotice(error instanceof Error ? error.message : "The form could not be signed.");
          } finally {
            setBusy(false);
          }
        }}
      />
    </main>
  );
}
