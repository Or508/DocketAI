"use client";

import type { CaseWorkspace, IntakeSummary } from "@docketai/shared-types";

import { FIELD_LABEL, FOLDER_LABEL, SLOT_LABEL, processLabel, processTypeOf, type FolderTone } from "@/lib/filing";
import { useOfficeSettings } from "@/lib/use-office-settings";

export function CaseCover({
  workspace,
  intake,
  tone,
}: {
  workspace: CaseWorkspace;
  intake: IntakeSummary | null;
  tone: FolderTone;
}) {
  const settings = useOfficeSettings();
  const processType = processTypeOf(workspace);
  const drawers = workspace.process.required_documents;
  const filled = drawers.filter((drawer) => workspace.gap.identified.some((item) => item.document_type === drawer.type_key));
  const fields = workspace.process.required_fields;
  const filledFields = fields.filter((field) => (workspace.field_values[field.key] ?? "").trim()).length;
  const formLoaded = (intake?.forms ?? []).some((item) => item.role === "form");
  const formScore = formLoaded ? 25 : 0;
  const drawerScore = drawers.length ? Math.round((filled.length / drawers.length) * 25) : 25;
  const fieldScore = fields.length ? Math.round((filledFields / fields.length) * 50) : 50;
  const score = Math.max(0, Math.min(100, formScore + drawerScore + fieldScore));
  const seal = workspace.case.audit.signer_verification_id;

  return (
    <article className="print-sheet">
      <p className="text-sm font-semibold">{settings.officeName}</p>
      <h1 className="mt-2 font-serif text-3xl">{workspace.case.client_name || workspace.case.name}</h1>
      <p className="mt-1">{processLabel(processType, workspace.process.name)}</p>
      <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <div>
          <dt className="font-semibold">מספר תיק</dt>
          <dd dir="ltr">{workspace.case.id}</dd>
        </div>
        <div>
          <dt className="font-semibold">מצב</dt>
          <dd>{FOLDER_LABEL[tone]}</dd>
        </div>
        <div>
          <dt className="font-semibold">ציון מוכנות</dt>
          <dd>{score}%</dd>
        </div>
        {seal ? (
          <div>
            <dt className="font-semibold">קוד חותם</dt>
            <dd dir="ltr">{seal}</dd>
          </div>
        ) : null}
      </dl>
      <h2 className="mt-4 font-semibold">פרטים אישיים</h2>
      <table className="mt-2 w-full border-collapse text-sm">
        <tbody>
          {fields.map((field) => (
            <tr key={field.key}>
              <th className="border border-ink/20 px-2 py-1 text-start font-semibold">{FIELD_LABEL[field.key] ?? field.label_he ?? field.label}</th>
              <td className="border border-ink/20 px-2 py-1" dir="auto">
                {(workspace.field_values[field.key] ?? "").trim() || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2 className="mt-4 font-semibold">מגירות</h2>
      <ul className="mt-2 text-sm">
        <li>{formLoaded ? "✓" : "⚠"} טופס יעד</li>
        {drawers.map((drawer) => {
          const ready = filled.some((item) => item.type_key === drawer.type_key);
          return (
            <li key={drawer.type_key}>
              {ready ? "✓" : "⚠"} {SLOT_LABEL[drawer.type_key] ?? drawer.label_he ?? drawer.label}
            </li>
          );
        })}
      </ul>
    </article>
  );
}

export const CASE_PRINT_CSS = `
.print-sheet { display: none; }
@media print {
  .no-print { display: none !important; }
  .print-sheet { display: block !important; }
  body { background: white !important; }
}
`;
