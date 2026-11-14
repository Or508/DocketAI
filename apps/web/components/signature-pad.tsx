"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import SignatureCanvas from "react-signature-canvas";

import { Button } from "@/components/ui/button";

const TOO_SMALL = "נא לחתום חתימה מלאה.";
const INK = "#16130f";
const MIN_LINE = 2.5;

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
    issue: () => signatureIssue(strokes.current),
    png: () => exportSignature(strokes.current),
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
          penColor={INK}
          minWidth={MIN_LINE}
          maxWidth={4}
          dotSize={MIN_LINE}
          clearOnResize={false}
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

function signatureIssue(data: Strokes): string | null {
  let points = 0;
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const stroke of data) {
    for (const point of stroke) {
      points += 1;
      minX = Math.min(minX, point.x);
      maxX = Math.max(maxX, point.x);
      minY = Math.min(minY, point.y);
      maxY = Math.max(maxY, point.y);
    }
  }
  if (points === 0) return TOO_SMALL;
  const wide = Number.isFinite(minX) && (maxX - minX >= 1 || maxY - minY >= 1);
  if (points >= 5 || wide) return null;
  return TOO_SMALL;
}

function exportSignature(data: Strokes): string {
  const width = 800;
  const height = 240;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  const points = data.flat();
  if (points.length === 0) return canvas.toDataURL("image/png");
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const point of points) {
    minX = Math.min(minX, point.x);
    maxX = Math.max(maxX, point.x);
    minY = Math.min(minY, point.y);
    maxY = Math.max(maxY, point.y);
  }
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  ctx.fillStyle = INK;
  ctx.strokeStyle = INK;
  if (spanX < 2 && spanY < 2) {
    ctx.beginPath();
    ctx.arc(width / 2, height / 2, 8, 0, Math.PI * 2);
    ctx.fill();
    return canvas.toDataURL("image/png");
  }
  const margin = 28;
  const scale = Math.min((width - margin * 2) / spanX, (height - margin * 2) / spanY);
  const offsetX = (width - spanX * scale) / 2;
  const offsetY = (height - spanY * scale) / 2;
  const xOf = (value: number) => offsetX + (value - minX) * scale;
  const yOf = (value: number) => offsetY + (value - minY) * scale;
  ctx.lineWidth = MIN_LINE;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const stroke of data) {
    if (stroke.length === 0) continue;
    if (stroke.length === 1) {
      ctx.beginPath();
      ctx.arc(xOf(stroke[0].x), yOf(stroke[0].y), MIN_LINE, 0, Math.PI * 2);
      ctx.fill();
      continue;
    }
    ctx.beginPath();
    ctx.moveTo(xOf(stroke[0].x), yOf(stroke[0].y));
    for (const point of stroke.slice(1)) ctx.lineTo(xOf(point.x), yOf(point.y));
    ctx.stroke();
  }
  return canvas.toDataURL("image/png");
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
