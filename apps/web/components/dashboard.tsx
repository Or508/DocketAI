"use client";

import type { CaseRead, CaseWorkspace, ProcessRead } from "@docketai/shared-types";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, FolderOpen, PenLine, Plus, Search, Trash2 } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import { WhatsAppReminder } from "@/components/whatsapp-reminder";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { OfficeTopNav } from "@/components/OfficeTopNav";
import { ApiError, api, detailFrom, downloadCaseArchive } from "@/lib/api";
import { archiveFilename } from "@/lib/dispatch";
import { dispatchFormTitle, folderFromWorkspace, processFamily, processLabel, type FolderTone, type ProcessFamily } from "@/lib/filing";
import { hebrewOfficeError } from "@/lib/hebrew";
import { readOfficeSettings } from "@/lib/office-settings";
import { formatWhen } from "@/lib/utils";

type Bucket = "all" | "preparing" | "awaiting" | "done";

const BUCKETS: { id: Bucket; label: string }[] = [
  { id: "all", label: "הכל" },
  { id: "preparing", label: "בהכנה במשרד" },
  { id: "awaiting", label: "ממתין לחתימת לקוח" },
  { id: "done", label: "נחתם" },
];

type ProcessFilter = "all" | Exclude<ProcessFamily, "other">;

const PROCESS_FILTERS: { id: ProcessFilter; label: string }[] = [
  { id: "all", label: "כל הסוגים" },
  { id: "bl_6101", label: "בל/6101" },
  { id: "onboarding", label: "טופס 101" },
  { id: "real_estate", label: "מקרקעין" },
];

const NEW_CASE_KINDS = [
  { family: "bl_6101" as const, prefer: "bl_6101", label: "בל/6101", detail: "דיווח רב-שנתי לביטוח לאומי" },
  { family: "onboarding" as const, prefer: "employee_onboarding", label: "טופס 101", detail: "קליטת עובד חדש" },
  { family: "real_estate" as const, prefer: "real_estate", label: "עסקת מקרקעין", detail: "חוזה מכר ופרטי הנכס" },
];

function isDraft(tone: FolderTone) {
  return tone !== "done" && tone !== "awaiting";
}

function bucketOf(tone: FolderTone): Exclude<Bucket, "all"> {
  if (tone === "done") return "done";
  if (tone === "awaiting") return "awaiting";
  return "preparing";
}

type Card = {
  item: CaseRead;
  tone: FolderTone;
  phone: string;
  docsDone: number;
  docsTotal: number;
  fieldsDone: number;
  fieldsTotal: number;
};

