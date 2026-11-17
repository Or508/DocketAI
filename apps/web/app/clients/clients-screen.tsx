"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { OfficeTopNav } from "@/components/OfficeTopNav";

type ClientCase = {
  case_id: string;
  process_type: string;
  status: string;
  created_at: string | null;
  signed_at: string | null;
  verification_id: string | null;
};

type Client = {
  client_key: string;
  client_name: string;
  id_number: string | null;
  phone: string | null;
  address_summary: string | null;
  bank_summary: string | null;
  total_cases: number;
  signed_cases: number;
  reusable_docs_count: number;
  reusable_doc_types: string[];
  latest_case_id: string;
  cases: ClientCase[];
};

const PROCESS_NAMES: Record<string, string> = {
  bl_6101: "בל/6101",
  onboarding: "טופס 101 – קליטת עובד",
  employee_onboarding: "טופס 101",
  real_estate: "עסקת מקרקעין",
};
// The three cases a client's vault can open in one click.
const QUICK_CASES = [
  { process_type: "bl_6101", label: "בל/6101" },
  { process_type: "employee_onboarding", label: "טופס 101" },
  { process_type: "real_estate", label: "עסקת מקרקעין" },
] as const;
const STATUS_NAMES: Record<string, string> = {
  draft: "טיוטה",
  processing: "בקריאה",
  ready_for_review: "ממתין לבדיקה",
  filling: "במילוי",
  signed: "חתום",
  failed: "נכשל",
};
const VAULT_NAMES: Record<string, string> = {
  id_copy: "תעודת זהות",
  proof_of_address: "אישור כתובת",
  bank_confirmation: "אישור בנק",
};
const VAULT_ORDER = ["id_copy", "proof_of_address", "bank_confirmation"];

function toLogin() {
  window.location.assign(`/login?next=${encodeURIComponent("/clients")}`);
}

