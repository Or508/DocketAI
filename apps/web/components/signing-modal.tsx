"use client";

import { useEffect, useRef, useState } from "react";
import SignatureCanvas from "react-signature-canvas";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

export function SigningModal({
  open,
  busy,
  onOpenChange,
  onSign,
}: {
  open: boolean;
  busy: boolean;
  onOpenChange: (open: boolean) => void;
  onSign: (pngDataUrl: string) => Promise<void>;
}) {
  const pad = useRef<SignatureCanvas>(null);
  const [padError, setPadError] = useState<string | null>(null);

  useEffect(() => {
    if (open) pad.current?.clear();
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
            canvasProps={{ className: "h-40 w-full", width: 640, height: 160 }}
          />
          <div className="mx-4 mb-3 border-t border-ink/30" />
        </div>
        {padError ? <p className="mt-3 text-sm text-clay">{padError}</p> : null}
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => pad.current?.clear()} disabled={busy}>
            Clear
          </Button>
          <Button
            type="button"
            disabled={busy}
            onClick={() => {
              const canvas = pad.current;
              if (!canvas || canvas.isEmpty()) {
                setPadError("Draw a signature first.");
                return;
              }
              setPadError(null);
              void onSign(canvas.toDataURL("image/png"));
            }}
          >
            {busy ? "Stamping…" : "Stamp and finish"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
