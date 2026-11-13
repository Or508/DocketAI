import Link from "next/link";

export function Wordmark({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex items-baseline gap-2 rounded-sm">
      <span className="font-serif text-xl tracking-tight text-ink">ארון תיוק</span>
      <span className="text-xs font-semibold text-tide">מסמכים</span>
    </Link>
  );
}
