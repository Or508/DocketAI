import Link from "next/link";

/**
 * Links every public page carries: privacy, terms, accessibility, and the signed-document check.
 * Server component, no state; safe to drop at the bottom of any page.
 */
export function LegalFooter({ frame = "max-w-3xl px-4" }: { frame?: string }) {
  return (
    <footer className="mt-12 border-t border-line bg-white print:hidden">
      <nav aria-label="מידע משפטי ונגישות" className={`mx-auto flex flex-wrap gap-x-5 gap-y-2 py-5 text-sm text-mist ${frame}`}>
        <Link href="/privacy" className="underline-offset-4 hover:text-ink hover:underline focus-visible:text-ink focus-visible:underline">
          מדיניות פרטיות
        </Link>
        <Link href="/terms" className="underline-offset-4 hover:text-ink hover:underline focus-visible:text-ink focus-visible:underline">
          תנאי שימוש
        </Link>
        <Link href="/accessibility" className="underline-offset-4 hover:text-ink hover:underline focus-visible:text-ink focus-visible:underline">
          הצהרת נגישות
        </Link>
        <Link href="/verify" className="underline-offset-4 hover:text-ink hover:underline focus-visible:text-ink focus-visible:underline">
          אימות מסמך חתום
        </Link>
      </nav>
    </footer>
  );
}
