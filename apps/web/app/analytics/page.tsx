import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { OFFICE_COOKIE } from "@/lib/server/office-session";

import { AnalyticsScreen } from "./analytics-screen";

export const metadata: Metadata = {
  title: "דוחות, מדדי ביצוע וייצוא לאקסל",
  description: "מדדי המשרד: תיקים לפי מצב וסוג תהליך, שיעור המילוי האוטומטי, זמן עד חתימה, וייצוא דוח תיקים.",
};

export default async function AnalyticsPage() {
  // Office numbers: the same session as the cabinet.
  if (!(await cookies()).get(OFFICE_COOKIE)?.value) redirect("/login?next=%2Fanalytics");
  return <AnalyticsScreen />;
}
