import type { FieldSpec } from "@docketai/shared-types";

import { FIELD_LABEL } from "@/lib/filing";

const DONE = "כל הפרטים מולאו + חתימה דיגיטלית הוטבעה";

export function SignedChecklist({ fields }: { fields?: FieldSpec[] }) {
  const items = (fields ?? []).map((field) => ({
    key: field.key,
    label: FIELD_LABEL[field.key] ?? field.label_he ?? field.label,
  }));
  return (
    <div className="rounded-md border border-moss bg-[#e7f3ea] px-4 py-3 text-sm text-[#145c38]">
      <p className="font-semibold">
        {items.length > 0 ? `${items.length} מתוך ${items.length} שדות מולאו בטופס + חתימה דיגיטלית הוטבעה` : DONE}
      </p>
      {items.length > 0 ? (
        <ul className="mt-2 grid gap-1 sm:grid-cols-2">
          {items.map((item) => (
            <li key={item.key} className="font-medium">
              ✓ {item.label}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function SignedPdfFrame({ src }: { src: string }) {
  const view = src.includes("?") ? `${src}&view=1` : `${src}?view=1`;
  return (
    <iframe
      title="הטופס החתום"
      src={view}
      className="h-[72vh] w-full rounded-md border border-ink/15 bg-white"
    />
  );
}
