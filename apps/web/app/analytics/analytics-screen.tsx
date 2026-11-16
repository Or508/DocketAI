"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type ProcessBreakdown = {
  process_type: string;
  total: number;
  filling: number;
  waiting_for_signature: number;
  signed: number;
};

type Summary = {
  total_cases: number;
  filling_cases: number;
  waiting_for_signature_cases: number;
  signed_cases: number;
  avg_hours_to_sign: number | null;
  auto_extraction_rate_pct: number;
  by_process_type: ProcessBreakdown[];
  by_status: Record<string, number>;
};

const PROCESS_LABELS: Record<string, string> = {
  bl_6101: "בל/6101 – ביטוח לאומי",
  onboarding: "קליטת עובד חדש",
  real_estate: "עסקת מקרקעין",
};

const STAGES = [
  { key: "filling_cases", label: "בהכנה במשרד", bar: "bg-amberink", text: "text-amberink" },
  { key: "waiting_for_signature_cases", label: "ממתינים לחתימת לקוח", bar: "bg-tide", text: "text-tide" },
  { key: "signed_cases", label: "חתומים ומאומתים", bar: "bg-moss", text: "text-moss" },
] as const;

function formatDuration(hours: number | null): { value: string; unit: string } {
  if (hours === null) return { value: "—", unit: "אין עדיין תיקים חתומים" };
  if (hours < 1) return { value: String(Math.max(1, Math.round(hours * 60))), unit: "דקות" };
  if (hours < 48) return { value: hours.toLocaleString("he-IL", { maximumFractionDigits: 1 }), unit: "שעות" };
  return { value: (hours / 24).toLocaleString("he-IL", { maximumFractionDigits: 1 }), unit: "ימים" };
}

function share(part: number, whole: number): number {
  return whole > 0 ? Math.round((part / whole) * 100) : 0;
}

