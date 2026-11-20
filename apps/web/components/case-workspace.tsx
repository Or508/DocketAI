"use client";

import type { CaseProgressEvent, CaseWorkspace, IntakeSummary } from "@docketai/shared-types";
import { useCallback, useEffect, useRef, useState } from "react";

import { ActivityTimeline } from "@/components/activity-timeline";
import { InternalNotes } from "@/components/internal-notes";
import { AuditCard } from "@/components/audit-card";
import { FieldVerification } from "@/components/field-verification";
import { FilingSlots } from "@/components/filing-slots";
import { FillReportList } from "@/components/fill-report";
import { PdfCanvas } from "@/components/pdf-preview";
import { PipelineBanner } from "@/components/pipeline-banner";
import { ReadingPanel } from "@/components/reading-panel";
import { SignedChecklist, SignedPdfFrame } from "@/components/signed-review";
import { SignerLinkCard } from "@/components/signer-link-card";
import { SmartDropzone } from "@/components/smart-dropzone";
import { SourceCompare } from "@/components/source-compare";
import { SigningModal } from "@/components/signing-modal";
import { StatusPill } from "@/components/status-pill";
import { WhatsAppReminder } from "@/components/whatsapp-reminder";
import { Button } from "@/components/ui/button";
import { OfficeTopNav } from "@/components/OfficeTopNav";
import { ReadinessShield } from "@/components/readiness-shield";
import { CASE_PRINT_CSS, CaseCover } from "@/components/case-cover";
import { DocumentRequest } from "@/components/document-request";
import { OutreachStatus, SendToClientButton } from "@/components/client-outreach";
import { ApiError, api, downloadCaseArchive, filledFormUrl, signedDocumentUrl } from "@/lib/api";
import { archiveFilename } from "@/lib/dispatch";
import { FIELD_LABEL, blankFormNotice, dispatchFormTitle, folderFromWorkspace, formDrawerTitle, processLabel, processTypeOf } from "@/lib/filing";
import { hebrewDetail, hebrewOfficeError, hebrewUploadReason } from "@/lib/hebrew";