async function detail(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" && body.detail ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

function day(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString("he-IL");
}

export function ClientsScreen() {
  const [clients, setClients] = useState<Client[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setError(null);
    try {
      const response = await fetch("/api/clients", { cache: "no-store" });
      if (response.status === 401) return toLogin();
      if (!response.ok) {
        setError(response.status === 502 ? "לא ניתן להגיע לשירות המשרד." : "טעינת ספר הלקוחות נכשלה.");
        return;
      }
      setClients((await response.json()) as Client[]);
    } catch {
      setError("טעינת ספר הלקוחות נכשלה. בדקו את החיבור ונסו שוב.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const shown = useMemo(() => {
    const wanted = query.trim().toLowerCase();
    if (!clients || !wanted) return clients;
    return clients.filter((client) =>
      [client.client_name, client.id_number ?? "", client.phone ?? ""].some((value) => value.toLowerCase().includes(wanted)),
    );
  }, [clients, query]);

  const totals = useMemo(() => {
    const list = clients ?? [];
    return {
      clients: list.length,
      cases: list.reduce((sum, client) => sum + client.total_cases, 0),
      ready: list.filter((client) => client.reusable_docs_count > 0).length,
    };
  }, [clients]);

  return (
    <main className="mx-auto min-h-screen max-w-6xl px-5 py-6 lg:px-10 lg:py-10">
      <OfficeTopNav />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-ink">לקוחות</h1>
          <p className="mt-3 max-w-2xl text-mist">
            כל לקוח של המשרד, הפרטים שנקראו מהמסמכים שלו והתיקים שנפתחו עבורו. מסמכים שכבר נמסרו נשמרים בכספת, ותיק חדש
            נפתח מהם בלחיצה אחת.
          </p>
        </div>
      </header>

      {error ? (
        <div role="alert" className="mt-8 rounded-lg border border-clay/40 bg-white p-5">
          <p className="font-medium text-clay">{error}</p>
          <button type="button" onClick={() => void load()} className="mt-3 text-sm font-semibold text-tide underline">
            ניסיון נוסף
          </button>
        </div>
      ) : null}
      {!error && clients === null ? <p className="mt-8 text-mist">טוענים את ספר הלקוחות…</p> : null}

      {clients ? (
        <>
          <dl className="mt-8 grid grid-cols-3 gap-3 text-center">
            <Count label="לקוחות" value={totals.clients} />
            <Count label="תיקים" value={totals.cases} />
            <Count label="לקוחות עם מסמכים בכספת" value={totals.ready} />
          </dl>

          {clients.length > 0 ? (
            <div className="mt-6">
              <label htmlFor="client-search" className="block text-sm font-semibold">
                חיפוש לקוח
              </label>
              <input
                id="client-search"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="שם, מספר זהות או טלפון"
                className="mt-2 w-full max-w-md rounded-md border border-ink/20 bg-white px-3 py-2"
              />
            </div>
          ) : (
            <p className="mt-8 text-mist">
              עדיין אין לקוחות בספר. לקוח מופיע כאן ברגע שנפתח עבורו תיק עם שם לקוח או מספר זהות.
            </p>
          )}
          {clients.length > 0 && shown?.length === 0 ? <p className="mt-6 text-mist">לא נמצא לקוח מתאים.</p> : null}

          <div className="mt-6 space-y-6">
            {shown?.map((client) => (
              <ClientCard key={client.client_key} client={client} />
            ))}
          </div>
        </>
      ) : null}
    </main>
  );
}

function ClientCard({ client }: { client: Client }) {
  const headingId = `client-${client.latest_case_id}`;
  return (
    <article aria-labelledby={headingId} className="rounded-lg border border-ink/15 bg-white p-6 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 id={headingId} className="font-serif text-2xl leading-snug">
            {client.client_name}
          </h2>
          <p className="mt-1 text-sm text-mist">
            {client.total_cases === 1 ? "תיק אחד" : `${client.total_cases} תיקים`}
            {client.signed_cases > 0 ? ` · ${client.signed_cases} חתומים` : ""}
          </p>
        </div>
        {client.id_number ? (
          <span className="rounded-full border border-tide/40 bg-tide/10 px-3 py-1 text-sm font-semibold text-tide">
            ✓ מזוהה לפי מספר זהות
          </span>
        ) : (
          <span className="rounded-full border border-line bg-paper/40 px-3 py-1 text-sm text-mist">מזוהה לפי שם בלבד</span>
        )}
      </div>

      <dl className="mt-5 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
        <Detail label="מספר זהות" value={client.id_number} ltr />
        <Detail label="טלפון" value={client.phone} ltr />
        <Detail label="כתובת" value={client.address_summary} />
        <Detail label="חשבון בנק" value={client.bank_summary} />
      </dl>

      <section className="mt-6" aria-label="מסמכים בכספת">
        <h3 className="text-sm font-semibold">מסמכים בכספת</h3>
        <ul className="mt-2 flex flex-wrap gap-2 text-sm">
          {VAULT_ORDER.map((type) => {
            const held = client.reusable_doc_types.includes(type);
            return (
              <li
                key={type}
                className={
                  held
                    ? "rounded-md border border-tide/40 bg-tide/10 px-3 py-1 font-medium text-tide"
                    : "rounded-md border border-dashed border-line px-3 py-1 text-mist"
                }
              >
                {held ? "✓ " : ""}
                {VAULT_NAMES[type]}
                {held ? "" : " – חסר"}
              </li>
            );
          })}
        </ul>
      </section>

      <section className="mt-6" aria-label="תיקים">
        <h3 className="text-sm font-semibold">תיקים</h3>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[32rem] text-right text-sm">
            <thead>
              <tr className="border-b border-line text-xs text-mist">
                <th scope="col" className="py-2 pl-3 font-semibold">
                  טופס
                </th>
                <th scope="col" className="py-2 pl-3 font-semibold">
                  מצב
                </th>
                <th scope="col" className="py-2 pl-3 font-semibold">
                  נפתח
                </th>
                <th scope="col" className="py-2 pl-3 font-semibold">
                  נחתם
                </th>
                <th scope="col" className="py-2 font-semibold">
                  קוד אימות
                </th>
              </tr>
            </thead>
            <tbody>
              {client.cases.map((item) => (
                <tr key={item.case_id} className="border-b border-line/60 last:border-0">
                  <td className="py-2 pl-3">
                    <Link href={`/cases/${item.case_id}`} className="font-medium text-tide underline">
                      {PROCESS_NAMES[item.process_type] ?? item.process_type}
                    </Link>
                  </td>
                  <td className="py-2 pl-3">{STATUS_NAMES[item.status] ?? item.status}</td>
                  <td className="py-2 pl-3">{day(item.created_at)}</td>
                  <td className="py-2 pl-3">{day(item.signed_at)}</td>
                  <td className="py-2">
                    {item.verification_id ? (
                      <Link href={`/verify?code=${encodeURIComponent(item.verification_id)}`} dir="ltr" className="font-mono text-xs text-tide underline">
                        {item.verification_id}
                      </Link>
                    ) : (
                      <span className="text-mist">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <QuickCase client={client} />
    </article>
  );
}

function QuickCase({ client }: { client: Client }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reuses = client.reusable_docs_count > 0;

  async function open(processType: string) {
    setError(null);
    setBusy(processType);
    try {
      const response = await fetch("/api/clients/quick-case", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_case_id: client.latest_case_id, process_type: processType }),
      });
      if (response.status === 401) return toLogin();
      if (!response.ok) {
        setError(await detail(response, "פתיחת התיק נכשלה."));
        setBusy(null);
        return;
      }
      const body = (await response.json()) as { case?: { id?: string } };
      if (!body.case?.id) {
        setError("התיק נפתח, אך לא ניתן היה לעבור אליו. חפשו אותו בארון התיקים.");
        setBusy(null);
        return;
      }
      window.location.assign(`/cases/${body.case.id}`);
    } catch {
      setError("פתיחת התיק נכשלה. בדקו את החיבור ונסו שוב.");
      setBusy(null);
    }
  }

  return (
    <section className="mt-6 border-t border-line pt-5" aria-label="פתיחת תיק חדש">
      <h3 className="text-sm font-semibold">פתיחת תיק חדש ללקוח</h3>
      <p className="mt-1 text-sm text-mist">
        {reuses
          ? "המסמכים שבכספת מועתקים לתיק החדש, הטופס נטען והפרטים מתמלאים מיד."
          : "אין עדיין מסמכים בכספת: התיק ייפתח עם הטופס והפרטים הידועים, והמסמכים יועלו בתיק עצמו."}
      </p>
      <div className="mt-3 flex flex-wrap gap-3">
        {QUICK_CASES.map((item) => (
          <button
            key={item.process_type}
            type="button"
            disabled={busy !== null}
            onClick={() => void open(item.process_type)}
            className="rounded-md bg-tide px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
          >
            {busy === item.process_type ? "פותחים תיק…" : `+ ${item.label}`}
          </button>
        ))}
      </div>
      {error ? (
        <p role="alert" className="mt-3 text-sm font-medium text-clay">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function Detail({ label, value, ltr = false }: { label: string; value: string | null; ltr?: boolean }) {
  return (
    <div>
      <dt className="text-xs font-semibold text-mist">{label}</dt>
      <dd dir={value && ltr ? "ltr" : undefined} className={value ? (ltr ? "text-right font-mono" : "") : "text-mist"}>
        {value ?? "לא ידוע"}
      </dd>
    </div>
  );
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-line bg-white px-2 py-3">
      <dd className="font-serif text-2xl">{value}</dd>
      <dt className="text-xs font-semibold text-mist">{label}</dt>
    </div>
  );
}
