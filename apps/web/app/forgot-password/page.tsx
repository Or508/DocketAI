"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, account } from "@/lib/api";

function shown(error: unknown): string {
  if (error instanceof ApiError && error.message && error.message !== "Request failed") return error.message;
  return "לא ניתן להגיע לשירות המשרד.";
}

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [detail, setDetail] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setDetail(null);
    try {
      const result = await account.forgotPassword(email.trim());
      setDetail(result.detail);
    } catch (reason) {
      setDetail(shown(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-5">
      <form onSubmit={(event) => void onSubmit(event)} className="rounded-lg border border-ink/15 bg-white p-6 shadow-card">
        <h1 className="font-serif text-3xl">שכחתי סיסמה</h1>
        <label className="mt-5 block text-sm font-semibold" htmlFor="forgot-email">
          דוא״ל
        </label>
        <Input
          id="forgot-email"
          type="email"
          className="mt-2"
          dir="ltr"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoComplete="username"
        />
        <Button type="submit" className="mt-6 w-full" disabled={busy}>
          שליחת קישור
        </Button>
        {detail ? (
          <p className="mt-4 text-sm font-medium" role="status">
            {detail}
          </p>
        ) : null}
      </form>
      <p className="mt-4 text-center text-sm">
        <Link href="/login" className="text-mist underline-offset-2 hover:text-tide hover:underline">
          חזרה לכניסה
        </Link>
      </p>
    </main>
  );
}
