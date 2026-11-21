import type { Metadata } from "next";

import { PortalViewScreen } from "@/components/portal-view";

export const metadata: Metadata = {
  title: "חתימה על מסמך — DocFlow",
};

export default async function SignPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <PortalViewScreen token={token} />;
}
