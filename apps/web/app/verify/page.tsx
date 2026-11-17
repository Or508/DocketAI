import type { Metadata } from "next";
import { cookies } from "next/headers";

import { OFFICE_COOKIE } from "@/lib/server/office-session";

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
  // The office reaches this page from its own bar and keeps it; a client or an outside party
  // sees only the public header. The cookie decides which header, never what the check shows.
  const office = Boolean((await cookies()).get(OFFICE_COOKIE)?.value);
  return <VerifyScreen initialCode={(raw ?? "").trim().toUpperCase().slice(0, 32)} office={office} />;
}
