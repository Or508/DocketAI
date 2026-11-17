import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { OFFICE_COOKIE } from "@/lib/server/office-session";

import { SettingsScreen } from "./settings-screen";

export const metadata: Metadata = {
  title: "הגדרות משרד, מיתוג ותבניות תקשורת",
  description: "שם המשרד, פרטי קשר, תבניות וואטסאפ ואימייל, והעדפות פתיחת תיק.",
};

export default async function SettingsPage() {
  if (!(await cookies()).get(OFFICE_COOKIE)?.value) redirect("/login?next=%2Fsettings");
  return <SettingsScreen />;
}
