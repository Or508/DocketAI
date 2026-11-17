"use client";

import type { CaseWorkspace, FieldSpec, IntakeSummary } from "@docketai/shared-types";
import { israeliIdStatus } from "@docketai/shared-types";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { blankFormButton, FIELD_LABEL, processTypeOf } from "@/lib/filing";

type IntegrityCheck = {
  code: string;
  label_he: string;
  status: "pass" | "warn" | "fail";
  detail_he: string;
  field_key: string | null;
  drawer_type: string | null;
};

type IntegrityReport = {
  case_id: string;
  status: "pass" | "warn" | "block";
  score: number;
  checks: IntegrityCheck[];
};

export function ReadinessShield({
  caseId,
  workspace,
  intake,
  loadingForm,
  onLoadBlank,
  embedded = false,
}: {
  caseId: string;
  workspace: CaseWorkspace;
  intake: IntakeSummary | null;
  loadingForm: boolean;
  onLoadBlank?: () => Promise<void>;
  embedded?: boolean;
}) {
  const processType = processTypeOf(workspace);
  const formLoaded = (intake?.forms ?? []).some((item) => item.role === "form");
  const drawers = workspace.process.required_documents;
  const filledDrawers = drawers.filter((drawer) =>
    workspace.gap.identified.some((item) => item.document_type === drawer.type_key),
  );
  const fields = workspace.process.required_fields;
  const problems = fields.flatMap((field) => {
    const issue = fieldIssue(field, workspace.field_values[field.key] ?? "");
    return issue ? [{ key: field.key, label: fieldLabel(field), issue }] : [];
  });
  const validFields = fields.length - problems.length;
  const formScore = formLoaded ? 25 : 0;
  const drawerScore = drawers.length ? Math.round((filledDrawers.length / drawers.length) * 25) : 25;
  const fieldScore = fields.length ? Math.round((validFields / fields.length) * 50) : 50;
  const score = Math.max(0, Math.min(100, formScore + drawerScore + fieldScore));
  const ready = formLoaded && filledDrawers.length === drawers.length && problems.length === 0;
  const integrity = useIntegrity(caseId, workspace.case.updated_at);

  return (
    <section className={embedded ? "" : "rounded-lg border border-ink/15 bg-white p-4 shadow-card"} aria-label="בדיקת תקינות ומוכנות לפני שליחה לחתימה">
      <h3 className={embedded ? "text-sm font-bold text-tide" : "font-serif text-2xl"}>בדיקת מוכנות התיק לחתימה</h3>
      <ul className={`grid gap-3 text-sm ${embedded ? "mt-3" : "mt-4"}`}>
        <li className="rounded-md border border-ink/10 px-3 py-3">
          <p className="font-semibold">טופס יעד טעון</p>
          {formLoaded ? (
            <p className="mt-1 font-semibold text-[#0d4a2e]">✓ הטופס נמצא במגירה</p>
          ) : (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <p className="font-semibold text-[#4a3208]">⚠ חסר טופס למילוי</p>
              {onLoadBlank ? (
                <Button type="button" variant="outline" disabled={loadingForm} onClick={() => void onLoadBlank()}>
                  {loadingForm ? "טוען את הטופס…" : blankFormButton(processType)}
                </Button>
              ) : null}
            </div>
          )}
        </li>
        <li className="rounded-md border border-ink/10 px-3 py-3">
          <p className="font-semibold">מסמכי מקור במגירות</p>
          <p className="mt-1">
            {filledDrawers.length} מתוך {drawers.length} מגירות מלאות
            {drawers.length - filledDrawers.length > 0 ? ` · ${drawers.length - filledDrawers.length} ריקות` : ""}
          </p>
          <button type="button" className="mt-2 text-sm font-semibold text-tide underline" onClick={scrollToDrawers}>
            גלילה למגירות
          </button>
        </li>
        <li className="rounded-md border border-ink/10 px-3 py-3">
          <p className="font-semibold">שלמות שדות ואימות ת״ז/נייד</p>
          <p className="mt-1">
            {validFields} מתוך {fields.length} שדות תקינים
          </p>
          {problems.length ? (
            <ul className="mt-2 flex flex-wrap gap-2">
              {problems.map((problem) => (
                <li key={problem.key}>
                  <button
                    type="button"
                    className="rounded-full border border-amberink bg-[#f6e4c4] px-2 py-1 text-xs font-bold text-[#4a3208]"
                    onClick={() => focusField(problem.key)}
                  >
                    {problem.label}: {problem.issue}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 font-semibold text-[#0d4a2e]">✓ ת״ז ונייד תקינים, והשדות מולאו</p>
          )}
        </li>
        {integrity ? <IntegrityChecks report={integrity} /> : null}
      </ul>
      <div className="mt-4">
        <p className="mb-1 flex justify-between text-sm font-semibold">
          <span>ציון מוכנות התיק</span>
          <span>{score}%</span>
        </p>
        <span className="block h-2.5 overflow-hidden rounded-full bg-ink/10">
          <span className={`block h-full rounded-full ${ready ? "bg-moss" : "bg-tide"}`} style={{ width: `${score}%` }} />
        </span>
        <p className={`mt-2 text-sm font-bold ${ready ? "text-[#0d4a2e]" : "text-[#4a3208]"}`}>
          {ready ? "מוכן למשלוח לחתימה ✓" : "נדרשת השלמת פרטים לפני חתימה"}
        </p>
      </div>
    </section>
  );
}

function useIntegrity(caseId: string, revision: string) {
  const [report, setReport] = useState<IntegrityReport | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/cases/${caseId}/integrity`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) return null;
        return (await response.json()) as IntegrityReport;
      })
      .then((next) => {
        if (!cancelled) setReport(next);
      })
      .catch(() => {
        if (!cancelled) setReport(null);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, revision]);
  return report;
}

function IntegrityChecks({ report }: { report: IntegrityReport }) {
  const tone = report.status === "pass" ? "text-[#0d4a2e]" : report.status === "warn" ? "text-[#4a3208]" : "text-clay";
  const mark = report.status === "pass" ? "תקין" : report.status === "warn" ? "נדרשת בדיקה" : "חסום";
  return (
    <li className="rounded-md border border-ink/10 px-3 py-3">
      <p className="font-semibold">בדיקות השרת</p>
      <p className={`mt-1 font-semibold ${tone}`}>
        {mark} · ציון שרת {report.score}%
      </p>
      <ul className="mt-2 grid gap-2">
        {report.checks.map((check) => (
          <li key={check.code}>
            <button
              type="button"
              className={`w-full rounded-md border px-2 py-2 text-start text-xs font-semibold ${checkTone(check.status)}`}
              onClick={() => openCheck(check)}
            >
              <span className="block">
                {check.status === "pass" ? "✓" : check.status === "warn" ? "⚠" : "✕"} {check.label_he}
                {check.code === "cross_doc_consistency" ? " · הצלבת מסמכים" : ""}
              </span>
              {check.detail_he ? <span className="mt-1 block font-medium">{check.detail_he}</span> : null}
            </button>
          </li>
        ))}
      </ul>
    </li>
  );
}

function checkTone(status: IntegrityCheck["status"]) {
  if (status === "pass") return "border-moss bg-[#e7f5ee] text-[#0d4a2e]";
  if (status === "warn") return "border-amberink bg-[#f6e4c4] text-[#4a3208]";
  return "border-clay bg-[#fde8e4] text-clay";
}

function openCheck(check: IntegrityCheck) {
  if (check.field_key) focusField(check.field_key);
  else if (check.drawer_type) scrollToDrawers();
}

function fieldLabel(field: FieldSpec) {
  return FIELD_LABEL[field.key] ?? field.label_he ?? field.label;
}

function fieldIssue(field: FieldSpec, raw: string): string {
  const text = raw.trim();
  if (!text) return "חסר";
  if (field.field_type === "id_number" || field.key === "national_id" || field.key === "id_number") {
    const check = israeliIdStatus(text);
    if (check.status === "valid") return "";
    return check.status === "invalid" ? "ספרת ביקורת שגויה ⚠" : "חסרות ספרות";
  }
  if (field.field_type === "phone" || field.key === "phone") {
    return /^05\d{8}$/.test(text.replace(/\D/g, "")) ? "" : "פורמט נייד שגוי ⚠";
  }
  return "";
}

function scrollToDrawers() {
  document.getElementById("document-drawers")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function focusField(key: string) {
  const node = document.getElementById(`field-${key}`);
  node?.scrollIntoView({ behavior: "smooth", block: "center" });
  if (node instanceof HTMLElement) node.focus();
}
