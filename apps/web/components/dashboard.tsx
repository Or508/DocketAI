"use client";

import type { CaseRead, ProcessRead } from "@docketai/shared-types";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { StatusPill } from "@/components/status-pill";
import { Wordmark } from "@/components/wordmark";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api, apiBaseUrl } from "@/lib/api";
import { formatWhen } from "@/lib/utils";

export function Dashboard() {
  const router = useRouter();
  const [processes, setProcesses] = useState<ProcessRead[]>([]);
  const [cases, setCases] = useState<CaseRead[]>([]);
  const [name, setName] = useState("");
  const [clientName, setClientName] = useState("");
  const [processKey, setProcessKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.processes(), api.cases()])
      .then(([nextProcesses, nextCases]) => {
        if (cancelled) return;
        setProcesses(nextProcesses);
        setCases(nextCases);
        setProcessKey((current) => current || nextProcesses[0]?.key || "");
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof ApiError ? reason.message : `Cannot reach ${apiBaseUrl}`);
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
      setError(reason instanceof ApiError ? reason.message : "Could not open the case.");
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col px-5 py-8">
      <header className="flex items-end justify-between border-b border-line pb-5">
        <div>
          <Wordmark />
          <p className="mt-3 max-w-xl text-sm text-mist">
            Open a case, drop in the bundle, and the checklist shows what is identified, missing, or waiting on a person.
          </p>
        </div>
      </header>

      <div className="mt-8 grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <form onSubmit={onSubmit} className="h-fit rounded-lg border border-line bg-white/75 p-5 shadow-card">
          <h1 className="font-serif text-3xl">New case</h1>
          <label className="mt-5 block text-xs uppercase tracking-[0.16em] text-mist" htmlFor="case-name">
            Matter name
          </label>
          <Input id="case-name" className="mt-2" value={name} onChange={(event) => setName(event.target.value)} required />
          <label className="mt-4 block text-xs uppercase tracking-[0.16em] text-mist" htmlFor="client-name">
            Client
          </label>
          <Input
            id="client-name"
            className="mt-2"
            value={clientName}
            onChange={(event) => setClientName(event.target.value)}
          />
          <label className="mt-4 block text-xs uppercase tracking-[0.16em] text-mist" htmlFor="process">
            Process
          </label>
          <select
            id="process"
            className="mt-2 h-10 w-full rounded-md border border-line bg-white px-3 text-sm"
            value={processKey}
            onChange={(event) => setProcessKey(event.target.value)}
          >
            {processes.map((process) => (
              <option key={process.key} value={process.key}>
                {process.name}
              </option>
            ))}
          </select>
          {processKey ? (
            <p className="mt-3 text-sm text-mist">{processes.find((item) => item.key === processKey)?.description}</p>
          ) : null}
          {error ? <p className="mt-3 text-sm text-clay">{error}</p> : null}
          <Button className="mt-5 w-full" type="submit" disabled={busy || !processKey}>
            {busy ? "Opening…" : "Open case"}
          </Button>
        </form>

        <section>
          <h2 className="font-serif text-2xl">Open matters</h2>
          <div className="mt-4 divide-y divide-line overflow-hidden rounded-lg border border-line bg-white/75">
            {cases.length === 0 ? (
              <p className="p-5 text-sm text-mist">No cases yet.</p>
            ) : (
              cases.map((item) => (
                <a key={item.id} href={`/cases/${item.id}`} className="flex items-center justify-between gap-4 px-5 py-4 hover:bg-white">
                  <span>
                    <span className="block font-medium">{item.name}</span>
                    <span className="text-sm text-mist">
                      {item.client_name ? `${item.client_name} · ` : ""}
                      {item.process_name} · {item.document_count} files · {formatWhen(item.updated_at)}
                    </span>
                  </span>
                  <StatusPill status={item.status} />
                </a>
              ))
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
