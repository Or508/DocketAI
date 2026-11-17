"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

import { CommandPalette } from "@/components/command-palette";

const LINKS = [
  { href: "/cases", label: "ארון תיקים (/cases)", active: (path: string) => path === "/cases" || path.startsWith("/cases/") },
  { href: "/clients", label: "ספר לקוחות וכספת (/clients)", active: (path: string) => path === "/clients" || path.startsWith("/clients/") },
  { href: "/templates", label: "קטלוג טפסים (/templates)", active: (path: string) => path === "/templates" || path.startsWith("/templates/") },
  { href: "/analytics", label: "דוחות ואנליטיקה (/analytics)", active: (path: string) => path === "/analytics" || path.startsWith("/analytics/") },
  { href: "/verify", label: "אימות חותם (/verify)", active: (path: string) => path === "/verify" || path.startsWith("/verify/") },
] as const;

export function OfficeTopNav() {
  const path = usePathname() || "";
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <nav aria-label="סרגל ניווט משרדי אחיד" className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-ink/15 pb-3">
        <ul className="flex flex-wrap gap-2">
          {LINKS.map((item) => {
            const current = item.active(path);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={current ? "page" : undefined}
                  className={`inline-flex h-10 items-center rounded-md px-3 text-sm font-semibold ${current ? "bg-tide text-white" : "border-2 border-ink/15 bg-white text-ink"}`}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
        <button
          type="button"
          className="inline-flex h-10 items-center rounded-md border-2 border-ink/25 bg-white px-3 text-sm font-semibold text-ink"
          onClick={() => setOpen(true)}
        >
          חיפוש מהיר (Ctrl+K)
        </button>
      </nav>
      <CommandPalette open={open} onOpenChange={setOpen} />
    </>
  );
}
