import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Pubblica: il microfono di JAVBOT sul sito. Inoltra l'audio così com'è
 *  (multipart con il suo boundary) all'API, che lo trascrive sul nostro
 *  server senza salvarlo (apps/api/app/domains/javbot/voice.py). L'IP in
 *  X-Forwarded-For: il limite di frequenza è per visitatore. */
export async function POST(request: NextRequest) {
  const forwarded = request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip") ?? "";
  const apiRes = await fetch(`${API_INTERNAL_URL}/api/public-site/bot/transcribe`, {
    method: "POST",
    headers: {
      "Content-Type": request.headers.get("content-type") ?? "application/octet-stream",
      ...(forwarded ? { "X-Forwarded-For": forwarded } : {}),
    },
    body: await request.arrayBuffer(),
    cache: "no-store",
  });
  return new NextResponse(await apiRes.text(), {
    status: apiRes.status,
    headers: { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" },
  });
}
