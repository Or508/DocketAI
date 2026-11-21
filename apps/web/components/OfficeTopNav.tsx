"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Building2, FolderOpen, LogOut, Menu, Search, X } from "lucide-react";

import { CommandPalette } from "@/components/command-palette";

// Hebrew labels only. A route path is never part of what the office reads.
const SECTIONS = [
  { href: "/cases", label: "ארון תיקים" },
  { href: "/clients", label: "ספר לקוחות" },
  { href: "/templates", label: "קטלוג טפסים" },
  { href: "/analytics", label: "אנליטיקה" },
  { href: "/audit", label: "יומן אבטחה" },
  { href: "/verify", label: "אימות חותם" },
  { href: "/settings", label: "הגדרות" },
] as const;

// The organization created by default has an English name; the office sees it in Hebrew.
const ORGANIZATION_LABELS: Record<string, string> = { "Default organization": "משרד ראשי" };

function isActive(path: string, href: string) {
  return path === href || path.startsWith(`${href}/`) || (href === "/cases" && path === "/");
}

/**
 * The office's one top bar: brand and sections on the right, search, office and sign-out on the left.
 * It is fixed to the top of the window; every office screen leaves room for it (globals.css).
 */
export function OfficeTopNav() {
  const path = usePathname() || "";
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [organization, setOrganization] = useState<string | null>(null);
  const [demoUntil, setDemoUntil] = useState<string | null>(null);
  const shell = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
      if (event.key === "Escape") setDrawerOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/office/auth/me", { cache: "no-store" })
      .then(async (response) =>
        response.ok ? ((await response.json()) as { organization_name: string; demo_expires_at?: string | null }) : null,
      )
      .then((user) => {
        if (cancelled || !user) return;
        setOrganization(user.organization_name);
        setDemoUntil(user.demo_expires_at ?? null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // A link followed from the drawer closes it.
  useEffect(() => setDrawerOpen(false), [path]);

  // The bar is fixed. Its height includes the demo banner when that banner wraps, so the page starts below it.
  useEffect(() => {
    const node = shell.current;
    if (!node) return;
    const apply = () => {
      document.body.style.paddingTop = `${node.offsetHeight}px`;
    };
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(node);
    return () => {
      observer.disconnect();
      document.body.style.paddingTop = "";
    };
  }, [demoUntil]);

  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/login");
  }

  const office = organization ? (ORGANIZATION_LABELS[organization] ?? organization) : null;

  const whatsApp = `https://wa.me/972547302757?text=${encodeURIComponent("היי, ראיתי את הדמו של DocFlow ואשמח לשמוע עוד")}`;

  return (
    <>
      <div ref={shell} data-office-shell className="fixed inset-x-0 top-0 z-30 print:hidden">
      {demoUntil ? (
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 bg-tide px-4 py-2 text-sm text-white">
          <p>דמו · נמחק אוטומטית ב-{demoClock(demoUntil)} · לא להעלות מידע אמיתי</p>
          <a className="font-semibold underline-offset-2 hover:underline" href={whatsApp} target="_blank" rel="noopener noreferrer">
            דברו איתנו בוואטסאפ: 054-7302757
          </a>
        </div>
      ) : null}
      <header className="h-16 border-b border-line bg-white/95 backdrop-blur">
        <div className="flex h-full items-center justify-between gap-4 whitespace-nowrap px-4 lg:px-6">
          {/* Right: brand and sections. */}
          <div className="flex h-full min-w-0 items-center gap-6">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-label="פתיחת התפריט"
              aria-expanded={drawerOpen}
              className="flex h-10 w-10 items-center justify-center rounded-md text-ink hover:bg-ink/5 lg:hidden"
            >
              <Menu aria-hidden className="h-5 w-5" />
            </button>
            <Brand />
            <nav aria-label="ניווט המשרד" className="hidden h-full min-w-0 overflow-x-auto lg:block">
              <ul className="flex h-full items-stretch">
                {SECTIONS.map((item) => {
                  const current = isActive(path, item.href);
                  return (
                    <li key={item.href} className="flex">
                      <Link
                        href={item.href}
                        aria-current={current ? "page" : undefined}
                        className={`inline-flex items-center border-b-2 px-3 pt-0.5 text-sm transition-colors ${
                          current
                            ? "border-tide font-semibold text-tide"
                            : "border-transparent font-medium text-mist hover:border-line hover:text-ink"
                        }`}
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </nav>
          </div>

          {/* Left: search, the office, sign-out. */}
          <div className="flex shrink-0 items-center gap-2">
            <Link
              href="/how-it-works"
              className="hidden h-9 items-center rounded-md px-2.5 text-sm font-medium text-mist transition-colors hover:bg-ink/5 hover:text-ink lg:inline-flex"
            >
              איך זה עובד
            </Link>
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              aria-label="חיפוש מהיר (Ctrl+K)"
              className="flex h-9 items-center gap-2 rounded-full border border-line bg-paper px-3 text-sm text-mist transition-colors hover:border-ink/20 hover:text-ink"
            >
              <Search aria-hidden className="h-4 w-4" />
              <span className="hidden xl:inline">חיפוש מהיר</span>
              <kbd dir="ltr" className="hidden rounded border border-line bg-white px-1.5 py-0.5 font-sans text-[11px] text-mist sm:inline">
                Ctrl+K
              </kbd>
            </button>
            {office ? (
              <span
                dir="auto"
                title={office}
                className="hidden h-8 max-w-[11rem] items-center gap-1.5 truncate rounded-full bg-mint px-3 text-xs font-semibold text-tide xl:inline-flex"
              >
                <Building2 aria-hidden className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{office}</span>
              </span>
            ) : null}
            <button
              type="button"
              onClick={() => void signOut()}
              className="flex h-9 items-center gap-1.5 rounded-md px-2.5 text-sm font-medium text-mist transition-colors hover:bg-ink/5 hover:text-clay"
            >
              <LogOut aria-hidden className="h-4 w-4" />
              <span className="hidden sm:inline">יציאה</span>
            </button>
          </div>
        </div>
      </header>
      </div>

      {drawerOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="תפריט המשרד">
          <button type="button" aria-label="סגירת התפריט" className="absolute inset-0 bg-ink/30" onClick={() => setDrawerOpen(false)} />
          <div className="absolute inset-y-0 start-0 flex w-72 max-w-[85vw] flex-col bg-white shadow-lift">
            <div className="flex h-16 items-center justify-between border-b border-line px-4">
              <Brand />
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label="סגירת התפריט"
                className="flex h-9 w-9 items-center justify-center rounded-md text-mist hover:bg-ink/5"
              >
                <X aria-hidden className="h-5 w-5" />
              </button>
            </div>
            <nav aria-label="ניווט המשרד" className="flex-1 overflow-y-auto p-3">
              <ul className="space-y-0.5">
                {SECTIONS.map((item) => {
                  const current = isActive(path, item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={current ? "page" : undefined}
                        className={`flex h-11 items-center rounded-md px-3 text-sm ${
                          current ? "bg-mint font-semibold text-tide" : "font-medium text-ink/80 hover:bg-ink/5"
                        }`}
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
              <div className="mt-3 border-t border-line pt-3">
                <Link
                  href="/how-it-works"
                  className="flex h-11 items-center rounded-md px-3 text-sm font-medium text-mist hover:bg-ink/5 hover:text-ink"
                >
                  איך זה עובד
                </Link>
              </div>
            </nav>
            {office ? (
              <p dir="auto" className="flex items-center gap-2 border-t border-line px-5 py-4 text-sm font-semibold text-tide">
                <Building2 aria-hidden className="h-4 w-4" />
                {office}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      {demoUntil ? (
        <a
          href={whatsApp}
          target="_blank"
          rel="noopener noreferrer"
          className="fixed bottom-5 left-5 z-30 inline-flex h-12 items-center rounded-full bg-[#25D366] px-4 text-sm font-semibold text-white shadow-md print:hidden"
        >
          וואטסאפ
        </a>
      ) : null}

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </>
  );
}

function demoClock(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("he-IL", {
    timeZone: "Asia/Jerusalem",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function Brand() {
  return (
    <Link href="/cases" className="flex shrink-0 items-center gap-2.5 rounded-md">
      <span aria-hidden className="flex h-8 w-8 items-center justify-center rounded-lg bg-tide text-white shadow-sm">
        <FolderOpen className="h-[18px] w-[18px]" />
      </span>
      <span dir="ltr" className="text-base font-bold tracking-tight text-ink">
        DocketFlow
      </span>
      <span aria-hidden className="hidden h-5 w-px bg-line min-[1360px]:block" />
      <span className="hidden text-sm text-mist min-[1360px]:inline">מערכת תיקים וחתימות</span>
    </Link>
  );
}
