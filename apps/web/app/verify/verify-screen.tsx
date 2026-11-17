"use client";

import { DragEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { OfficeTopNav } from "@/components/OfficeTopNav";

type Seal = {
  valid: boolean;
  status: "valid" | "superseded";
  verification_id: string;
  process_type: string;
  masked_client_name: string;
  signed_at: string;
  signed_pdf_sha256: string;
  hash_matches: boolean | null;
};

type PickedFile = { name: string; size: number; digest: string };

type Outcome =
  | { kind: "seal"; seal: Seal }
  | { kind: "missing"; by: "code" | "file" }
  | { kind: "error"; message: string };

const CODE = /^DV-[0-9A-F]{12}$/;
const MAX_FILE_BYTES = 100 * 1024 * 1024;
const PROCESS_LABELS: Record<string, string> = {
  bl_6101: "טופס בל/6101 — ביטוח לאומי",
  onboarding: "קליטת לקוח",
};

async function sha256Hex(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} בייט`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} ק״ב`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} מ״ב`;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("he-IL", { dateStyle: "long", timeStyle: "short" }).format(date);
}

export function VerifyScreen({ initialCode }: { initialCode: string }) {
  const [code, setCode] = useState(initialCode);
  const [file, setFile] = useState<PickedFile | null>(null);
  const [hashing, setHashing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const latest = useRef(0);

  const check = useCallback(async (rawCode: string, digest: string | null) => {
    const wanted = rawCode.trim().toUpperCase();
    const ticket = ++latest.current;
    let path: string;
    let by: "code" | "file";
    if (CODE.test(wanted)) {
      path = digest ? `${wanted}?sha256=${digest}` : wanted;
      by = "code";
    } else if (wanted) {
      setOutcome({ kind: "error", message: "קוד האימות צריך להיראות כך: DV-XXXXXXXXXXXX (12 תווים אחרי המקף)." });
      return;
    } else if (digest) {
      path = `by-hash/${digest}`;
      by = "file";
    } else {
      setOutcome({ kind: "error", message: "הזינו קוד אימות או גררו לכאן את הקובץ החתום." });
      return;
    }
    setBusy(true);
    setOutcome(null);
    try {
      const response = await fetch(`/api/verify/${path}`, { cache: "no-store" });
      if (ticket !== latest.current) return;
      if (response.status === 404) {
        setOutcome({ kind: "missing", by });
      } else if (!response.ok) {
        setOutcome({
          kind: "error",
          message: response.status === 502 ? "לא ניתן להגיע לשירות האימות. נסו שוב בעוד רגע." : "הבדיקה נכשלה. נסו שוב.",
        });
      } else {
        const seal = (await response.json()) as Seal;
        if (ticket !== latest.current) return;
        setOutcome({ kind: "seal", seal });
        if (by === "file") setCode(seal.verification_id);
      }
    } catch {
      if (ticket === latest.current) setOutcome({ kind: "error", message: "הבדיקה נכשלה. בדקו את החיבור ונסו שוב." });
    } finally {
      if (ticket === latest.current) setBusy(false);
    }
  }, []);

  // A link from the signed packet arrives with the code already in the address.
  useEffect(() => {
    if (CODE.test(initialCode)) void check(initialCode, null);
  }, [initialCode, check]);

  async function take(picked: File | undefined) {
    if (!picked) return;
    if (picked.size > MAX_FILE_BYTES) {
      setOutcome({ kind: "error", message: "הקובץ גדול מדי לבדיקה (עד 100 מ״ב)." });
      return;
    }
    setHashing(true);
    setOutcome(null);
    try {
      const digest = await sha256Hex(picked);
      setFile({ name: picked.name, size: picked.size, digest });
      await check(code, digest);
    } catch {
      setOutcome({ kind: "error", message: "לא ניתן לקרוא את הקובץ." });
    } finally {
      setHashing(false);
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    void take(event.dataTransfer.files?.[0]);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void check(code, file?.digest ?? null);
  }

  function clearFile() {
    setFile(null);
    if (picker.current) picker.current.value = "";
    if (CODE.test(code.trim().toUpperCase())) void check(code, null);
    else setOutcome(null);
  }

  const working = busy || hashing;

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-5 py-10">
      <OfficeTopNav />
      <header className="mt-4">
        <p className="text-sm font-semibold text-tide">בדיקה ציבורית · ללא צורך בהתחברות</p>
        <h1 className="mt-2 font-serif text-3xl leading-tight sm:text-4xl">אימות חותם קריפטוגרפי ומסמכים חתומים</h1>
        <p className="mt-3 text-mist">
          כל מי שמחזיק במסמך חתום — הלקוח, המשרד או רשות חיצונית — יכול לבדוק כאן שהחתימה רשומה ותקפה, ושהקובץ שבידיו זהה
          בדיוק לקובץ שנחתם.
        </p>
      </header>

      <form onSubmit={onSubmit} className="mt-8 rounded-lg border-2 border-ink/15 bg-white p-6 shadow-card">
        <label className="block text-sm font-semibold" htmlFor="verify-code">
          קוד אימות
        </label>
        <p className="mt-1 text-sm text-mist">מופיע בדף אישור החתימה שבסוף המסמך החתום.</p>
        <input
          id="verify-code"
          dir="ltr"
          inputMode="text"
          autoComplete="off"
          spellCheck={false}
          maxLength={32}
          placeholder="DV-XXXXXXXXXXXX"
          value={code}
          onChange={(event) => setCode(event.target.value.toUpperCase())}
          className="mt-2 w-full rounded-md border-2 border-line bg-white px-3 py-2 text-left font-mono text-lg tracking-wider outline-none focus:border-tide"
        />

        <p className="mt-6 text-sm font-semibold">הקובץ החתום (PDF)</p>
        <p className="mt-1 text-sm text-mist">
          טביעת האצבע (SHA-256) מחושבת בדפדפן שלכם. הקובץ עצמו אינו נשלח לשום מקום.
        </p>
        <div
          role="button"
          tabIndex={0}
          aria-label="בחירת קובץ PDF חתום לבדיקה"
          onClick={() => picker.current?.click()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              picker.current?.click();
            }
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`mt-2 cursor-pointer rounded-md border-2 border-dashed px-4 py-8 text-center outline-none transition-colors focus-visible:border-tide ${
            dragging ? "border-tide bg-tide/5" : "border-line bg-paper/50 hover:border-tide"
          }`}
        >
          <input
            ref={picker}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={(event) => void take(event.target.files?.[0])}
          />
          {hashing ? (
            <p className="font-medium">מחשבים טביעת אצבע…</p>
          ) : file ? (
            <div>
              <p className="break-all font-medium">{file.name}</p>
              <p className="mt-1 text-sm text-mist">{formatSize(file.size)} · לחצו או גררו כדי להחליף</p>
            </div>
          ) : (
            <div>
              <p className="font-medium">גררו לכאן את קובץ ה־PDF החתום</p>
              <p className="mt-1 text-sm text-mist">או לחצו לבחירת קובץ. אפשר לבדוק גם בלי קוד אימות.</p>
            </div>
          )}
        </div>
        {file ? (
          <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-semibold text-mist">טביעת האצבע של הקובץ שלכם</p>
              <p dir="ltr" className="mt-1 break-all text-left font-mono text-xs">
                {file.digest}
              </p>
            </div>
            <button type="button" onClick={clearFile} className="text-sm font-semibold text-clay underline">
              הסרת הקובץ
            </button>
          </div>
        ) : null}

        <button
          type="submit"
          disabled={working}
          className="mt-6 w-full rounded-md bg-tide px-4 py-3 font-semibold text-white transition-opacity disabled:opacity-60"
        >
          {working ? "בודקים…" : "בדיקת החותם"}
        </button>
      </form>

      <section aria-live="polite" className="mt-6">
        {outcome?.kind === "error" ? (
          <p role="alert" className="rounded-lg border-2 border-clay/40 bg-white p-4 font-medium text-clay">
            {outcome.message}
          </p>
        ) : null}
        {outcome?.kind === "missing" ? (
          <div role="alert" className="rounded-lg border-2 border-clay/40 bg-white p-5">
            <p className="text-lg font-semibold text-clay">
              {outcome.by === "file" ? "הקובץ אינו תואם לאף חותם רשום" : "לא נמצא חותם תחת קוד האימות הזה"}
            </p>
            <p className="mt-2 text-mist">
              {outcome.by === "file"
                ? "ייתכן שהקובץ שונה לאחר החתימה, או שאינו מסמך שנחתם במערכת. אם יש בידיכם קוד אימות, הזינו אותו כדי לדעת אם החותם עצמו קיים."
                : "בדקו שהקוד הועתק במלואו מדף אישור החתימה."}
            </p>
          </div>
        ) : null}
        {outcome?.kind === "seal" ? <SealResult seal={outcome.seal} /> : null}
      </section>
    </main>
  );
}

function SealResult({ seal }: { seal: Seal }) {
  const altered = seal.hash_matches === false;
  const superseded = !seal.valid;
  return (
    <div className="space-y-4">
      {altered ? (
        <Badge tone="clay" mark="✕" title="הקובץ שונה מאז החתימה — טביעת האצבע אינה תואמת">
          הקובץ שבדקתם אינו זהה לקובץ שנחתם תחת קוד זה. אין להסתמך עליו כעל המסמך החתום.
        </Badge>
      ) : null}
      {superseded ? (
        <Badge tone="amberink" mark="!" title="התיק נפתח מחדש והחתימה הוחלפה">
          {seal.hash_matches
            ? "הקובץ אכן נחתם תחת קוד זה, אך החתימה הזו אינה בתוקף עוד. בקשו מהמשרד את המסמך המעודכן."
            : "החתימה שנרשמה תחת קוד זה אינה בתוקף עוד. בקשו מהמשרד את המסמך המעודכן."}
        </Badge>
      ) : null}
      {!altered && !superseded ? (
        <Badge tone="moss" mark="✓" title="מסמך מקורי וחתום דיגיטלית — החותם תקף">
          {seal.hash_matches
            ? "טביעת האצבע של הקובץ שלכם זהה לזו שנרשמה בעת החתימה: הקובץ לא שונה."
            : "החותם רשום ותקף. כדי לוודא שגם הקובץ שבידיכם הוא המסמך שנחתם, גררו אותו לתיבה שלמעלה."}
        </Badge>
      ) : null}

      <dl className="rounded-lg border-2 border-ink/15 bg-white p-5 shadow-card">
        <Row label="קוד אימות">
          <span dir="ltr" className="font-mono">
            {seal.verification_id}
          </span>
        </Row>
        <Row label="מצב החותם">{seal.valid ? "תקף" : "הוחלף"}</Row>
        <Row label="סוג המסמך">{PROCESS_LABELS[seal.process_type] ?? seal.process_type}</Row>
        <Row label="החותם/ת">{seal.masked_client_name || "—"}</Row>
        <Row label="מועד החתימה">{formatDate(seal.signed_at)}</Row>
        <Row label="טביעת אצבע רשומה (SHA-256)">
          <span dir="ltr" className="block break-all text-left font-mono text-xs">
            {seal.signed_pdf_sha256}
          </span>
        </Row>
        <Row label="התאמת הקובץ" last>
          {seal.hash_matches === null ? "לא נבדק קובץ" : seal.hash_matches ? "הקובץ תואם" : "הקובץ אינו תואם"}
        </Row>
      </dl>
      <p className="text-sm text-mist">
        מטעמי פרטיות מוצג כאן שם חלקי בלבד, ללא מספר זהות, כתובת, טלפון או פרטי בנק.
      </p>
    </div>
  );
}

const TONES = {
  moss: "border-moss bg-moss/10 text-moss",
  amberink: "border-amberink bg-amberink/10 text-amberink",
  clay: "border-clay bg-clay/10 text-clay",
} as const;

const MARKS = {
  moss: "bg-moss",
  amberink: "bg-amberink",
  clay: "bg-clay",
} as const;

function Badge({
  tone,
  mark,
  title,
  children,
}: {
  tone: keyof typeof TONES;
  mark: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div role="status" className={`flex gap-4 rounded-lg border-2 p-5 ${TONES[tone]}`}>
      <span
        aria-hidden
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-xl font-bold text-white ${MARKS[tone]}`}
      >
        {mark}
      </span>
      <div>
        <p className="text-lg font-semibold leading-snug">{title}</p>
        <p className="mt-1 text-ink">{children}</p>
      </div>
    </div>
  );
}

function Row({ label, children, last = false }: { label: string; children: React.ReactNode; last?: boolean }) {
  return (
    <div className={`grid gap-1 py-3 sm:grid-cols-[13rem_1fr] sm:gap-4 ${last ? "" : "border-b border-line/60"}`}>
      <dt className="text-sm font-semibold text-mist">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}
