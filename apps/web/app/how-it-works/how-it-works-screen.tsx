"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowLeft,
  BadgeCheck,
  Briefcase,
  Building2,
  CircleCheck,
  Circle,
  Clock,
  Download,
  Eye,
  FileText,
  FolderOpen,
  History,
  KeyRound,
  ListChecks,
  Lock,
  MessageSquare,
  PenLine,
  RotateCcw,
  Scale,
  ScanSearch,
  ShieldCheck,
  Stethoscope,
  Upload,
} from "lucide-react";

// ---------------------------------------------------------------------------------------------
// Sample data. The same invented employee as the downloadable files in /public/demo.
// ---------------------------------------------------------------------------------------------

type DocKey = "id" | "arnona" | "bank";

type SampleDoc = {
  key: DocKey;
  title: string;
  file: string;
  explains: string;
  fills: string[];
};

const DOCS: SampleDoc[] = [
  {
    key: "id",
    title: "צילום תעודת זהות",
    file: "/demo/01-teudat-zehut.pdf",
    explains: "המערכת מזהה את השם ואת מספר הזהות, ובודקת את ספרת הביקורת.",
    fills: ["first_name", "last_name", "national_id"],
  },
  {
    key: "arnona",
    title: "חשבון ארנונה",
    file: "/demo/02-arnona.pdf",
    explains: "מכאן נלקחת כתובת המגורים לטופס.",
    fills: ["street", "house_number", "city"],
  },
  {
    key: "bank",
    title: "אישור ניהול חשבון",
    file: "/demo/03-ishur-bank.pdf",
    explains: "מכאן נלקחים פרטי הבנק להעברת המשכורת.",
    fills: ["bank_name", "bank_branch", "bank_account"],
  },
];

type Field = { key: string; label: string; value: string; from: DocKey | "clerk" };

const FIELDS: Field[] = [
  { key: "first_name", label: "שם פרטי", value: "דנה", from: "id" },
  { key: "last_name", label: "שם משפחה", value: "כהן", from: "id" },
  { key: "national_id", label: "מספר זהות", value: "100000009", from: "id" },
  { key: "street", label: "רחוב", value: "הרצל", from: "arnona" },
  { key: "house_number", label: "מס' בית", value: "15", from: "arnona" },
  { key: "city", label: "יישוב", value: "תל אביב", from: "arnona" },
  { key: "phone", label: "טלפון נייד", value: "050-1234567", from: "clerk" },
  { key: "bank_name", label: "שם הבנק", value: "לאומי", from: "bank" },
  { key: "bank_branch", label: "מס' סניף", value: "800", from: "bank" },
  { key: "bank_account", label: "מספר חשבון", value: "456789", from: "bank" },
];

const SOURCE_LABEL: Record<Field["from"], string> = {
  id: "מתעודת הזהות",
  arnona: "מחשבון הארנונה",
  bank: "מאישור הבנק",
  clerk: "הלקוח ענה בצ׳אט",
};

// ---------------------------------------------------------------------------------------------
// Page copy.
// ---------------------------------------------------------------------------------------------

const PAINS = [
  {
    icon: MessageSquare,
    title: "רודפים אחרי מסמכים",
    text: "צילומים מגיעים בוואטסאפ, במייל ובדואר. חלק חסרים, חלק לא קריאים, ואף אחד לא יודע מה עוד חסר בתיק.",
  },
  {
    icon: FileText,
    title: "מקלידים את אותם פרטים שוב",
    text: "מספר זהות, כתובת וחשבון בנק מועתקים ידנית מהמסמך לטופס. כל ספרה שגויה היא טופס שחוזר.",
  },
  {
    icon: PenLine,
    title: "חתימה על נייר",
    text: "מדפיסים, שולחים, מחכים, סורקים. ובסוף אין תיעוד מסודר של מי חתם, מתי ועל איזו גרסה.",
  },
  {
    icon: Clock,
    title: "זמן של המשרד הולך לאיבוד",
    text: "שעות של עבודה פקידותית על כל תיק, במקום על העבודה המקצועית עצמה.",
  },
];

