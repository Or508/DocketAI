"use client";

import QRCode from "qrcode";
import { useEffect, useState } from "react";

export function SigningQr({ value, prominent = false }: { value: string; prominent?: boolean }) {
  const [svg, setSvg] = useState("");
  const size = prominent ? 220 : 148;

  useEffect(() => {
    let cancelled = false;
    void QRCode.toString(value, {
      type: "svg",
      margin: 1,
      width: size,
      errorCorrectionLevel: "M",
      color: { dark: "#16130f", light: "#ffffff" },
    }).then((markup) => {
      if (!cancelled) setSvg(markup);
    });
    return () => {
      cancelled = true;
    };
  }, [value, size]);

  if (!svg) return null;
  return (
    <figure className={`shrink-0 rounded-md border border-ink/15 bg-white p-2 ${prominent ? "shadow-md" : ""}`}>
      <div
        className={`${prominent ? "h-[220px] w-[220px]" : "h-[148px] w-[148px]"} [&_svg]:h-full [&_svg]:w-full`}
        aria-label="קוד QR לקישור החתימה"
        role="img"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      <figcaption
        className={`mt-1 text-center font-semibold leading-5 text-ink ${
          prominent ? "max-w-[220px] text-base" : "max-w-[148px] text-xs"
        }`}
      >
        {prominent ? "סרקו כדי לחתום מהטלפון" : "סרקו לפתיחת החתימה בטלפון"}
      </figcaption>
    </figure>
  );
}
