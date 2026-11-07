"use client";

import { useRef, useState } from "react";

import { SignaturePad, type SignaturePadHandle } from "@/components/signature-pad";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

export function SigningModal({
  open,
  busy,
  consentLabel,
  notice,
  onOpenChange,
  onSign,
}: {
  open: boolean;
  busy: boolean;
  consentLabel?: string;
  notice?: string;
  onOpenChange: (open: boolean) => void;
  onSign: (pngDataUrl: string) => Promise<void>;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle className="pe-12">Sign the packet</DialogTitle>
        <p className="mt-2 text-sm text-mist">
          Draw the signature. It is stamped onto the signature box of the filled form.
        </p>
        <div className="mt-4">
          <SignatureForm busy={busy} consentLabel={consentLabel} notice={notice} onSign={onSign} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function SignatureForm({
  busy,
  consentLabel,
  notice,
  onSign,
}: {
  busy: boolean;
  consentLabel?: string;
  notice?: string;
  onSign: (pngDataUrl: string) => Promise<void>;
}) {
  const pad = useRef<SignaturePadHandle>(null);
  const sending = useRef(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewWidth, setPreviewWidth] = useState(0);
  const [padError, setPadError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function showPreview() {
    const issue = pad.current?.issue();
    if (issue) {
      setPadError(issue);
      setPreview(null);
      return;
    }
    setPadError(null);
    setPreview(pad.current?.png() ?? null);
    setPreviewWidth(pad.current?.width() ?? 0);
  }

  return (
    <div>
      <SignaturePad
        ref={pad}
        onChange={() => {
          setPreview(null);
          setPadError(null);
        }}
      />
      <Button type="button" variant="outline" className="mt-3 min-h-11 w-full" onClick={showPreview} disabled={busy}>
        Preview signature
      </Button>
      {preview ? (
        <figure className="mt-4 min-w-0">
          <img
            src={preview}
            alt="Signature preview"
            className="h-auto max-w-full rounded-md border border-line bg-white"
            style={previewWidth > 0 ? { width: previewWidth } : undefined}
          />
          <figcaption className="mt-2 text-xs leading-5 text-mist">This is the signature that will be stamped.</figcaption>
        </figure>
      ) : null}
      {consentLabel ? (
        <label className="mt-4 flex min-h-11 items-center gap-3 text-sm leading-6">
          <input
            type="checkbox"
            className="size-11 shrink-0"
            checked={accepted}
            onChange={(event) => setAccepted(event.target.checked)}
          />
          <span>{consentLabel}</span>
        </label>
      ) : null}
      {notice ? <p className="mt-2 text-sm leading-6 text-mist">{notice}</p> : null}
      {padError ? <p className="mt-3 text-sm text-clay">{padError}</p> : null}
      <div className="mt-4">
        <Button
          type="button"
          className="min-h-11 w-full"
          disabled={busy || submitting || !preview || (consentLabel ? !accepted : false)}
          onClick={() => {
            if (sending.current || !preview) return;
            sending.current = true;
            setSubmitting(true);
            void onSign(preview).finally(() => {
              sending.current = false;
              setSubmitting(false);
            });
          }}
        >
          {busy || submitting ? "Stamping…" : "Stamp and finish"}
        </Button>
      </div>
    </div>
  );
}
