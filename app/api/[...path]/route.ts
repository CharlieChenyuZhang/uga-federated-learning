import type { NextRequest } from "next/server";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const BACKEND = process.env.CAMPUS_API_URL || "http://127.0.0.1:8000";
const LIMIT = 2 * 1024 * 1024 + 16384;
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const origin = request.headers.get("origin");
  // Next dev can normalize nextUrl to localhost even when the browser uses 127.0.0.1.
  // Validate the actual Host against a fixed local allowlist before comparing origins.
  const host = request.headers.get("host");
  const allowedHosts = new Set(["127.0.0.1:3000", "localhost:3000"]);
  if (
    !host ||
    !allowedHosts.has(host) ||
    (origin && origin !== `http://${host}`)
  )
    return Response.json(
      { detail: "Cross-origin requests are not allowed." },
      { status: 403 },
    );
  if (request.headers.get("sec-fetch-site") === "cross-site")
    return Response.json(
      { detail: "Cross-site requests are not allowed." },
      { status: 403 },
    );
  const { path } = await context.params;
  const headers = new Headers();
  for (const name of ["content-type", "cookie"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  let body: Uint8Array | undefined;
  if (!["GET", "HEAD"].includes(request.method)) {
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (reader)
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > LIMIT) {
          await reader.cancel();
          return Response.json(
            { detail: "Use a file smaller than 2 MB." },
            { status: 413 },
          );
        }
        chunks.push(value);
      }
    body = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      body.set(chunk, offset);
      offset += chunk.length;
    }
  }
  try {
    const upstream = await fetch(
      `${BACKEND}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`,
      {
        method: request.method,
        headers,
        body: body as BodyInit | undefined,
        cache: "no-store",
        signal: AbortSignal.timeout(path[0] === "chat" ? 600000 : 30000),
      },
    );
    const outgoing = new Headers({
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const key of ["content-type", "set-cookie", "content-disposition"]) {
      const value = upstream.headers.get(key);
      if (value) outgoing.set(key, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: outgoing,
    });
  } catch {
    return Response.json(
      {
        detail:
          "The local training service is offline. Start it with ./scripts/dev.sh, then retry.",
      },
      { status: 503 },
    );
  }
}
export { proxy as GET, proxy as POST, proxy as PATCH, proxy as DELETE };