const STEPS = [
  {
    icon: Upload,
    title: "הלקוח מעלה מסמכים",
    text: "בקישור אישי מהנייד או מהמחשב. בלי אפליקציה ובלי סיסמה. כל קובץ נבדק לפני שהוא נכנס לתיק.",
  },
  {
    icon: ScanSearch,
    title: "המערכת ממיינת ומזהה",
    text: "כל מסמך נכנס למגירה הנכונה בתיק: תעודת זהות, חשבון ארנונה, אישור בנק. מסמך שהמערכת לא בטוחה בו מחכה לאישור שלכם.",
  },
  {
    icon: ListChecks,
    title: "רואים מה חסר",
    text: "רשימה ברורה של מה כבר יש בתיק ומה עדיין חסר, לפני שמישהו מגלה את זה ברגע האחרון.",
  },
  {
    icon: MessageSquare,
    title: "הטופס מתמלא מהמסמכים",
    text: "הפרטים נלקחים מהמסמכים עצמם. מה שאין במסמכים, הלקוח משלים בצ׳אט קצר שבודק כל תשובה, למשל ספרת ביקורת של תעודת זהות.",
  },
  {
    icon: PenLine,
    title: "הלקוח חותם",
    text: "הלקוח רואה את הטופס המלא לפני החתימה, וחותם על המסך. אם מישהו במשרד משנה פרט אחר כך, נדרשת חתימה מחדש.",
  },
  {
    icon: BadgeCheck,
    title: "תיק סגור ומתועד",
    text: "קובץ PDF חתום עם תעודת השלמה: מי חתם, מתי, ומאיזה מכשיר. כל אחד יכול לבדוק שהקובץ לא שונה.",
  },
];

const AUDIENCES = [
  { icon: Scale, title: "משרדי עורכי דין ונוטריון", text: "קליטת לקוח, ייפוי כוח, הסכמי שכר טרחה ותיקים שחוזרים על עצמם." },
  { icon: Building2, title: "תיווך ונדל״ן", text: "עסקת מקרקעין: מסמכי זיהוי, נסחים ואישורים, וחתימה של הצדדים." },
  { icon: Briefcase, title: "שכר ומשאבי אנוש", text: "טופס 101 לעובד חדש, מלא מתוך המסמכים שלו וחתום תוך דקות." },
  { icon: Stethoscope, title: "מרפאות", text: "טופסי הסכמה לטיפול, חתומים לפני הטיפול ושמורים בתיק המטופל." },
];

const SECURITY = [
  { icon: KeyRound, title: "קישור אישי לכל לקוח", text: "כל קישור פותח רק את התיק שלו, ונסגר לכתיבה ברגע שהחתימה הושלמה." },
  { icon: Lock, title: "כניסה בשני שלבים למשרד", text: "סיסמה וקוד מאפליקציית אימות. אחרי כמה ניסיונות שגויים הכתובת ננעלת." },
  { icon: History, title: "כל פעולה מתועדת", text: "יומן ביקורת של העלאות, שינויים וחתימות. אפשר לייצא אותו." },
  { icon: Eye, title: "אתם מחליטים על ה-AI", text: "אפשר לכבות את הקריאה האוטומטית לכל המשרד. אז כל מסמך ממתין לאישור של אדם." },
];

const FAQ = [
  {
    q: "האם הלקוח צריך להתקין משהו או לפתוח חשבון?",
    a: "לא. הלקוח מקבל קישור, מעלה מסמכים, עונה על כמה שאלות וחותם. הכול בדפדפן, גם בנייד.",
  },
  {
    q: "מה קורה אם המערכת קוראת פרט לא נכון?",
    a: "כל פרט מסומן במקור שלו, והמשרד יכול לבדוק ולתקן לפני השליחה לחתימה. מסמך שהמערכת לא בטוחה בו לא נספר כמסמך שהתקבל.",
  },
  {
    q: "האם החתימה תקפה?",
    a: "זו חתימה אלקטרונית עם תיעוד מלא של התהליך וטביעת אצבע של הקובץ. למסמכים שהחוק דורש בהם חתימה אלקטרונית מאושרת, דברו איתנו.",
  },
  {
    q: "איפה נשמרים המסמכים?",
    a: "באחסון של המשרד, מופרדים ממשרדים אחרים. המערכת לא שומרת את שם הקובץ או את שם הלקוח בנתיב האחסון.",
  },
  {
    q: "אפשר לנסות לפני שמתחייבים?",
    a: "כן. ההדגמה בדף הזה עובדת בלי הרשמה, ואת שלושת הקבצים לדוגמה אפשר להעלות לתיק אמיתי במערכת ולראות את התהליך מקצה לקצה.",
  },
];

