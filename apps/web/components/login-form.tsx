"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const FAILURE = "הדוא״ל או הסיסמה שגויים.";
const CODE_FAILURE = "הקוד שגוי או שפג תוקפו. נסו את הקוד החדש מהאפליקציה.";

function safeNext(value: string | null): string {
  if (!value) return "/";
  try {
    const target = new URL(value, window.location.origin);
    return target.origin === window.location.origin ? target.href : "/";
  } catch {
    return "/";
  }
}

export function LoginForm({ nextPath }: { nextPath: string | null }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [awaitingCode, setAwaitingCode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(awaitingCode ? { email, password, code } : { email, password }),
      });
      if (!response.ok) {
        const failure = (await response.json().catch(() => null)) as { detail?: unknown; code?: unknown } | null;
        if (response.status === 401 && failure?.code === "mfa_required") {
          setAwaitingCode(true);
          setError(awaitingCode ? CODE_FAILURE : null);
          setBusy(false);
          return;
        }
        setError(response.status === 502 ? "לא ניתן להגיע לשירות המשרד." : FAILURE);
        setBusy(false);
        return;
      }
      window.location.assign(safeNext(nextPath));
    } catch {
      setError(FAILURE);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="rounded-lg border border-ink/15 bg-white p-6 shadow-card">
        <p className="text-sm font-semibold text-tide">ארון תיוק ובקרת מסמכים</p>
        <h1 className="mt-2 font-serif text-3xl">כניסת משרד</h1>
        <label className="mt-5 block text-sm font-semibold" htmlFor="email">
          דוא״ל
        </label>
        <Input id="email" type="email" className="mt-2" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="username" />
        <label className="mt-4 block text-sm font-semibold" htmlFor="password">
          סיסמה
        </label>
        <Input
          id="password"
          type="password"
          className="mt-2"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          autoComplete="current-password"
        />
        <p className="mt-2 text-sm">
          <Link href="/forgot-password" className="text-mist underline-offset-2 hover:text-tide hover:underline">
            שכחתי סיסמה
          </Link>
        </p>
        {awaitingCode ? (
          <>
            <label className="mt-4 block text-sm font-semibold" htmlFor="mfa-code">
              קוד מאפליקציית האימות
            </label>
            <Input
              id="mfa-code"
              className="mt-2"
              dir="ltr"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={9}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              required
              autoFocus
            />
            <p className="mt-2 text-xs text-mist">אפשר להזין גם קוד שחזור.</p>
            {error ? (
              <p className="mt-2 text-sm font-medium text-clay" role="alert">
                {error}
              </p>
            ) : null}
          </>
        ) : null}
        {!awaitingCode && error ? (
          <p className="mt-4 text-sm font-medium text-clay" role="alert">
            {error}
          </p>
        ) : null}
        <Button type="submit" className="mt-6 w-full" disabled={busy}>
          {busy ? "נכנסים…" : "כניסה"}
        </Button>
    </form>
  );
}