export function CaseWorkspaceView({ caseId }: { caseId: string }) {
  const [workspace, setWorkspace] = useState<CaseWorkspace | null>(null);
  const [intake, setIntake] = useState<IntakeSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [signing, setSigning] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(true);
  const [previewLarge, setPreviewLarge] = useState(false);
  const [rereading, setRereading] = useState(false);
  const [loadingForm, setLoadingForm] = useState(false);
  const [sourceFile, setSourceFile] = useState<{ id: string; name: string } | null>(null);
  const [watch, setWatch] = useState(false);
  const [slotErrors, setSlotErrors] = useState<Record<string, string>>({});
  const [pendingSlots, setPendingSlots] = useState<string[]>([]);
  const [outreachTick, setOutreachTick] = useState(0);
  const claimsRef = useRef<DrawerClaim[]>([]);
  const claiming = useRef(false);
  const uploadQueue = useRef(Promise.resolve());

  const finishClaims = useCallback(
    async (next: CaseWorkspace, nextIntake: IntakeSummary) => {
      if (claiming.current) return { workspace: next, intake: nextIntake };
      claiming.current = true;
      try {
        let latest = next;
        let latestIntake = nextIntake;
        const left: DrawerClaim[] = [];
        for (const claim of claimsRef.current) {
          const document = findNamed(latest, latestIntake, claim.filename);
          if (!document || document.busy) {
            left.push(claim);
            continue;
          }
          try {
            if (claim.slot === "form") {
              const already = latestIntake.forms.some((item) => item.document_id === document.id && item.role === "form");
              if (!already) {
                const title = formDrawerTitle(processTypeOf(latest));
                await api.setDocumentRole(caseId, document.id, "form", title);
                for (const other of latestIntake.forms) {
                  if (other.role === "form" && other.document_id !== document.id) {
                    await api.setDocumentRole(caseId, other.document_id, "evidence");
                  }
                }
                latest = await api.workspace(caseId);
                latestIntake = await api.intake(caseId);
              }
            } else if (document.type !== claim.slot) {
              latest = await api.classify(caseId, document.id, claim.slot);
              latestIntake = await api.intake(caseId);
            }
            setSlotErrors((current) => ({ ...current, [claim.slot]: "" }));
          } catch (reason) {
            if (isStillReading(reason)) {
              left.push(claim);
            } else {
              setSlotErrors((current) => ({ ...current, [claim.slot]: hebrewOfficeError(reason) }));
            }
          }
        }
        claimsRef.current = left;
        setPendingSlots(left.map((claim) => claim.slot));
        return { workspace: latest, intake: latestIntake };
      } finally {
        claiming.current = false;
      }
    },
    [caseId],
  );

  const refresh = useCallback(async () => {
    const [next, nextIntake] = await Promise.all([api.workspace(caseId), api.intake(caseId)]);
    const settled = await finishClaims(next, nextIntake);
    setWorkspace(settled.workspace);
    setIntake(settled.intake);
    const reading =
      settled.workspace.case.status === "processing" ||
      settled.workspace.gap.in_progress.length > 0 ||
      claimsRef.current.length > 0;
    setWatch(reading);
  }, [caseId, finishClaims]);

  useEffect(() => {
    let cancelled = false;
    refresh().catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof ApiError ? reason.message : "לא ניתן לטעון את התיק.");
    });
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  const processing =
    watch || workspace?.case.status === "processing" || (workspace?.gap.in_progress.length ?? 0) > 0;
  useEffect(() => {
    if (!processing) return;
    const source = new EventSource(`/api/office/cases/${caseId}/events`);
    source.addEventListener("progress", (event) => {
      const progress = JSON.parse((event as MessageEvent).data) as CaseProgressEvent;
      const { status, ...pipeline } = progress;
      setWorkspace((current) =>
        current
          ? { ...current, case: { ...current.case, status }, gap: { ...current.gap, pipeline } }
          : current,
      );
    });
    source.addEventListener("done", () => {
      void refresh().catch(() => undefined);
      source.close();
    });
    const timer = window.setInterval(() => {
      void refresh().catch(() => undefined);
    }, 2000);
    return () => {
      source.close();
      window.clearInterval(timer);
    };
  }, [processing, caseId, refresh]);

  useEffect(() => {
    if (!previewLarge) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setPreviewLarge(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [previewLarge]);

  async function run(action: () => Promise<CaseWorkspace>, note?: string) {
    setBusy(true);
    setError(null);
    try {
      setWorkspace(await action());
      const nextIntake = await api.intake(caseId);
      setIntake(nextIntake);
      setNotice(note ?? null);
      return true;
    } catch (reason) {
      setError(hebrewOfficeError(reason));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function uploadSlot(slot: string, file: File, replace = false) {
    setSlotErrors((current) => ({ ...current, [slot]: "" }));
    setPendingSlots((current) => (current.includes(slot) ? current : [...current, slot]));
    try {
      const uploaded = await api.upload(caseId, [file], {
        ...(slot === "form" ? { role: "form" as const } : { documentType: slot }),
        replaceExisting: replace,
      });
      if (uploaded.rejected.length) {
        setSlotErrors((current) => ({
          ...current,
          [slot]: uploaded.rejected.map((item) => hebrewUploadReason(item.reason)).join(" "),
        }));
        setPendingSlots((current) => current.filter((item) => item !== slot));
        setWorkspace(uploaded.workspace);
        return;
      }
      const names = [...uploaded.accepted_filenames, ...uploaded.skipped_duplicates];
      const filename = names[0] || file.name;
      claimsRef.current = [...claimsRef.current.filter((claim) => claim.slot !== slot), { slot, filename }];
      if (slot !== "form") {
        const placed = findNamed(uploaded.workspace, intake, filename);
        if (placed && !placed.busy && placed.type !== slot) {
          try {
            uploaded.workspace = await api.classify(caseId, placed.id, slot);
          } catch (reason) {
            if (!isStillReading(reason)) {
              setSlotErrors((current) => ({ ...current, [slot]: hebrewOfficeError(reason) }));
            }
          }
        }
      }
      setWorkspace(uploaded.workspace);
      setNotice(uploaded.skipped_duplicates.length ? "הקובץ כבר היה בתיק והוכנס למגירה שנבחרה." : "הקובץ נכנס למגירה.");
      setWatch(true);
      await refresh();
    } catch (reason) {
      setSlotErrors((current) => ({ ...current, [slot]: hebrewOfficeError(reason) }));
      setPendingSlots(claimsRef.current.map((claim) => claim.slot));
      if (claimsRef.current.length) setWatch(true);
    }
  }

  function queueUpload(slot: string, file: File, replace = false) {
    const next = uploadQueue.current.then(() => uploadSlot(slot, file, replace));
    uploadQueue.current = next.then(
      () => undefined,
      () => undefined,
    );
    return next;
  }

  async function rereadDocuments() {
    if (!workspace) return;
    const formIds = new Set((intake?.forms ?? []).filter((item) => item.role === "form").map((item) => item.document_id));
    const sources = workspace.gap.identified.filter((item) => item.document_type && !formIds.has(item.document_id));
    if (!sources.length) {
      setError("אין מסמכי מקור מסווגים לקריאה מחדש.");
      return;
    }
    setRereading(true);
    setError(null);
    try {
      for (const document of sources) {
        await api.classify(caseId, document.document_id, document.document_type);
      }
      setNotice("השדות נקראו מחדש מהמסמכים.");
      await refresh();
    } catch (reason) {
      setError(hebrewOfficeError(reason));
    } finally {
      setRereading(false);
    }
  }

  async function removeDocument(slot: string, documentId: string) {
    setSlotErrors((current) => ({ ...current, [slot]: "" }));
    try {
      setWorkspace(await api.deleteDocument(caseId, documentId));
      setNotice(slot === "form" ? "הטופס הוסר." : "הקובץ הוסר.");
      await refresh();
    } catch (reason) {
      setSlotErrors((current) => ({ ...current, [slot]: hebrewOfficeError(reason) }));
    }
  }

  async function moveDocument(documentId: string, fromSlot: string, toSlot: string) {
    if (toSlot === fromSlot) return;
    setSlotErrors((current) => ({ ...current, [fromSlot]: "" }));
    try {
      if (toSlot === "form") {
        const title = workspace ? formDrawerTitle(processTypeOf(workspace)) : undefined;
        await api.setDocumentRole(caseId, documentId, "form", title);
        for (const other of intake?.forms ?? []) {
          if (other.role === "form" && other.document_id !== documentId) {
            await api.setDocumentRole(caseId, other.document_id, "evidence");
          }
        }
      } else {
        if (fromSlot === "form") await api.setDocumentRole(caseId, documentId, "evidence");
        setWorkspace(await api.classify(caseId, documentId, toSlot));
      }
      setNotice("הקובץ הועבר למגירה.");
      await refresh();
    } catch (reason) {
      setSlotErrors((current) => ({ ...current, [fromSlot]: hebrewOfficeError(reason) }));
    }
  }

  if (!workspace && !error) {
    return <p className="px-6 py-10 text-sm text-ink">טוען את התיק…</p>;
  }
  if (!workspace) {
    return <p className="px-6 py-10 text-sm font-medium text-clay">{error}</p>;
  }

  const form = intake?.forms.find((item) => item.role === "form") ?? null;
  const tone = folderFromWorkspace(workspace);
  const processType = processTypeOf(workspace);
  const loadedNotice = blankFormNotice(processType);
  const previewRev = [
    workspace.case.updated_at,
    form?.document_id ?? "",
    workspace.gap.identified.map((item) => item.document_id).join(","),
    stamp(Object.keys(workspace.field_values).sort().map((key) => workspace.field_values[key]).join("\n")),
  ].join("|");
  const previewUrl = form ? filledFormUrl(caseId, form.document_id) : "";
  const archiveName = archiveFilename(workspace.case.client_name || workspace.case.name);

  async function saveArchive() {
    setBusy(true);
    setError(null);
    try {
      await downloadCaseArchive(caseId, archiveName);
    } catch (reason) {
      setError(hebrewOfficeError(reason));
    } finally {
      setBusy(false);
    }
  }

  async function loadBlankForm() {
    setLoadingForm(true);
    setError(null);
    try {
      await api.loadDefaultForm(caseId);
      setNotice(loadedNotice);
      await refresh();
    } catch (reason) {
      setError(hebrewOfficeError(reason));
    } finally {
      setLoadingForm(false);
    }
  }

  async function reopenCase() {
    const confirmed = window.confirm(
      "פתיחת התיק מחדש משחררת את הפרטים לתיקון. החתימה הקיימת מתבטלת, והלקוח יצטרך לחתום שוב על קישור חדש. להמשיך?",
    );
    if (!confirmed) return;
    setBusy(true);
    setError(null);
    try {
      await api.reopenCase(caseId);
      setNotice("התיק נפתח מחדש. אפשר לתקן פרטים ואז לשלוח קישור חתימה חדש.");
      await refresh();
    } catch (reason) {
      setError(hebrewOfficeError(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-[96rem] px-5 py-6 lg:px-8 lg:py-8">
      <style>{CASE_PRINT_CSS}</style>
      <CaseCover workspace={workspace} intake={intake} tone={tone} />
      <div className="no-print">
      <OfficeTopNav />
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 border-b border-line pb-5">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
          <a href="/cases" className="text-sm font-medium text-mist hover:text-tide">
            תיקים ‹
          </a>
          <h1 className="text-3xl font-bold tracking-tight text-ink">{workspace.case.client_name || workspace.case.name}</h1>
          <StatusPill tone={tone} />
          <p className="text-sm text-mist">{processLabel(processType, workspace.process.name)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" disabled={busy} onClick={() => void saveArchive()}>
            הורדת התיק (ZIP)
          </Button>
          <Button type="button" variant="outline" onClick={() => window.print()}>
            הדפסת דף תיק
          </Button>
          {workspace.case.status === "signed" ? (
            <Button type="button" variant="ghost" disabled={busy} onClick={() => void reopenCase()}>
              פתיחת תיק מחדש לתיקון
            </Button>
          ) : null}
          {tone === "awaiting" ? (
            <WhatsAppReminder
              className="max-w-xs"
              clientName={workspace.case.client_name || workspace.case.name}
              phone={workspace.field_values.phone ?? ""}
              formTitle={dispatchFormTitle(processType)}
              explain
            />
          ) : null}
        </div>
      </header>

      {error ? (
        <p className="mt-4 text-sm font-medium text-clay" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? <p className="mt-4 text-sm font-medium text-moss">{notice}</p> : null}
      {processing ? <PipelineBanner pipeline={workspace.gap.pipeline} /> : null}

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-12 lg:gap-6">
        <div className="space-y-6 lg:col-span-7">
        <FilingSlots
          workspace={workspace}
          intake={intake}
          pendingSlots={pendingSlots}
          slotErrors={slotErrors}
          onUpload={queueUpload}
          onRemove={removeDocument}
          onMove={moveDocument}
          onReread={rereadDocuments}
          rereading={rereading}
          onLoadBlank={workspace.case.status !== "signed" ? loadBlankForm : undefined}
          loadingBlank={loadingForm}
          onView={setSourceFile}
          lead={
            workspace.case.status !== "signed" ? (
              <SmartDropzone
                compact
                caseId={caseId}
                onUploaded={(next, summary) => {
                  setWorkspace(next);
                  setNotice(summary);
                  setError(null);
                  setWatch(true);
                  void refresh();
                }}
              />
            ) : null
          }
        />
        <FieldVerification
          processKey={workspace.process.key}
          process={workspace.process}
          field_values={workspace.field_values}
          field_sources={workspace.field_sources}
          busy={busy}
          sourceFor={(fieldKey) => sourceDocument(fieldKey, workspace, intake)}
          onViewSource={setSourceFile}
          onSave={async (key, value) => {
            setBusy(true);
            setError(null);
            try {
              setWorkspace(await api.setField(caseId, key, value));
              setNotice("הפרט נשמר והתצוגה התעדכנה.");
            } catch (reason) {
              setNotice(null);
              throw new ApiError(hebrewOfficeError(reason), reason instanceof ApiError ? reason.status : 400);
            } finally {
              setBusy(false);
            }
          }}
        />
        <section className="rounded-lg border border-ink/15 bg-white p-4 shadow-card">
          <h2 className="font-serif text-xl">מוכנות התיק, שליחה לחתימה ובקשת מסמכים</h2>
          <div className="mt-4">
            <ReadinessShield
              embedded
              caseId={caseId}
              workspace={workspace}
              intake={intake}
              loadingForm={loadingForm}
              onLoadBlank={workspace.case.status !== "signed" ? loadBlankForm : undefined}
            />
            <div className="mt-4 border-t border-ink/10 pt-4">
              <SendToClientButton
                caseId={caseId}
                readyToSign={workspace.ready_to_sign}
                onSent={() => setOutreachTick((value) => value + 1)}
              />
            </div>
            <SignerLinkCard
              embedded
              caseId={caseId}
              clientName={workspace.case.client_name || workspace.case.name}
              phone={workspace.field_values.phone ?? ""}
              email={workspace.field_values.email ?? ""}
              signed={workspace.case.status === "signed"}
              waiting={tone === "awaiting" || workspace.gap.pipeline.stage === "ready_for_signature"}
              verificationId={workspace.case.audit.signer_verification_id}
              processKey={processType}
              onRevoked={(next) => {
                setWorkspace(next);
                setNotice("קישור החתימה בוטל והתיק חזר לעריכה.");
                void refresh();
              }}
            />
            {workspace.case.status !== "signed" ? (
              <DocumentRequest
                embedded
                caseId={caseId}
                clientName={workspace.case.client_name || workspace.case.name}
                phone={workspace.field_values.phone ?? ""}
                processTitle={dispatchFormTitle(processType)}
              />
            ) : null}
            <div className="mt-4 border-t border-ink/10 pt-4">
              <Button type="button" variant="outline" disabled={!workspace.ready_to_sign || busy} onClick={() => setSigning(true)}>
                חתימת המשרד
              </Button>
              {workspace.signing_blockers.length > 0 ? (
                <ul className="mt-3 space-y-1 text-sm font-medium text-clay">
                  {workspace.signing_blockers.map((item) => (
                    <li key={item}>{hebrewDetail(409, item)}</li>
                  ))}
                </ul>
              ) : null}
              {workspace.case.download_ready ? (
                <div className="mt-4 space-y-3">
                  <SignedChecklist />
                  <a className="block text-sm font-semibold text-tide underline" href={signedDocumentUrl(caseId)}>
                    הורדת הטופס החתום
                  </a>
                </div>
              ) : null}
            </div>
          </div>
        </section>
        <AuditCard caseId={caseId} audit={workspace.case.audit} />
        </div>
        <aside className="lg:sticky lg:top-20 lg:col-span-5">
          <section className="rounded-lg border border-ink/15 bg-white shadow-card">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink/10 px-4 py-3">
              <h2 className="font-serif text-xl">טיוטת הטופס הממולא</h2>
              <div className="flex flex-wrap gap-2">
                <Button type="button" size="sm" variant="outline" disabled={!form} onClick={() => setPreviewLarge(true)}>
                  הגדל למסך מלא
                </Button>
                {form ? (
                  <a
                    className="inline-flex h-8 items-center rounded-md border border-ink/30 bg-white px-2.5 text-xs font-semibold text-ink"
                    href={`${previewUrl}?rev=${encodeURIComponent(previewRev)}`}
                    download="טיוטת-טופס.pdf"
                  >
                    הורד טיוטה
                  </a>
                ) : null}
                <Button type="button" size="sm" variant="outline" onClick={() => setPreviewOpen((open) => !open)}>
                  {previewOpen ? "כיווץ" : "פתיחה"}
                </Button>
              </div>
            </div>
            {previewOpen ? (
              <div className="max-h-[calc(100vh-8rem)] overflow-auto px-4 py-4">
                {form ? (
                  <>
                    <PdfCanvas url={previewUrl} refreshKey={previewRev} />
                    <FillReportList caseId={caseId} documentId={form.document_id} refreshKey={previewRev} />
                  </>
                ) : (
                  <p className="text-sm text-ink">סמנו PDF כטופס למילוי וחתימה כדי לראות את הטיוטה כאן.</p>
                )}
                {workspace.case.download_ready ? (
                  <div className="mt-4 border-t border-ink/10 pt-4">
                    <SignedPdfFrame src={signedDocumentUrl(caseId)} />
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        </aside>
      </div>
      <div className="mt-5 grid gap-5">
        <InternalNotes caseId={caseId} />
        <OutreachStatus caseId={caseId} refreshKey={outreachTick} />
        <ActivityTimeline caseId={caseId} />
        <ReadingPanel workspace={workspace} />
      </div>

      {sourceFile ? (
        <SourceCompare
          caseId={caseId}
          file={sourceFile}
          fields={workspace.process.required_fields.map((field) => ({
            key: field.key,
            label: FIELD_LABEL[field.key] ?? field.label_he ?? field.label,
            value: workspace.field_values[field.key] ?? "",
          }))}
          onClose={() => setSourceFile(null)}
        />
      ) : null}

      {previewLarge && form ? (
        <div
          className="fixed inset-0 z-50 flex flex-col bg-[#16130f]/80 p-3 sm:p-6"
          role="dialog"
          aria-modal="true"
          aria-label="טיוטת הטופס הממולא"
          onKeyDown={(event) => {
            if (event.key === "Escape") setPreviewLarge(false);
          }}
        >
          <div className="mx-auto flex h-full min-h-0 w-full max-w-5xl flex-col rounded-lg border border-ink bg-paper shadow-card">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink/15 px-4 py-3">
              <h2 className="font-serif text-2xl">טיוטת הטופס הממולא</h2>
              <div className="flex flex-wrap gap-2">
                <a
                  className="inline-flex h-11 items-center rounded-md bg-tide px-3 text-sm font-semibold text-white"
                  href={`${previewUrl}?rev=${encodeURIComponent(previewRev)}`}
                  download="טיוטת-טופס.pdf"
                >
                  הורד טיוטה
                </a>
                <Button type="button" variant="outline" onClick={() => setPreviewLarge(false)}>
                  סגירה
                </Button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto bg-[#f4f0e6] px-4 py-4">
              <PdfCanvas url={previewUrl} refreshKey={previewRev} maxPages={8} scale={1.6} />
            </div>
          </div>
        </div>
      ) : null}

      <SigningModal
        open={signing}
        busy={busy}
        consentLabel={workspace.consent_text}
        onOpenChange={setSigning}
        onSign={async (png) => {
          const ok = await run(() => api.sign(caseId, png), "הטופס נחתם.");
          if (ok) setSigning(false);
        }}
      />
      </div>
    </main>
  );
}

function stamp(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) hash = (hash * 33 + value.charCodeAt(index)) >>> 0;
  return hash.toString(36);
}

type DrawerClaim = { slot: string; filename: string };

type NamedDocument = { id: string; filename: string; type: string | null; busy: boolean };

function isStillReading(reason: unknown) {
  return reason instanceof ApiError && reason.status === 409 && /processing/i.test(reason.message);
}

function findNamed(workspace: CaseWorkspace, intake: IntakeSummary | null, filename: string): NamedDocument | undefined {
  const want = filename.trim().toLowerCase();
  const hits = namedDocuments(workspace, intake).filter((item) => item.filename.trim().toLowerCase() === want);
  return hits.find((item) => !item.busy) ?? hits[0];
}

function namedDocuments(workspace: CaseWorkspace, intake: IntakeSummary | null): NamedDocument[] {
  const hits: NamedDocument[] = [
    ...workspace.gap.in_progress.map((item) => ({
      id: item.document_id,
      filename: item.filename,
      type: null,
      busy: true,
    })),
    ...workspace.gap.identified.map((item) => ({
      id: item.document_id,
      filename: item.filename,
      type: item.document_type,
      busy: false,
    })),
    ...workspace.gap.unrecognized.map((item) => ({
      id: item.document_id,
      filename: item.filename,
      type: item.suggested_type,
      busy: false,
    })),
  ];
  for (const report of workspace.readings) {
    if (hits.some((item) => item.id === report.document_id)) continue;
    hits.push({
      id: report.document_id,
      filename: report.filename,
      type: report.document_type,
      busy: false,
    });
  }
  for (const form of intake?.forms ?? []) {
    if (hits.some((item) => item.id === form.document_id)) continue;
    hits.push({ id: form.document_id, filename: form.filename, type: null, busy: false });
  }
  const extra = (workspace.case as { documents?: unknown }).documents;
  if (Array.isArray(extra)) {
    for (const item of extra) {
      if (!item || typeof item !== "object") continue;
      const row = item as { id?: unknown; document_id?: unknown; filename?: unknown; original_filename?: unknown; document_type?: unknown; status?: unknown };
      const id = String(row.document_id ?? row.id ?? "");
      const name = String(row.filename ?? row.original_filename ?? "");
      if (!id || !name || hits.some((hit) => hit.id === id)) continue;
      const status = String(row.status ?? "");
      hits.push({
        id,
        filename: name,
        type: row.document_type ? String(row.document_type) : null,
        busy: status === "uploaded" || status === "processing",
      });
    }
  }
  return hits;
}

const FIELD_DRAWER: Record<string, string> = {
  last_name: "id_copy",
  first_name: "id_copy",
  full_name: "id_copy",
  national_id: "id_copy",
  id_number: "id_copy",
  city: "proof_of_address",
  street: "proof_of_address",
  house_number: "proof_of_address",
  address_he: "proof_of_address",
  phone: "proof_of_address",
  email: "id_copy",
  bank_name: "bank_confirmation",
  bank_branch: "bank_confirmation",
  bank_account: "bank_confirmation",
};

function sourceDocument(fieldKey: string, workspace: CaseWorkspace, intake: IntakeSummary | null) {
  const files = namedDocuments(workspace, intake).filter((item) => !item.busy);
  const linked = workspace.field_sources[fieldKey]?.document_id;
  const fromField = linked ? files.find((item) => item.id === linked) : undefined;
  if (fromField) return { id: fromField.id, name: fromField.filename };
  const drawer = FIELD_DRAWER[fieldKey];
  const match = drawer ? files.find((item) => item.type === drawer) : undefined;
  return match ? { id: match.id, name: match.filename } : null;
}
