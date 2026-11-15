import { forwardVerify, notFound } from "../forward";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CODE = /^DV-[0-9A-F]{12}$/;
const SHA256 = /^[0-9a-f]{64}$/;

export async function GET(request: Request, context: { params: Promise<{ verificationId: string }> }) {
  const { verificationId } = await context.params;
  const code = verificationId.trim().toUpperCase();
  if (!CODE.test(code)) return notFound();
  const digest = (new URL(request.url).searchParams.get("sha256") ?? "").trim().toLowerCase();
  if (digest && !SHA256.test(digest)) {
    return Response.json(
      { detail: "טביעת האצבע אינה תקינה." },
      { status: 422, headers: { "Cache-Control": "no-store" } },
    );
  }
  return forwardVerify(digest ? `${code}?sha256=${digest}` : code);
}
