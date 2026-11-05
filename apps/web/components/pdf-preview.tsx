"use client";

import type { CaseWorkspace } from "@docketai/shared-types";
import { useEffect, useMemo, useRef, useState } from "react";

import { documentFileUrl } from "@/lib/api";

export function PdfPreview({ caseId, workspace }: { caseId: string; workspace: CaseWorkspace }) {
  const files = useMemo(() => previewFiles(workspace), [workspace]);
  const [selected, setSelected] = useState("");
  const host = useRef<HTMLDivElement>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (!files.some((file) => file.id === selected)) {
      setSelected(files[0]?.id ?? "");
    }
  }, [files, selected]);

  useEffect(() => {
    const node = host.current;
    if (!node) return;
    node.replaceChildren();
    if (!selected) {
      setNote(null);
      return;
    }
    let cancelled = false;
    setNote(null);
    void (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
        const response = await fetch(documentFileUrl(caseId, selected));
        if (!response.ok) throw new Error("The preview could not be loaded.");
        const data = new Uint8Array(await response.arrayBuffer());
        const pdf = await pdfjs.getDocument({ data }).promise;
        const count = Math.min(pdf.numPages, 3);
        for (let pageNumber = 1; pageNumber <= count; pageNumber += 1) {
          if (cancelled) break;
          const page = await pdf.getPage(pageNumber);
          const viewport = page.getViewport({ scale: 1.15 });
          const canvas = document.createElement("canvas");
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          canvas.className = "mb-3 w-full rounded-md bg-white shadow-card";
          await page.render({ canvas, viewport }).promise;
          if (!cancelled) node.appendChild(canvas);
        }
        await pdf.cleanup();
      } catch {
        if (!cancelled) setNote("This file could not be previewed.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [caseId, selected]);

  return (
    <section className="rounded-lg border border-line bg-white/80 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.18em] text-tide">Source</p>
          <h2 className="font-serif text-2xl">Uploaded file</h2>
        </div>
        {files.length > 0 ? (
          <select
            className="h-10 max-w-full rounded-md border border-line bg-white px-3 text-sm"
            value={selected}
            aria-label="Choose a file to preview"
            onChange={(event) => setSelected(event.target.value)}
          >
            {files.map((file) => (
              <option key={file.id} value={file.id}>
                {file.name}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      <div className="max-h-[40rem] overflow-auto px-4 py-4">
        {files.length === 0 ? (
          <p className="text-sm text-mist">Upload a PDF to preview it beside the clerk.</p>
        ) : null}
        {note ? <p className="mb-3 text-sm text-clay">{note}</p> : null}
        <div ref={host} />
      </div>
    </section>
  );
}

function previewFiles(workspace: CaseWorkspace) {
  const rows = [
    ...workspace.gap.identified.map((item) => ({ id: item.document_id, name: item.filename })),
    ...workspace.gap.unrecognized.map((item) => ({ id: item.document_id, name: item.filename })),
    ...workspace.gap.in_progress.map((item) => ({ id: item.document_id, name: item.filename })),
  ];
  const seen = new Set<string>();
  return rows.filter((row) => {
    if (seen.has(row.id)) return false;
    seen.add(row.id);
    return true;
  });
}
