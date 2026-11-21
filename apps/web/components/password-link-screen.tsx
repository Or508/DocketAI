"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, account, type AccountLink } from "@/lib/api";

const GONE = "הקישור כבר לא פעיל. אפשר לבקש קישור חדש.";

function linkProblem(error: unknown): string {
  if (error instanceof ApiError && error.message && error.message !== "Request failed") return error.message;
  return GONE;
}

export function PasswordLinkScreen({ token, purpose }: { token: string; purpose: "invite" | "reset" }) {
  const [info, setInfo] = useState<AccountLink | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    let cancelled = false;
    account
      .link(token)
      .then((next) => {
        if (cancelled) return;
        if (next.purpose !== purpose) {
          setProblem(GONE);
          return;
        }
        setInfo(next);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setProblem(linkProblem(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [token, purpose]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!info) return;
    setError(null);
    if (password.length < info.min_password_length) {
      setError(`בחרו סיסמה של ${info.min_password_length} תווים לפחות.`);
      return;
    }
    if (password !== repeat) {
      setError("הסיסמאות אינן זהות.");
      return;
    }
    setBusy(true);
    try {
      if (purpose === "invite") await account.acceptInvite(token, password);
      else await account.resetPassword(token, password);
      setDone(true);
    } catch (reason) {
      setError(linkProblem(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-5">
      <div className="rounded-lg border border-ink/15 bg-white p-6 shadow-card">
        {problem ? (
          <p className="text-sm font-medium text-clay" role="alert">
            {problem}
          </p>
        ) : null}
        {done ? (
          <p className="text-sm font-semibold text-[#0d4a2e]" role="status">
            {purpose === "invite" ? "החשבון מוכן. אפשר להתחבר עכשיו." : "הסיסמה עודכנה. התחברו עם הסיסמה החדשה."}
          </p>
        ) : null}
        {info && !done && !problem ? (
          <form onSubmit={(event) => void onSubmit(event)}>
            <h1 className="font-serif text-3xl">{purpose === "invite" ? `הצטרפות ל${info.organization_name}` : "בחירת סיסמה חדשה"}</h1>
            {purpose === "invite" ? <p className="mt-3 text-sm">שלום {info.display_name}</p> : null}
            <label className="mt-5 block text-sm font-semibold" htmlFor="link-email">
              דוא״ל
            </label>
            <Input id="link-email" className="mt-2" dir="ltr" type="email" value={info.email} readOnly />
            <label className="mt-4 block text-sm font-semibold" htmlFor="link-password">
              סיסמה
            </label>
            <Input
              id="link-password"
              className="mt-2"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoComplete="new-password"
            />
            <label className="mt-4 block text-sm font-semibold" htmlFor="link-password-repeat">
              סיסמה נוספת
            </label>
            <Input
              id="link-password-repeat"
              className="mt-2"
              type="password"
              value={repeat}
              onChange={(event) => setRepeat(event.target.value)}
              required
              autoComplete="new-password"
            />
            {error ? (
              <p className="mt-4 text-sm font-medium text-clay" role="alert">
                {error}
              </p>
            ) : null}
            <Button type="submit" className="mt-6 w-full" disabled={busy}>
              שמירת הסיסמה
            </Button>
          </form>
        ) : !info && !problem ? (
          <p className="text-sm text-mist">טוענים…</p>
        ) : null}
        {done ? (
          <Button asChild className="mt-6 w-full">
            <Link href="/login" referrerPolicy="no-referrer">
              כניסה
            </Link>
          </Button>
        ) : null}
      </div>
      {problem ? (
        <p className="mt-4 text-center text-sm">
          <Link href="/login" referrerPolicy="no-referrer" className="text-mist underline-offset-2 hover:text-tide hover:underline">
            כניסה
          </Link>
        </p>
      ) : null}
    </main>
  );
}
