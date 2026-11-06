"use client";

import type { SigningLinkRead } from "@docketai/shared-types";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";

function when(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
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
      setNote(error instanceof Error ? error.message : "The signing link could not be loaded.");
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
      setNote(error instanceof Error ? error.message : "The link could not be created.");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!freshUrl) return;
    await navigator.clipboard.writeText(freshUrl);
    setNote("Copied.");
  }

  async function revoke() {
    setBusy(true);
    setNote(null);
    try {
      await api.revokeSigningLink(caseId);
      setFreshUrl(null);
      await load();
    } catch (error) {
      setNote(error instanceof Error ? error.message : "The link could not be revoked.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-lg border border-line bg-[#fbf8f2] shadow-card">
      <div className="border-b border-line px-4 py-4">
        <p className="text-[11px] uppercase tracking-[0.18em] text-tide">Signer</p>
        <h2 className="font-serif text-2xl">Magic link</h2>
      </div>
      <div className="space-y-3 px-4 py-4 text-sm">
        {link ? (
          <p>
            {link.state === "open"
              ? `Open until ${when(link.expires_at)}`
              : link.state === "completed"
                ? "The signer has finished."
                : "This link is no longer active."}
          </p>
        ) : (
          <p className="text-mist">No signing link yet.</p>
        )}
        {freshUrl ? (
          <div className="space-y-2">
            <p className="text-xs text-mist">This address is shown only once.</p>
            <p dir="auto" className="break-all rounded-md border border-line bg-white px-3 py-2">
              {freshUrl}
            </p>
            <Button type="button" variant="outline" onClick={() => void copy()}>
              Copy link
            </Button>
          </div>
        ) : null}
        {note ? <p className="text-clay">{note}</p> : null}
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => void create()} disabled={busy}>
            Create link
          </Button>
          {link?.state === "open" ? (
            <Button type="button" variant="danger" onClick={() => void revoke()} disabled={busy}>
              Revoke
            </Button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
