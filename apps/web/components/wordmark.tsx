import Link from "next/link";

export function Wordmark({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex items-baseline gap-2">
      <span className="font-serif text-xl tracking-tight">Docket</span>
      <span className="text-[11px] uppercase tracking-[0.22em] text-tide">AI</span>
    </Link>
  );
}
