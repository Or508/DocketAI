import type { CaseWorkspace, SkipReason } from "@docketai/shared-types";

import { FIELD_LABEL } from "@/lib/filing";

const REASONS: Record<SkipReason, string> = {
  no_text_layer: "אין שכבת טקסט",
  label_not_found: "לא נמצאה תווית",
  ambiguous_match: "נמצא יותר מערך אחד",
  validator_rejected: "הערך לא עבר בדיקה",
  id_mismatch: "מספר הזהות לא תואם לתיק",
  already_filled: "השדה כבר מולא",
};

export function ReadingPanel({ workspace }: { workspace: CaseWorkspace }) {
  const reports = workspace.readings ?? [];
  if (reports.length === 0) return null;
  const labels = new Map(
    workspace.process.required_fields.map((field) => [field.key, FIELD_LABEL[field.key] ?? field.label_he ?? field.label]),
  );

  return (
    <section className="rounded-lg border-2 border-ink/15 bg-white p-5 shadow-card">
      <h2 className="font-serif text-2xl">קריאת המסמכים</h2>
      <p className="mt-1 text-sm leading-6 text-ink">מה נקרא מהקבצים, מה דולג, ומה נשאר למשרד.</p>
      <ul className="mt-4 space-y-4">
        {reports.map((report) => (
          <li key={report.document_id} className="rounded-md border-2 border-ink/10 px-3 py-3 text-sm leading-6">
            <p className="font-semibold">{report.filename}</p>
            <p className="text-ink">{report.enabled ? "הקריאה פעילה." : "הקריאה כבויה — לא נכתב ערך מהקובץ."}</p>
            {report.blocked === "id_mismatch" ? <p className="font-medium text-clay">{REASONS.id_mismatch}</p> : null}
            {report.accepted.map((hit) => (
              <p key={hit.slot_key}>נקרא: {labels.get(hit.slot_key) ?? hit.slot_key}</p>
            ))}
            {report.conflicts.map((conflict) => (
              <p key={conflict.slot_key}>
                {labels.get(conflict.slot_key) ?? conflict.slot_key}: נשאר הערך הקיים. בקובץ מופיע ערך אחר.
              </p>
            ))}
            {report.skips.map((skip) => (
              <p key={`${skip.slot_key}-${skip.reason}`}>
                דולג {labels.get(skip.slot_key) ?? skip.slot_key}: {REASONS[skip.reason]}
              </p>
            ))}
          </li>
        ))}
      </ul>
    </section>
  );
}