// ---------------------------------------------------------------------------------------------
// Screen.
// ---------------------------------------------------------------------------------------------

export function HowItWorksScreen() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:right-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:shadow-lift"
      >
        דלג לתוכן
      </a>
      <SiteHeader />
      <main id="main">
        <Hero />
        <Section id="problem" eyebrow="הבעיה" title="מה גוזל למשרד את הזמן">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {PAINS.map((item) => (
              <Card key={item.title} icon={item.icon} title={item.title} text={item.text} tone="clay" />
            ))}
          </div>
        </Section>
        <Section id="how" eyebrow="הפתרון" title="איך זה עובד, בשישה צעדים" tinted>
          <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {STEPS.map((step, index) => (
              <li key={step.title} className="rounded-lg border border-line bg-white p-5 shadow-card">
                <div className="mb-3 flex items-center gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-tide text-sm font-bold text-white">
                    {index + 1}
                  </span>
                  <step.icon aria-hidden className="h-5 w-5 text-tide" />
                </div>
                <h3 className="text-base font-bold">{step.title}</h3>
                <p className="mt-1.5 text-sm leading-6 text-mist">{step.text}</p>
              </li>
            ))}
          </ol>
        </Section>
        <Section
          id="demo"
          eyebrow="הדגמה"
          title="נסו בעצמכם: טופס 101 לעובדת חדשה"
          lead="לחצו על המסמכים לפי הסדר ותראו איך התיק מתמלא. כל הפרטים בדויים."
        >
          <Demo />
        </Section>
        <Section id="samples" eyebrow="קבצים לדוגמה" title="הורידו ונסו במערכת עצמה" tinted>
          <Samples />
        </Section>
        <Section id="who" eyebrow="למי זה מתאים" title="לכל משרד שעובד עם מסמכים של לקוחות">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {AUDIENCES.map((item) => (
              <Card key={item.title} icon={item.icon} title={item.title} text={item.text} />
            ))}
          </div>
        </Section>
        <Section id="security" eyebrow="אבטחה ופרטיות" title="המידע של הלקוחות שלכם נשאר שלכם" tinted>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {SECURITY.map((item) => (
              <Card key={item.title} icon={item.icon} title={item.title} text={item.text} />
            ))}
          </div>
          <p className="mt-5 text-sm text-mist">
            קיבלתם מסמך חתום וחשוב לכם לדעת שלא שונה?{" "}
            <Link href="/verify" className="font-semibold text-tide underline underline-offset-4">
              בדקו אותו כאן
            </Link>
            .
          </p>
        </Section>
        <Section id="faq" eyebrow="שאלות נפוצות" title="מה שואלים אותנו">
          <div className="divide-y divide-line rounded-lg border border-line bg-white shadow-card">
            {FAQ.map((item) => (
              <details key={item.q} className="group p-5 [&_summary::-webkit-details-marker]:hidden">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold">
                  {item.q}
                  <span aria-hidden className="text-xl leading-none text-tide transition group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="mt-3 text-sm leading-6 text-mist">{item.a}</p>
              </details>
            ))}
          </div>
        </Section>
      </main>
      <SiteFooter />
    </div>
  );
}

