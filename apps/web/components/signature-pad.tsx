"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import SignatureCanvas from "react-signature-canvas";

import { Button } from "@/components/ui/button";

const TOO_SMALL = "נא לחתום חתימה מלאה.";

type Strokes = ReturnType<SignatureCanvas["toData"]>;

export type SignaturePadHandle = {
  issue: () => string | null;
  png: () => string;
  width: () => number;
};

export const SignaturePad = forwardRef<SignaturePadHandle, { onChange?: () => void }>(function SignaturePad(
  { onChange },
  ref,
) {
  const frameRef = useRef<HTMLDivElement>(null);
  const padRef = useRef<SignatureCanvas>(null);
  const strokes = useRef<Strokes>([]);

  useImperativeHandle(ref, () => ({
    issue: () => (padRef.current ? signatureIssue(padRef.current) : TOO_SMALL),
    png: () => padRef.current?.toDataURL("image/png") ?? "",
    width: () => padRef.current?.getCanvas().clientWidth ?? 0,
  }));

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const observer = new ResizeObserver(() => {
      restore(padRef.current, strokes.current);
    });
    observer.observe(frame);
    restore(padRef.current, strokes.current);
    return () => observer.disconnect();
  }, []);

  function remember() {
    strokes.current = readStrokes(padRef.current);
    onChange?.();
  }

  function undo() {
    const next = readStrokes(padRef.current);
    next.pop();
    strokes.current = next;
    padRef.current?.clear();
    if (next.length) padRef.current?.fromData(next);
    onChange?.();
  }

  function clear() {
    strokes.current = [];
    padRef.current?.clear();
    onChange?.();
  }

  return (
    <div>
      <div ref={frameRef} className="rounded-md border border-line bg-white">
        <SignatureCanvas
          ref={padRef}
          penColor="#1c1915"
          onEnd={remember}
          canvasProps={{ className: "h-40 w-full touch-none" }}
        />
        <div className="mx-4 mb-3 border-t border-ink/30" />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" variant="outline" className="min-h-11 min-w-11" onClick={undo}>
          ביטול קו
        </Button>
        <Button type="button" variant="ghost" className="min-h-11 min-w-11" onClick={clear}>
          ניקוי
        </Button>
      </div>
    </div>
  );
});

function readStrokes(pad: SignatureCanvas | null): Strokes {
  return pad ? pad.toData() : [];
}

function signatureIssue(pad: SignatureCanvas): string | null {
  const data = readStrokes(pad);
  if (data.length < 2) return TOO_SMALL;
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  for (const stroke of data) {
    for (const point of stroke) {
      minX = Math.min(minX, point.x);
      maxX = Math.max(maxX, point.x);
    }
  }
  const width = pad.getCanvas().clientWidth;
  if (!Number.isFinite(minX) || width <= 0 || maxX - minX < width * 0.25) return TOO_SMALL;
  return null;
}

function restore(pad: SignatureCanvas | null, data: Strokes) {
  const canvas = pad?.getCanvas();
  if (!canvas) return;
  const cssWidth = canvas.clientWidth;
  const cssHeight = canvas.clientHeight || 160;
  if (cssWidth < 2 || cssHeight < 2) return;
  const ratio = Math.max(window.devicePixelRatio || 1, 1);
  const nextWidth = Math.round(cssWidth * ratio);
  const nextHeight = Math.round(cssHeight * ratio);
  if (canvas.width === nextWidth && canvas.height === nextHeight) return;
  canvas.width = nextWidth;
  canvas.height = nextHeight;
  canvas.getContext("2d")?.setTransform(ratio, 0, 0, ratio, 0, 0);
  if (data.length) pad?.fromData(data);
}
