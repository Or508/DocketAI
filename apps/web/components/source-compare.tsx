"use client";

import { documentFileUrl } from "@/lib/api";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

export function SourceCompare({
  caseId,
  file,
  fields,
  onClose,
}: {
  caseId: string;
  file: { id: string; name: string };
  fields: { key: string; label: string; value: string }[];
  onClose: () => void;
}) {
  const src = `${documentFileUrl(caseId, file.id)}?view=1`;
  const image = /\.(png|jpe?g|gif|webp|bmp|tiff?)$/i.test(file.name);
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="w-[min(96vw,76rem)] p-0" aria-describedby={undefined}>
        <div className="border-b-2 border-ink/10 px-5 py-4 pe-16">
          <DialogTitle>צפייה בקובץ המקור</DialogTitle>
          <p className="mt-1 truncate text-sm font-semibold text-ink" title={file.name}>
            {file.name}
          </p>
        </div>
        <div className="grid min-h-0 gap-0 lg:grid-cols-[minmax(0,1.3fr)_minmax(16rem,0.7fr)]">
          <div className="min-h-[50vh] bg-[#f4f0e6] p-3">
            {image ? (
              // The office cookie authorizes this same-origin file. An img tag sends it.
              // eslint-disable-next-line @next/next/no-img-element
              <img src={src} alt={file.name} className="mx-auto max-h-[72vh] w-full object-contain" />
            ) : (
              <iframe title={file.name} src={src} className="h-[72vh] w-full bg-white" />
            )}
          </div>
          <aside className="max-h-[72vh] overflow-auto border-t-2 border-ink/10 px-4 py-4 lg:border-s-2 lg:border-t-0">
            <p className="font-semibold text-ink">הפרטים שחולצו</p>
            <ul className="mt-3 grid gap-2">
              {fields.map((field) => (
                <li key={field.key} className="rounded-md border-2 border-ink/10 px-3 py-2">
                  <p className="text-xs font-semibold text-ink">{field.label}</p>
                  <p className="mt-1 text-sm" dir="auto">
                    {field.value.trim() || "עדיין ריק"}
                  </p>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      </DialogContent>
    </Dialog>
  );
}
