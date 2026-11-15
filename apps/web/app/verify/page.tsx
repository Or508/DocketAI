import type { Metadata } from "next";

import { VerifyScreen } from "./verify-screen";

export const metadata: Metadata = {
  title: "אימות חותם קריפטוגרפי ומסמכים חתומים",
  description: "בדיקה ציבורית של חותם החתימה הדיגיטלית ושל שלמות הקובץ החתום.",
  robots: { index: false },
};

export default async function VerifyPage({
  searchParams,
}: {
  searchParams: Promise<{ code?: string | string[] }>;
}) {
  const params = await searchParams;
  const raw = Array.isArray(params.code) ? params.code[0] : params.code;
  return <VerifyScreen initialCode={(raw ?? "").trim().toUpperCase().slice(0, 32)} />;
}
