"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

type Drawer = {
  id: string;
  label_he: string;
  accepted_document_types: string[];
  required: boolean;
  reads_fields: string[];
};

type FieldSource = { drawer_id: string; label_he: string };

type MappedField = {
  key: string;
  label_he: string;
  field_type: string;
  required: boolean;
  sources: FieldSource[];
  target: { page: number | null; mode: "digit_boxes" | "text" | null; section_he: string | null };
};

type Template = {
  process_type: string;
  title_he: string;
  description_he: string;
  form_source: "official_blank" | "generated";
  default_template_available: boolean;
  required_drawers: Drawer[];
  mapped_fields: MappedField[];
  case_counts: { total: number; filling: number; signed: number };
};

const OFFICE = "/api/office";
const MODE_LABELS = { digit_boxes: "משבצות ספרות", text: "טקסט חופשי" } as const;

function toLogin() {
  window.location.assign(`/login?next=${encodeURIComponent("/templates")}`);
}

async function detail(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" && body.detail ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

export function TemplatesScreen() {
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const response = await fetch("/api/templates", { cache: "no-store" });
      if (response.status === 401) return toLogin();
      if (!response.ok) {
        setError(response.status === 502 ? "לא ניתן להגיע לשירות המשרד." : "טעינת הקטלוג נכשלה.");
        return;
      }
      setTemplates((await response.json()) as Template[]);
    } catch {
      setError("טעינת הקטלוג נכשלה. בדקו את החיבור ונסו שוב.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-5 py-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-tide">ארון תיוק ובקרת מסמכים</p>
          <h1 className="mt-2 font-serif text-3xl leading-tight sm:text-4xl">קטלוג טפסים ותבניות אוטומציה</h1>
          <p className="mt-3 max-w-2xl text-mist">
            כל טופס שהמשרד ממלא: אילו מסמכים הוא דורש מהלקוח, אילו שדות מתמלאים מתוכם, והאם הטופס הריק זמין במערכת.
          </p>
        </div>
        <nav className="flex gap-4 text-sm font-semibold">
          <Link href="/cases" className="text-tide underline">
            חזרה לארון התיקים
          </Link>
          <Link href="/verify" className="text-tide underline">
            אימות חותם ציבורי
          </Link>
        </nav>
      </header>

      {error ? (
        <div role="alert" className="mt-8 rounded-lg border-2 border-clay/40 bg-white p-5">
          <p className="font-medium text-clay">{error}</p>
          <button type="button" onClick={() => void load()} className="mt-3 text-sm font-semibold text-tide underline">
            ניסיון נוסף
          </button>
        </div>
      ) : null}
      {!error && templates === null ? <p className="mt-8 text-mist">טוענים את הקטלוג…</p> : null}
      {templates?.length === 0 ? <p className="mt-8 text-mist">לא הוגדרו טפסים במערכת.</p> : null}

      <div className="mt-8 space-y-8">
        {templates?.map((template) => (
          <TemplateCard key={template.process_type} template={template} />
        ))}
      </div>
    </main>
  );
}

function TemplateCard({ template }: { template: Template }) {
  const official = template.form_source === "official_blank";
  const ready = template.default_template_available;
  const headingId = `template-${template.process_type}`;
  return (
    <article aria-labelledby={headingId} className="rounded-lg border-2 border-ink/15 bg-white p-6 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p dir="ltr" className="text-right font-mono text-xs text-mist">
            {template.process_type}
          </p>
          <h2 id={headingId} className="mt-1 font-serif text-2xl leading-snug">
            {template.title_he}
          </h2>
          <p className="mt-2 max-w-2xl text-mist">{template.description_he}</p>
        </div>
        <span
          className={`shrink-0 rounded-full border-2 px-3 py-1 text-sm font-semibold ${
            ready ? "border-moss bg-moss/10 text-moss" : "border-amberink bg-amberink/10 text-amberink"
          }`}
        >
          {ready
            ? official
              ? "הטופס הרשמי זמין במערכת"
              : "תבנית המערכת מוכנה"
            : official
              ? "הטופס הרשמי חסר — נדרשת העלאה ידנית"
              : "התבנית חסרה"}
        </span>
      </div>

      <dl className="mt-5 grid grid-cols-3 gap-3 text-center">
        <Count label="סה״כ תיקים" value={template.case_counts.total} />
        <Count label="בהכנה" value={template.case_counts.filling} />
        <Count label="חתומים" value={template.case_counts.signed} />
      </dl>

      <section className="mt-6">
        <h3 className="text-sm font-semibold text-tide">מגירות המסמכים ({template.required_drawers.length})</h3>
        <ul className="mt-2 grid gap-3 sm:grid-cols-3">
          {template.required_drawers.map((drawer) => (
            <li key={drawer.id} className="rounded-md border border-line bg-paper/40 p-3">
              <p className="font-semibold">{drawer.label_he}</p>
              <p className="mt-1 text-sm text-mist">
                {drawer.required ? "חובה" : "רשות"} ·{" "}
                {drawer.reads_fields.length > 0 ? `ממלאת ${drawer.reads_fields.length} שדות` : "לתיעוד בלבד"}
              </p>
              <p dir="ltr" className="mt-1 text-right font-mono text-xs text-mist">
                {drawer.accepted_document_types.join(", ")}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-6">
        <h3 className="text-sm font-semibold text-tide">שדות הטופס ומקורות המילוי ({template.mapped_fields.length})</h3>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[36rem] border-collapse text-sm">
            <thead>
              <tr className="border-b-2 border-line text-right text-mist">
                <th scope="col" className="py-2 pl-3 font-semibold">
                  שדה
                </th>
                <th scope="col" className="py-2 pl-3 font-semibold">
                  מקור המילוי
                </th>
                <th scope="col" className="py-2 pl-3 font-semibold">
                  חלק בטופס
                </th>
                <th scope="col" className="py-2 font-semibold">
                  יעד ב־PDF
                </th>
              </tr>
            </thead>
            <tbody>
              {template.mapped_fields.map((field) => (
                <tr key={field.key} className="border-b border-line/60 align-top">
                  <th scope="row" className="py-2 pl-3 text-right font-semibold">
                    {field.label_he}
                    {field.required ? null : <span className="font-normal text-mist"> (רשות)</span>}
                  </th>
                  <td className="py-2 pl-3">
                    {field.sources.length > 0 ? (
                      <span className="flex flex-wrap gap-1">
                        {field.sources.map((source, index) => (
                          <span
                            key={source.drawer_id}
                            className="rounded-full border border-tide/40 bg-tide/5 px-2 py-0.5 text-tide"
                          >
                            {field.sources.length > 1 ? `${index + 1}. ` : ""}
                            {source.label_he}
                          </span>
                        ))}
                      </span>
                    ) : (
                      <span className="text-mist">הקלדה ע״י המשרד או הלקוח</span>
                    )}
                  </td>
                  <td className="py-2 pl-3 text-mist">{field.target.section_he ?? "—"}</td>
                  <td className="py-2">
                    {field.target.mode ? (
                      <>
                        {MODE_LABELS[field.target.mode]}
                        {field.target.page ? <span className="text-mist"> · עמוד {field.target.page}</span> : null}
                      </>
                    ) : (
                      <span className="text-mist">{ready ? "לא אותר בטופס" : "ייקבע עם טעינת הטופס"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <OpenCase template={template} />
    </article>
  );
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-line bg-paper/40 px-2 py-3">
      <dd className="font-serif text-2xl">{value}</dd>
      <dt className="text-xs font-semibold text-mist">{label}</dt>
    </div>
  );
}

function OpenCase({ template }: { template: Template }) {
  const [open, setOpen] = useState(false);
  const [client, setClient] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputId = `client-${template.process_type}`;
  const loadsForm = template.form_source === "official_blank" && template.default_template_available;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const name = client.trim() || "לקוח חדש";
    setError(null);
    setBusy("פותחים תיק…");
    try {
      const created = await fetch(`${OFFICE}/cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, client_name: name, process_key: template.process_type }),
      });
      if (created.status === 401) return toLogin();
      if (!created.ok) {
        setError(await detail(created, "פתיחת התיק נכשלה."));
        setBusy(null);
        return;
      }
      const { id } = (await created.json()) as { id: string };
      if (loadsForm) {
        setBusy("טוענים את הטופס הרשמי…");
        // The case exists either way; a form that fails to load can be uploaded from the case itself.
        await fetch(`${OFFICE}/cases/${id}/load-default-form`, { method: "POST" }).catch(() => null);
      }
      window.location.assign(`/cases/${id}`);
    } catch {
      setError("פתיחת התיק נכשלה. בדקו את החיבור ונסו שוב.");
      setBusy(null);
    }
  }

  if (!open) {
    return (
      <div className="mt-6">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-md bg-tide px-4 py-3 font-semibold text-white"
        >
          + פתח תיק חדש מתבנית זו
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="mt-6 rounded-md border-2 border-tide/30 bg-tide/5 p-4">
      <label htmlFor={inputId} className="block text-sm font-semibold">
        שם הלקוח
      </label>
      <div className="mt-2 flex flex-wrap gap-3">
        <input
          id={inputId}
          autoFocus
          maxLength={160}
          placeholder="לקוח חדש"
          value={client}
          onChange={(event) => setClient(event.target.value)}
          disabled={busy !== null}
          className="min-w-0 flex-1 rounded-md border-2 border-line bg-white px-3 py-2 outline-none focus:border-tide"
        />
        <button
          type="submit"
          disabled={busy !== null}
          className="rounded-md bg-tide px-4 py-2 font-semibold text-white disabled:opacity-60"
        >
          {busy ?? "+ פתח תיק חדש מתבנית זו"}
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => {
            setOpen(false);
            setError(null);
          }}
          className="px-2 text-sm font-semibold text-mist underline"
        >
          ביטול
        </button>
      </div>
      <p className="mt-2 text-sm text-mist">
        {loadsForm
          ? "התיק ייפתח עם הטופס הרשמי כבר טעון, ותועברו ישר אליו."
          : template.form_source === "official_blank"
            ? "הטופס הרשמי אינו זמין במערכת: התיק ייפתח ריק ואת הטופס תעלו מתוכו."
            : "התיק ייפתח ותועברו ישר אליו."}
      </p>
      {error ? (
        <p role="alert" className="mt-2 text-sm font-medium text-clay">
          {error}
        </p>
      ) : null}
    </form>
  );
}
