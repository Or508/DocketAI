"use client";

import type { CaseWorkspace, DocumentTypeSpec } from "@docketai/shared-types";
import type { ReactNode } from "react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export function CaseChecklist({
  workspace,
  busy,
  onUpload,
  onClassify,
}: {
  workspace: CaseWorkspace;
  busy: boolean;
  onUpload: (files: File[]) => Promise<void>;
  onClassify: (documentId: string, documentType: string) => Promise<void>;
}) {
  const gap = workspace.gap;
  const options = dedupe([...workspace.process.required_documents, ...workspace.process.optional_documents]);

  return (
    <section className="rounded-lg border border-line bg-white/80 p-5 shadow-card" dir="rtl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-serif text-2xl">הקבצים בתיק</h2>
          <p className="text-sm text-mist">{gap.total_files} קבצים בתיק</p>
        </div>
        <UploadButtons busy={busy} onUpload={onUpload} />
      </div>

      <Bucket title="בעיבוד" count={gap.in_progress.length} tone="border-tide">
        {gap.in_progress.map((item) => (
          <p key={item.document_id} className="text-sm">
            {item.filename}
          </p>
        ))}
      </Bucket>

      <Bucket title="זוהו" count={gap.identified.length} tone="border-moss">
        {gap.identified.map((item) => (
          <div key={item.document_id} className="flex items-baseline justify-between gap-3 text-sm">
            <span>
              <span className="font-medium">{item.label_he ?? item.label}</span>
              <span className="block text-mist">{item.filename}</span>
            </span>
            <span className="text-xs text-moss">
              {item.source === "human" ? "אושר" : item.confidence != null ? `${Math.round(item.confidence * 100)}%` : "אוטומטי"}
            </span>
          </div>
        ))}
      </Bucket>

      <Bucket title="ממתינים לסימון" count={gap.unrecognized.length} tone="border-amberink">
        {gap.unrecognized.map((item) => (
          <ReviewRow key={item.document_id} item={item} options={options} busy={busy} onClassify={onClassify} />
        ))}
      </Bucket>

      <Bucket title="חסרים" count={gap.missing.length} tone="border-clay">
        {gap.missing.map((item) => (
          <div key={item.type_key} className="text-sm">
            <span className="font-medium">{item.label_he ?? item.label}</span>
            <span className="mt-1 block text-mist">
              {item.found_count} מתוך {item.required_count}
            </span>
          </div>
        ))}
      </Bucket>
    </section>
  );
}

function UploadButtons({ busy, onUpload }: { busy: boolean; onUpload: (files: File[]) => Promise<void> }) {
  return (
    <div className="flex gap-2">
      <label className="inline-flex h-8 cursor-pointer items-center rounded-md border border-line bg-white px-2.5 text-xs font-medium">
        קבצים
        <input
          className="sr-only"
          type="file"
          multiple
          accept="image/*,application/pdf,.pdf,.png,.jpg,.jpeg,.webp,.heic,.bmp,.gif,.tiff"
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = "";
            if (files.length) void onUpload(files);
          }}
        />
      </label>
      <label className="inline-flex h-8 cursor-pointer items-center rounded-md border border-line bg-white px-2.5 text-xs font-medium">
        תיקייה
        <input
          className="sr-only"
          type="file"
          multiple
          disabled={busy}
          // Non-standard directory picker used by Chromium and Safari.
          {...{ webkitdirectory: "", directory: "" }}
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = "";
            if (files.length) void onUpload(files);
          }}
        />
      </label>
    </div>
  );
}

function ReviewRow({
  item,
  options,
  busy,
  onClassify,
}: {
  item: CaseWorkspace["gap"]["unrecognized"][number];
  options: DocumentTypeSpec[];
  busy: boolean;
  onClassify: (documentId: string, documentType: string) => Promise<void>;
}) {
  const [choice, setChoice] = useState(item.suggested_type ?? "");
  return (
    <div className="text-sm">
      <p className="font-medium">{item.filename}</p>
      {item.rationale ? <p className="mt-1 text-mist">{item.rationale}</p> : null}
      <div className="mt-2 flex gap-2">
        <select
          className="h-8 flex-1 rounded-md border border-line bg-white px-2 text-xs"
          value={choice}
          onChange={(event) => setChoice(event.target.value)}
          aria-label={`סוג עבור ${item.filename}`}
        >
          <option value="">בחרו סוג</option>
          {options.map((option) => (
            <option key={option.type_key} value={option.type_key}>
              {option.label_he ?? option.label}
            </option>
          ))}
        </select>
        <Button
          size="sm"
          variant="outline"
          disabled={busy || !choice}
          onClick={() => void onClassify(item.document_id, choice)}
        >
          אישור
        </Button>
      </div>
    </div>
  );
}

function Bucket({
  title,
  count,
  tone,
  children,
}: {
  title: string;
  count: number;
  tone: string;
  children: ReactNode;
}) {
  return (
    <div className={`mt-5 border-s-2 ps-4 ${tone}`}>
      <h3 className="text-xs uppercase tracking-[0.16em] text-mist">
        {title} · {count}
      </h3>
      <div className="mt-2 space-y-3">{count === 0 ? <p className="text-sm text-mist">אין</p> : children}</div>
    </div>
  );
}

function dedupe(items: DocumentTypeSpec[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.type_key)) return false;
    seen.add(item.type_key);
    return true;
  });
}
