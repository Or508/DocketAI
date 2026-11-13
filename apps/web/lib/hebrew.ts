import type { FillStatus } from "@docketai/shared-types";

import { ApiError } from "@/lib/api";

const HEBREW = /[\u0590-\u05FF]/;

export const FILL_STATUS_LABEL: Record<FillStatus, string> = {
  ok: "נכתב בטופס",
  overflow: "חורג מהתיבה",
  mismatch: "אין תיבה תואמת",
  skipped_prefilled: "התיבה כבר מלאה",
  comb_unsupported: "תיבות הספרות לא נתמכות",
  awaiting_value: "ממתין לערך",
};

export const PHONE_BOXES_NOTE = "בבל/6101 הטלפון נכנס לתיבות ספרות: בדיוק 10 ספרות, למשל 0501234567, בלי מקף.";

export function hebrewOfficeError(error: unknown): string {
  if (!(error instanceof ApiError)) return "הפעולה נכשלה.";
  return hebrewDetail(error.status, error.message);
}

export function hebrewDetail(status: number, detail: string): string {
  const text = detail.trim();
  if (status === 422 || /could not be written/i.test(text)) {
    return "הערך לא נכנס לתיבה בטופס. בטלפון נייד נדרשות בדיוק 10 ספרות.";
  }
  if (/only a pdf with form fields/i.test(text)) {
    return "אפשר לסמן כטופס רק קובץ PDF שיש בו שדות למילוי.";
  }
  if (/mark exactly one uploaded form/i.test(text)) {
    return "יש לסמן בדיוק טופס אחד למילוי וחתימה.";
  }
  if (/already signed/i.test(text)) return "אי אפשר לשנות קבצים בתיק שכבר נחתם.";
  if (/not a form/i.test(text)) return "הקובץ הזה אינו הטופס למילוי.";
  if (/no place on the form/i.test(text)) return "לפרטים האלה אין מקום על הטופס.";
  if (/needs 9 to 15 digits/i.test(text)) return "טלפון נייד חייב להיות בדיוק 10 ספרות כדי להיכנס לתיבות.";
  if (/too short/i.test(text)) return "הפרט קצר מדי.";
  if (/too long/i.test(text)) return "הפרט ארוך מדי.";
  if (/not a valid 9-digit/i.test(text)) return "מספר הזהות אינו תקין.";
  if (/enter a value/i.test(text)) return "יש להזין ערך בשדה.";
  if (/unknown field/i.test(text)) return "השדה הזה אינו פרט אישי בטופס.";
  if (/this document is still processing/i.test(text)) return "אי אפשר להסיר או להעביר את הקובץ בזמן שהוא עדיין נקרא.";
  if (/still processing/i.test(text)) return "הקבצים עדיין נקראים. אפשר להעלות למגירה בלי לחכות.";
  if (/needs review/i.test(text)) return "עדיין יש מסמך שממתין לסיווג או לסימון כטופס.";
  if (/missing required documents/i.test(text)) return "חסרים מסמכי מקור נדרשים.";
  if (/still need:/i.test(text)) return "עדיין חסרים פרטים אישיים.";
  if (/failed processing/i.test(text)) return "עיבוד התיק נכשל.";
  if (/upload the document bundle/i.test(text)) return "יש להעלות את המסמכים לפני החתימה.";
  if (/form changed|review it again/i.test(text)) {
    return "המשרד עדכן פרט בטופס בהסכמתך – אנא עבור על הטופס המעודכן לפני החתימה";
  }
  if (status === 400) return "הפרט לא נשמר. בדקו את הערך ונסו שוב.";
  if (status === 409) return "אי אפשר להמשיך כל עוד התיק לא מוכן לחתימה.";
  if (HEBREW.test(text)) return text;
  return "הפעולה נכשלה.";
}

export function hebrewUploadReason(reason: string): string {
  const text = reason.trim();
  if (/HEIC/i.test(text)) return "תמונת HEIC לא נתמכת. שמרו אותה כ־JPEG או PNG והעלו שוב.";
  if (/not a PDF or a supported image/i.test(text)) return "הקובץ אינו PDF או תמונה נתמכת (PNG, JPEG, WEBP, GIF, BMP, TIFF).";
  if (/could not be read as an image/i.test(text)) return "לא ניתן לקרוא את הקובץ כתמונה.";
  if (/is empty/i.test(text)) return "הקובץ ריק.";
  if (/exceeds/i.test(text)) return "הקובץ גדול מדי.";
  if (HEBREW.test(text)) return text;
  return hebrewDetail(400, text);
}
