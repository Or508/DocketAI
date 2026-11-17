export const OFFICE_SETTINGS_KEY = "docketflow_office_settings_v1";
const SETTINGS_EVENT = "docket-office-settings";

export type OfficeSettings = {
  officeName: string;
  officePhone: string;
  replyEmail: string;
  signatureFooter: string;
  signingTemplate: string;
  reminderTemplate: string;
  intakeTemplate: string;
  autoLoadForm: boolean;
  showChecksumWarnings: boolean;
};

export const DEFAULT_OFFICE_SETTINGS: OfficeSettings = {
  officeName: "משרד עו״ד ונוטריון",
  officePhone: "",
  replyEmail: "",
  signatureFooter: "",
  signingTemplate: "שלום {client_name}, {process_title} מוכן לבדיקה ולחתימה דיגיטלית בקישור המאובטח: {link}",
  reminderTemplate: "שלום {client_name}, תזכורת ידידותית להשלמת החתימה הדיגיטלית על {process_title}. הטופס ממתין לחתימתך.",
  intakeTemplate: "שלום {client_name}, נשמח להשלמת המסמכים ל{process_title}. קישור להעלאת מסמכים: {link}",
  autoLoadForm: true,
  showChecksumWarnings: true,
};

export function readOfficeSettings(): OfficeSettings {
  if (typeof window === "undefined") return DEFAULT_OFFICE_SETTINGS;
  try {
    const raw = window.localStorage.getItem(OFFICE_SETTINGS_KEY);
    if (!raw) return DEFAULT_OFFICE_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<OfficeSettings>;
    return { ...DEFAULT_OFFICE_SETTINGS, ...parsed };
  } catch {
    return DEFAULT_OFFICE_SETTINGS;
  }
}

export function writeOfficeSettings(settings: OfficeSettings) {
  window.localStorage.setItem(OFFICE_SETTINGS_KEY, JSON.stringify(settings));
  window.dispatchEvent(new Event(SETTINGS_EVENT));
}

export function resetOfficeSettings() {
  writeOfficeSettings(DEFAULT_OFFICE_SETTINGS);
}

export function applyOfficeTemplate(
  template: string,
  values: { client_name: string; process_title: string; link: string },
  settings: OfficeSettings,
) {
  const body = template
    .replaceAll("{client_name}", values.client_name.trim() || "לקוח")
    .replaceAll("{process_title}", values.process_title)
    .replaceAll("{link}", values.link);
  const footer = [settings.signatureFooter.trim(), settings.officeName.trim()].filter(Boolean).join("\n");
  return footer ? `${body}\n\n${footer}` : body;
}

export function subscribeOfficeSettings(onChange: () => void) {
  const notify = () => onChange();
  window.addEventListener("storage", notify);
  window.addEventListener(SETTINGS_EVENT, notify);
  return () => {
    window.removeEventListener("storage", notify);
    window.removeEventListener(SETTINGS_EVENT, notify);
  };
}
