"use client";

import type { OfficeContact } from "@docketai/shared-types";
import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";

import { LegalFooter } from "@/app/(legal)/legal-footer";
import { PublicBrand } from "@/app/verify/public-brand";

type Drawer = { document_type: string; label_he: string; filled: boolean; filename: string | null };

type Intake = {
  case_id: string;
  client_name: string;
  process_type: string;
  process_title_he: string;
  status: string;
  required_drawers: Drawer[];
  all_drawers_filled: boolean;
  office: OfficeContact | null;
};

type RoutedFile = {
  filename: string;
  outcome: "received" | "pending" | "rejected";
  document_type: string | null;
  label_he: string | null;
  reason_he: string | null;
};

type View =
  | { kind: "loading" }
  | { kind: "ready"; intake: Intake }
  | { kind: "gone" }
  | { kind: "missing" }
  | { kind: "offline" };

const TOKEN = /^[A-Za-z0-9_-]{20,128}$/;
const MAX_FILES = 5;
const MAX_FILE_BYTES = 25 * 1024 * 1024;
const ACCEPT = "application/pdf,image/*,.pdf,.jpg,.jpeg,.png,.heic,.webp";

export function UploadScreen({ token }: { token: string }) {
  const [view, setView] = useState<View>({ kind: "loading" });
  // "all" while a mixed batch is on its way, a document type while one drawer's file is.
  const [sending, setSending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<RoutedFile[] | null>(null);
  const batchPicker = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!TOKEN.test(token)) {
      setView({ kind: "missing" });
      return;
    }
    try {
      const response = await fetch(`/api/intake/${token}`, { cache: "no-store" });
      if (response.status === 404) setView({ kind: "missing" });
      else if (response.status === 410) setView({ kind: "gone" });
      else if (!response.ok) setView({ kind: "offline" });
      else setView({ kind: "ready", intake: (await response.json()) as Intake });
    } catch {
      setView({ kind: "offline" });
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function send(files: File[], documentType: string | null) {
    setError(null);
    setResults(null);
    if (files.length === 0) return;
    if (files.length > MAX_FILES) {
      setError(`אפשר להעלות עד ${MAX_FILES} קבצים בבת אחת. בחרו פחות קבצים ונסו שוב.`);
      return;
    }
    const tooBig = files.find((file) => file.size > MAX_FILE_BYTES);
    if (tooBig) {
      setError(`הקובץ "${tooBig.name}" גדול מדי (עד 25 מ״ב לקובץ).`);
      return;
    }
    const body = new FormData();
    for (const file of files) body.append("files", file, file.name);
    if (documentType) body.set("document_type", documentType);
    setSending(documentType ?? "all");
    try {
      const response = await fetch(`/api/intake/${token}/upload`, { method: "POST", body });
      if (response.status === 410) {
        setView({ kind: "gone" });
      } else if (response.status === 404) {
        setView({ kind: "missing" });
      } else if (response.status === 413) {
        setError("הקבצים גדולים מדי. נסו להעלות אותם אחד אחד.");
      } else if (response.status === 502) {
        setError("לא הצלחנו להגיע לשירות. נסו שוב בעוד רגע.");
      } else if (!response.ok) {
        setError("ההעלאה לא הצליחה. ודאו שהקבצים הם PDF או תמונה, ונסו שוב.");
      } else {
        const { routed_files: routed, ...intake } = (await response.json()) as Intake & { routed_files: RoutedFile[] };
        setView({ kind: "ready", intake });
        setResults(routed);
      }
    } catch {
      setError("ההעלאה לא הצליחה. בדקו את החיבור לאינטרנט ונסו שוב.");
    } finally {
      setSending(null);
    }
  }

  function onBatch(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    void send(files, null);
  }

  return (
    <>
    <PublicBrand frame="max-w-xl px-4" />
    <main className="mx-auto w-full max-w-xl px-4 pb-16 pt-8 sm:pt-10">
      <header>
        <p className="text-sm font-semibold text-tide">קישור אישי ומאובטח מהמשרד</p>
        <h1 className="mt-2 text-3xl font-bold leading-tight tracking-tight text-ink sm:text-4xl">העלאת מסמכים מאובטחת לתיק</h1>
        {view.kind === "ready" ? <SentBy office={view.intake.office} /> : null}
      </header>

      {view.kind === "loading" ? (
        <p className="mt-8 text-mist" aria-live="polite">
          טוענים את רשימת המסמכים…
        </p>
      ) : null}

      {view.kind === "missing" ? (
        <Notice title="הקישור אינו תקין">
          ודאו שהעתקתם את הקישור במלואו מההודעה שקיבלתם, או בקשו מהמשרד לשלוח קישור חדש.
        </Notice>
      ) : null}

      {view.kind === "gone" ? (
        <Notice title="הקישור כבר אינו פעיל">
          ייתכן שהתיק כבר נחתם, שתוקף הקישור פג, או שהמשרד שלח קישור חדש במקומו. לקבלת קישור עדכני פנו למשרד.
        </Notice>
      ) : null}

      {view.kind === "offline" ? (
        <Notice title="לא הצלחנו לטעון את הדף">
          <span>נסו שוב בעוד רגע.</span>
          <button
            type="button"
            onClick={() => {
              setView({ kind: "loading" });
              void load();
            }}
            className="mt-4 block w-full rounded-md bg-tide px-4 py-3 font-semibold text-white"
          >
            ניסיון נוסף
          </button>
        </Notice>
      ) : null}

      {view.kind === "ready" ? (
        <>
          <p className="mt-3 text-mist">
            {view.intake.client_name ? `שלום ${view.intake.client_name}, ` : ""}
            כדי להשלים את התיק ({view.intake.process_title_he}) אנחנו צריכים מכם את המסמכים שברשימה. אפשר לצלם אותם
            בטלפון או לבחור קובצי PDF.
          </p>

          {view.intake.all_drawers_filled ? (
            <section
              role="status"
              className="mt-6 rounded-lg border border-moss/50 bg-white p-5 shadow-card"
            >
              <h2 className="font-serif text-2xl text-moss">כל המסמכים התקבלו ✓</h2>
              <p className="mt-2 text-mist">
                תודה! המסמכים הועברו למשרד ואין צורך בפעולה נוספת. אפשר לסגור את הדף. אם העליתם מסמך שגוי, אפשר
                להחליף אותו כאן למטה.
              </p>
              <p className="mt-2 text-mist">מה הלאה: המשרד יבדוק את המסמכים. אם יידרשו פרטים נוספים או חתימה, תקבלו הודעה.</p>
            </section>
          ) : null}

          <section className="mt-6" aria-labelledby="needed-title">
            <div className="flex items-end justify-between gap-3">
              <h2 id="needed-title" className="text-sm font-semibold">
                המסמכים הנדרשים
              </h2>
              <p className="text-sm text-mist">
                התקבלו{" "}
                <span className="font-semibold tabular-nums text-ink">
                  {view.intake.required_drawers.filter((drawer) => drawer.filled).length}
                </span>{" "}
                מתוך <span className="tabular-nums">{view.intake.required_drawers.length}</span>
              </p>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink/10" aria-hidden>
              <div
                className="h-full rounded-full bg-moss transition-all duration-500"
                style={{
                  width: `${Math.round(
                    (100 * view.intake.required_drawers.filter((drawer) => drawer.filled).length) /
                      Math.max(view.intake.required_drawers.length, 1),
                  )}%`,
                }}
              />
            </div>
            <ul className="mt-4 space-y-3">
              {view.intake.required_drawers.map((drawer) => (
                <DrawerRow
                  key={drawer.document_type}
                  drawer={drawer}
                  busy={sending !== null}
                  sendingThis={sending === drawer.document_type}
                  onPick={(file) => void send([file], drawer.document_type)}
                />
              ))}
            </ul>
          </section>

          <section className="mt-6 rounded-lg border border-ink/15 bg-white p-5 shadow-card">
            <h2 className="font-semibold">העלאת כמה מסמכים בבת אחת</h2>
            <p className="mt-1 text-sm text-mist">
              בחרו עד {MAX_FILES} קבצים יחד. נזהה לבד איזה מסמך הוא מה ונתייק כל אחד במקומו.
            </p>
            <input
              ref={batchPicker}
              type="file"
              accept={ACCEPT}
              multiple
              className="hidden"
              onChange={onBatch}
              aria-hidden
              tabIndex={-1}
            />
            <button
              type="button"
              disabled={sending !== null}
              onClick={() => batchPicker.current?.click()}
              className="mt-4 w-full rounded-md bg-tide px-4 py-4 text-lg font-semibold text-white transition-opacity disabled:opacity-60"
            >
              {sending === "all" ? "מעלים ומזהים את המסמכים…" : "בחירת קבצים או צילום"}
            </button>
          </section>

          <div aria-live="polite">
            {error ? (
              <p role="alert" className="mt-4 rounded-lg border border-clay/40 bg-white p-4 font-medium text-clay">
                {error}
              </p>
            ) : null}
            {results ? <Results files={results} /> : null}
          </div>

          <p className="mt-8 text-center text-xs text-mist">
            הקבצים נשלחים ישירות לתיק שלכם במשרד. הדף הזה אינו מציג פרטים אישיים מתוך המסמכים.
          </p>
        </>
      ) : null}
    </main>
    <LegalFooter frame="max-w-xl px-4" />
    </>
  );
}

function SentBy({ office }: { office: OfficeContact | null }) {
  if (!office) return null;
  const phone = office.phone?.trim() || null;
  const email = office.email?.trim() || null;
  return (
    <div className="mt-2 text-sm leading-6">
      <p>נשלח אליכם מ{office.name}</p>
      {phone || email ? (
        <p className="mt-1 flex min-w-0 flex-wrap gap-x-2 gap-y-1">
          <span>לשאלות</span>
          {phone ? (
            <a className="break-all underline-offset-2 hover:underline" dir="ltr" href={`tel:${phone}`}>
              {phone}
            </a>
          ) : null}
          {email ? (
            <a className="min-w-0 break-all underline-offset-2 hover:underline" dir="ltr" href={`mailto:${email}`}>
              {email}
            </a>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}

function DrawerRow({
  drawer,
  busy,
  sendingThis,
  onPick,
}: {
  drawer: Drawer;
  busy: boolean;
  sendingThis: boolean;
  onPick: (file: File) => void;
}) {
  const picker = useRef<HTMLInputElement>(null);
  return (
    <li
      className={`rounded-lg border bg-white p-4 shadow-card ${drawer.filled ? "border-moss/40" : "border-ink/15"}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold">{drawer.label_he}</p>
          {drawer.filled && drawer.filename ? (
            <p className="mt-1 break-all text-sm text-mist" dir="auto">
              {drawer.filename}
            </p>
          ) : (
            <p className="mt-1 text-sm text-mist">עדיין לא התקבל</p>
          )}
        </div>
        {drawer.filled ? (
          <span className="shrink-0 rounded-full bg-moss px-3 py-1 text-sm font-semibold text-white">התקבל ✓</span>
        ) : (
          <span className="shrink-0 rounded-full border border-[#f1dfbd] bg-[#fdf5e6] px-3 py-1 text-sm font-semibold text-[#7a4f0f]">
            חסר
          </span>
        )}
      </div>
      <input
        ref={picker}
        type="file"
        accept={ACCEPT}
        className="hidden"
        aria-hidden
        tabIndex={-1}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onPick(file);
        }}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => picker.current?.click()}
        aria-label={`${drawer.filled ? "החלפת" : "העלאת"} ${drawer.label_he}`}
        className={`mt-3 w-full rounded-md border px-4 py-3 font-semibold transition-opacity disabled:opacity-60 ${
          drawer.filled ? "border-line bg-white text-ink" : "border-tide bg-white text-tide"
        }`}
      >
        {sendingThis ? "מעלים…" : drawer.filled ? "החלפת המסמך" : "צילום או בחירת קובץ"}
      </button>
    </li>
  );
}

function Results({ files }: { files: RoutedFile[] }) {
  const received = files.filter((file) => file.outcome === "received").length;
  return (
    <section className="mt-4 rounded-lg border border-ink/15 bg-white p-5 shadow-card">
      <h2 className="font-semibold">
        {received === files.length
          ? files.length === 1
            ? "המסמך התקבל ✓"
            : `כל ${files.length} המסמכים התקבלו ✓`
          : `התקבלו ${received} מתוך ${files.length} קבצים`}
      </h2>
      <ul className="mt-3 space-y-3">
        {files.map((file, index) => (
          <li key={`${file.filename}-${index}`} className="text-sm">
            <p className="break-all font-medium" dir="auto">
              {file.filename}
            </p>
            {file.outcome === "received" ? (
              <p className="mt-0.5 font-semibold text-moss">התקבל ✓{file.label_he ? ` · ${file.label_he}` : ""}</p>
            ) : (
              <p className={`mt-0.5 ${file.outcome === "rejected" ? "text-clay" : "text-amberink"}`}>
                {file.reason_he ?? "הקובץ לא תויק."}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Notice({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section role="alert" className="mt-8 rounded-lg border border-ink/15 bg-white p-6 shadow-card">
      <h2 className="font-serif text-2xl">{title}</h2>
      <div className="mt-2 text-mist">{children}</div>
    </section>
  );
}
