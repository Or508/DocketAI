"use client";

import type { CaseRead, CaseWorkspace, ProcessRead } from "@docketai/shared-types";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { StatusPill } from "@/components/status-pill";
import { Wordmark } from "@/components/wordmark";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { OfficeBar } from "@/components/office-bar";
import { ApiError, api } from "@/lib/api";
import { folderFromWorkspace, processLabel, type FolderTone } from "@/lib/filing";
import { formatWhen } from "@/lib/utils";

type Card = {
  item: CaseRead;
  tone: FolderTone;
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
          <div className="mt-4 grid gap-4">
            {cards.length === 0 ? (
              <p className="rounded-lg border-2 border-dashed border-ink/20 bg-white p-5 text-sm text-ink">אין עדיין תיקיות.</p>
            ) : (
              cards.map((card) => <FolderCard key={card.item.id} card={card} />)
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function FolderCard({ card }: { card: Card }) {
  const docPct = card.docsTotal ? Math.round((card.docsDone / card.docsTotal) * 100) : 0;
  const fieldPct = card.fieldsTotal ? Math.round((card.fieldsDone / card.fieldsTotal) * 100) : 0;
  return (
    <a
      href={`/cases/${card.item.id}`}
      className="block rounded-lg border-2 border-ink/15 bg-white p-5 shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-tide hover:shadow-lg"
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
    return { item, tone, docsDone: item.document_count, docsTotal: Math.max(item.document_count, 1), fieldsDone: 0, fieldsTotal: 0 };
  }
  const docsTotal = workspace.process.required_documents.reduce((sum, document) => sum + document.min_count, 0);
  const docsDone = docsTotal - workspace.gap.missing.reduce((sum, document) => sum + Math.max(document.required_count - document.found_count, 0), 0);
  const fields = workspace.process.required_fields.filter((field) => field.required);
  const fieldsDone = fields.filter((field) => (workspace.field_values[field.key] ?? "").trim()).length;
  return {
    item,
    tone: folderFromWorkspace(workspace),
    docsDone: Math.max(docsDone, 0),
    docsTotal,
    fieldsDone,
    fieldsTotal: fields.length,
  };
}
