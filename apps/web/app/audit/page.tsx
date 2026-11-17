import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { OFFICE_COOKIE } from "@/lib/server/office-session";

import { AuditScreen } from "./audit-screen";

export const metadata: Metadata = {
  title: "יומן אבטחה, ציות ובקרת פעולות משרדית",
  description: "כל הפעולות שנעשו בתיקי המשרד: חתימות, העלאות, קישורי חתימה שבוטלו ושימוש חוזר במסמכים.",
};

export default async function AuditPage() {
  // The office audit trail: the same session as the cabinet.
  if (!(await cookies()).get(OFFICE_COOKIE)?.value) redirect("/login?next=%2Faudit");
  return <AuditScreen />;
}