function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4">
        <Link href="/how-it-works" className="flex items-center gap-2.5" aria-label="DocketFlow — איך זה עובד">
          <span aria-hidden className="flex h-8 w-8 items-center justify-center rounded-lg bg-tide text-white shadow-sm">
            <FolderOpen className="h-[18px] w-[18px]" />
          </span>
          <span dir="ltr" className="text-base font-bold tracking-tight">
            DocketFlow
          </span>
        </Link>
        <nav aria-label="ניווט בדף" className="hidden items-center gap-5 text-sm font-medium text-mist md:flex">
          <a href="#how" className="hover:text-ink">איך זה עובד</a>
          <a href="#demo" className="hover:text-ink">הדגמה</a>
          <a href="#samples" className="hover:text-ink">קבצים לדוגמה</a>
          <a href="#security" className="hover:text-ink">אבטחה</a>
          <a href="#faq" className="hover:text-ink">שאלות</a>
        </nav>
        <Link
          href="/login"
          className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink hover:border-tide hover:text-tide"
        >
          כניסה למשרד
        </Link>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="border-b border-line bg-white">
      <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-14 md:grid-cols-[1.1fr_0.9fr] md:py-20">
        <div>
          <p className="mb-3 inline-flex items-center gap-2 rounded-full bg-mint px-3 py-1 text-xs font-semibold text-tide">
            <ShieldCheck aria-hidden className="h-3.5 w-3.5" />
            בעברית, מקצה לקצה
          </p>
          <h1 className="text-3xl font-extrabold leading-tight tracking-tight sm:text-4xl md:text-5xl">
            פחות רדיפה אחרי מסמכים.
            <br />
            פחות הקלדה. חתימה בתוך דקות.
          </h1>
          <p className="mt-5 max-w-xl text-lg leading-8 text-mist">
            הלקוח מעלה מסמכים בקישור אישי. DocketFlow ממיין אותם, מראה מה חסר, ממלא את הטופס מתוך המסמכים ושולח
            לחתימה דיגיטלית עם תיעוד מלא.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <a
              href="#demo"
              className="inline-flex items-center gap-2 rounded-md bg-tide px-5 py-3 font-semibold text-white shadow-card hover:bg-[#0b403b]"
            >
              לנסות את ההדגמה
              <ArrowLeft aria-hidden className="h-4 w-4" />
            </a>
            <a
              href="#samples"
              className="inline-flex items-center gap-2 rounded-md border border-line bg-white px-5 py-3 font-semibold hover:border-tide hover:text-tide"
            >
              <Download aria-hidden className="h-4 w-4" />
              קבצים לדוגמה
            </a>
          </div>
        </div>
        <HeroCase />
      </div>
    </section>
  );
}

