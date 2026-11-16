"use client";

import type { CaseRead, CaseWorkspace, ProcessRead } from "@docketai/shared-types";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { StatusPill } from "@/components/status-pill";
import { WhatsAppReminder } from "@/components/whatsapp-reminder";
import { Wordmark } from "@/components/wordmark";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { OfficeBar } from "@/components/office-bar";
import { ApiError, api, detailFrom, downloadCaseArchive } from "@/lib/api";
import { archiveFilename } from "@/lib/dispatch";
import { folderFromWorkspace, processLabel, type FolderTone } from "@/lib/filing";
import { hebrewOfficeError } from "@/lib/hebrew";
import { formatWhen } from "@/lib/utils";

type Bucket = "all" | "preparing" | "awaiting" | "done";

const FILTERS: { id: Bucket; label: string }[] = [
  { id: "all", label: "הכל" },
  { id: "preparing", label: "בהכנה במשרד" },
  { id: "awaiting", label: "ממתין לחתימת לקוח" },
  { id: "done", label: "נחתם" },
];

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
  const [cards, setCards] = useState<Card[]>([]);
  const [name, setName] = useState("");
  const [clientName, setClientName] = useState("");
  const [processKey, setProcessKey] = useState("bl_6101");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [bucket, setBucket] = useState<Bucket>("all");
  const [actionError, setActionError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.processes(), api.cases()])
      .then(async ([nextProcesses, nextCases]) => {
        if (cancelled) return;
        setProcesses(nextProcesses);
        setProcessKey((current) => current || nextProcesses.find((item) => item.key === "bl_6101")?.key || nextProcesses[0]?.key || "");
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
        if (!cancelled) setError(reason instanceof ApiError ? reason.message : "לא ניתן להגיע לארון התיוק.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.createCase({
        name,
        process_key: processKey,
        client_name: clientName || undefined,
      });
      router.push(`/cases/${created.id}`);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "לא ניתן לפתוח את התיק.");
      setBusy(false);
    }
  }

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
      setCards((current) => current.filter((item) => item.item.id !== card.item.id));
    } catch (reason) {
      setActionError(hebrewOfficeError(reason));
    } finally {
      setActingId(null);
    }
  }

  const needle = query.trim().toLowerCase();
  const visible = cards.filter((card) => {
    if (bucket !== "all" && bucketOf(card.tone) !== bucket) return false;
    if (!needle) return true;
    const haystack = [card.item.client_name, card.item.name, card.item.id].filter(Boolean).join(" ").toLowerCase();
    return haystack.includes(needle);
  });

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col px-5 py-8">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b-2 border-ink/15 pb-5">
        <div>
          <Wordmark />
          <div className="mt-3">
            <OfficeBar />
          </div>
          <p className="mt-3 text-sm font-semibold tracking-wide text-tide">ארון תיוק ובקרת מסמכים</p>
          <h1 className="mt-1 font-serif text-4xl text-ink">תיקיות לקוח</h1>
          <nav className="mt-3 flex flex-wrap gap-4 text-sm font-semibold">
            <a className="text-tide underline" href="/templates">
              קטלוג טפסים (/templates)
            </a>
            <a className="text-tide underline" href="/verify">
              אימות חותם ציבורי (/verify)
            </a>
            <a className="text-tide underline" href="/analytics">
              דוחות ואנליטיקה (/analytics)
            </a>
            <button
              type="button"
              className="inline-flex h-10 items-center rounded-md border-2 border-ink/25 bg-white px-3 text-sm font-semibold text-ink"
              disabled={exporting}
              onClick={() => void exportCsv()}
            >
              {exporting ? "מייצא…" : "ייצוא לאקסל (CSV)"}
            </button>
          </nav>
        </div>
      </header>

      <div className="mt-8 grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <form onSubmit={onSubmit} className="h-fit rounded-lg border-2 border-ink/15 bg-white p-5 shadow-card transition duration-200 hover:-translate-y-0.5">
          <h2 className="font-serif text-3xl">תיק חדש</h2>
          <label className="mt-5 block text-sm font-semibold text-ink" htmlFor="case-name">
            שם התיק
          </label>
          <Input id="case-name" className="mt-2" value={name} onChange={(event) => setName(event.target.value)} required />
          <label className="mt-4 block text-sm font-semibold text-ink" htmlFor="client-name">
            שם הלקוח
          </label>
          <Input id="client-name" className="mt-2" value={clientName} onChange={(event) => setClientName(event.target.value)} />
          <label className="mt-4 block text-sm font-semibold text-ink" htmlFor="process">
            תהליך
          </label>
          <select
            id="process"
            className="mt-2 h-11 w-full rounded-md border-2 border-ink/25 bg-white px-3 text-base focus:border-tide focus:outline-none focus:ring-2 focus:ring-tide"
            value={processKey}
            onChange={(event) => setProcessKey(event.target.value)}
          >
            {processes.map((process) => (
              <option key={process.key} value={process.key}>
                {processLabel(process.key, process.name)}
              </option>
            ))}
          </select>
          {error ? (
            <p className="mt-3 text-sm font-medium text-clay" role="alert">
              {error}
            </p>
          ) : null}
          <Button className="mt-5 w-full" type="submit" disabled={busy || !processKey}>
            {busy ? "פותח…" : "פתיחת תיק"}
          </Button>
        </form>

        <section>
          <h2 className="font-serif text-2xl">הארון</h2>
          {actionError ? (
            <p className="mt-3 text-sm font-medium text-clay" role="alert">
              {actionError}
            </p>
          ) : null}
          <div className="mt-4 space-y-3">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="חיפוש לפי שם לקוח או מספרתיק..."
              aria-label="חיפוש לפי שם לקוח או מספרתיק..."
            />
            <div className="flex flex-wrap gap-2" role="tablist" aria-label="סינון לפי מצב">
              {FILTERS.map((item) => {
                const count = item.id === "all" ? cards.length : cards.filter((card) => bucketOf(card.tone) === item.id).length;
                const selected = bucket === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    className={`min-h-11 rounded-md border-2 px-3 text-sm font-semibold ${selected ? "border-tide bg-tide text-white" : "border-ink/15 bg-white text-ink"}`}
                    onClick={() => setBucket(item.id)}
                  >
                    {item.label} ({count})
                  </button>
                );
              })}
            </div>
          </div>
          <div className="mt-4 grid gap-4">
            {cards.length === 0 ? (
              <p className="rounded-lg border-2 border-dashed border-ink/20 bg-white p-5 text-sm text-ink">אין עדיין תיקיות.</p>
            ) : visible.length === 0 ? (
              <p className="rounded-lg border-2 border-dashed border-ink/20 bg-white p-5 text-sm text-ink">אין תיקיות בתצוגה הזו.</p>
            ) : (
              visible.map((card) => (
                <FolderCard
                  key={card.item.id}
                  card={card}
                  busy={actingId === card.item.id}
                  onDownload={() => void downloadArchive(card)}
                  onDelete={card.tone === "done" || card.tone === "awaiting" ? undefined : () => void deleteDraft(card)}
                  remind={card.tone === "awaiting"}
                />
              ))
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function FolderCard({
  card,
  busy,
  onDownload,
  onDelete,
  remind,
}: {
  card: Card;
  busy: boolean;
  onDownload: () => void;
  onDelete?: () => void;
  remind?: boolean;
}) {
  const docPct = card.docsTotal ? Math.round((card.docsDone / card.docsTotal) * 100) : 0;
  const fieldPct = card.fieldsTotal ? Math.round((card.fieldsDone / card.fieldsTotal) * 100) : 0;
  return (
    <article className="overflow-hidden rounded-lg border-2 border-ink/15 bg-white shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-tide hover:shadow-lg">
    <a
      href={`/cases/${card.item.id}`}
      className="block p-5"
    >
      <span className="flex flex-wrap items-start justify-between gap-3">
        <span>
          <span className="block font-serif text-2xl text-ink">{card.item.client_name || card.item.name}</span>
          <span className="mt-1 block text-sm text-ink">
            {processLabel(card.item.process_key, card.item.process_name)} · {formatWhen(card.item.updated_at)}
          </span>
        </span>
        <StatusPill tone={card.tone} />
      </span>
      <span className="mt-4 grid gap-3 sm:grid-cols-2">
        <Meter label="מסמכים" done={card.docsDone} total={card.docsTotal} pct={docPct} />
        <Meter label="פרטים אישיים" done={card.fieldsDone} total={card.fieldsTotal} pct={fieldPct} />
      </span>
    </a>
    <div className="flex flex-wrap gap-2 border-t-2 border-ink/10 px-5 py-3">
      <button
        type="button"
        className="inline-flex h-10 items-center rounded-md border-2 border-ink/25 bg-white px-3 text-sm font-semibold text-ink"
        disabled={busy}
        onClick={onDownload}
      >
        הורד ZIP
      </button>
      {remind ? (
        <WhatsAppReminder clientName={card.item.client_name || card.item.name} phone={card.phone} />
      ) : null}
      {onDelete ? (
        <button
          type="button"
          className="inline-flex h-10 items-center rounded-md border-2 border-clay px-3 text-sm font-semibold text-clay"
          disabled={busy}
          onClick={onDelete}
        >
          מחק תיק טיוטה
        </button>
      ) : null}
    </div>
    </article>
  );
}

function Meter({ label, done, total, pct }: { label: string; done: number; total: number; pct: number }) {
  return (
    <span className="block">
      <span className="mb-1 flex justify-between text-xs font-semibold text-ink">
        <span>{label}</span>
        <span>
          {done}/{total}
        </span>
      </span>
      <span className="block h-2.5 overflow-hidden rounded-full bg-ink/10">
        <span className="block h-full rounded-full bg-tide transition-all duration-500" style={{ width: `${pct}%` }} />
      </span>
    </span>
  );
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
