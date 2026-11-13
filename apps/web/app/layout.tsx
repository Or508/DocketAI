import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ארון תיוק ובקרת מסמכים",
  description: "תיק לקוח, מילוי טופס, בדיקת פרטים אישיים וחתימה דיגיטלית.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