/** A still picture of a finished case, so the outcome is visible before the reader scrolls. */
function HeroCase() {
  return (
    <div aria-hidden className="rounded-lg border border-line bg-paper p-4 shadow-lift">
      <div className="rounded-md border border-line bg-white p-4">
        <div className="flex items-center justify-between">
          <span className="font-bold">דנה כהן · טופס 101</span>
          <span className="rounded-full bg-[#e3f1e8] px-2.5 py-0.5 text-xs font-semibold text-moss">חתום</span>
        </div>
        <ul className="mt-4 space-y-2 text-sm">
          {DOCS.map((doc) => (
            <li key={doc.key} className="flex items-center gap-2">
              <CircleCheck className="h-4 w-4 text-moss" />
              {doc.title}
            </li>
          ))}
        </ul>
        <div className="mt-4 h-2 rounded-full bg-line">
          <div className="h-2 w-full rounded-full bg-tide" />
        </div>
        <p className="mt-2 text-xs text-mist">10 מתוך 10 פרטים מולאו · 9 מהם מתוך המסמכים</p>
      </div>
      <div className="mt-3 flex items-center gap-2 rounded-md border border-line bg-white p-3 text-xs text-mist">
        <BadgeCheck className="h-4 w-4 text-tide" />
        תעודת השלמה · קוד אימות <span dir="ltr" className="font-mono text-ink">DV-3F9A12C07B4E</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// The interactive demo. Nothing leaves the browser.
// ---------------------------------------------------------------------------------------------

type Stage = "collect" | "review" | "signed";

function Demo() {
  const [added, setAdded] = useState<DocKey[]>([]);
  const [phone, setPhone] = useState(false);
  const [stage, setStage] = useState<Stage>("collect");
  const [lastNote, setLastNote] = useState("התיק נפתח. ממתינים למסמכים של העובדת.");

  const filled = FIELDS.filter((field) => (field.from === "clerk" ? phone : added.includes(field.from)));
  const allDocs = added.length === DOCS.length;
  const complete = filled.length === FIELDS.length;

  function add(doc: SampleDoc) {
    if (added.includes(doc.key)) return;
    setAdded((current) => [...current, doc.key]);
    setLastNote(`${doc.title} התקבל ונכנס למגירה. מולאו ${doc.fills.length} פרטים בטופס.`);
  }

  function answer() {
    setPhone(true);
    setLastNote("העובדת ענתה בצ׳אט. המספר נבדק ונרשם בטופס.");
  }

  function sign() {
    setStage("signed");
    setLastNote("העובדת חתמה. נוצר קובץ PDF חתום עם תעודת השלמה.");
  }

  function reset() {
    setAdded([]);
    setPhone(false);
    setStage("collect");
    setLastNote("ההדגמה התחילה מחדש.");
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
      {/* The client's side. */}
      <div className="rounded-lg border border-line bg-white p-5 shadow-card">
        <h3 className="flex items-center gap-2 font-bold">
          <Upload aria-hidden className="h-4 w-4 text-tide" />
          1. המסמכים שהעובדת מעלה
        </h3>
        <ul className="mt-4 space-y-3">
          {DOCS.map((doc) => {
            const done = added.includes(doc.key);
            return (
              <li key={doc.key} className={`rounded-md border p-3 ${done ? "border-[#bcdcc8] bg-[#f1f8f3]" : "border-line"}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold">{doc.title}</p>
                    <p className="mt-0.5 text-sm text-mist">{doc.explains}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => add(doc)}
                    disabled={done || stage === "signed"}
                    className="shrink-0 rounded-md bg-tide px-3 py-1.5 text-sm font-semibold text-white hover:bg-[#0b403b] disabled:cursor-default disabled:bg-[#cfe5e1] disabled:text-tide"
                  >
                    {done ? "בתיק ✓" : "העלאה"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>

        <div className="mt-5 border-t border-line pt-4">
          <h3 className="flex items-center gap-2 font-bold">
            <MessageSquare aria-hidden className="h-4 w-4 text-tide" />
            2. מה שאין במסמכים
          </h3>
          <div className="mt-3 space-y-2 text-sm">
            <p className="max-w-[85%] rounded-lg rounded-tr-sm bg-paper px-3 py-2">
              מה מספר הטלפון הנייד שלך? נשתמש בו רק לעדכונים על הטופס.
            </p>
            {phone ? (
              <p className="mr-auto max-w-[85%] rounded-lg rounded-tl-sm bg-tide px-3 py-2 text-white" dir="rtl">
                <span dir="ltr">050-1234567</span>
              </p>
            ) : (
              <button
                type="button"
                onClick={answer}
                disabled={stage === "signed"}
                className="mr-auto block rounded-md border border-tide px-3 py-1.5 font-semibold text-tide hover:bg-mint"
              >
                לענות בשם העובדת
              </button>
            )}
          </div>
        </div>
      </div>

      {/* The office's side. */}
      <div className="rounded-lg border border-line bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 font-bold">
            <FolderOpen aria-hidden className="h-4 w-4 text-tide" />
            3. מה המשרד רואה: התיק של דנה כהן
          </h3>
          <button type="button" onClick={reset} className="inline-flex items-center gap-1 text-sm text-mist hover:text-ink">
            <RotateCcw aria-hidden className="h-3.5 w-3.5" />
            להתחיל מחדש
          </button>
        </div>

        <p role="status" aria-live="polite" className="mt-3 rounded-md bg-mint px-3 py-2 text-sm text-tide">
          {lastNote}
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-[0.8fr_1.2fr]">
          <div>
            <p className="text-sm font-semibold">מסמכים בתיק</p>
            <ul className="mt-2 space-y-1.5 text-sm">
              {DOCS.map((doc) => (
                <li key={doc.key} className="flex items-center gap-2">
                  {added.includes(doc.key) ? (
                    <CircleCheck aria-hidden className="h-4 w-4 text-moss" />
                  ) : (
                    <Circle aria-hidden className="h-4 w-4 text-line" />
                  )}
                  <span className={added.includes(doc.key) ? "" : "text-mist"}>
                    {doc.title}
                    <span className="sr-only">{added.includes(doc.key) ? " — התקבל" : " — חסר"}</span>
                  </span>
                </li>
              ))}
            </ul>
            {!allDocs && (
              <p className="mt-3 text-xs text-clay">
                חסרים {DOCS.length - added.length} מסמכים. אי אפשר לשלוח לחתימה עד שהתיק שלם.
              </p>
            )}
          </div>

          <div>
            <div className="flex items-center justify-between text-sm">
              <span className="font-semibold">טופס 101</span>
              <span className="text-mist">
                {filled.length} מתוך {FIELDS.length} פרטים
              </span>
            </div>
            <div
              className="mt-2 h-2 rounded-full bg-line"
              role="progressbar"
              aria-label="פרטים שמולאו בטופס"
              aria-valuemin={0}
              aria-valuemax={FIELDS.length}
              aria-valuenow={filled.length}
            >
              <div
                className="h-2 rounded-full bg-tide transition-all duration-500 motion-reduce:transition-none"
                style={{ width: `${(filled.length / FIELDS.length) * 100}%` }}
              />
            </div>
            <dl className="mt-3 divide-y divide-line rounded-md border border-line text-sm">
              {FIELDS.map((field) => {
                const shown = filled.includes(field);
                return (
                  <div key={field.key} className="flex items-baseline justify-between gap-2 px-3 py-1.5">
                    <dt className="text-mist">{field.label}</dt>
                    <dd className="text-left">
                      {shown ? (
                        <>
                          <span className="font-semibold" dir={/\d/.test(field.value) ? "ltr" : "rtl"}>
                            {field.value}
                          </span>
                          <span className="block text-[11px] text-mist">{SOURCE_LABEL[field.from]}</span>
                        </>
                      ) : (
                        <span className="text-mist">—</span>
                      )}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </div>
        </div>

        <div className="mt-5 border-t border-line pt-4">
          {stage === "signed" ? (
            <div className="rounded-md border border-[#bcdcc8] bg-[#f1f8f3] p-4">
              <p className="flex items-center gap-2 font-bold text-moss">
                <BadgeCheck aria-hidden className="h-5 w-5" />
                הטופס נחתם ונשמר בתיק
              </p>
              <ul className="mt-2 space-y-1 text-sm text-ink">
                <li>קובץ PDF חתום עם תעודת השלמה ומספור עמודים.</li>
                <li>נרשמו מי חתם, מתי, ומאיזה מכשיר.</li>
                <li>
                  קוד אימות לבדיקה ציבורית: <span dir="ltr" className="font-mono">DV-3F9A12C07B4E</span>
                </li>
              </ul>
            </div>
          ) : stage === "review" ? (
            <div className="rounded-md border border-line p-4">
              <p className="font-semibold">4. העובדת רואה את הטופס המלא וחותמת</p>
              <div className="mt-3 flex h-20 items-center justify-center rounded-md border border-dashed border-mist/40 bg-paper text-sm text-mist">
                <span className="font-[cursive] text-2xl text-ink">דנה כהן</span>
              </div>
              <button
                type="button"
                onClick={sign}
                className="mt-3 inline-flex items-center gap-2 rounded-md bg-tide px-4 py-2 font-semibold text-white hover:bg-[#0b403b]"
              >
                <PenLine aria-hidden className="h-4 w-4" />
                לחתום בשם העובדת
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => {
                setStage("review");
                setLastNote("נשלח קישור חתימה. העובדת בודקת את הטופס.");
              }}
              disabled={!complete}
              className="inline-flex items-center gap-2 rounded-md bg-tide px-4 py-2 font-semibold text-white hover:bg-[#0b403b] disabled:cursor-not-allowed disabled:bg-line disabled:text-mist"
            >
              <PenLine aria-hidden className="h-4 w-4" />
              שליחה לחתימה
            </button>
          )}
          {!complete && stage === "collect" && (
            <p className="mt-2 text-xs text-mist">הכפתור נפתח כשכל המסמכים בתיק והלקוחה ענתה על השאלה.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function Samples() {
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
      <div className="rounded-lg border border-line bg-white p-5 shadow-card">
        <h3 className="font-bold">שלושה מסמכים של עובדת בדויה</h3>
        <p className="mt-1 text-sm text-mist">כל קובץ מסומן כמסמך לדוגמה. הפרטים לא שייכים לאדם אמיתי.</p>
        <ul className="mt-4 space-y-3">
          {DOCS.map((doc) => (
            <li key={doc.key}>
              <a
                href={doc.file}
                download
                className="flex items-center justify-between gap-3 rounded-md border border-line p-3 hover:border-tide"
              >
                <span className="flex items-center gap-3">
                  <FileText aria-hidden className="h-5 w-5 text-tide" />
                  <span>
                    <span className="block font-semibold">{doc.title}</span>
                    <span className="block text-xs text-mist">PDF · {doc.explains}</span>
                  </span>
                </span>
                <Download aria-hidden className="h-4 w-4 shrink-0 text-mist" />
                <span className="sr-only">הורדה</span>
              </a>
            </li>
          ))}
        </ul>
      </div>
      <div className="rounded-lg border border-line bg-white p-5 shadow-card">
        <h3 className="font-bold">כך מנסים אותם במערכת</h3>
        <ol className="mt-4 space-y-3 text-sm leading-6">
          {[
            "נכנסים למערכת ופותחים תיק חדש מסוג ״טופס 101 — קליטת עובד חדש״.",
            "גוררים לתיק את שלושת הקבצים, או שולחים ללקוח קישור להעלאה ומעלים דרכו.",
            "רואים כל מסמך נכנס למגירה שלו, ואת הטופס מתמלא מתוך המסמכים.",
            "משלימים את הטלפון, בודקים את הטופס ושולחים קישור לחתימה.",
            "אחרי החתימה מורידים את הקובץ החתום ובודקים אותו בדף האימות.",
          ].map((text, index) => (
            <li key={text} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-mint text-xs font-bold text-tide">
                {index + 1}
              </span>
              {text}
            </li>
          ))}
        </ol>
        <Link
          href="/login"
          className="mt-5 inline-flex items-center gap-2 rounded-md bg-tide px-4 py-2 font-semibold text-white hover:bg-[#0b403b]"
        >
          כניסה למערכת
          <ArrowLeft aria-hidden className="h-4 w-4" />
        </Link>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Building blocks.
// ---------------------------------------------------------------------------------------------

function Section({
  id,
  eyebrow,
  title,
  lead,
  tinted = false,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  lead?: string;
  tinted?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={`scroll-mt-16 ${tinted ? "bg-[#efefea]" : ""}`}>
      <div className="mx-auto max-w-6xl px-4 py-14">
        <p className="text-sm font-semibold text-tide">{eyebrow}</p>
        <h2 id={`${id}-title`} className="mt-1 text-2xl font-extrabold tracking-tight sm:text-3xl">
          {title}
        </h2>
        {lead && <p className="mt-2 max-w-2xl text-mist">{lead}</p>}
        <div className="mt-7">{children}</div>
      </div>
    </section>
  );
}

function Card({
  icon: Icon,
  title,
  text,
  tone = "tide",
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  title: string;
  text: string;
  tone?: "tide" | "clay";
}) {
  return (
    <div className="rounded-lg border border-line bg-white p-5 shadow-card">
      <span
        className={`flex h-10 w-10 items-center justify-center rounded-lg ${tone === "clay" ? "bg-[#f6e7e2] text-clay" : "bg-mint text-tide"}`}
      >
        <Icon aria-hidden className="h-5 w-5" />
      </span>
      <h3 className="mt-3 font-bold">{title}</h3>
      <p className="mt-1.5 text-sm leading-6 text-mist">{text}</p>
    </div>
  );
}

function SiteFooter() {
  return (
    <footer className="border-t border-line bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-sm text-mist">
        <span dir="ltr">DocketFlow</span>
        <nav aria-label="קישורים" className="flex gap-5">
          <Link href="/verify" className="hover:text-ink">אימות מסמך חתום</Link>
          <Link href="/login" className="hover:text-ink">כניסה למשרד</Link>
        </nav>
      </div>
    </footer>
  );
}
