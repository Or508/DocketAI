import { forwardAnalytics } from "../forward";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return forwardAnalytics("export.csv");
}
