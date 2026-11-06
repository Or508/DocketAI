"use client";

import { useEffect, useRef, useState } from "react";
import SignatureCanvas from "react-signature-canvas";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

export function SigningModal({
  open,
  busy,
  consentLabel,
  onOpenChange,
  onSign,
}: {
  open: boolean;
  busy: boolean;
  consentLabel?: string;
  onOpenChange: (open: boolean) => void;
  onSign: (pngDataUrl: string) => Promise<void>;
}) {
  const pad = useRef<SignatureCanvas>(null);
  const sending = useRef(false);
  const [padError, setPadError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setAccepted(false);
    setPadError(null);
    setSubmitting(false);
    sending.current = false;
    const frame = window.requestAnimationFrame(() => {
      const canvas = pad.current?.getCanvas();
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) return;
      const ratio = Math.max(window.devicePixelRatio || 1, 1);
      canvas.width = Math.round(rect.width * ratio);
      canvas.height = Math.round(rect.height * ratio);
      canvas.getContext("2d")?.scale(ratio, ratio);
      pad.current?.clear();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Sign the packet</DialogTitle>
        <p className="mt-2 text-sm text-mist">
          Draw the signature. It is stamped onto the signature box of the filled form.
        </p>
        <div className="mt-4 rounded-md border border-line bg-white">
          <SignatureCanvas
            ref={pad}
            penColor="#1c1915"
            canvasProps={{ className: "h-40 w-full touch-none" }}
          />
          <div className="mx-4 mb-3 border-t border-ink/30" />
        </div>
        {consentLabel ? (
          <label className="mt-4 flex items-start gap-2 text-sm leading-6">
            <input
              type="checkbox"
              className="mt-1"
              checked={accepted}
              onChange={(event) => setAccepted(event.target.checked)}
            />
            <span>{consentLabel}</span>
          </label>
        ) : null}
        {padError ? <p className="mt-3 text-sm text-clay">{padError}</p> : null}
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => pad.current?.clear()} disabled={busy}>
            Clear
          </Button>
          <Button
            type="button"
            disabled={busy || submitting || (consentLabel ? !accepted : false)}
            onClick={() => {
              if (sending.current) return;
              const canvas = pad.current;
              if (!canvas || canvas.isEmpty()) {
                setPadError("Draw a signature first.");
                return;
              }
              setPadError(null);
              sending.current = true;
              setSubmitting(true);
              void onSign(canvas.toDataURL("image/png")).finally(() => {
                sending.current = false;
                setSubmitting(false);
              });
            }}
          >
            {busy ? "Stamping…" : "Stamp and finish"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
