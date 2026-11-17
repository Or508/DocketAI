import type { Metadata } from "next";
import { Heebo } from "next/font/google";
import "./globals.css";

// Served from this app at build time: no page makes a request to Google.
const heebo = Heebo({
  subsets: ["hebrew", "latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ארון תיוק ובקרת מסמכים",
  description: "תיק לקוח, מילוי טופס, בדיקת פרטים אישיים וחתימה דיגיטלית.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl" className={heebo.variable}>
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
