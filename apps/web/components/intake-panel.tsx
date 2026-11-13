"use client";

import type { IntakeSummary } from "@docketai/shared-types";
import { useEffect, useState } from "react";

import { PdfCanvas } from "@/components/pdf-preview";
import { Button } from "@/components/ui/button";
import { ApiError, api, filledFormUrl } from "@/lib/api";

export function IntakePanel({
  caseId,
  refreshKey,
  busy,
  onChanged,
}: {
  caseId: string;
  refreshKey: string;
  busy: boolean;
  onChanged: () => Promise<void>;
}) {
  const [intake, setIntake] = useState<IntakeSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [marking, setMarking] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .intake(caseId)
      .then((next) => {
        if (!cancelled) {
          setIntake(next);
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof ApiError ? reason.message : "Could not load the intake.");
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, refreshKey]);

  async function markForm(documentId: string) {
    setMarking(documentId);
    setError(null);
    try {
      await api.setDocumentRole(caseId, documentId, "form");
      await onChanged();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "This file could not be marked as the form.");
    } finally {
      setMarking(null);
    }
  }

  if (!intake && !error) return null;
  const waiting = (intake?.missing_documents.length ?? 0) > 0;

  return (
    <section className="rounded-lg border border-line bg-white/80 p-5 shadow-card">
      <p className="text-[11px] uppercase tracking-[0.18em] text-tide">Intake</p>
      <h2 className="font-serif text-2xl" dir="rtl">
        {waiting ? "קודם הקבצים החסרים" : "הקבצים בפנים. עכשיו השדות הריקים"}
      </h2>
      <p className="mt-2 text-sm leading-6 text-mist" dir="rtl">
        {intake?.prompt_he}
      </p>
      {error ? <p className="mt-3 text-sm text-clay">{error}</p> : null}
      {waiting ? (
        <ul className="mt-4 space-y-2">
          {intake?.missing_documents.map((item) => (
            <li key={item.type_key} className="rounded-md border border-line px-3 py-2 text-sm" dir="rtl">
              {item.label_he ?? item.label}
            </li>
          ))}
        </ul>
      ) : null}
      {intake && intake.forms.length > 0 ? (
        <div className="mt-4 space-y-4">
          {intake.forms.map((form) => (
            <article key={form.document_id} className="rounded-md border border-line px-3 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div dir="rtl">
                  <h3 className="text-sm font-medium">{form.display_title || "טופס המשרד"}</h3>
                  <p className="text-sm text-mist">
                    {form.bound_empty} שדות ריקים מתוך {form.bound} שקשורים לתיק
                  </p>
                </div>
                {form.role === "evidence" ? (
                  <Button
                    type="button"
                    variant="outline"
                    disabled={busy || marking === form.document_id}
                    onClick={() => void markForm(form.document_id)}
                  >
                    זה הטופס למילוי
                  </Button>
                ) : null}
              </div>
              {form.role === "form" ? (
                <div className="mt-3">
                  <PdfCanvas url={filledFormUrl(caseId, form.document_id)} refreshKey={refreshKey} />
                </div>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}