export function AnalyticsScreen() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/analytics/summary", { cache: "no-store" });
      if (response.status === 401) {
        window.location.assign(`/login?next=${encodeURIComponent("/analytics")}`);
        return;
      }
      if (!response.ok) {
        setError(response.status === 502 ? "לא ניתן להגיע לשירות המשרד." : "טעינת המדדים נכשלה.");
        return;
      }
      setSummary((await response.json()) as Summary);
    } catch {
      setError("טעינת המדדים נכשלה. בדקו את החיבור ונסו שוב.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const duration = formatDuration(summary?.avg_hours_to_sign ?? null);
  const processes = summary?.by_process_type.filter((item) => item.total > 0) ?? [];

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-5 py-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-tide">ארון תיוק ובקרת מסמכים</p>
          <h1 className="mt-2 font-serif text-3xl leading-tight sm:text-4xl">דוחות, מדדי ביצוע וייצוא לאקסל</h1>
          <p className="mt-3 max-w-2xl text-mist">
            תמונת מצב של תיקי המשרד: כמה בהכנה, כמה ממתינים לחתימה וכמה נחתמו, וכמה מהעבודה נעשתה אוטומטית מתוך המסמכים.
          </p>
        </div>
        <nav className="flex flex-wrap gap-4 text-sm font-semibold">
          <Link href="/cases" className="text-tide underline">
            ארון התיקים
          </Link>
          <Link href="/templates" className="text-tide underline">
            קטלוג טפסים
          </Link>
          <Link href="/verify" className="text-tide underline">
            אימות חותם ציבורי
          </Link>
        </nav>
      </header>

      <section className="mt-8 flex flex-wrap items-center justify-between gap-4 rounded-lg border-2 border-tide/30 bg-tide/5 p-5">
        <div className="min-w-0">
          <h2 className="font-semibold">דוח תיקים מלא</h2>
          <p className="mt-1 text-sm text-mist">
            שורה לכל תיק: לקוח, סוג תהליך, מצב, מועדי פתיחה וחתימה וקוד אימות. הקובץ נפתח באקסל עם עברית תקינה.
          </p>
        </div>
        <a
          href="/api/analytics/export.csv"
          download="office_cases_report.csv"
          className="shrink-0 rounded-md bg-tide px-5 py-3 font-semibold text-white"
        >
          הורדת דוח תיקים מלא לאקסל (CSV)
        </a>
      </section>

      {error ? (
        <div role="alert" className="mt-6 rounded-lg border-2 border-clay/40 bg-white p-5">
          <p className="font-medium text-clay">{error}</p>
          <button type="button" onClick={() => void load()} className="mt-3 text-sm font-semibold text-tide underline">
            ניסיון נוסף
          </button>
        </div>
      ) : null}
      {loading && !summary ? <p className="mt-8 text-mist">טוענים מדדים…</p> : null}

      {summary ? (
        <>
          <section aria-label="מדדים עיקריים" className="mt-6 grid gap-4 sm:grid-cols-3">
            <Kpi label="סה״כ תיקים" value={summary.total_cases.toLocaleString("he-IL")} note="כל תיקי המשרד" />
            <Kpi
              label="אחוז מילוי אוטומטי ללא עריכה ידנית"
              value={`${summary.auto_extraction_rate_pct.toLocaleString("he-IL", { maximumFractionDigits: 1 })}%`}
              note="מתוך כלל השדות שמולאו, אלה שנקראו ישירות ממסמך"
            />
            <Kpi label="זמן ממוצע לחתימת לקוח" value={duration.value} note={duration.unit} />
          </section>

          <section className="mt-6 rounded-lg border-2 border-ink/15 bg-white p-6 shadow-card">
            <h2 className="font-serif text-xl">פילוח לפי סטטוס</h2>
            {summary.total_cases === 0 ? (
              <p className="mt-3 text-mist">עדיין לא נפתחו תיקים במשרד.</p>
            ) : (
              <ul className="mt-4 space-y-4">
                {STAGES.map((stage) => {
                  const count = summary[stage.key];
                  const percent = share(count, summary.total_cases);
                  return (
                    <li key={stage.key}>
                      <div className="flex items-baseline justify-between gap-3">
                        <span className={`font-semibold ${stage.text}`}>{stage.label}</span>
                        <span className="text-sm text-mist">
                          <span className="text-base font-semibold text-ink">{count.toLocaleString("he-IL")}</span> ·{" "}
                          {percent}%
                        </span>
                      </div>
                      <div
                        role="img"
                        aria-label={`${stage.label}: ${count} תיקים, ${percent} אחוזים`}
                        className="mt-1 h-3 overflow-hidden rounded-full bg-line/50"
                      >
                        <div className={`h-full rounded-full ${stage.bar}`} style={{ width: `${percent}%` }} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="mt-6 rounded-lg border-2 border-ink/15 bg-white p-6 shadow-card">
            <h2 className="font-serif text-xl">פילוח לפי סוג תהליך</h2>
            {processes.length === 0 ? (
              <p className="mt-3 text-mist">אין תיקים להצגה.</p>
            ) : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[32rem] border-collapse text-sm">
                  <thead>
                    <tr className="border-b-2 border-line text-right text-mist">
                      <th scope="col" className="py-2 pl-3 font-semibold">
                        תהליך
                      </th>
                      <th scope="col" className="py-2 pl-3 font-semibold">
                        סה״כ
                      </th>
                      <th scope="col" className="py-2 pl-3 font-semibold">
                        בהכנה
                      </th>
                      <th scope="col" className="py-2 pl-3 font-semibold">
                        ממתינים לחתימה
                      </th>
                      <th scope="col" className="py-2 font-semibold">
                        חתומים
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {processes.map((item) => (
                      <tr key={item.process_type} className="border-b border-line/60">
                        <th scope="row" className="py-2 pl-3 text-right font-semibold">
                          {PROCESS_LABELS[item.process_type] ?? item.process_type}
                        </th>
                        <td className="py-2 pl-3 font-semibold">{item.total.toLocaleString("he-IL")}</td>
                        <td className="py-2 pl-3">{item.filling.toLocaleString("he-IL")}</td>
                        <td className="py-2 pl-3">{item.waiting_for_signature.toLocaleString("he-IL")}</td>
                        <td className="py-2">
                          {item.signed.toLocaleString("he-IL")}
                          <span className="text-mist"> · {share(item.signed, item.total)}%</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <div className="mt-4 flex justify-end">
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="text-sm font-semibold text-tide underline disabled:opacity-60"
            >
              {loading ? "מרעננים…" : "רענון המדדים"}
            </button>
          </div>
        </>
      ) : null}
    </main>
  );
}

function Kpi({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-lg border-2 border-ink/15 bg-white p-5 shadow-card">
      <p className="text-sm font-semibold text-mist">{label}</p>
      <p className="mt-2 font-serif text-4xl leading-none">{value}</p>
      <p className="mt-2 text-sm text-mist">{note}</p>
    </div>
  );
}
