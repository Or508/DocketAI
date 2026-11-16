"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { hebrewOfficeError } from "@/lib/hebrew";

const LABELS: Record<string, string> = {
  case_created: "תיק נוצר",
  created: "תיק נוצר",
  document_uploaded: "מסמך הועלה",
  client_document_uploaded: "מסמך הועלה",
  file_uploaded: "מסמך הועלה",
  upload: "מסמך הועלה",
  default_form_loaded: "טופס בל/6101 נטען מהמערכת",
  document_removed: "קובץ הוסר",
  manual_classify: "סיווג/תפקיד עודכן",
  auto_classify: "סיווג/תפקיד עודכן",
  document_role_changed: "סיווג/תפקיד עודכן",
  field_prefilled: "שדות עודכנו במשרד",
  field_updated: "שדות עודכנו במשרד",
  fields_updated: "שדות עודכנו במשרד",
  signing_link_created: "קישור חתימה נוצר",
  fill_and_sign: "טופס נחתם דיגיטלית",
  signed: "טופס נחתם דיגיטלית",
  case_reopened: "תיק נפתח מחדש לתיקון",
  archive_exported: "תיק יוצא לארכיון ZIP",
  internal_note_added: "הערה פנימית נוספה לתיק",
  signing_link_revoked: "קישור חתימה בוטל",
  signature_invalidated: "החתימה בוטלה",
};

const BADGES: { key: string; label: string }[] = [
  { key: "signer_verification_id", label: "מזהה אימות" },
  { key: "verification_id", label: "מזהה אימות" },
  { key: "superseded_verification_id", label: "מזהה קודם" },
  { key: "file_sha256", label: "SHA-256 קובץ" },
  { key: "signed_pdf_sha256", label: "SHA-256 קובץ" },
  { key: "content_sha256", label: "SHA-256 תוכן" },
  { key: "form_pdf_sha256", label: "SHA-256 טופס" },
  { key: "sha256", label: "SHA-256" },
  { key: "content_hash", label: "SHA-256" },
  { key: "superseded_signed_pdf_sha256", label: "SHA-256 קודם" },
];

type TimelineEvent = {
  id: string;
  action: string;
  at: string;
  details: Record<string, unknown>;
};

export function ActivityTimeline({ caseId }: { caseId: string }) {
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setEvents(eventsFrom(await api.timeline(caseId)));
    } catch (reason) {
      setEvents(null);
      setError(hebrewOfficeError(reason));
    } finally {
      setLoading(false);
    }
  }

  return (
    <details
      className="rounded-lg border-2 border-ink/15 bg-white shadow-card"
      onToggle={(event) => {
        if (event.currentTarget.open && !loading) void load();
      }}
    >
      <summary className="cursor-pointer list-none px-4 py-4 font-serif text-2xl text-ink [&::-webkit-details-marker]:hidden">
        יומן פעילות וביקורת
      </summary>
      <div className="border-t-2 border-ink/10 px-4 py-4">
        {loading ? <p className="text-sm text-ink">טוען את היומן…</p> : null}
        {error ? (
          <p className="text-sm font-medium text-clay" role="alert">
            {error}
          </p>
        ) : null}
        {events && events.length === 0 ? <p className="text-sm text-ink">אין עדיין אירועים ביומן.</p> : null}
        {events && events.length > 0 ? (
          <ol className="grid gap-3">
            {events.map((item) => (
              <li key={item.id} className="rounded-md border-2 border-ink/10 px-3 py-3">
                <p className="font-semibold text-ink">{LABELS[item.action] ?? "אירוע בתיק"}</p>
                <p className="mt-1 text-sm text-ink">
                  <time dateTime={item.at}>{israelTime(item.at)}</time>
                </p>
                <BadgeRow details={item.details} />
              </li>
            ))}
          </ol>
        ) : null}
      </div>
    </details>
  );
}

function BadgeRow({ details }: { details: Record<string, unknown> }) {
  const seen = new Set<string>();
  const badges = BADGES.flatMap(({ key, label }) => {
    const value = details[key];
    if (typeof value !== "string" || !value || seen.has(value)) return [];
    seen.add(value);
    return [{ label, value }];
  });
  if (!badges.length) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-2">
      {badges.map((badge) => (
        <li
          key={`${badge.label}-${badge.value}`}
          title={badge.value}
          className="max-w-full truncate rounded-md border-2 border-tide/30 bg-[#e7f3f2] px-2 py-1 font-mono text-xs text-tide"
          dir="ltr"
        >
          {badge.label}: {shorten(badge.value)}
        </li>
      ))}
    </ul>
  );
}

function shorten(value: string) {
  if (value.length <= 18) return value;
  return `${value.slice(0, 8)}…${value.slice(-4)}`;
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

function eventsFrom(body: unknown): TimelineEvent[] {
  const root = asRecord(body);
  const list = Array.isArray(body)
    ? body
    : Array.isArray(root?.events)
      ? root.events
      : Array.isArray(root?.items)
        ? root.items
        : Array.isArray(root?.timeline)
          ? root.timeline
          : [];
  return list
    .flatMap((item, index) => {
      const row = asRecord(item);
      if (!row) return [];
      const action = stringOf(row.action);
      const at = stringOf(row.created_at) || stringOf(row.at);
      if (!action || !at) return [];
      const details = {
        ...(asRecord(row.previous) ?? {}),
        ...(asRecord(row.previous_value) ?? {}),
        ...(asRecord(row.details) ?? {}),
        ...(asRecord(row.new_value) ?? {}),
        ...(asRecord(row.metadata) ?? {}),
      };
      for (const key of ["signer_verification_id", "verification_id", "file_sha256", "content_sha256"]) {
        if (typeof row[key] === "string") details[key] = row[key];
      }
      const id = stringOf(row.id) || `${at}-${action}-${index}`;
      return [{ id, action, at, details }];
    })
    .sort((left, right) => left.at.localeCompare(right.at));
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function stringOf(value: unknown) {
  return typeof value === "string" ? value : "";
}
