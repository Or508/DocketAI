import { NextResponse } from "next/server";

import { clientIpHeaders } from "@/lib/server/client-ip";
import { sameOrigin } from "@/lib/server/office-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const TOKEN = /^[A-Za-z0-9_-]{20,128}$/;
const DOCUMENT_TYPE = /^[a-z0-9_]{1,64}$/;
const MAX_FILES = 5;
// Five files of 25 MB each, plus the multipart framing.
const MAX_BODY_BYTES = MAX_FILES * 25 * 1024 * 1024 + 1024 * 1024;

/**
 * Public: the client hands in one to five files through their intake link.
 * Only the files, and the drawer chosen for a single file, go upstream. No office session is sent.
 */
export async function POST(request: Request, context: { params: Promise<{ token: string }> }) {
  const { token } = await context.params;
  if (!TOKEN.test(token)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404, headers: NO_STORE });
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
  const files = [...incoming.getAll("files"), ...incoming.getAll("file")].filter(
    (item): item is File => item instanceof File,
  );
  if (files.length === 0) {
    return NextResponse.json({ detail: "בחרו לפחות קובץ אחד." }, { status: 400, headers: NO_STORE });
  }
  if (files.length > MAX_FILES) {
    return NextResponse.json({ detail: `אפשר להעלות עד ${MAX_FILES} קבצים בבת אחת.` }, { status: 400, headers: NO_STORE });
  }
  const outgoing = new FormData();
  for (const file of files) outgoing.append("files", file, file.name);
  const chosen = incoming.get("document_type");
  if (typeof chosen === "string" && chosen) {
    if (!DOCUMENT_TYPE.test(chosen) || files.length !== 1) {
      return NextResponse.json({ detail: "אפשר לבחור סוג מסמך לקובץ אחד בכל פעם." }, { status: 400, headers: NO_STORE });
    }
    outgoing.set("document_type", chosen);
  }

  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  try {
    const upstream = await fetch(`${base}/intake/${token}/upload`, {
      method: "POST",
      body: outgoing,
      headers: clientIpHeaders(request),
      cache: "no-store",
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { ...NO_STORE, "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "לא ניתן להגיע לשירות." }, { status: 502, headers: NO_STORE });
  }
}
