import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { OFFICE_COOKIE } from "@/lib/server/office-session";

import { ClientsScreen } from "./clients-screen";

export const metadata: Metadata = {
  title: "ספר לקוחות וכספת מסמכים חכמה",
  description: "כל לקוחות המשרד, הפרטים המאומתים שלהם, התיקים שלהם ופתיחת תיק חדש מהמסמכים שכבר נמסרו.",
};

export default async function ClientsPage() {
  // The office client book: the same session as the cabinet.
  if (!(await cookies()).get(OFFICE_COOKIE)?.value) redirect("/login?next=%2Fclients");
  return <ClientsScreen />;
}
