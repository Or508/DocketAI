"use client";

import type { CaseWorkspace } from "@docketai/shared-types";
import { useCallback, useEffect, useState } from "react";

import { CaseChecklist } from "@/components/case-checklist";
import { ChatPanel } from "@/components/chat-panel";
import { FieldVerification } from "@/components/field-verification";
import { PdfPreview } from "@/components/pdf-preview";
import { PipelineBanner } from "@/components/pipeline-banner";
import { SigningModal } from "@/components/signing-modal";
import { StatusPill } from "@/components/status-pill";
import { Wordmark } from "@/components/wordmark";
import { Button } from "@/components/ui/button";
import { ApiError, api, apiBaseUrl, signedDocumentUrl } from "@/lib/api";

export function CaseWorkspaceView({ caseId }: { caseId: string }) {
  const [workspace, setWorkspace] = useState<CaseWorkspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [signing, setSigning] = useState(false);
  const [liveReply, setLiveReply] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const next = await api.workspace(caseId);
    setWorkspace(next);
  }, [caseId]);

  useEffect(() => {
    let cancelled = false;
    api
      .workspace(caseId)
      .then((next) => {
        if (!cancelled) setWorkspace(next);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof ApiError ? reason.message : "Could not load this case.");
      });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  const processing = workspace?.case.status === "processing" || (workspace?.gap.in_progress.length ?? 0) > 0;
  useEffect(() => {
    if (!processing) return;
    const source = new EventSource(`${apiBaseUrl}/cases/${caseId}/events`);
    source.addEventListener("progress", (event) => {
      const pipeline = JSON.parse((event as MessageEvent).data) as CaseWorkspace["gap"]["pipeline"];
      setWorkspace((current) => (current ? { ...current, gap: { ...current.gap, pipeline } } : current));
    });
    source.addEventListener("done", () => {
      void refresh().catch(() => undefined);
      source.close();
    });
    const timer = window.setInterval(() => {
      void refresh().catch(() => undefined);
    }, 2000);
    return () => {
      source.close();
      window.clearInterval(timer);
    };
  }, [processing, caseId, refresh]);

  async function run(
    action: () => Promise<CaseWorkspace | { workspace: CaseWorkspace; rejected?: { filename: string; reason: string }[]; skipped_duplicates?: string[] }>,
    note?: string,
  ) {
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      setWorkspace("workspace" in result ? result.workspace : result);
      const rejected = "rejected" in result && result.rejected ? result.rejected : [];
      const skipped = "skipped_duplicates" in result && result.skipped_duplicates ? result.skipped_duplicates : [];
      if (rejected.length) {
        setNotice(null);
        setError(rejected.map((item) => `${item.filename}: ${item.reason}`).join(" "));
      } else {
        const extra = skipped.length ? ` Skipped duplicates: ${skipped.join(", ")}.` : "";
        setNotice(note ? `${note}${extra}` : extra.trim() || null);
      }
      return rejected.length === 0;
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "The request failed.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  if (!workspace && !error) {
    return <p className="px-6 py-10 text-sm text-mist">Loading the case…</p>;
  }
  if (!workspace) {
    return <p className="px-6 py-10 text-sm text-clay">{error}</p>;
  }

  return (
    <main className="mx-auto min-h-screen max-w-7xl px-5 py-6">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-line pb-4">
        <div>
          <Wordmark />
          <h1 className="mt-4 font-serif text-4xl">{workspace.case.name}</h1>
          <p className="mt-1 text-sm text-mist">
            {workspace.case.client_name ? `${workspace.case.client_name} · ` : ""}
            {workspace.process.name}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <StatusPill status={workspace.case.status} />
          <Button type="button" disabled={!workspace.ready_to_sign || busy} onClick={() => setSigning(true)}>
            Sign packet
          </Button>
          {workspace.case.download_ready ? (
            <a className="text-sm text-tide underline" href={signedDocumentUrl(caseId)}>
              Download signed PDF
            </a>
          ) : null}
        </div>
      </header>

      {error ? <p className="mt-4 text-sm text-clay">{error}</p> : null}
      {notice ? <p className="mt-4 text-sm text-moss">{notice}</p> : null}
      {workspace.signing_blockers.length > 0 ? (
        <ul className="mt-4 space-y-1 text-sm text-mist">
          {workspace.signing_blockers.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}

      <PipelineBanner pipeline={workspace.gap.pipeline} />

      <div className="mt-6 grid items-start gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.9fr)]">
        <div className="space-y-5">
          <PdfPreview caseId={caseId} workspace={workspace} />
          <CaseChecklist
            workspace={workspace}
            busy={busy}
            onUpload={async (files) => {
              const result = await run(() => api.upload(caseId, files));
              void result;
              window.setTimeout(() => {
                void refresh().catch(() => undefined);
              }, 700);
            }}
            onClassify={async (documentId, documentType) => {
              await run(() => api.classify(caseId, documentId, documentType), "Classification saved.");
            }}
          />
        </div>
        <div className="space-y-5">
          <FieldVerification
            workspace={workspace}
            busy={busy}
            onSave={async (key, value) => {
              await run(() => api.setField(caseId, key, value));
            }}
          />
          <ChatPanel
            workspace={workspace}
            busy={busy}
            liveReply={liveReply}
            onSend={async (message) => {
              setLiveReply("");
              try {
                await run(() => api.streamChat(caseId, message, setLiveReply));
              } finally {
                setLiveReply(null);
              }
            }}
          />
        </div>
      </div>

      <SigningModal
        open={signing}
        busy={busy}
        onOpenChange={setSigning}
        onSign={async (png) => {
          const ok = await run(() => api.sign(caseId, png), "The packet is signed.");
          if (ok) setSigning(false);
        }}
      />
    </main>
  );
}
