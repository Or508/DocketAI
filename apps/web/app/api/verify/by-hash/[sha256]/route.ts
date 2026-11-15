import { forwardVerify, notFound } from "../../forward";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SHA256 = /^[0-9a-f]{64}$/;

export async function GET(_request: Request, context: { params: Promise<{ sha256: string }> }) {
  const { sha256 } = await context.params;
  const digest = sha256.trim().toLowerCase();
  if (!SHA256.test(digest)) return notFound();
  return forwardVerify(`by-hash/${digest}`);
}
