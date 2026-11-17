"use client";

import QRCode from "qrcode";
import { useEffect, useState } from "react";

export function SigningQr({ value }: { value: string }) {
  const [svg, setSvg] = useState("");

  useEffect(() => {
    let cancelled = false;
    void QRCode.toString(value, {
      type: "svg",
      margin: 1,
      width: 148,
      errorCorrectionLevel: "M",
      color: { dark: "#16130f", light: "#ffffff" },
    }).then((markup) => {
      if (!cancelled) setSvg(markup);
    });
    return () => {
      cancelled = true;
    };
  }, [value]);

  if (!svg) return null;
  return (
    <figure className="shrink-0 rounded-md border border-ink/15 bg-white p-2">
      <div
        className="h-[148px] w-[148px] [&_svg]:h-full [&_svg]:w-full"
        aria-label="קוד QR לקישור החתימה"
        role="img"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      <figcaption className="mt-1 max-w-[148px] text-center text-xs font-semibold leading-5 text-ink">
        סרקו לפתיחת החתימה בטלפון
      </figcaption>
    </figure>
  );
}
