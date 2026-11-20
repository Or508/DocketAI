import type { Metadata } from "next";

import { HowItWorksScreen } from "./how-it-works-screen";

export const metadata: Metadata = {
  title: "איך DocketFlow עובד — מסמכים, טופס וחתימה בתיק אחד",
  description:
    "המשרד מקבל את המסמכים של הלקוח, המערכת מזהה מה חסר, ממלאת את הטופס מתוך המסמכים ושולחת לחתימה דיגיטלית עם תיעוד מלא. כולל הדגמה וקבצים לדוגמה.",
};

// Public: no office session is read or needed. Everything on this page is invented sample data.
export default function HowItWorksPage() {
  return <HowItWorksScreen />;
}
