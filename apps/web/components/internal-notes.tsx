"use client";

import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, detailFrom } from "@/lib/api";
import { hebrewOfficeError } from "@/lib/hebrew";

type Note = {
  id: string;
  body: string;
  author: string;
  createdAt: string;
};

export function InternalNotes({ caseId }: { caseId: string }) {
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [posting, setPosting] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setNotes(notesFrom(await readNotes(caseId)));
    } catch (reason) {
      setNotes(null);
      setError(hebrewOfficeError(reason));
    }
  }, [caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const body = draft.trim();
    if (!body) return;
    setPosting(true);
    setError(null);
    try {
      const created = notesFrom(await writeNote(caseId, body));
      setDraft("");
      if (created.length > 0) {
        setNotes((current) => mergeNotes(current ?? [], created));
      } else {
        setNotes(notesFrom(await readNotes(caseId)));
      }
    } catch (reason) {
      setError(hebrewOfficeError(reason));
    } finally {
      setPosting(false);
    }
  }

  return (
    <section className="rounded-lg border border-ink/15 bg-white shadow-card" aria-label="הערות פנימיות לצוות המשרד">
      <div className="border-b border-ink/10 px-4 py-4">
        <h2 className="font-serif text-2xl">הערות פנימיות לצוות המשרד</h2>
        <p className="mt-1 text-sm font-semibold text-clay">לשימוש פנימי של המשרד בלבד — לא מוצג ללקוח</p>
      </div>
      <div className="space-y-4 px-4 py-4">
        {error ? (
          <p className="text-sm font-medium text-clay" role="alert">
            {error}
          </p>
        ) : null}
        {notes === null && !error ? <p className="text-sm text-ink">טוענים את ההערות…</p> : null}
        {notes && notes.length === 0 ? <p className="text-sm text-ink">אין עדיין הערות פנימיות.</p> : null}
        {notes && notes.length > 0 ? (
          <ol className="space-y-3">
            {notes.map((note) => (
              <li key={note.id} className="rounded-md border border-ink/10 bg-paper px-3 py-3">
                <p className="whitespace-pre-wrap text-sm text-ink">{note.body}</p>
                <p className="mt-2 text-xs font-semibold text-ink/70">
                  {note.author}
                  {note.createdAt ? ` · ${israelTime(note.createdAt)}` : ""}
                </p>
              </li>
            ))}
          </ol>
        ) : null}
        <form onSubmit={(event) => void onSubmit(event)} className="space-y-3">
          <label className="block text-sm font-semibold text-ink" htmlFor={`note-${caseId}`}>
            הערה חדשה
          </label>
          <Textarea
            id={`note-${caseId}`}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            maxLength={2000}
            placeholder="הערה לצוות המשרד"
            rows={3}
          />
          <Button type="submit" disabled={posting || !draft.trim()}>
            {posting ? "שומר…" : "שמירת הערה"}
          </Button>
        </form>
      </div>
    </section>
  );
}

async function readNotes(caseId: string) {
  return requestNotes(caseId);
}

async function writeNote(caseId: string, body: string) {
  return requestNotes(caseId, { method: "POST", body: JSON.stringify({ body }) });
}

async function requestNotes(caseId: string, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api/cases/${caseId}/notes`, { ...init, headers, cache: "no-store" });
  if (response.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(`/cases/${caseId}`)}`);
    throw new ApiError("Sign in required.", 401);
  }
  if (!response.ok) {
    let message = response.statusText;
    try {
      message = detailFrom(await response.json());
    } catch {
      message = response.statusText;
    }
    throw new ApiError(message || "Request failed", response.status);
  }
  if (response.status === 204) return null;
  return response.json() as Promise<unknown>;
}

function mergeNotes(current: Note[], created: Note[]) {
  const seen = new Set(current.map((note) => note.id));
  return [...current, ...created.filter((note) => !seen.has(note.id))].sort((left, right) =>
    left.createdAt.localeCompare(right.createdAt),
  );
}

function notesFrom(body: unknown): Note[] {
  return listFrom(body)
    .flatMap((item, index) => {
      const row = asRecord(item);
      if (!row) return [];
      const content = text(row.body) || text(row.text) || text(row.content) || text(row.note);
      if (!content) return [];
      const user = asRecord(row.user) ?? asRecord(row.author);
      const author =
        text(row.author_email) ||
        text(row.author_name) ||
        (typeof row.author === "string" ? row.author.trim() : "") ||
        text(row.created_by) ||
        text(row.actor) ||
        text(user?.display_name) ||
        text(user?.name) ||
        text(user?.full_name) ||
        text(user?.email) ||
        "צוות המשרד";
      const createdAt = text(row.created_at) || text(row.createdAt) || text(row.at);
      return [{ id: text(row.id) || `${createdAt}:${index}:${content.slice(0, 12)}`, body: content, author, createdAt }];
    })
    .sort((left, right) => left.createdAt.localeCompare(right.createdAt));
}

function listFrom(body: unknown): unknown[] {
  if (Array.isArray(body)) return body;
  const root = asRecord(body);
  if (!root) return [];
  if (Array.isArray(root.notes)) return root.notes;
  if (Array.isArray(root.items)) return root.items;
  if (root.note && typeof root.note === "object") return [root.note];
  if (typeof root.body === "string" || typeof root.text === "string" || typeof root.content === "string") return [root];
  return [];
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function text(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function israelTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("he-IL", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Jerusalem",
  }).format(parsed);
}
