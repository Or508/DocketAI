import { FolderOpen, Lock } from "lucide-react";

/**
 * The header a client sees on the public pages (signing, document upload, seal check):
 * the product name and a note that the page is a secure link. No office navigation.
 * Shared by app/sign, app/upload and app/verify.
 */
export function PublicBrand({ frame = "max-w-3xl px-4" }: { frame?: string }) {
  // `frame` is the page's own width and side padding, so the header lines up with the content below.
  return (
    <header className="border-b border-line bg-white/95 print:hidden">
      <div className={`mx-auto flex h-14 items-center justify-between gap-3 ${frame}`}>
        <span className="flex items-center gap-2.5">
          <span aria-hidden className="flex h-8 w-8 items-center justify-center rounded-lg bg-tide text-white shadow-sm">
            <FolderOpen className="h-[18px] w-[18px]" />
          </span>
          <span dir="ltr" className="text-base font-bold tracking-tight text-ink">
            DocketFlow
          </span>
        </span>
        <span className="flex items-center gap-1.5 text-xs font-medium text-mist">
          <Lock aria-hidden className="h-3.5 w-3.5" />
          חיבור מאובטח
        </span>
      </div>
    </header>
  );
}
