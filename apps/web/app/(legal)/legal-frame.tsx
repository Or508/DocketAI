import { PublicBrand } from "@/app/verify/public-brand";

import { LegalFooter } from "./legal-footer";
import { isDraft } from "./operator";

/** The shared frame of the privacy, terms and accessibility pages: header, title, date, body, footer. */
export function LegalFrame({ title, updated, children }: { title: string; updated: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:right-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:shadow-lift"
      >
        דילוג לתוכן
      </a>
      <PublicBrand />
      <main id="content" className="mx-auto max-w-3xl px-4 py-10">
        {isDraft() ? (
          <p role="note" className="mb-6 rounded-md border border-amberink bg-[#fbf3e4] px-4 py-3 text-sm font-semibold text-[#4a3208]">
            טיוטה: פרטי המפעיל עוד לא הושלמו והנוסח טרם נבדק על ידי עורך דין.
          </p>
        ) : null}
        <h1 className="font-serif text-4xl leading-tight">{title}</h1>
        <p className="mt-2 text-sm text-mist">עודכן לאחרונה: {updated}</p>
        <div className="legal-text mt-8 space-y-8 text-base leading-8">{children}</div>
      </main>
      <LegalFooter />
    </div>
  );
}

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-bold">{title}</h2>
      {children}
    </section>
  );
}

export function List({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="list-disc space-y-2 ps-6">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}
