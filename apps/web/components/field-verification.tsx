"use client";

import type { FieldSource, FieldSpec, ProcessRead } from "@docketai/shared-types";
import { formatEmail, formatPhone, israeliIdStatus } from "@docketai/shared-types";
import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { FIELD_LABEL, sourceBadge } from "@/lib/filing";
import { ApiError } from "@/lib/api";
import { PHONE_BOXES_NOTE } from "@/lib/hebrew";

const GROUPS = [
  { title: "שם וזהות", keys: ["last_name", "first_name", "full_name", "national_id"] },
  { title: "יישוב / עיר, רחוב ומס' בית", keys: ["city", "street", "house_number", "address_he"] },
  { title: "טלפון נייד", keys: ["phone", "email"] },
  { title: "בנק / סניף / חשבון", keys: ["bank_name", "bank_branch", "bank_account"] },
];

export function FieldVerification({
  processKey,
  process,
  field_values,
  field_sources,
  busy,
  onSave,
}: {
  processKey: string;
  process: Pick<ProcessRead, "required_fields">;
  field_values: Record<string, string>;
  field_sources: Record<string, FieldSource>;
  busy: boolean;
  onSave: (key: string, value: string) => Promise<void>;
}) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const saveRef = useRef(onSave);
  saveRef.current = onSave;

  useEffect(() => {
    const next: Record<string, string> = {};
    for (const field of process.required_fields) {
      const stored = field_values[field.key] ?? "";
      next[field.key] = field.field_type === "phone" ? phoneDraft(processKey, stored) : stored;
    }
    setDrafts(next);
  }, [field_values, process.required_fields, processKey]);

  useEffect(() => {
    const timers: number[] = [];
    for (const field of process.required_fields) {
      const raw = drafts[field.key] ?? "";
      if (!raw.trim()) continue;
      if (comparable(field, raw) === comparable(field, field_values[field.key] ?? "")) continue;
      if (localProblem(processKey, field, raw)) continue;
      timers.push(
        window.setTimeout(() => {
          void saveRef.current(field.key, raw);
        }, 400),
      );
    }
    return () => {
      for (const timer of timers) window.clearTimeout(timer);
    };
  }, [drafts, field_values, process.required_fields, processKey]);

  function change(field: FieldSpec, value: string) {
    let next = value;
    if (field.field_type === "phone") next = phoneDraft(processKey, value);
    if (field.field_type === "email") next = formatEmail(value);
    if (field.field_type === "id_number") next = value.replace(/[^\d]/g, "").slice(0, 9);
    setDrafts((current) => ({ ...current, [field.key]: next }));
  }

  async function commit(field: FieldSpec) {
    const raw = drafts[field.key] ?? "";
    if (comparable(field, raw) === comparable(field, field_values[field.key] ?? "")) return;
    const problem = localProblem(processKey, field, raw);
    if (problem) {
      setErrors((current) => ({ ...current, [field.key]: problem }));
      return;
    }
    if (!raw.trim()) return;
    const payload = field.field_type === "phone" ? raw.replace(/\D/g, "") : raw.trim();
    setErrors((current) => ({ ...current, [field.key]: "" }));
    try {
      await onSave(field.key, payload);
    } catch (reason) {
      const message = reason instanceof ApiError ? reason.message : "הפרט לא נשמר. בדקו את הערך ונסו שוב.";
      setErrors((current) => ({ ...current, [field.key]: message }));
    }
  }

  const grouped = new Set(GROUPS.flatMap((group) => group.keys));
  const rest = process.required_fields.filter((field) => !grouped.has(field.key));

  return (
    <section className="rounded-lg border-2 border-ink/15 bg-white shadow-card">
      <div className="border-b-2 border-ink/10 px-4 py-4">
        <h2 className="font-serif text-2xl">בקרת ותיקון פרטים אישיים לפני חתימה</h2>
        <p className="mt-2 text-sm leading-6 text-ink">
          כאן מתקנים רק פרט אישי שנקרא לא נכון או חסר: שם, זהות, יישוב, רחוב, מספר בית, טלפון וחשבון. נוסח חוקי או סעיף סטטוטורי לא נערכים במסך הזה.
        </p>
      </div>
      <div className="space-y-5 px-4 py-4">
        {GROUPS.map((group) => {
          const fields = process.required_fields.filter((field) => group.keys.includes(field.key));
          if (!fields.length) return null;
          return (
            <fieldset key={group.title} className="space-y-3">
              <legend className="text-sm font-bold text-tide">{group.title}</legend>
              {fields.map((field) => (
                <FieldRow
                  key={field.key}
                  field={field}
                  value={drafts[field.key] ?? ""}
                  badge={sourceBadge(field_sources[field.key], Boolean((field_values[field.key] ?? "").trim()))}
                  error={errors[field.key] ?? ""}
                  note={field.key === "phone" && processKey === "bl_6101" ? PHONE_BOXES_NOTE : ""}
                  busy={busy}
                  onChange={(value) => change(field, value)}
                  onBlur={() => void commit(field)}
                />
              ))}
            </fieldset>
          );
        })}
        {rest.length ? (
          <fieldset className="space-y-3">
            <legend className="text-sm font-bold text-tide">פרטים נוספים</legend>
            {rest.map((field) => (
              <FieldRow
                key={field.key}
                field={field}
                value={drafts[field.key] ?? ""}
                badge={sourceBadge(field_sources[field.key], Boolean((field_values[field.key] ?? "").trim()))}
                error={errors[field.key] ?? ""}
                note={field.key === "phone" && processKey === "bl_6101" ? PHONE_BOXES_NOTE : ""}
                busy={busy}
                onChange={(value) => change(field, value)}
                onBlur={() => void commit(field)}
              />
            ))}
          </fieldset>
        ) : null}
      </div>
    </section>
  );
}

