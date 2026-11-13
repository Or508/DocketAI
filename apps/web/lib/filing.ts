import type { CaseStatus, CaseWorkspace, FieldSource } from "@docketai/shared-types";

export type FolderTone = "missing" | "review" | "awaiting" | "done";

export const FOLDER_LABEL: Record<FolderTone, string> = {
  missing: "טיוטה / חסרים מסמכים",
  review: "מוכן לבדיקת משרד",
  awaiting: "ממתין לחתימת לקוח",
  done: "נחתם והושלם",
};

export const PROCESS_LABEL: Record<string, string> = {
  bl_6101: "בל/6101 – דיווח רב-שנתי ביטוח לאומי",
  onboarding: "קליטת עובד",
  real_estate: "עסקת מקרקעין",
};

export const SLOT_LABEL: Record<string, string> = {
  id_copy: "תעודת זהות",
  proof_of_address: "חשבון ארנונה / כתובת",
  bank_confirmation: "אישור ניהול חשבון",
  tax_form: "טופס מס",
  pension_form: "טופס פנסיה",
  title_deed: "נסח טאבו",
  purchase_agreement: "הסכם מכר",
};

export const FIELD_LABEL: Record<string, string> = {
  last_name: "שם משפחה",
  first_name: "שם פרטי",
  full_name: "שם מלא",
  national_id: "מספר זהות",
  city: "יישוב / עיר",
  street: "רחוב",
  house_number: "מס' בית",
  address_he: "כתובת",
  phone: "טלפון נייד",
  email: "דוא״ל",
  bank_name: "בנק",
  bank_branch: "סניף",
  bank_account: "חשבון",
};

export function processLabel(key: string, fallback: string) {
  return PROCESS_LABEL[key] ?? fallback;
}

export function folderTone(input: {
  status: CaseStatus;
  missingDocs: number;
  missingFields: number;
  readyToSign: boolean;
}): FolderTone {
  if (input.status === "signed") return "done";
  if (input.status === "draft" || input.status === "failed" || input.status === "processing" || input.missingDocs > 0) {
    return "missing";
  }
  if (input.readyToSign && input.missingFields === 0) return "awaiting";
  return "review";
}

export function folderFromWorkspace(workspace: CaseWorkspace): FolderTone {
  return folderTone({
    status: workspace.case.status,
    missingDocs: workspace.gap.missing.length,
    missingFields: workspace.missing_fields.length,
    readyToSign: workspace.ready_to_sign,
  });
}

export function sourceBadge(source: FieldSource | undefined, hasValue: boolean): string {
  if (!hasValue || !source) return "ממתין להשלמת משרד";
  if (source.source === "office") return "עודכן במשרד";
  if (source.source === "client") return "הוזן ע״י הלקוח";
  if (source.source === "document") return "נקרא ממסמך";
  return "ממתין להשלמת משרד";
}
