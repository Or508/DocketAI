const NO_STORE = { "Cache-Control": "no-store" };

export function notFound(): Response {
  return Response.json({ detail: "לא נמצא חותם." }, { status: 404, headers: NO_STORE });
}

/** Pass a public verification lookup to the API. `path` is already validated by the caller. */
export async function forwardVerify(path: string): Promise<Response> {
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  try {
    const upstream = await fetch(`${base}/verify/${path}`, { cache: "no-store" });
    const body = await upstream.text();
    return new Response(body, {
      status: upstream.status,
      headers: { ...NO_STORE, "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return Response.json({ detail: "לא ניתן להגיע לשירות האימות." }, { status: 502, headers: NO_STORE });
  }
}
