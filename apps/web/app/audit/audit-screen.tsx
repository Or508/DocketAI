"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { OfficeTopNav } from "@/components/OfficeTopNav";

type AuditEvent = {
  event_id: string;
  case_id: string;
  client_name: string | null;
  case_name: string;
  process_type: string;
  action: string;
  actor: string;
  created_at: string;
  metadata: Record<string, unknown>;
};

type AuditCenter = {
  total_events: number;
  signed_count: number;
  smart_uploads_count: number;
  vault_reuses_count: number;
  revocations_count: number;
  action_counts: Record<string, number>;
  matched_events: number;
  events: AuditEvent[];
};

const ACTION_NAMES: Record<string, string> = {
  auto_classify: "סיווג אוטומטי של מסמך",
  manual_classify: "תיוק מסמך במגירה",
  fill_and_sign: "מילוי וחתימה",
  signature_invalidated: "חתימה בוטלה עקב שינוי",
  signing_link_created: "קישור חתימה נשלח",
  signing_link_revoked: "קישור חתימה בוטל והתיק הוחזר לעריכה",
  field_prefilled: "שדות מולאו מתוך מסמך",
  document_role_changed: "סוג הקובץ שונה",
  document_removed: "מסמך הוסר",
  archive_exported: "ארכיון התיק יוצא",
  case_reopened: "תיק חתום נפתח לתיקון",
  default_form_loaded: "הטופס הריק נטען",
  smart_upload_completed: "העלאה חכמה",
  client_vault_reused: "שימוש חוזר במסמכי הכספת",
  internal_note_added: "הערה פנימית נוספה",
  client_document_uploaded: "הלקוח העלה מסמך",
  intake_link_created: "נוצר קישור להעלאת מסמכים עבור הלקוח",
  client_intake_uploaded: "הלקוח העלה מסמכים מרחוק לתיק",
};
// The filters shown first; the rest follow in the order the office has used them.
const PINNED = ["fill_and_sign", "smart_upload_completed", "client_vault_reused", "signing_link_revoked"];
const PROCESS_NAMES: Record<string, string> = {
  bl_6101: "בל/6101",
  onboarding: "טופס 101 – קליטת עובד",
  employee_onboarding: "טופס 101",
  real_estate: "עסקת מקרקעין",
};
const DRAWER_NAMES: Record<string, string> = {
  id_copy: "תעודת זהות",
  proof_of_address: "אישור כתובת",
  bank_confirmation: "אישור בנק",
  tax_form: "טופס 101",
  title_deed: "נסח טאבו",
  purchase_agreement: "הסכם מכר",
};
const PAGE = 100;
const STAMP = new Intl.DateTimeFormat("he-IL", {
  timeZone: "Asia/Jerusalem",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

function toLogin() {
  window.location.assign(`/login?next=${encodeURIComponent("/audit")}`);
}

function auditExportHref(action: string | null, query: string) {
  const params = new URLSearchParams();
  if (action) params.set("action", action);
  if (query) params.set("q", query);
  const search = params.toString();
  return search ? `/api/audit/export.csv?${search}` : "/api/audit/export.csv";
}

function stamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : STAMP.format(date);
}

function actorName(actor: string): string {
  if (actor === "system") return "המערכת";
  if (actor === "signer" || actor.startsWith("signer")) return "הלקוח החותם";
  if (actor.startsWith("user:")) return "איש צוות";
  return actor;
}

/** One short Hebrew line of what the event's safe details say, or nothing. */
function summary(event: AuditEvent): string | null {
  const data = event.metadata;
  const parts: string[] = [];
  const routed = data.routed_files;
  if (Array.isArray(routed)) {
    const filed = routed.filter((item) => item && typeof item === "object" && (item as { outcome?: string }).outcome === "routed");
    parts.push(`${filed.length} מתוך ${routed.length} קבצים תויקו`);
  }
  if (typeof data.document_type === "string") parts.push(DRAWER_NAMES[data.document_type] ?? data.document_type);
  if (Array.isArray(data.document_types) && data.document_types.length > 0) {
    parts.push(data.document_types.map((item) => DRAWER_NAMES[String(item)] ?? String(item)).join(", "));
  }
  if (typeof data.documents === "number" && !Array.isArray(routed)) parts.push(`${data.documents} מסמכים`);
  if (Array.isArray(data.fields) && data.fields.length > 0) parts.push(`${data.fields.length} שדות`);
  if (typeof data.revoked_links === "number") parts.push(`${data.revoked_links} קישורים בוטלו`);
  if (data.form_loaded === false) parts.push("הטופס הריק לא נטען");
  if (typeof data.verification_id === "string") parts.push(`קוד אימות ${data.verification_id}`);
  return parts.length > 0 ? parts.join(" · ") : null;
}

export function AuditScreen() {
  const [center, setCenter] = useState<AuditCenter | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  // Search as the clerk types, without a request per keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(typed.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [typed]);

  const load = useCallback(async () => {
    const request = ++latest.current;
    setError(null);
    setLoading(true);
    const params = new URLSearchParams({ limit: String(PAGE) });
    if (action) params.set("action", action);
    if (query) params.set("q", query);
    try {
      const response = await fetch(`/api/audit?${params.toString()}`, { cache: "no-store" });
      if (request !== latest.current) return;
      if (response.status === 401) return toLogin();
      if (!response.ok) {
        setError(response.status === 502 ? "לא ניתן להגיע לשירות המשרד." : "טעינת היומן נכשלה.");
        return;
      }
      setCenter((await response.json()) as AuditCenter);
    } catch {
      if (request === latest.current) setError("טעינת היומן נכשלה. בדקו את החיבור ונסו שוב.");
    } finally {
      if (request === latest.current) setLoading(false);
    }
  }, [action, query]);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = center?.action_counts ?? {};
  const pills = [
    ...PINNED.filter((key) => counts[key] || key === action),
    ...Object.keys(counts)
      .filter((key) => !PINNED.includes(key))
      .sort((first, second) => counts[second] - counts[first]),
  ];
  const filtering = Boolean(action || query);

  return (
    <main className="mx-auto min-h-screen max-w-6xl px-5 py-6 lg:px-10 lg:py-10">
      <OfficeTopNav />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
        <h1 className="text-3xl font-bold tracking-tight text-ink">יומן אבטחה</h1>
        <p className="mt-3 max-w-2xl text-mist">
          כל פעולה שנעשתה בתיקי המשרד, מהחדשה לישנה: מי עשה, מתי ובאיזה תיק. היומן מציג מזהים וספירות בלבד, בלי הפרטים
          האישיים של הלקוחות.
        </p>
        </div>
        <a
          href={auditExportHref(action, query)}
          className="inline-flex h-10 items-center rounded-md bg-tide px-3 text-sm font-semibold text-white"
        >
          ייצוא יומן לאקסל (CSV)
        </a>
      </header>

      {error ? (
        <div role="alert" className="mt-8 rounded-lg border border-clay/40 bg-white p-5">
          <p className="font-medium text-clay">{error}</p>
          <button type="button" onClick={() => void load()} className="mt-3 text-sm font-semibold text-tide underline">
            ניסיון נוסף
          </button>
        </div>
      ) : null}
      {!error && center === null ? <p className="mt-8 text-mist">טוענים את היומן…</p> : null}

      {center ? (
        <>
          <dl className="mt-8 grid grid-cols-2 gap-3 text-center sm:grid-cols-5">
            <Kpi label="סך כל הפעולות" value={center.total_events} />
            <Kpi label="חתימות" value={center.signed_count} />
            <Kpi label="העלאות חכמות" value={center.smart_uploads_count} />
            <Kpi label="שימוש חוזר בכספת" value={center.vault_reuses_count} />
            <Kpi label="קישורים שבוטלו" value={center.revocations_count} />
          </dl>

          <section className="mt-8" aria-label="סינון היומן">
            <label htmlFor="audit-search" className="block text-sm font-semibold">
              חיפוש ביומן
            </label>
            <input
              id="audit-search"
              type="search"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              placeholder="שם לקוח, שם תיק או סוג טופס"
              className="mt-2 w-full max-w-md rounded-md border border-ink/20 bg-white px-3 py-2"
            />
            <div role="group" aria-label="סינון לפי סוג פעולה" className="mt-4 flex flex-wrap gap-2">
              <Pill label="כל הפעולות" count={center.total_events} selected={action === null} onSelect={() => setAction(null)} />
              {pills.map((key) => (
                <Pill
                  key={key}
                  label={ACTION_NAMES[key] ?? key}
                  count={counts[key] ?? 0}
                  selected={action === key}
                  onSelect={() => setAction(action === key ? null : key)}
                />
              ))}
            </div>
          </section>

          <p className="mt-6 text-sm text-mist" aria-live="polite">
            {loading
              ? "מעדכנים…"
              : center.matched_events === 0
                ? filtering
                  ? "אין פעולות שמתאימות לסינון."
                  : "עדיין לא נרשמו פעולות ביומן."
                : center.matched_events > center.events.length
                  ? `מוצגות ${center.events.length} הפעולות האחרונות מתוך ${center.matched_events}.`
                  : `${center.matched_events} פעולות.`}
          </p>

          {center.events.length > 0 ? (
            <div className="mt-3 overflow-x-auto rounded-lg border border-ink/15 bg-white shadow-card">
              <table className="w-full min-w-[44rem] text-right text-sm">
                <thead>
                  <tr className="border-b border-line text-xs text-mist">
                    <th scope="col" className="px-4 py-3 font-semibold">
                      מועד (שעון ישראל)
                    </th>
                    <th scope="col" className="px-4 py-3 font-semibold">
                      פעולה
                    </th>
                    <th scope="col" className="px-4 py-3 font-semibold">
                      תיק
                    </th>
                    <th scope="col" className="px-4 py-3 font-semibold">
                      בוצע על ידי
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {center.events.map((event) => {
                    const line = summary(event);
                    return (
                      <tr key={event.event_id} className="border-b border-line/60 align-top last:border-0">
                        <td dir="ltr" className="whitespace-nowrap px-4 py-3 text-right font-mono text-xs">
                          {stamp(event.created_at)}
                        </td>
                        <td className="px-4 py-3">
                          <p className="font-medium">{ACTION_NAMES[event.action] ?? event.action}</p>
                          {line ? <p className="mt-1 text-xs text-mist">{line}</p> : null}
                        </td>
                        <td className="px-4 py-3">
                          <Link href={`/cases/${event.case_id}`} className="font-medium text-tide underline">
                            {event.client_name || event.case_name}
                          </Link>
                          <p className="mt-1 text-xs text-mist">{PROCESS_NAMES[event.process_type] ?? event.process_type}</p>
                        </td>
                        <td className="px-4 py-3 text-mist">{actorName(event.actor)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      ) : null}
    </main>
  );
}

function Pill({
  label,
  count,
  selected,
  onSelect,
}: {
  label: string;
  count: number;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={`inline-flex h-9 items-center gap-2 rounded-full px-3 text-sm font-semibold ${
        selected ? "bg-tide text-white" : "border border-ink/15 bg-white text-ink"
      }`}
    >
      {label}
      <span className={selected ? "text-white/80" : "text-mist"}>{count}</span>
    </button>
  );
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-ink/15 bg-white px-2 py-4">
      <dd className="font-serif text-3xl">{value}</dd>
      <dt className="mt-1 text-xs font-semibold text-mist">{label}</dt>
    </div>
  );
}
