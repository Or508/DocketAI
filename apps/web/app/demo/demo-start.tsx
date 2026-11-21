"use client";

import { useState } from "react";

const SCENARIOS = [
  { id: "law", label: "משרד עורכי דין: עסקת מקרקעין" },
  { id: "dental", label: "מרפאת שיניים: טפסי הסכמה" },
  { id: "hr", label: "משאבי אנוש: טופס 101" },
] as const;

export function DemoStart() {
  const [scenario, setScenario] = useState<(typeof SCENARIOS)[number]["id"]>("law");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/demo/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
        setError(typeof body?.detail === "string" ? body.detail : "הפעולה לא הצליחה. נסו שוב.");
        setBusy(false);
        return;
      }
      window.location.assign("/cases");
    } catch {
      setError("לא ניתן להגיע לשירות. נסו שוב.");
      setBusy(false);
    }
  }

  return (
    <div className="mt-8">
      <fieldset>
        <legend className="text-sm font-semibold text-ink">בחרו תרחיש</legend>
        <div className="mt-3 grid gap-2">
          {SCENARIOS.map((item) => (
            <label key={item.id} className="flex items-center gap-3 rounded-md border border-line px-3 py-2 text-sm">
              <input
                type="radio"
                name="scenario"
                value={item.id}
                checked={scenario === item.id}
                onChange={() => setScenario(item.id)}
              />
              {item.label}
            </label>
          ))}
        </div>
      </fieldset>
      <button
        type="button"
        onClick={() => void start()}
        disabled={busy}
        className="mt-4 inline-flex h-11 items-center rounded-md bg-tide px-5 text-sm font-semibold text-white disabled:opacity-60"
      >
        התחילו דמו
      </button>
      {error ? (
        <p role="alert" className="mt-3 text-sm text-clay">
          {error}
        </p>
      ) : null}
    </div>
  );
}
