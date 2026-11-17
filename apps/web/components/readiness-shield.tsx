"use client";

import type { CaseWorkspace, FieldSpec, IntakeSummary } from "@docketai/shared-types";
import { israeliIdStatus } from "@docketai/shared-types";

import { Button } from "@/components/ui/button";
import { blankFormButton, FIELD_LABEL, processTypeOf } from "@/lib/filing";

export function ReadinessShield({
  workspace,
  intake,
  loadingForm,
  onLoadBlank,
}: {
  workspace: CaseWorkspace;
  intake: IntakeSummary | null;
  loadingForm: boolean;
  onLoadBlank?: () => Promise<void>;
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

  return (
    <section className="rounded-lg border-2 border-ink/15 bg-white p-4 shadow-card" aria-label="בדיקת תקינות ומוכנות לפני שליחה לחתימה">
      <h2 className="font-serif text-2xl">בדיקת מוכנות התיק לחתימה</h2>
      <ul className="mt-4 grid gap-3 text-sm">
        <li className="rounded-md border-2 border-ink/10 px-3 py-3">
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
        <li className="rounded-md border-2 border-ink/10 px-3 py-3">
          <p className="font-semibold">מסמכי מקור במגירות</p>
          <p className="mt-1">
            {filledDrawers.length} מתוך {drawers.length} מגירות מלאות
            {drawers.length - filledDrawers.length > 0 ? ` · ${drawers.length - filledDrawers.length} ריקות` : ""}
          </p>
          <button type="button" className="mt-2 text-sm font-semibold text-tide underline" onClick={scrollToDrawers}>
            גלילה למגירות
          </button>
        </li>
        <li className="rounded-md border-2 border-ink/10 px-3 py-3">
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
                    className="rounded-full border-2 border-amberink bg-[#f6e4c4] px-2 py-1 text-xs font-bold text-[#4a3208]"
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
