import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Pubblica: la registrazione di una famiglia dal link del suo club. Inoltra
 *  e basta, ogni controllo lo fa l'API (auth/service.py::register_family). */
export async function POST(request: NextRequest) {
  const apiRes = await fetch(`${API_INTERNAL_URL}/api/auth/register-family`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
  return new NextResponse(await apiRes.text(), {
    status: apiRes.status,
    headers: { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" },
  });
}
