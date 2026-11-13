export type CaseStatus =
  | "draft"
  | "processing"
  | "ready_for_review"
  | "filling"
  | "signed"
  | "failed";

export type DocumentStatus =
  | "uploaded"
  | "processing"
  | "classified"
  | "needs_review"
  | "failed";

export type ClassificationSource = "pending" | "auto" | "human";

export type FieldType = "text" | "email" | "phone" | "date" | "id_number";

export interface ReadingPart {
  labels: string[];
}

export interface ReadingRule {
  kind: "labeled" | "unique" | "composite";
  slot_key: string;
  labels: string[];
  parts: ReadingPart[];
  piece: "street" | "house_number" | "city" | null;
}

export interface DocumentReading {
  enabled: boolean;
  one_person: boolean;
  rules: ReadingRule[];
}

export interface DocumentTypeSpec {
  type_key: string;
  label: string;
  label_he: string | null;
  description: string;
  min_count: number;
  reading: DocumentReading | null;
}

export interface Provenance {
  form_he: string | null;
  section_he: string | null;
  purpose_he: string | null;
  form_en: string | null;
  section_en: string | null;
  purpose_en: string | null;
}

export interface FieldSpec {
  key: string;
  label: string;
  label_he: string | null;
  field_type: FieldType;
  pdf_field_name: string;
  required: boolean;
  rtl: boolean;
  provenance: Provenance | null;
}

export type ValueSource = "client" | "document" | "office";

export interface FieldSource {
  source: ValueSource;
  document_id: string | null;
}

export interface ProcessRead {
  key: string;
  name: string;
  description: string;
  required_documents: DocumentTypeSpec[];
  optional_documents: DocumentTypeSpec[];
  required_fields: FieldSpec[];
}

export interface CaseCertificate {
  case_reference: string;
  channel: "portal" | "office";
  signer_ip: string | null;
  signer_user_agent: string | null;
  consent_text: string;
  created_at: string;
  data_completed_at: string | null;
  link_issued_at: string | null;
  signed_at: string;
  total_pages: number;
}

export interface CaseAudit {
  is_signed: boolean;
  signed_at: string | null;
  signer_verification_id: string | null;
  content_sha256: string | null;
  file_sha256: string | null;
  certificate: CaseCertificate | null;
}

export interface CaseRead {
  id: string;
  name: string;
  client_name: string | null;
  status: CaseStatus;
  process_key: string;
  process_name: string;
  document_count: number;
  download_ready: boolean;
  created_at: string;
  updated_at: string;
  audit: CaseAudit;
}

export interface IdentifiedDocument {
  document_id: string;
  filename: string;
  document_type: string;
  label: string;
  label_he: string | null;
  confidence: number | null;
  source: ClassificationSource;
}

export interface MissingRequirement {
  type_key: string;
  label: string;
  label_he: string | null;
  required_count: number;
  found_count: number;
}

export interface UnrecognizedDocument {
  document_id: string;
  filename: string;
  suggested_type: string | null;
  confidence: number | null;
  rationale: string | null;
}

export interface InProgressDocument {
  document_id: string;
  filename: string;
  status: DocumentStatus;
}

export type PipelineStage =
  | "draft"
  | "parsing"
  | "classifying"
  | "auditing"
  | "awaiting_input"
  | "ready_for_signature"
  | "signed"
  | "failed";

export interface PipelineProgress {
  stage: PipelineStage;
  completed: number;
  total: number;
  message: string;
}

export interface GapReport {
  case_id: string;
  status: CaseStatus;
  total_files: number;
  identified: IdentifiedDocument[];
  missing: MissingRequirement[];
  unrecognized: UnrecognizedDocument[];
  in_progress: InProgressDocument[];
  pipeline: PipelineProgress;
}

export interface FormAnchorRef {
  document_id: string;
  filename: string;
  field_name: string;
  page: number;
  rect: number[];
  match: "exact" | "synonym";
}

export interface WhyItem {
  kind: "template" | "form";
  text_he: string;
  text_en: string;
  document_id: string | null;
  page: number | null;
}

export interface OpenSlot {
  key: string;
  label: string;
  label_he: string | null;
  anchors: FormAnchorRef[];
  why: WhyItem[];
}

export interface DocumentRoleUpdate {
  role: "evidence" | "form";
  display_title: string | null;
}

export interface DocumentRoleRead {
  document_id: string;
  role: "evidence" | "form";
  display_title: string | null;
}

export type FillStatus =
  | "ok"
  | "overflow"
  | "mismatch"
  | "skipped_prefilled"
  | "comb_unsupported"
  | "awaiting_value";

export interface FillReportField {
  field_name: string;
  page: number;
  slot_key: string;
  status: FillStatus;
  source: ValueSource | null;
}

export interface FillReport {
  document_id: string;
  fields: FillReportField[];
}

export interface IntakeForm {
  document_id: string;
  filename: string;
  role: "evidence" | "form";
  display_title: string | null;
  widgets_total: number;
  bound: number;
  bound_empty: number;
  unbound: number;
}

