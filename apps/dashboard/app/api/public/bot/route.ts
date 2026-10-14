import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Pubblica: JAVBOT del sito. Inoltra e basta; l'API risponde solo con dati
 *  pubblici (apps/api/app/domains/javbot/public.py). L'indirizzo di chi
 *  scrive passa in X-Forwarded-For: il limite di frequenza dell'API è per
 *  IP, e senza questo conterebbe tutti i visitatori come uno solo (la
 *  dashboard). */
export async function POST(request: NextRequest) {
  const forwarded = request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip") ?? "";
  const apiRes = await fetch(`${API_INTERNAL_URL}/api/public-site/bot`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(forwarded ? { "X-Forwarded-For": forwarded } : {}) },
    body: await request.text(),
    cache: "no-store",
  });
  return new NextResponse(await apiRes.text(), {
    status: apiRes.status,
    headers: { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" },
  });
}
