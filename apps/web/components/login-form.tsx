"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const FAILURE = "Email or password is incorrect.";

// Parse the way the browser will: it strips tabs and newlines, so "/<tab>/host" is really "//host".
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
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        setError(FAILURE);
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
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-5">
      <form onSubmit={onSubmit} className="rounded-lg border border-line bg-white/75 p-6 shadow-card">
        <p className="text-[11px] uppercase tracking-[0.18em] text-tide">DocketAI</p>
        <h1 className="mt-2 font-serif text-3xl">Sign in</h1>
        <label className="mt-5 block text-xs uppercase tracking-[0.16em] text-mist" htmlFor="email">
          Email
        </label>
        <Input id="email" type="email" className="mt-2" value={email} onChange={(event) => setEmail(event.target.value)} required />
        <label className="mt-4 block text-xs uppercase tracking-[0.16em] text-mist" htmlFor="password">
          Password
        </label>
        <Input
          id="password"
          type="password"
          className="mt-2"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        {error ? <p className="mt-4 text-sm text-clay">{error}</p> : null}
        <Button type="submit" className="mt-6 w-full" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </main>
  );
}
