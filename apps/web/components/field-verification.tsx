"use client";

import type { FieldSpec, ProcessRead } from "@docketai/shared-types";
import { formatEmail, formatPhone, israeliIdStatus } from "@docketai/shared-types";
import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";

export function FieldVerification({
  process,
  field_values,
  busy,
  onSave,
}: {
  process: Pick<ProcessRead, "required_fields">;
  field_values: Record<string, string>;
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
      next[field.key] = field.field_type === "phone" ? formatPhone(stored) : stored;
    }
    setDrafts(next);
  }, [field_values, process.required_fields]);

  useEffect(() => {
    const timers: number[] = [];
    for (const field of process.required_fields) {
      const raw = drafts[field.key] ?? "";
      if (!raw.trim()) continue;
      if (comparable(field, raw) === comparable(field, field_values[field.key] ?? "")) continue;
      if (localProblem(field, raw)) continue;
      timers.push(
        window.setTimeout(() => {
          void saveRef.current(field.key, raw);
        }, 400),
      );
    }
    return () => {
      for (const timer of timers) window.clearTimeout(timer);
    };
  }, [drafts, field_values, process.required_fields]);

  function change(field: FieldSpec, value: string) {
    let next = value;
    if (field.field_type === "phone") next = formatPhone(value);
    if (field.field_type === "email") next = formatEmail(value);
    if (field.field_type === "id_number") next = value.replace(/[^\d]/g, "").slice(0, 9);
    setDrafts((current) => ({ ...current, [field.key]: next }));
  }

  async function commit(field: FieldSpec) {
    const raw = drafts[field.key] ?? "";
    if (comparable(field, raw) === comparable(field, field_values[field.key] ?? "")) return;
    const problem = localProblem(field, raw);
    if (problem) {
      setErrors((current) => ({ ...current, [field.key]: problem }));
      return;
    }
    setErrors((current) => ({ ...current, [field.key]: "" }));
    await onSave(field.key, raw);
  }

  return (
    <section className="rounded-lg border border-line bg-[#fbf8f2] shadow-card">
      <div className="border-b border-line px-4 py-4">
        <p className="text-[11px] uppercase tracking-[0.18em] text-tide">Verification</p>
        <h2 className="font-serif text-2xl">Fields on the form</h2>
      </div>
      <div className="space-y-3 px-4 py-4">
        {process.required_fields.map((field) => {
          const value = drafts[field.key] ?? "";
          const idCheck = field.field_type === "id_number" ? israeliIdStatus(value) : null;
          const hint = errors[field.key] || (idCheck && idCheck.status !== "empty" ? idCheck.message : "");
          const tone =
            errors[field.key] || idCheck?.status === "invalid"
              ? "text-clay"
              : idCheck?.status === "valid"
                ? "text-moss"
                : "text-mist";
          return (
            <label key={field.key} className="block text-sm">
              <span className="mb-1 block text-mist">
                {field.label}
                {field.label_he ? ` · ${field.label_he}` : ""}
              </span>
              <Input
                id={`field-${field.key}`}
                value={value}
                disabled={busy}
                dir={field.rtl ? "rtl" : "ltr"}
                className="scroll-mt-28"
                inputMode={field.field_type === "phone" || field.field_type === "id_number" ? "numeric" : undefined}
                aria-invalid={Boolean(errors[field.key]) || idCheck?.status === "invalid"}
                onChange={(event) => change(field, event.target.value)}
                onBlur={() => {
                  void commit(field);
                }}
              />
              {hint ? <span className={`mt-1 block text-xs ${tone}`}>{hint}</span> : null}
            </label>
          );
        })}
      </div>
    </section>
  );
}

function comparable(field: FieldSpec, raw: string): string {
  if (field.field_type === "phone" || field.field_type === "id_number") return raw.replace(/\D/g, "");
  if (field.field_type === "email") return formatEmail(raw);
  return raw.trim();
}

function localProblem(field: FieldSpec, raw: string): string {
  const text = raw.trim();
  if (!text) return `Enter a value for ${field.label}.`;
  if (field.field_type === "id_number") {
    const check = israeliIdStatus(text);
    return check.status === "valid" ? "" : check.message || "The national ID is not valid.";
  }
  if (field.field_type === "email" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(text)) {
    return `${field.label} needs an address like name@example.com.`;
  }
  if (field.field_type === "phone") {
    const digits = text.replace(/\D/g, "");
    if (digits.length < 9 || digits.length > 15) return `${field.label} needs 9 to 15 digits.`;
  }
  if (field.field_type === "text" && text.length < 2) return `${field.label} is too short.`;
  return "";
}
