export function israeliMobile(raw: string): string | null {
  const digits = raw.replace(/\D/g, "");
  if (!digits) return null;
  if (digits.startsWith("972") && digits.length >= 11) return digits;
  if (digits.startsWith("0") && digits.length >= 10) return `972${digits.slice(1)}`;
  return null;
}

export function signingMessage(clientName: string, signingUrl: string) {
  const name = clientName.trim() || "לקוח";
  return `שלום ${name}, טופס בל/6101 (דיווח רב-שנתי לביטוח לאומי) מוכן לבדיקה ולחתימה דיגיטלית בקישור המאובטח: ${signingUrl}`;
}

export function signedMessage(clientName: string, verificationId: string, link: string | null) {
  const name = clientName.trim() || "לקוח";
  const proof = link ? ` ניתן לצפות באישור בקישור: ${link}` : "";
  return `שלום ${name}, הטופס נחתם דיגיטלית. מזהה אימות: ${verificationId}.${proof}`;
}

export function whatsAppUrl(phone: string, text: string) {
  return `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
}

export function mailUrl(email: string, subject: string, body: string) {
  return `mailto:${email.trim()}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

export function archiveFilename(clientName: string) {
  const cleaned = clientName.replace(/[\\/:*?"<>|]+/g, " ").trim() || "case";
  return `case_${cleaned}_archive.zip`;
}
