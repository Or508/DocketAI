import type { Metadata } from "next";

import { PasswordLinkScreen } from "@/components/password-link-screen";

export const metadata: Metadata = {
  referrer: "no-referrer",
};

export default async function JoinPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <PasswordLinkScreen token={token} purpose="invite" />;
}
