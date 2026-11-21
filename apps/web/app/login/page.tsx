import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "כניסה למשרד — DocFlow",
};

import { LegalFooter } from "@/app/(legal)/legal-footer";
import { LoginForm } from "@/components/login-form";

import { DemoLink } from "./demo-link";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const params = await searchParams;
  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-5">
        <LoginForm nextPath={params.next ?? null} />
        <p className="mt-4 text-center text-sm">
          <Link href="/how-it-works" className="text-mist underline-offset-2 hover:text-tide hover:underline">
            איך זה עובד?
          </Link>
        </p>
        <DemoLink />
      </main>
      <LegalFooter frame="max-w-md px-5" />
    </div>
  );
}