function FieldRow({
  field,
  value,
  badge,
  error,
  note,
  busy,
  onChange,
  onBlur,
}: {
  field: FieldSpec;
  value: string;
  badge: string;
  error: string;
  note: string;
  busy: boolean;
  onChange: (value: string) => void;
  onBlur: () => void;
}) {
  const idCheck = field.field_type === "id_number" ? israeliIdStatus(value) : null;
  const hint = error || idMessage(idCheck?.status);
  const waiting = badge === "ממתין להשלמת משרד";
  return (
    <label className="block text-sm" htmlFor={`field-${field.key}`}>
      <span className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold text-ink">{FIELD_LABEL[field.key] ?? field.label_he ?? field.label}</span>
        <span className={`rounded-full border-2 px-2 py-0.5 text-xs font-bold ${waiting ? "border-amberink bg-[#f6e4c4] text-[#4a3208]" : "border-moss bg-[#e7f5ee] text-[#0d4a2e]"}`}>
          {badge}
        </span>
      </span>
      <Input
        id={`field-${field.key}`}
        value={value}
        disabled={busy}
        dir={field.rtl ? "rtl" : "ltr"}
        inputMode={field.field_type === "phone" || field.field_type === "id_number" ? "numeric" : undefined}
        aria-invalid={Boolean(error) || idCheck?.status === "invalid"}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
      />
      {note ? <span className="mt-1 block text-xs font-medium leading-5 text-ink">{note}</span> : null}
      {hint ? <span className={`mt-1 block text-xs font-medium ${error || idCheck?.status === "invalid" ? "text-clay" : "text-moss"}`}>{hint}</span> : null}
    </label>
  );
}

function idMessage(status: string | undefined) {
  if (status === "valid") return "ספרת הביקורת תקינה.";
  if (status === "incomplete") return "חסרות ספרות במספר הזהות.";
  if (status === "invalid") return "מספר הזהות אינו תקין.";
  return "";
}

function phoneDraft(processKey: string, raw: string): string {
  if (processKey === "bl_6101") return raw.replace(/\D/g, "").slice(0, 10);
  return formatPhone(raw);
}

function comparable(field: FieldSpec, raw: string): string {
  if (field.field_type === "phone" || field.field_type === "id_number") return raw.replace(/\D/g, "");
  if (field.field_type === "email") return formatEmail(raw);
  return raw.trim();
}

function localProblem(processKey: string, field: FieldSpec, raw: string): string {
  const text = raw.trim();
  const label = FIELD_LABEL[field.key] ?? field.label_he ?? field.label;
  if (!text) return "";
  if (field.field_type === "id_number") {
    const check = israeliIdStatus(text);
    return check.status === "valid" ? "" : idMessage(check.status) || "מספר הזהות לא תקין.";
  }
  if (field.field_type === "email" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(text)) {
    return `${label} צריך כתובת כמו name@example.com.`;
  }
  if (field.field_type === "phone") {
    const digits = text.replace(/\D/g, "");
    if (processKey === "bl_6101") {
      return digits.length === 10 ? "" : "טלפון נייד חייב להיות בדיוק 10 ספרות כדי להיכנס לתיבות.";
    }
    if (digits.length < 9 || digits.length > 15) return `${label} צריך 9 עד 15 ספרות.`;
  }
  if (field.field_type === "text" && text.length < (field.required ? 2 : 1)) return `${label} קצר מדי.`;
  return "";
}
