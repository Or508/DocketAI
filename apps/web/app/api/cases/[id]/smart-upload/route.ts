import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { OFFICE_COOKIE, officeCookieOptions, sameOrigin } from "@/lib/server/office-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_FILES = 10;
// Ten files of 25 MB each, plus the multipart framing.
const MAX_BODY_BYTES = 10 * 25 * 1024 * 1024 + 1024 * 1024;

type Context = { params: Promise<{ id: string }> };

/** Smart upload: a mixed drop of files, each filed by the office service in its own drawer. */
export async function POST(request: Request, context: Context) {
  const { id } = await context.params;
  if (!UUID.test(id)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404, headers: NO_STORE });
  }
  const token = (await cookies()).get(OFFICE_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Sign in required.", code: "unauthenticated" }, { status: 401, headers: NO_STORE });
  }
  if (!sameOrigin(request)) {
    return NextResponse.json({ detail: "Forbidden", code: "forbidden" }, { status: 403, headers: NO_STORE });
  }
  if (Number(request.headers.get("content-length") ?? "0") > MAX_BODY_BYTES) {
    return NextResponse.json({ detail: "הקבצים גדולים מדי." }, { status: 413, headers: NO_STORE });
  }

  let incoming: FormData;
  try {
    incoming = await request.formData();
  } catch {
    return NextResponse.json({ detail: "לא התקבלו קבצים." }, { status: 400, headers: NO_STORE });
  }
  // Only the files go upstream; any other form field is dropped here.
  const files = incoming.getAll("files").filter((item): item is File => item instanceof File);
  if (files.length === 0) {
    return NextResponse.json({ detail: "בחרו לפחות קובץ אחד." }, { status: 400, headers: NO_STORE });
  }
  if (files.length > MAX_FILES) {
    return NextResponse.json({ detail: `אפשר להעלות עד ${MAX_FILES} קבצים בבת אחת.` }, { status: 400, headers: NO_STORE });
  }
  const outgoing = new FormData();
  for (const file of files) outgoing.append("files", file, file.name);

  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  try {
    const upstream = await fetch(`${base}/cases/${id}/smart-upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: outgoing,
      cache: "no-store",
    });
    const response = new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { ...NO_STORE, "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
    if (upstream.status === 401) response.cookies.set(OFFICE_COOKIE, "", officeCookieOptions(0));
    return response;
  } catch {
    return NextResponse.json({ detail: "לא ניתן להגיע לשירות המשרד." }, { status: 502, headers: NO_STORE });
  }
}