export interface IntakeSummary {
  forms: IntakeForm[];
  missing_documents: MissingRequirement[];
  open_slots: OpenSlot[];
  prompt_he: string;
  prompt_en: string;
}

export type SkipReason =
  | "no_text_layer"
  | "label_not_found"
  | "ambiguous_match"
  | "validator_rejected"
  | "id_mismatch"
  | "already_filled";

export interface SlotHit {
  slot_key: string;
  rule: "labeled" | "unique" | "composite";
  label: string | null;
}

export interface SlotSkip {
  slot_key: string;
  reason: SkipReason;
  rule: "labeled" | "unique" | "composite";
  label: string | null;
}

export interface SlotConflict {
  slot_key: string;
  value: string;
}

export interface DocumentReadingReport {
  document_id: string;
  filename: string;
  document_type: string | null;
  enabled: boolean;
  accepted: SlotHit[];
  skips: SlotSkip[];
  conflicts: SlotConflict[];
  blocked: "id_mismatch" | null;
}

export interface UnboundAnchor {
  document_id: string;
  filename: string;
  field_name: string;
  page: number;
  empty: boolean;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface FieldUpdateRequest {
  key: string;
  value: string;
}

export interface ChatRequest {
  message: string;
}

export interface CaseProgressEvent {
  stage: PipelineStage;
  completed: number;
  total: number;
  message: string;
  status: CaseStatus;
}

export interface StreamError {
  detail: string;
}

export interface SigningLinkRead {
  state: "open" | "completed" | "unavailable";
  created_at: string;
  expires_at: string;
}

export interface SigningLinkCreated {
  url: string;
  expires_at: string;
}

export interface PortalProcess {
  name: string;
  required_fields: FieldSpec[];
}

export interface PortalSeal {
  signed_at: string;
  signer_verification_id: string;
  file_sha256: string;
  recorded_ip: string | null;
  time_zone: "Asia/Jerusalem";
}

export interface PortalView {
  state: "open" | "completed";
  process: PortalProcess;
  client_name: string | null;
  messages: ChatMessage[];
  field_values: Record<string, string>;
  missing_fields: FieldSpec[];
  ready_to_sign: boolean;
  waiting_on_office: boolean;
  review_digest: string | null;
  expires_at: string;
  signed_at: string | null;
  download_expires_at: string | null;
  consent_text: string;
  seal: PortalSeal | null;
}

export interface PortalSignRequest {
  signature_png_base64: string;
  review_digest: string;
  consent: true;
}

export interface CaseWorkspace {
  case: CaseRead;
  gap: GapReport;
  process: ProcessRead;
  messages: ChatMessage[];
  field_values: Record<string, string>;
  field_sources: Record<string, FieldSource>;
  missing_fields: FieldSpec[];
  open_slots: OpenSlot[];
  unbound_anchors: UnboundAnchor[];
  ready_to_sign: boolean;
  signing_blockers: string[];
  consent_text: string;
  readings: DocumentReadingReport[];
}

export type ChatStreamEvent =
  | { event: "delta"; data: string }
  | { event: "replace"; data: string }
  | { event: "workspace"; data: CaseWorkspace }
  | { event: "error"; data: StreamError };

export interface FileRejection {
  filename: string;
  reason: string;
}

export interface UploadResult {
  workspace: CaseWorkspace;
  job_id: string | null;
  accepted_filenames: string[];
  skipped_duplicates: string[];
  rejected: FileRejection[];
}

export type IsraeliIdStatus = "empty" | "incomplete" | "valid" | "invalid";

export function israeliIdStatus(raw: string): { status: IsraeliIdStatus; message: string } {
  const digits = raw.replace(/\D/g, "");
  if (!digits) return { status: "empty", message: "" };
  if (digits.length > 9) return { status: "invalid", message: "A national ID is 9 digits." };
  if (digits.length < 9) return { status: "incomplete", message: `${digits.length} of 9 digits` };
  if (digits === "000000000" || !israeliIdChecksum(digits)) {
    return { status: "invalid", message: "The checksum does not match." };
  }
  return { status: "valid", message: "Checksum matches." };
}

export function formatPhone(raw: string): string {
  const plus = raw.trim().startsWith("+");
  const digits = raw.replace(/\D/g, "").slice(0, 15);
  if (!digits) return plus ? "+" : "";
  if (!plus && digits.startsWith("0") && digits.length <= 10) {
    return [digits.slice(0, 3), digits.slice(3, 6), digits.slice(6, 10)].filter(Boolean).join("-");
  }
  const grouped = digits.replace(/(\d{3})(?=\d)/g, "$1 ").trim();
  return plus ? `+${grouped}` : grouped;
}

export function formatEmail(raw: string): string {
  return raw.replace(/\s+/g, "").toLowerCase();
}

function israeliIdChecksum(padded: string): boolean {
  let total = 0;
  for (let index = 0; index < padded.length; index += 1) {
    let product = Number(padded[index]) * (index % 2 === 0 ? 1 : 2);
    if (product > 9) product = Math.floor(product / 10) + (product % 10);
    total += product;
  }
  return total % 10 === 0;
}
