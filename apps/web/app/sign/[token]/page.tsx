import { PortalViewScreen } from "@/components/portal-view";

export default async function SignPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <PortalViewScreen token={token} />;
}
