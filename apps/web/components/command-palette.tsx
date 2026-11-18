"use client";

import type { CaseRead, ProcessRead } from "@docketai/shared-types";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, api } from "@/lib/api";
import { caseOpeners, processLabel } from "@/lib/filing";
import { readOfficeSettings } from "@/lib/office-settings";

const SECTIONS = [
  { href: "/cases", label: "ארון תיקים" },
  { href: "/clients", label: "ספר לקוחות וכספת" },
  { href: "/templates", label: "קטלוג טפסים" },
  { href: "/analytics", label: "דוחות ואנליטיקה" },
  { href: "/verify", label: "אימות חותם" },
  { href: "/audit", label: "יומן אבטחה" },
  { href: "/settings", label: "הגדרות" },
] as const;


export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [cases, setCases] = useState<CaseRead[]>([]);
  const [processes, setProcesses] = useState<ProcessRead[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setQuery("");
    setError(null);
    api
      .me()
      .catch(() => null)
      .then(async (profile) => {
        const [nextCases, nextProcesses] = await Promise.all([api.cases(), api.processes(profile?.profession)]);
        return [nextCases, nextProcesses] as const;
      })
      .then(([nextCases, nextProcesses]) => {
        if (cancelled) return;
        setCases(nextCases);
        setProcesses(nextProcesses);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof ApiError ? reason.message : "לא ניתן לטעון את התיקים.");
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onOpenChange(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  const needle = query.trim().toLowerCase();
  const matches = useMemo(() => {
    const rows = cases.map((item) => ({
      item,
      haystack: [item.client_name, item.name, item.id, item.process_key, item.process_name, processLabel(item.process_key, item.process_name)]
        .filter(Boolean)
        .join(" ")
        .toLowerCase(),
    }));
    const filtered = needle ? rows.filter((row) => row.haystack.includes(needle)) : rows;
    return filtered.slice(0, 8);
  }, [cases, needle]);

  const sections = needle ? SECTIONS.filter((item) => item.label.toLowerCase().includes(needle)) : SECTIONS;
  const openers = caseOpeners(processes);
  const quick = needle ? openers.filter((item) => item.label.toLowerCase().includes(needle)) : openers;

  function go(href: string) {
    onOpenChange(false);
    router.push(href);
  }

  async function openQuick(key: string, label: string) {
    setBusy(true);
    setError(null);
    try {
      const catalog = processes.length ? processes : await api.processes();
      const match = catalog.find((item) => item.key === key);
      if (!match) throw new ApiError("התהליך לא נמצא בקטלוג.", 404);
      const created = await api.createCase({ name: label, process_key: match.key });
      if (readOfficeSettings().autoLoadForm) {
        try {
          await api.loadDefaultForm(created.id);
        } catch {
          /* The case is open. The workspace can load the form again. */
        }
      }
      onOpenChange(false);
      router.push(`/cases/${created.id}`);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "לא ניתן לפתוח את התיק.");
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center bg-[#1c1915]/40 px-4 pt-[12vh]" onMouseDown={() => onOpenChange(false)}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="חיפוש מהיר בתיקים ולקוחות"
        className="w-full max-w-xl rounded-lg border border-ink bg-paper p-4 shadow-card"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <label className="block text-sm font-semibold" htmlFor="command-query">
          חיפוש מהיר בתיקים ולקוחות
        </label>
        <input
          id="command-query"
          autoFocus
          value={query}
          placeholder="שם לקוח, מספר תיק, או סוג תהליך"
          className="mt-2 h-11 w-full rounded-md border border-ink/25 bg-white px-3 text-base"
          onChange={(event) => setQuery(event.target.value)}
        />
        {error ? (
          <p className="mt-3 text-sm font-medium text-clay" role="alert">
            {error}
          </p>
        ) : null}
        <div className="mt-4 grid max-h-[50vh] gap-4 overflow-auto">
          <section>
            <p className="text-xs font-bold text-mist">מעבר במשרד</p>
            <ul className="mt-2 grid gap-1">
              {sections.map((item) => (
                <li key={item.href}>
                  <button type="button" className="w-full rounded-md px-2 py-2 text-start text-sm font-semibold hover:bg-ink/5" onClick={() => go(item.href)}>
                    {item.label}
                  </button>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <p className="text-xs font-bold text-mist">תיקים</p>
            <ul className="mt-2 grid gap-1">
              {matches.length ? (
                matches.map(({ item }) => (
                  <li key={item.id}>
                    <button type="button" className="w-full rounded-md px-2 py-2 text-start hover:bg-ink/5" onClick={() => go(`/cases/${item.id}`)}>
                      <span className="block text-sm font-semibold">{item.client_name || item.name}</span>
                      <span className="block text-xs text-mist">{processLabel(item.process_key, item.process_name)}</span>
                    </button>
                  </li>
                ))
              ) : (
                <li className="px-2 py-2 text-sm text-mist">אין תיק תואם.</li>
              )}
            </ul>
          </section>
          <section>
            <p className="text-xs font-bold text-mist">+ פתיחת תיק מהיר</p>
            <ul className="mt-2 grid gap-1">
              {quick.map((item) => (
                <li key={item.key}>
                  <button
                    type="button"
                    className="w-full rounded-md px-2 py-2 text-start text-sm font-semibold hover:bg-ink/5 disabled:opacity-50"
                    disabled={busy}
                    onClick={() => void openQuick(item.key, item.label)}
                  >
                    {item.label}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
