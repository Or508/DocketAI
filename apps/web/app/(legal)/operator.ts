// The one place for the details the legal pages quote. Fill every "[...]" before real clients use the site:
// until then each legal page shows a "draft" banner (see legal-frame.tsx).
// The texts themselves still need a lawyer's review (docs/deploy/render.md, "before real client data").
export const OPERATOR = {
  // The legal entity that runs DocketFlow, and its registration number (ח.פ. or ע.מ.).
  name: "[שם העסק]",
  registration: "[ח.פ. / ע.מ.]",
  address: "[כתובת למשלוח דואר]",
  email: "[privacy@example.co.il]",
  // רכז/ת נגישות, required by the accessibility regulations.
  accessibilityName: "[שם רכז/ת הנגישות]",
  accessibilityPhone: "[טלפון]",
  accessibilityEmail: "[accessibility@example.co.il]",
  // The court the terms point to.
  court: "[תל אביב-יפו]",
} as const;

// The date each page was last changed. Update it with every change to that page's text.
export const UPDATED = {
  privacy: "21 בנובמבר 2026",
  terms: "21 בנובמבר 2026",
  accessibility: "21 בנובמבר 2026",
} as const;

export function isDraft(): boolean {
  return Object.values(OPERATOR).some((value) => value.startsWith("["));
}