export function Dashboard() {
  const router = useRouter();
  const [processes, setProcesses] = useState<ProcessRead[]>([]);
  const [cards, setCards] = useState<Card[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [bucket, setBucket] = useState<Bucket>("all");
  const [actionError, setActionError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [processFilter, setProcessFilter] = useState<ProcessFilter>("all");
  const [selected, setSelected] = useState<string[]>([]);
  const [createOpen, setCreateOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.processes(), api.cases()])
      .then(async ([nextProcesses, nextCases]) => {
        if (cancelled) return;
        setProcesses(nextProcesses);
        const loaded = await Promise.all(
          nextCases.map(async (item) => {
            try {
              return toCard(item, await api.workspace(item.id));
            } catch {
              return toCard(item, null);
            }
          }),
        );
        if (!cancelled) setCards(loaded);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setLoadError(reason instanceof ApiError ? reason.message : "לא ניתן להגיע לארון התיוק.");
          setCards([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function downloadArchive(card: Card) {
    setActingId(card.item.id);
    setActionError(null);
    try {
      await downloadCaseArchive(card.item.id, archiveFilename(card.item.client_name || card.item.name));
    } catch (reason) {
      setActionError(hebrewOfficeError(reason));
    } finally {
      setActingId(null);
    }
  }

  async function exportCsv() {
    setExporting(true);
    setActionError(null);
    try {
      const response = await fetch("/api/analytics/export.csv", { cache: "no-store" });
      if (response.status === 401) {
        window.location.assign(`/login?next=${encodeURIComponent("/cases")}`);
        return;
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
      const blob = await response.blob();
      const match = /filename="?([^";]+)"?/i.exec(response.headers.get("Content-Disposition") ?? "");
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = match?.[1] || "analytics.csv";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setActionError(hebrewOfficeError(reason));
    } finally {
      setExporting(false);
    }
  }

  async function deleteDraft(card: Card) {
    const label = card.item.client_name || card.item.name;
    if (!window.confirm(`למחוק את תיק הטיוטה של ${label}? התיק והקבצים שבו יימחקו.`)) return;
    setActingId(card.item.id);
    setActionError(null);
    try {
      const response = await fetch(`/api/cases/${card.item.id}`, { method: "DELETE" });
      if (response.status === 401) {
        window.location.assign(`/login?next=${encodeURIComponent("/cases")}`);
        return;
      }
      if (!response.ok && response.status !== 204) {
        let message = response.statusText;
        try {
          message = detailFrom(await response.json());
        } catch {
          message = response.statusText;
        }
        throw new ApiError(message || "Request failed", response.status);
      }
      setCards((current) => (current ?? []).filter((item) => item.item.id !== card.item.id));
      setSelected((current) => current.filter((id) => id !== card.item.id));
    } catch (reason) {
      setActionError(hebrewOfficeError(reason));
    } finally {
      setActingId(null);
    }
  }

  async function deleteSelected(ids: string[]) {
    if (!ids.length) return;
    if (!window.confirm(`למחוק ${ids.length} תיקי טיוטה? התיקים והקבצים שבהם יימחקו.`)) return;
    setActingId("bulk");
    setActionError(null);
    const removed: string[] = [];
    let failure: string | null = null;
    for (const id of ids) {
      try {
        const response = await fetch(`/api/cases/${id}`, { method: "DELETE" });
        if (response.status === 401) {
          window.location.assign(`/login?next=${encodeURIComponent("/cases")}`);
          return;
        }
        if (!response.ok && response.status !== 204) {
          let message = response.statusText;
          try {
            message = detailFrom(await response.json());
          } catch {
            message = response.statusText;
          }
          throw new ApiError(message || "Request failed", response.status);
        }
        removed.push(id);
      } catch (reason) {
        failure = hebrewOfficeError(reason);
        break;
      }
    }
    if (removed.length) {
      const gone = new Set(removed);
      setCards((current) => (current ?? []).filter((card) => !gone.has(card.item.id)));
      setSelected((current) => current.filter((id) => !gone.has(id)));
    }
    setActionError(failure);
    setActingId(null);
  }

  function toggleSelected(id: string) {
    setSelected((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  const all = cards ?? [];
  const needle = query.trim().toLowerCase();
  const visible = all.filter((card) => {
    if (bucket !== "all" && bucketOf(card.tone) !== bucket) return false;
    if (processFilter !== "all" && processFamily(card.item.process_key) !== processFilter) return false;
    if (!needle) return true;
    const haystack = [card.item.client_name, card.item.name, card.item.id].filter(Boolean).join(" ").toLowerCase();
    return haystack.includes(needle);
  });
  const selectedIds = selected.filter((id) => visible.some((card) => card.item.id === id && isDraft(card.tone)));
  const countOf = (id: Bucket) => (id === "all" ? all.length : all.filter((card) => bucketOf(card.tone) === id).length);

  return (
    <main className="mx-auto min-h-screen max-w-6xl px-5 py-6 lg:px-10 lg:py-10">
      <OfficeTopNav />

      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-ink">תיקיות לקוח</h1>
          <p className="mt-1 text-mist">כל תיקי הלקוחות של המשרד, ממה שעוד חסר ועד מה שכבר נחתם.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" onClick={() => setCreateOpen(true)}>
            <Plus aria-hidden className="h-4 w-4" />
            פתיחת תיק חדש
          </Button>
          <Button type="button" variant="outline" disabled={exporting} onClick={() => void exportCsv()}>
            <Download aria-hidden className="h-4 w-4" />
            {exporting ? "מייצא…" : "ייצוא לאקסל"}
          </Button>
        </div>
      </header>

      <section className="mt-8 overflow-hidden rounded-lg border border-line bg-white shadow-card" aria-label="רשימת התיקים">
        <div className="border-b border-line p-4">
          <div className="relative">
            <Search aria-hidden className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-mist" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="חיפוש לפי שם לקוח או מספר תיק"
              aria-label="חיפוש לפי שם לקוח או מספר תיק"
              className="h-10 ps-9 shadow-none"
            />
          </div>
        </div>
        <div className="space-y-2 border-b border-line bg-[#fbfbf9] px-4 py-3">
          <Segmented
            label="סינון לפי מצב התיק"
            items={BUCKETS.map((item) => ({ id: item.id, label: item.label, count: cards ? countOf(item.id) : null }))}
            value={bucket}
            onChange={setBucket}
          />
          <Segmented label="סינון לפי סוג תהליך" items={PROCESS_FILTERS} value={processFilter} onChange={setProcessFilter} />
        </div>

        {selectedIds.length > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-[#fbf1ee] px-4 py-2.5">
            <p className="text-sm font-semibold text-ink">נבחרו {selectedIds.length} תיקי טיוטה</p>
            <Button type="button" size="sm" variant="danger" disabled={actingId === "bulk"} onClick={() => void deleteSelected(selectedIds)}>
              <Trash2 aria-hidden className="h-3.5 w-3.5" />
              {actingId === "bulk" ? "מוחק…" : "מחיקת הטיוטות שנבחרו"}
            </Button>
          </div>
        ) : null}

        {actionError || loadError ? (
          <p className="border-b border-line bg-[#fbf1ee] px-4 py-3 text-sm font-medium text-clay" role="alert">
            {actionError ?? loadError}
          </p>
        ) : null}

        {cards === null ? (
          <ListSkeleton />
        ) : all.length === 0 ? (
          <EmptyState
            title="הארון עדיין ריק"
            body="פתחו את התיק הראשון: בחרו לקוח ותהליך, והמערכת תבקש ממנו את המסמכים ותמלא את הטופס."
            action={
              <Button type="button" onClick={() => setCreateOpen(true)}>
                <Plus aria-hidden className="h-4 w-4" />
                פתיחת תיק ראשון
              </Button>
            }
          />
        ) : visible.length === 0 ? (
          <EmptyState title="אין תיקים שמתאימים לסינון" body="נסו חיפוש אחר, או הציגו את כל התיקים." />
        ) : (
          <ul className="divide-y divide-line">
            {visible.map((card) => (
              <CaseRow
                key={card.item.id}
                card={card}
                busy={actingId === card.item.id}
                onDownload={() => void downloadArchive(card)}
                onDelete={isDraft(card.tone) ? () => void deleteDraft(card) : undefined}
                remind={card.tone === "awaiting"}
                selected={selected.includes(card.item.id)}
                onToggle={isDraft(card.tone) ? () => toggleSelected(card.item.id) : undefined}
              />
            ))}
          </ul>
        )}
      </section>

      <NewCaseDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        processes={processes}
        onCreated={(id) => router.push(`/cases/${id}`)}
      />
    </main>
  );
}

function NewCaseDialog({
  open,
  onOpenChange,
  processes,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  processes: ProcessRead[];
  onCreated: (id: string) => void;
}) {
  const [clientName, setClientName] = useState("");
  const [caseName, setCaseName] = useState("");
  const [family, setFamily] = useState<(typeof NEW_CASE_KINDS)[number]["family"]>("bl_6101");
  const [loadForm, setLoadForm] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Each time the dialog opens it starts clean, with the office's own default for the blank form.
  useEffect(() => {
    if (!open) return;
    setClientName("");
    setCaseName("");
    setError(null);
    setBusy(false);
    setLoadForm(readOfficeSettings().autoLoadForm);
  }, [open]);

  const kinds = NEW_CASE_KINDS.map((kind) => ({
    ...kind,
    process:
      processes.find((process) => process.key === kind.prefer) ??
      processes.find((process) => processFamily(process.key) === kind.family),
  }));
  const chosen = kinds.find((kind) => kind.family === family);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!chosen?.process) return;
    setBusy(true);
    setError(null);
    try {
      const client = clientName.trim();
      const created = await api.createCase({
        name: caseName.trim() || client || chosen.label,
        process_key: chosen.process.key,
        client_name: client || undefined,
      });
      if (loadForm) {
        try {
          await api.loadDefaultForm(created.id);
        } catch {
          /* The case is open. The workspace can load the blank form again. */
        }
      }
      onCreated(created.id);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "לא ניתן לפתוח את התיק.");
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(92vw,34rem)]">
        <DialogTitle>תיק חדש</DialogTitle>
        <p className="mt-1 text-sm text-mist">בחרו לקוח ותהליך. את המסמכים והפרטים משלימים בתוך התיק.</p>
        <form onSubmit={submit} className="mt-5 space-y-5">
          <div>
            <label className="block text-sm font-semibold text-ink" htmlFor="new-client">
              שם הלקוח
            </label>
            <Input
              id="new-client"
              className="mt-1.5"
              value={clientName}
              onChange={(event) => setClientName(event.target.value)}
              placeholder="לדוגמה: דנה כהן"
              autoFocus
            />
          </div>

          <fieldset>
            <legend className="text-sm font-semibold text-ink">תהליך</legend>
            <div className="mt-1.5 grid gap-2 sm:grid-cols-3">
              {kinds.map((kind) => {
                const active = kind.family === family;
                return (
                  <label
                    key={kind.family}
                    className={`cursor-pointer rounded-md border p-3 transition-colors ${
                      kind.process ? "" : "pointer-events-none opacity-50"
                    } ${active ? "border-tide bg-mint ring-1 ring-tide" : "border-line hover:border-ink/25"}`}
                  >
                    <input
                      type="radio"
                      name="new-case-kind"
                      className="sr-only"
                      checked={active}
                      disabled={!kind.process}
                      onChange={() => setFamily(kind.family)}
                    />
                    <span className="block text-sm font-semibold text-ink">{kind.label}</span>
                    <span className="mt-0.5 block text-xs text-mist">{kind.detail}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <div>
            <label className="block text-sm font-semibold text-ink" htmlFor="new-case-name">
              שם התיק <span className="font-normal text-mist">(לא חובה)</span>
            </label>
            <Input
              id="new-case-name"
              className="mt-1.5"
              value={caseName}
              onChange={(event) => setCaseName(event.target.value)}
              placeholder={clientName.trim() || chosen?.label || ""}
            />
          </div>

          <label className="flex items-start gap-3 rounded-md bg-paper p-3 text-sm">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-[#0e4f49]"
              checked={loadForm}
              onChange={(event) => setLoadForm(event.target.checked)}
            />
            <span>
              <span className="block font-semibold text-ink">לטעון את הטופס הריק לתיק</span>
              <span className="block text-mist">הטופס הרשמי של התהליך ייטען מיד, מוכן למילוי.</span>
            </span>
          </label>

          {error ? (
            <p className="text-sm font-medium text-clay" role="alert">
              {error}
            </p>
          ) : null}

          <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-4">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              ביטול
            </Button>
            <Button type="submit" disabled={busy || !chosen?.process}>
              {busy ? "פותח…" : "פתיחת התיק"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function CaseRow({
  card,
  busy,
  onDownload,
  onDelete,
  remind,
  selected = false,
  onToggle,
}: {
  card: Card;
  busy: boolean;
  onDownload: () => void;
  onDelete?: () => void;
  remind?: boolean;
  selected?: boolean;
  onToggle?: () => void;
}) {
  const title = card.item.client_name || card.item.name;
  const whole = card.docsTotal + card.fieldsTotal;
  const readiness = whole ? Math.round(((card.docsDone + card.fieldsDone) / whole) * 100) : 0;
  return (
    <li
      className={`group grid grid-cols-[1.25rem_minmax(0,1fr)] items-center gap-x-4 gap-y-3 px-4 py-4 transition-colors hover:bg-[#fbfbf9] md:grid-cols-[1.25rem_minmax(0,1fr)_11rem_10rem_11rem] ${
        selected ? "bg-[#fbf1ee]" : ""
      }`}
    >
      <span className="flex justify-center">
        {onToggle ? (
          <input
            type="checkbox"
            className="h-4 w-4 accent-[#0e4f49]"
            checked={selected}
            onChange={onToggle}
            aria-label={`בחירת תיק הטיוטה של ${title}`}
          />
        ) : null}
      </span>

      <a href={`/cases/${card.item.id}`} className="flex min-w-0 items-center gap-3 rounded-md">
        <span
          aria-hidden
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-mint text-sm font-bold text-tide"
        >
          {initials(title)}
        </span>
        <span className="min-w-0">
          <span className="block truncate font-semibold text-ink group-hover:text-tide">{title}</span>
          <span className="mt-0.5 block truncate text-sm text-mist">
            {processLabel(card.item.process_key, card.item.process_name)} · {formatWhen(card.item.updated_at)}
          </span>
        </span>
      </a>

      <div className="col-start-2 md:col-start-auto" title={`מסמכים ${card.docsDone}/${card.docsTotal} · פרטים ${card.fieldsDone}/${card.fieldsTotal}`}>
        <div className="flex items-center justify-between text-xs text-mist">
          <span>מוכנות</span>
          <span className="font-semibold tabular-nums text-ink">{readiness}%</span>
        </div>
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink/10">
          <div
            className={`h-full rounded-full transition-all duration-500 ${readiness === 100 ? "bg-moss" : "bg-tide"}`}
            style={{ width: `${readiness}%` }}
          />
        </div>
        <div className="mt-1 flex gap-3 text-[11px] text-mist">
          <span>מסמכים {card.docsDone}/{card.docsTotal}</span>
          <span>פרטים {card.fieldsDone}/{card.fieldsTotal}</span>
        </div>
      </div>

      <div className="col-start-2 md:col-start-auto">
        <StatusPill tone={card.tone} />
      </div>

      <div className="col-start-2 flex items-center gap-1 md:col-start-auto md:justify-end">
        {remind ? (
          <WhatsAppReminder
            className="h-8 px-2.5 text-xs"
            clientName={title}
            phone={card.phone}
            formTitle={dispatchFormTitle(card.item.process_key)}
          />
        ) : null}
        <IconButton label={`הורדת התיק של ${title} כקובץ ZIP`} disabled={busy} onClick={onDownload}>
          <Download className="h-4 w-4" />
        </IconButton>
        <a
          href={`/cases/${card.item.id}`}
          aria-label={`פתיחת התיק של ${title}`}
          title="פתיחת התיק"
          className="flex h-8 w-8 items-center justify-center rounded-md text-mist transition-colors hover:bg-ink/5 hover:text-ink"
        >
          <PenLine aria-hidden className="h-4 w-4" />
        </a>
        {onDelete ? (
          <IconButton label={`מחיקת תיק הטיוטה של ${title}`} disabled={busy} onClick={onDelete} danger>
            <Trash2 className="h-4 w-4" />
          </IconButton>
        ) : null}
      </div>
    </li>
  );
}

/**
 * A compact segmented control: one choice at a time, with an optional count on each segment.
 * It is only as wide as its segments; on a narrow screen it scrolls sideways instead of wrapping.
 */
function Segmented<T extends string>({
  label,
  items,
  value,
  onChange,
}: {
  label: string;
  items: { id: T; label: string; count?: number | null }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div
      className="no-scrollbar flex w-full min-w-0 gap-1.5 overflow-x-auto whitespace-nowrap rounded-lg border border-line bg-paper p-0.5"
      role="tablist"
      aria-label={label}
    >
      {items.map((item) => {
        const active = value === item.id;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.id)}
            className={`inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md px-3 text-sm transition-colors ${
              active ? "bg-white font-semibold text-ink shadow-sm ring-1 ring-line" : "font-medium text-mist hover:text-ink"
            }`}
          >
            {item.label}
            {item.count !== undefined && item.count !== null ? (
              <span
                className={`min-w-5 rounded-full px-1.5 text-center text-xs tabular-nums ${
                  active ? "bg-mint text-tide" : "bg-ink/5 text-mist"
                }`}
              >
                {item.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

function IconButton({
  label,
  disabled,
  onClick,
  danger = false,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={`flex h-8 w-8 items-center justify-center rounded-md text-mist transition-colors disabled:opacity-40 ${
        danger ? "hover:bg-[#fbf1ee] hover:text-clay" : "hover:bg-ink/5 hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

function EmptyState({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-16 text-center">
      <span aria-hidden className="flex h-12 w-12 items-center justify-center rounded-full bg-mint text-tide">
        <FolderOpen className="h-6 w-6" />
      </span>
      <p className="mt-4 font-semibold text-ink">{title}</p>
      <p className="mt-1 max-w-sm text-sm text-mist">{body}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

function ListSkeleton() {
  return (
    <ul className="divide-y divide-line" aria-busy="true" aria-label="טוען תיקים">
      {[0, 1, 2].map((row) => (
        <li key={row} className="flex items-center gap-4 px-4 py-5">
          <span className="w-5" />
          <span className="h-10 w-10 animate-pulse rounded-full bg-ink/5" />
          <span className="flex-1 space-y-2">
            <span className="block h-3.5 w-40 animate-pulse rounded bg-ink/5" />
            <span className="block h-3 w-64 animate-pulse rounded bg-ink/5" />
          </span>
        </li>
      ))}
    </ul>
  );
}

function initials(name: string) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  return words.length === 1 ? words[0].charAt(0) : `${words[0].charAt(0)}${words[words.length - 1].charAt(0)}`;
}

function toCard(item: CaseRead, workspace: CaseWorkspace | null): Card {
  if (!workspace) {
    const tone = item.status === "signed" ? "done" : item.status === "filling" ? "awaiting" : item.status === "ready_for_review" ? "review" : "missing";
    return { item, tone, phone: "", docsDone: item.document_count, docsTotal: Math.max(item.document_count, 1), fieldsDone: 0, fieldsTotal: 0 };
  }
  const docsTotal = workspace.process.required_documents.reduce((sum, document) => sum + document.min_count, 0);
  const docsDone = docsTotal - workspace.gap.missing.reduce((sum, document) => sum + Math.max(document.required_count - document.found_count, 0), 0);
  const fields = workspace.process.required_fields.filter((field) => field.required);
  const fieldsDone = fields.filter((field) => (workspace.field_values[field.key] ?? "").trim()).length;
  return {
    item,
    phone: workspace.field_values.phone ?? "",
    tone: folderFromWorkspace(workspace),
    docsDone: Math.max(docsDone, 0),
    docsTotal,
    fieldsDone,
    fieldsTotal: fields.length,
  };
}
