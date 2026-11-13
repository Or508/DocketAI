"use client";

import type { PortalSeal } from "@docketai/shared-types";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export function IntegrityPanel({
  seal,
  downloadExpiresAt,
  signedPdfUrl,
  certificateUrl,
}: {
  seal: PortalSeal;
  downloadExpiresAt: string | null;
  signedPdfUrl: string;
  certificateUrl: string;
}) {
  const [copied, setCopied] = useState(false);
  const signed = new Intl.DateTimeFormat("he-IL", {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone: seal.time_zone,
  }).format(new Date(seal.signed_at));

  return (
    <section className="rounded-lg border border-line bg-white/80 shadow-card">
      <div className="border-b border-line px-4 py-4">
        <p className="text-sm font-semibold text-tide">אישור והורדה</p>
        <h2 className="font-serif text-2xl">טביעת אצבע של הקובץ</h2>
      </div>
      <div className="space-y-4 px-4 py-4">
        <p className="text-sm leading-6">נחתם ב־{signed}, שעון ישראל.</p>
        <p className="text-sm leading-6">
          מזהה אימות <span className="break-all font-mono text-xs">{seal.signer_verification_id}</span>
        </p>
        <div>
          <p className="text-sm leading-6">טביעת אצבע SHA-256</p>
          <p className="mt-2 break-all rounded-md border border-line bg-[#fbf8f2] p-3 font-mono text-xs leading-5">
            {seal.file_sha256}
          </p>
          <Button
            type="button"
            variant="outline"
            className="mt-2 min-h-11"
            onClick={() => {
              // The clipboard API is missing on insecure origins and some in-app browsers.
              if (!navigator.clipboard) return;
              void navigator.clipboard.writeText(seal.file_sha256).then(
                () => setCopied(true),
                () => setCopied(false),
              );
            }}
          >
            {copied ? "הועתק" : "העתקה"}
          </Button>
        </div>
        {seal.recorded_ip ? (
          <p className="break-all text-sm leading-6" dir="auto">
            כתובת רשת שנרשמה {seal.recorded_ip}
          </p>
        ) : null}
        <p className="text-sm leading-6">טביעת האצבע של הקובץ שהורדתם צריכה להיות זהה.</p>
        <details className="rounded-md border border-line bg-[#fbf8f2]">
          <summary className="flex min-h-11 cursor-pointer items-center px-3 text-sm">איך בודקים את הקובץ</summary>
          <pre className="whitespace-pre-wrap break-all px-3 pb-3 font-mono text-xs leading-5">{`shasum -a 256 signed-document.pdf
certutil -hashfile signed-document.pdf SHA256`}</pre>
        </details>
        <div className="flex flex-col gap-2">
          <Button asChild className="min-h-11 w-full">
            <a href={signedPdfUrl}>הורדת הטופס החתום</a>
          </Button>
          <Button asChild variant="outline" className="min-h-11 w-full">
            <a href={certificateUrl}>הורדת אישור החתימה</a>
          </Button>
        </div>
        {downloadExpiresAt ? (
          <p className="text-sm text-mist">
            ההורדה פתוחה עד{" "}
            {`${new Intl.DateTimeFormat("he-IL", { dateStyle: "long", timeZone: seal.time_zone }).format(
              new Date(downloadExpiresAt),
            )}.`}
          </p>
        ) : null}
      </div>
    </section>
  );
}
