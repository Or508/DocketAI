"use client";

import { X } from "lucide-react";
import { useRef, useState } from "react";

import { SignaturePad, type SignaturePadHandle } from "@/components/signature-pad";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTitle } from "@/components/ui/dialog";

export function SigningModal({
  open,
  busy,
  consentLabel,
  notice,
  alert,
  onOpenChange,
  onSign,
}: {
  open: boolean;
  busy: boolean;
  consentLabel?: string;
  notice?: string;
  alert?: string | null;
  onOpenChange: (open: boolean) => void;
  onSign: (pngDataUrl: string) => Promise<void>;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent hideClose>
        <div className="flex items-start justify-between gap-4">
          <DialogTitle>חתימה דיגיטלית</DialogTitle>
          <DialogClose className="flex h-11 w-11 shrink-0 items-center justify-center text-mist hover:text-ink" aria-label="סגירה">
            <X className="h-4 w-4" />
          </DialogClose>
        </div>
        <p className="mt-2 text-sm text-ink">חתמו באצבע או בעכבר. החתימה מוטבעת בתיבת החתימה של הטופס הממולא.</p>
        <div className="mt-4">
          <SignatureForm busy={busy} consentLabel={consentLabel} notice={notice} alert={alert} onSign={onSign} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function SignatureForm({
  busy,
  consentLabel,
  notice,
  alert,
  onSign,
}: {
  busy: boolean;
  consentLabel?: string;
  notice?: string;
  alert?: string | null;
  onSign: (pngDataUrl: string) => Promise<void>;
}) {
  const pad = useRef<SignaturePadHandle>(null);
  const sending = useRef(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewWidth, setPreviewWidth] = useState(0);
  const [padError, setPadError] = useState<string | null>(null);
  const [hasInk, setHasInk] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function syncInk() {
    const issue = pad.current ? pad.current.issue() : "נא לחתום חתימה מלאה.";
    setHasInk(issue === null);
    if (issue === null) setPadError(null);
  }

  function showPreview() {
    const issue = pad.current?.issue();
    if (issue) {
      setPadError(issue);
      setHasInk(false);
      setPreview(null);
      return;
    }
    setPadError(null);
    setHasInk(true);
    setPreview(pad.current?.png() ?? null);
    setPreviewWidth(pad.current?.width() ?? 0);
  }

  return (
    <div>
      <SignaturePad
        ref={pad}
        onChange={() => {
          setPreview(null);
          syncInk();
        }}
      />
      <Button type="button" variant="outline" className="mt-3 min-h-11 w-full" onClick={showPreview} disabled={busy}>
        תצוגה מקדימה של החתימה
      </Button>
      {preview ? (
        <figure className="mt-4 min-w-0">
          <img
            src={preview}
            alt="תצוגה מקדימה של החתימה"
            className="h-auto max-w-full rounded-md border border-line bg-white"
            style={previewWidth > 0 ? { width: previewWidth } : undefined}
          />
          <figcaption className="mt-2 text-xs leading-5 text-ink">זו החתימה שתוטבע על הטופס.</figcaption>
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
      {alert ? (
        <p className="mt-3 text-sm font-semibold text-clay" role="alert">
          {alert}
        </p>
      ) : null}
      {padError ? <p className="mt-3 text-sm text-clay">{padError}</p> : null}
      <div className="mt-4">
        <Button
          type="button"
          className="min-h-11 w-full"
          disabled={busy || submitting || !hasInk || (consentLabel ? !accepted : false)}
          onClick={() => {
            const issue = pad.current?.issue();
            if (issue) {
              setPadError(issue);
              setHasInk(false);
              return;
            }
            const png = pad.current?.png() ?? "";
            if (sending.current || !png) return;
            sending.current = true;
            setSubmitting(true);
            setPadError(null);
            void onSign(png).finally(() => {
              sending.current = false;
              setSubmitting(false);
            });
          }}
        >
          {busy || submitting ? "חותמים…" : "אישור וחתימה"}
        </Button>
      </div>
    </div>
  );
}
