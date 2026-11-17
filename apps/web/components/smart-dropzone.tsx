"use client";

import type { CaseWorkspace } from "@docketai/shared-types";
import { useState } from "react";

import { ApiError, detailFrom } from "@/lib/api";
import { DRAWER_ACCEPT } from "@/lib/clipboard-files";
import { hebrewOfficeError } from "@/lib/hebrew";

export function SmartDropzone({
  caseId,
  onUploaded,
  compact = false,
}: {
  caseId: string;
  onUploaded: (workspace: CaseWorkspace, notice: string) => void;
  compact?: boolean;
}) {
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(list: File[]) {
    const files = list.filter((file) => file.size > 0 || file.name);
    if (!files.length || busy) return;
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      for (const file of files) body.append("files", file, file.name);
      const response = await fetch(`/api/cases/${caseId}/smart-upload`, { method: "POST", body, cache: "no-store" });
      if (response.status === 401) {
        window.location.assign(`/login?next=${encodeURIComponent(`/cases/${caseId}`)}`);
        return;
      }
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        throw new ApiError(detailFrom(payload) || "Request failed", response.status);
      }
      const workspace = workspaceFrom(payload);
      if (!workspace) throw new ApiError("התשובה מהמשרד לא כללה את התיק.", response.status);
      onUploaded(workspace, successNotice(payload));
    } catch (reason) {
      setError(hebrewOfficeError(reason));
    } finally {
      setBusy(false);
      setOver(false);
    }
  }

  return (
    <section
      className={`rounded-lg border border-dashed bg-white ${compact ? "px-3 py-2.5" : "p-5 shadow-card"} ${over ? "border-tide bg-[#e7f3f2]" : "border-tide/50"}`}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        void send([...event.dataTransfer.files]);
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className={compact ? "text-sm font-semibold" : "font-serif text-2xl"}>העלאה חכמה מרוכזת (זרוק ת"ז, ארנונה ואישור בנק יחד)</h2>
          {compact ? null : <p className="mt-1 text-sm text-ink">אפשר לבחור או לגרור כמה קבצים יחד. המערכת ממיינת כל קובץ למגירה המתאימה.</p>}
        </div>
        <label className={`inline-flex cursor-pointer items-center rounded-md bg-tide font-semibold text-white ${compact ? "h-8 px-3 text-xs" : "h-11 px-4 text-sm"}`}>
          {busy ? "ממיינים…" : "בחירת קבצים"}
          <input
            className="sr-only"
            type="file"
            multiple
            accept={DRAWER_ACCEPT}
            disabled={busy}
            onChange={(event) => {
              const chosen = [...(event.target.files ?? [])];
              event.target.value = "";
              void send(chosen);
            }}
          />
        </label>
      </div>
      {error ? (
        <p className="mt-3 text-sm font-medium text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function workspaceFrom(body: unknown): CaseWorkspace | null {
  if (!body || typeof body !== "object") return null;
  const row = body as CaseWorkspace;
  if (!row.case || !row.process || !row.gap || !row.field_values) return null;
  return row;
}

function successNotice(body: unknown) {
  const files = routedFiles(body);
  const routed = files.filter((file) => file.outcome === "routed").length;
  const waiting = files.filter((file) => file.outcome === "unrouted").length;
  const rejected = files.filter((file) => file.outcome === "rejected").length;
  const parts = ["ההעלאה החכמה הושלמה. הקבצים מוינו אוטומטית למגירות."];
  if (routed) parts.push(`${routed} קבצים נכנסו למגירה.`);
  if (waiting) parts.push(`${waiting} קבצים ממתינים לשיבוץ ידני.`);
  if (rejected) parts.push(`${rejected} קבצים לא התקבלו.`);
  return parts.join(" ");
}

function routedFiles(body: unknown) {
  if (!body || typeof body !== "object" || !("routed_files" in body)) return [];
  const list = (body as { routed_files?: unknown }).routed_files;
  if (!Array.isArray(list)) return [];
  return list.flatMap((item) => {
    if (!item || typeof item !== "object" || !("outcome" in item)) return [];
    const outcome = (item as { outcome?: unknown }).outcome;
    return outcome === "routed" || outcome === "unrouted" || outcome === "rejected" ? [{ outcome }] : [];
  });
}
