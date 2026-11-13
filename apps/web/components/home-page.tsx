import Link from "next/link";

import { Wordmark } from "@/components/wordmark";

const CLIENT = [
  "הלקוח מקבל טופס שכבר מולא.",
  "הדבר היחיד שנשאר לו הוא לחתום.",
  "הוא לא מקליד פרטים, ולא משלים מסמכים.",
];

const OFFICE = [
  "המשרד מכניס את הקבצים החסרים.",
  "המערכת כותבת לשדה ריק רק ערך אחד, חד-משמעי, שעבר בדיקה.",
  "ספק, כפילות, או סריקה בלי טקסט נשארים אצל המשרד, עם סיבה.",
  "חתימה דיגיטלית, כשצריך, נעשית בתוך המערכת על הטופס המלא.",
];

export function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-5 py-8" dir="rtl">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-5">
        <Wordmark />
        <Link
          href="/office"
          className="inline-flex h-10 items-center justify-center rounded-md border border-line bg-white/70 px-3 text-sm font-medium"
        >
          אל המשרד
        </Link>
      </header>

      <section className="max-w-3xl py-14">
        <p className="text-[11px] uppercase tracking-[0.18em] text-tide">Docket</p>
        <h1 className="mt-3 font-serif text-5xl leading-tight">המשרד מכניס את הקבצים. הלקוח רק חותם.</h1>
        <p className="mt-5 text-lg leading-8 text-mist">
          המערכת מזהה מה חסר בתיק, ממלאת את השדות הריקים בטופס של העסק, ומשאירה למשרד רק את מה שלא נקרא בביטחון.
        </p>
      </section>

      <section className="grid gap-5 pb-16 md:grid-cols-2">
        <article className="rounded-lg border border-line bg-white/80 p-6 shadow-card">
          <p className="text-[11px] uppercase tracking-[0.18em] text-tide">לעסק</p>
          <h2 className="mt-2 font-serif text-3xl">סוגר את התיק בלי הקלדה</h2>
          <ul className="mt-4 space-y-3 text-sm leading-6">
            {OFFICE.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </article>
        <article className="rounded-lg border border-line bg-white/80 p-6 shadow-card">
          <p className="text-[11px] uppercase tracking-[0.18em] text-tide">ללקוח</p>
          <h2 className="mt-2 font-serif text-3xl">חותם על טופס מלא</h2>
          <ul className="mt-4 space-y-3 text-sm leading-6">
            {CLIENT.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </article>
      </section>
    </main>
  );
}
