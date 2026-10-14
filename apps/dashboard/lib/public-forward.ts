import "server-only";
import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Inoltra un POST pubblico all'API così com'è. L'indirizzo di chi scrive
 *  passa in X-Forwarded-For (il limite di frequenza dell'API è per IP: senza,
 *  conterebbe tutti i visitatori come uno solo, la dashboard) e lo
 *  User-Agent per riconoscere un robot nella casella dei messaggi. */
export async function forwardPublicPost(request: NextRequest, path: string): Promise<NextResponse> {
  const forwarded = request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip") ?? "";
  const userAgent = request.headers.get("user-agent") ?? "";
  const apiRes = await fetch(`${API_INTERNAL_URL}/api${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(forwarded ? { "X-Forwarded-For": forwarded } : {}),
      ...(userAgent ? { "User-Agent": userAgent.slice(0, 200) } : {}),
    },
    body: await request.text(),
    cache: "no-store",
  });
  return new NextResponse(await apiRes.text(), {
    status: apiRes.status,
    headers: { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" },
  });
}
