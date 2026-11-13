"use client";

import type { FillReport } from "@docketai/shared-types";
import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { FIELD_LABEL } from "@/lib/filing";
import { FILL_STATUS_LABEL, hebrewOfficeError } from "@/lib/hebrew";

export function FillReportList({
  caseId,
  documentId,
  refreshKey,
}: {
  caseId: string;
  documentId: string;
  refreshKey: string;
}) {
  const [report, setReport] = useState<FillReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .fillReport(caseId, documentId)
      .then((next) => {
        if (!cancelled) {
          setReport(next);
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof ApiError ? hebrewOfficeError(reason) : "לא ניתן לטעון את דוח המילוי.");
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, documentId, refreshKey]);

  if (error) return <p className="text-sm font-medium text-clay">{error}</p>;
  if (!report) return <p className="text-sm text-ink">טוען את מצב המילוי…</p>;
  if (report.fields.length === 0) return <p className="text-sm text-ink">אין עדיין שדות קשורים בטופס.</p>;

  return (
    <ul className="mt-3 space-y-2">
      {report.fields.map((field) => {
        const calm = field.status === "ok";
        const waiting = field.status === "awaiting_value";
        return (
          <li key={`${field.field_name}:${field.page}`} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="font-semibold text-ink">
              {FIELD_LABEL[field.slot_key] ?? field.slot_key}
              <span className="ms-2 font-medium text-ink/70">עמ׳ {field.page}</span>
            </span>
            <span
              className={`rounded-full border-2 px-2 py-0.5 text-xs font-bold ${
                calm
                  ? "border-moss bg-[#e7f5ee] text-[#0d4a2e]"
                  : waiting
                    ? "border-amberink bg-[#f6e4c4] text-[#4a3208]"
                    : "border-clay bg-[#f8e6e1] text-[#5e2216]"
              }`}
            >
              {FILL_STATUS_LABEL[field.status]}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
