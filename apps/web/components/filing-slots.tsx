"use client";

import { useEffect, useState } from "react";
import type { CaseWorkspace, IntakeSummary } from "@docketai/shared-types";

import { Button } from "@/components/ui/button";
import { DRAWER_ACCEPT, filesFromTransfer } from "@/lib/clipboard-files";
import { SLOT_LABEL } from "@/lib/filing";

const FORM_LABEL = "טופס למילוי וחתימה - בל/6101";
const RECEIVED_READ = "התקבל · נקראו שדות אוטומטית";
const RECEIVED_NOTE = "הקובץ נקלט במגירה (לא זוהו שדות אוטומטיים בקובץ זה – ניתן להשלים ידנית במרכז המסך)";

type DrawerFile = { id: string; name: string };
type DrawerChoice = { id: string; label: string };

export function FilingSlots({
  workspace,
  intake,
  pendingSlots,
  slotErrors,
  onUpload,
  onRemove,
  onMove,
  onReread,
  rereading,
}: {
  workspace: CaseWorkspace;
  intake: IntakeSummary | null;
  pendingSlots: string[];
  slotErrors: Record<string, string>;
  onUpload: (slot: string, file: File, replace?: boolean) => Promise<void>;
  onRemove: (slot: string, documentId: string) => Promise<void>;
  onMove: (documentId: string, fromSlot: string, toSlot: string) => Promise<void>;
  onReread: () => Promise<void>;
  rereading: boolean;
}) {
  const [armed, setArmed] = useState<string | null>(null);
  const forms = intake?.forms.filter((item) => item.role === "form") ?? [];
  const formTitle = workspace.process.key === "bl_6101" ? FORM_LABEL : "טופס למילוי וחתימה";
  const sources = [...workspace.process.required_documents, ...workspace.process.optional_documents];
  const choices: DrawerChoice[] = [
    { id: "form", label: formTitle },
    ...sources.map((document) => ({
      id: document.type_key,
      label: SLOT_LABEL[document.type_key] ?? document.label_he ?? document.label,
    })),
  ];
  const formFiles: DrawerFile[] = forms.map((item) => ({ id: item.document_id, name: item.display_title || item.filename }));
  const shown = new Set(formFiles.map((item) => item.id));
  const sourceFiles = new Map<string, DrawerFile[]>();
  for (const document of sources) {
    const files = workspace.gap.identified
      .filter((item) => item.document_type === document.type_key)
      .map((item) => ({ id: item.document_id, name: item.filename }));
    sourceFiles.set(document.type_key, files);
    for (const file of files) shown.add(file.id);
  }
  const listed = new Set((intake?.forms ?? []).map((item) => item.document_id));
  const waiting = [
    ...(intake?.forms.filter((item) => item.role === "evidence" && !shown.has(item.document_id)) ?? []).map((item) => ({
      id: item.document_id,
      name: item.display_title || item.filename,
    })),
    ...workspace.gap.unrecognized
      .filter((item) => !listed.has(item.document_id) && !shown.has(item.document_id))
      .map((item) => ({ id: item.document_id, name: item.filename })),
  ];

  useEffect(() => {
    function onPaste(event: ClipboardEvent) {
      if (!armed) return;
      const target = event.target;
      if (target instanceof HTMLElement) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable) return;
      }
      const files = filesFromTransfer(event.clipboardData);
      if (!files.length) return;
      event.preventDefault();
      const occupied = armed === "form" ? formFiles.length > 0 : (sourceFiles.get(armed)?.length ?? 0) > 0;
      files.forEach((file, index) => void onUpload(armed, file, occupied && index === 0));
    }
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [armed, formFiles.length, onUpload, sourceFiles]);

  return (
    <section className="rounded-lg border-2 border-ink/15 bg-white p-5 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-serif text-2xl">מגירות מסמכים</h2>
          <p className="mt-1 text-sm text-ink">אפשר להעלות, לגרור, או להדביק צילום מסך (Ctrl+V) על המגירה. ירוק — הקובץ במקום.</p>
        </div>
        <Button type="button" variant="outline" disabled={rereading} onClick={() => void onReread()}>
          {rereading ? "קוראים מחדש…" : "קרא מחדש מהמסמכים"}
        </Button>
      </div>
      <div className="mt-4 grid gap-3">
        <Slot
          slot="form"
          title={formTitle}
          files={formFiles}
          fieldsRead={formFiles.some((file) => fieldsWereRead(workspace, file.id))}
          pending={pendingSlots.includes("form")}
          error={slotErrors.form ?? ""}
          armed={armed === "form"}
          choices={choices}
          onArm={() => setArmed("form")}
          onUpload={onUpload}
          onRemove={onRemove}
          onMove={onMove}
        />
        {sources.map((document) => {
          const files = sourceFiles.get(document.type_key) ?? [];
          return (
            <Slot
              key={document.type_key}
              slot={document.type_key}
              title={SLOT_LABEL[document.type_key] ?? document.label_he ?? document.label}
              files={files}
              fieldsRead={files.some((file) => fieldsWereRead(workspace, file.id))}
              pending={pendingSlots.includes(document.type_key)}
              error={slotErrors[document.type_key] ?? ""}
              armed={armed === document.type_key}
              choices={choices}
              onArm={() => setArmed(document.type_key)}
              onUpload={onUpload}
              onRemove={onRemove}
              onMove={onMove}
            />
          );
        })}
        {waiting.length ? (
          <div className="rounded-lg border-2 border-amberink bg-[#fbf3e4] p-4">
            <p className="font-semibold text-ink">ממתינים לשיבוץ</p>
            {slotErrors.waiting ? (
              <p className="mt-2 text-sm font-semibold leading-6 text-clay" role="alert">
                {slotErrors.waiting}
              </p>
            ) : null}
            <ul className="mt-3 grid gap-2">
              {waiting.map((file) => (
                <FileRow
                  key={file.id}
                  file={file}
                  fromSlot="waiting"
                  choices={choices}
                  onRemove={onRemove}
                  onMove={onMove}
                />
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function fieldsWereRead(workspace: CaseWorkspace, documentId: string) {
  const report = workspace.readings.find((item) => item.document_id === documentId);
  if (report && report.accepted.length > 0) return true;
  return Object.values(workspace.field_sources).some(
    (source) => source.source === "document" && source.document_id === documentId,
  );
}

function Slot({
  slot,
  title,
  files,
  fieldsRead,
  pending,
  error,
  armed,
  choices,
  onArm,
  onUpload,
  onRemove,
  onMove,
}: {
  slot: string;
  title: string;
  files: DrawerFile[];
  fieldsRead: boolean;
  pending: boolean;
  error: string;
  armed: boolean;
  choices: DrawerChoice[];
  onArm: () => void;
  onUpload: (slot: string, file: File, replace?: boolean) => Promise<void>;
  onRemove: (slot: string, documentId: string) => Promise<void>;
  onMove: (documentId: string, fromSlot: string, toSlot: string) => Promise<void>;
}) {
  const [over, setOver] = useState(false);
  const ready = files.length > 0;
  const status = ready ? (fieldsRead ? RECEIVED_READ : "התקבל") : "חסר";

  function take(incoming: File[], replace: boolean) {
    incoming.forEach((file, index) => void onUpload(slot, file, replace && index === 0));
  }

  return (
    <div
      tabIndex={0}
      onMouseEnter={onArm}
      onFocus={onArm}
      onPaste={(event) => {
        const incoming = filesFromTransfer(event.clipboardData);
        if (!incoming.length) return;
        event.preventDefault();
        take(incoming, ready);
      }}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
        onArm();
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        take(filesFromTransfer(event.dataTransfer), ready);
      }}
      className={`rounded-lg border-2 p-4 outline-none transition duration-200 focus-visible:ring-2 focus-visible:ring-tide ${
        ready ? "border-moss bg-[#e7f5ee]" : "border-amberink bg-[#fbf3e4]"
      } ${over || armed ? "ring-2 ring-tide" : ""}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-semibold text-ink">{title}</p>
          <p className={`text-sm font-bold ${ready ? "text-[#0d4a2e]" : "text-[#5c3b08]"}`}>{status}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FileButton label={ready ? "החלף קובץ במגירה" : "העלאה למגירה"} onFile={(file) => onUpload(slot, file, ready)} />
          {ready ? <FileButton label="+ הוסף קובץ נוסף" quiet onFile={(file) => onUpload(slot, file, false)} /> : null}
        </div>
      </div>
      {files.length ? (
        <ul className="mt-3 grid gap-2">
          {files.map((file) => (
            <FileRow key={file.id} file={file} fromSlot={slot} choices={choices} onRemove={onRemove} onMove={onMove} />
          ))}
        </ul>
      ) : null}
      {pending ? <p className="mt-2 text-sm font-medium text-ink">הקובץ נקלט ומסיים קליטה למגירה.</p> : null}
      {ready && !fieldsRead ? <p className="mt-2 text-sm font-medium leading-6 text-[#0d4a2e]">{RECEIVED_NOTE}</p> : null}
      {error ? (
        <p className="mt-2 text-sm font-semibold leading-6 text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function FileRow({
  file,
  fromSlot,
  choices,
  onRemove,
  onMove,
}: {
  file: DrawerFile;
  fromSlot: string;
  choices: DrawerChoice[];
  onRemove: (slot: string, documentId: string) => Promise<void>;
  onMove: (documentId: string, fromSlot: string, toSlot: string) => Promise<void>;
}) {
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-md border-2 border-ink/15 bg-white px-3 py-2">
      <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink" title={file.name}>
        {file.name}
      </span>
      <button
        type="button"
        className="inline-flex h-9 items-center rounded-md border-2 border-clay px-2 text-xs font-bold text-clay transition duration-200 hover:-translate-y-0.5"
        onClick={() => void onRemove(fromSlot, file.id)}
      >
        הסר ✕
      </button>
      <label className="text-xs font-semibold text-ink">
        <span className="sr-only">העבר למגירה</span>
        <select
          className="h-9 max-w-44 rounded-md border-2 border-ink/25 bg-white px-2 text-xs font-semibold text-ink"
          value=""
          aria-label={`העבר את ${file.name} למגירה`}
          onChange={(event) => {
            const target = event.target.value;
            event.target.value = "";
            if (target) void onMove(file.id, fromSlot, target);
          }}
        >
          <option value="">העבר למגירה...</option>
          {choices
            .filter((choice) => choice.id !== fromSlot)
            .map((choice) => (
              <option key={choice.id} value={choice.id}>
                {choice.label}
              </option>
            ))}
        </select>
      </label>
    </li>
  );
}

function FileButton({ label, quiet, onFile }: { label: string; quiet?: boolean; onFile: (file: File) => Promise<void> }) {
  return (
    <label
      className={
        quiet
          ? "inline-flex h-11 cursor-pointer items-center text-sm font-semibold text-tide underline"
          : "inline-flex h-11 cursor-pointer items-center rounded-md bg-ink px-3 text-sm font-semibold text-white transition duration-200 hover:-translate-y-0.5"
      }
    >
      {label}
      <input
        className="sr-only"
        type="file"
        accept={DRAWER_ACCEPT}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) void onFile(file);
        }}
      />
    </label>
  );
}
