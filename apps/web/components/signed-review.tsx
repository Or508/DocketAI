const CHECKS = ["שם מלא", "מספר זהות", "כתובת", "טלפון נייד", "פרטי בנק"] as const;

export function SignedChecklist() {
  return (
    <div className="rounded-md border border-moss bg-[#e7f3ea] px-4 py-3 text-sm text-[#145c38]">
      <p className="font-semibold">10 מתוך 10 שדות מולאו בטופס + חתימה דיגיטלית הוטבעה</p>
      <ul className="mt-2 grid gap-1 sm:grid-cols-2">
        {CHECKS.map((item) => (
          <li key={item} className="font-medium">
            ✓ {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SignedPdfFrame({ src }: { src: string }) {
  const view = src.includes("?") ? `${src}&view=1` : `${src}?view=1`;
  return (
    <iframe
      title="הטופס החתום"
      src={view}
      className="h-[72vh] w-full rounded-md border border-ink/15 bg-white"
    />
  );
}
