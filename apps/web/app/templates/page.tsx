import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { OFFICE_COOKIE } from "@/lib/server/office-session";

import { TemplatesScreen } from "./templates-screen";

export const metadata: Metadata = {
  title: "קטלוג טפסים ותבניות אוטומציה",
  description: "הטפסים שהמשרד ממלא, המגירות שכל טופס דורש והשדות שמתמלאים מתוך המסמכים.",
};

export default async function TemplatesPage() {
  // The office catalog: the same session as the cabinet.
  if (!(await cookies()).get(OFFICE_COOKIE)?.value) redirect("/login?next=%2Ftemplates");
  return <TemplatesScreen />;
}
