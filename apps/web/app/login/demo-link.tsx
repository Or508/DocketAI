"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

/** Shown only when the API has the public demo switched on. The check runs in the browser. */
export function DemoLink() {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/demo/info", { cache: "no-store" })
      .then(async (response) => (response.ok ? ((await response.json()) as { enabled?: boolean }) : null))
      .then((info) => {
        if (!cancelled && info?.enabled) setEnabled(true);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (!enabled) return null;
  return (
    <p className="mt-2 text-center text-sm">
      <Link href="/demo" className="text-tide underline-offset-2 hover:underline">
        רוצים לנסות? דמו בלי הרשמה
      </Link>
    </p>
  );
}
