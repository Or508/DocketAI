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
  "Insured details declaration": "בל/6101 – דיווח רב-שנתי ביטוח לאומי",
  onboarding: "קליטת עובד",
  employee_onboarding: "קליטת עובד",
  "Employee onboarding": "קליטת עובד",
  real_estate: "עסקת מקרקעין",
  "Real estate closing": "עסקת מקרקעין",
};

export type ProcessFamily = "bl_6101" | "onboarding" | "real_estate" | "other";

export function processFamily(key: string): ProcessFamily {
  if (key === "bl_6101" || key === "Insured details declaration") return "bl_6101";
  if (key === "onboarding" || key === "employee_onboarding" || key === "Employee onboarding") return "onboarding";
  if (key === "real_estate" || key === "Real estate closing") return "real_estate";
  return "other";
}

export function processTypeOf(workspace: { process: { key: string }; process_type?: unknown }) {
  return typeof workspace.process_type === "string" && workspace.process_type ? workspace.process_type : workspace.process.key;
}

export function blankFormButton(key: string) {
  const family = processFamily(key);
  if (family === "bl_6101") return "טען טופס בל/6101 אוטומטית";
  if (family === "onboarding") return "טען טופס 101 אוטומטית";
  return "טען טופס תבנית אוטומטית";
}

export function blankFormNotice(key: string) {
  const family = processFamily(key);
  if (family === "bl_6101") return "טופס בל/6101 נטען מהמערכת.";
  if (family === "onboarding") return "טופס 101 נטען מהמערכת.";
  return "טופס התבנית נטען מהמערכת.";
}

export function formDrawerTitle(key: string) {
  const family = processFamily(key);
  if (family === "bl_6101") return "טופס למילוי וחתימה - בל/6101";
  if (family === "onboarding") return "טופס 101 – קליטת עובד חדש";
  if (family === "real_estate") return "טופס עסקת מקרקעין";
  return "טופס למילוי וחתימה";
}

/** The form name used in WhatsApp and email, so a 101 case is not described as BL/6101. */
export function dispatchFormTitle(key: string) {
  const family = processFamily(key);
  if (family === "bl_6101") return "טופס בל/6101 (דיווח רב-שנתי לביטוח לאומי)";
  if (family === "onboarding") return "טופס 101 (קליטת עובד חדש)";
  if (family === "real_estate") return "טופס עסקת מקרקעין";
  return "הטופס";
}

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
