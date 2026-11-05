import { CaseWorkspaceView } from "@/components/case-workspace";

export default async function CasePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <CaseWorkspaceView caseId={id} />;
}
