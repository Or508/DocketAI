"use client";

import type { CaseAudit, CaseCertificate } from "@docketai/shared-types";
import { Check, Copy, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { certificateUrl } from "@/lib/api";

const MISSING = "Not recorded for this packet";
const BLANK = "Not recorded";

export function AuditCard({ caseId, audit }: { caseId: string; audit: CaseAudit }) {
  const [copied, setCopied] = useState<string | null>(null);
  if (!audit.is_signed) return null;

  async function copy(label: string, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
      window.setTimeout(() => {
        setCopied((current) => (current === label ? null : current));
      }, 1500);
    } catch {
      return;
    }
  }

  const signedAt = audit.signed_at
    ? `${new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: "medium",
        timeZone: "Asia/Jerusalem",
      }).format(new Date(audit.signed_at))} Israel time`
    : MISSING;

  return (
    <section className="rounded-lg border border-line bg-[#fbf8f2] shadow-card">
      <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.18em] text-tide">Audit & Integrity</p>
          <h2 className="font-serif text-2xl">Signature record</h2>
        </div>
        <ShieldCheck className="h-5 w-5 text-tide" aria-hidden="true" />
      </div>
      <dl className="space-y-3 px-4 py-4 text-sm">
        <PlainRow label="Status" value="Signed" />
        <PlainRow label="Signed at" value={signedAt} />
        <CopyRow label="Verification reference" value={audit.signer_verification_id} copied={copied} onCopy={copy} />
        <CopyRow
          label="File SHA-256"
          value={audit.file_sha256}
          hint="Matches the downloaded PDF."
          copied={copied}
          onCopy={copy}
        />
        <CopyRow
          label="Form content SHA-256"
          value={audit.content_sha256}
          hint="Printed in the PDF footer. Calculated before the footer was added, so it differs from the file hash."
          copied={copied}
          onCopy={copy}
        />
      </dl>
      <CertificateSection caseId={caseId} certificate={audit.certificate} />
      <p className="border-t border-line px-4 py-3 text-xs leading-5 text-mist">
        This record shows whether the file has changed since signing. It does not verify the signer's identity.
      </p>
    </section>
  );
}

function israelTime(value: string | null) {
  if (!value) return BLANK;
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone: "Asia/Jerusalem",
  }).format(new Date(value));
}

function CertificateSection({ caseId, certificate }: { caseId: string; certificate: CaseCertificate | null }) {
  if (!certificate) {
    return <p className="border-t border-line px-4 py-3 text-sm">No certificate for this packet</p>;
  }
  const method = certificate.channel === "portal" ? "Secure signing link" : "Office workspace";
  return (
    <div className="border-t border-line px-4 py-4">
      <h3 className="font-serif text-xl">Certificate</h3>
      <dl className="mt-3 space-y-3 text-sm">
        <PlainRow label="Case reference" value={certificate.case_reference} />
        <PlainRow label="Signing method" value={method} />
        <PlainRow label="IP address" value={certificate.signer_ip ?? BLANK} />
        <PlainRow label="Browser" value={certificate.signer_user_agent ?? BLANK} />
        <PlainRow label="Case created" value={israelTime(certificate.created_at)} />
        <PlainRow label="Data collection completed" value={israelTime(certificate.data_completed_at)} />
        <PlainRow label="Signing link issued" value={israelTime(certificate.link_issued_at)} />
        <PlainRow label="Signed" value={israelTime(certificate.signed_at)} />
        <PlainRow label="Total pages" value={String(certificate.total_pages)} />
      </dl>
      <a
        className="mt-3 inline-block text-sm text-tide underline"
        href={certificateUrl(caseId)}
        target="_blank"
        rel="noreferrer"
      >
        View certificate
      </a>
    </div>
  );
}

function PlainRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-mist">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function CopyRow({
  label,
  value,
  hint,
  copied,
  onCopy,
}: {
  label: string;
  value: string | null;
  hint?: string;
  copied: string | null;
  onCopy: (label: string, value: string) => Promise<void>;
}) {
  const shown = value ?? MISSING;
  return (
    <div>
      <dt className="text-mist">{label}</dt>
      <dd className="flex items-start gap-2">
        <span dir="ltr" className="min-w-0 flex-1 break-all font-mono text-xs leading-5">
          {shown}
        </span>
        {value ? (
          <button
            type="button"
            className="mt-0.5 text-tide"
            aria-label={`Copy ${label}`}
            onClick={() => void onCopy(label, value)}
          >
            {copied === label ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
        ) : null}
      </dd>
      {hint ? <p className="mt-1 text-xs leading-5 text-mist">{hint}</p> : null}
    </div>
  );
}
