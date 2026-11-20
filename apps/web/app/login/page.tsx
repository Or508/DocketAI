import Link from "next/link";

import { LoginForm } from "@/components/login-form";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const params = await searchParams;
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-5">
      <LoginForm nextPath={params.next ?? null} />
      <p className="mt-4 text-center text-sm">
        <Link href="/how-it-works" className="text-mist underline-offset-2 hover:text-tide hover:underline">
          איך זה עובד?
        </Link>
      </p>
    </main>
  );
}
