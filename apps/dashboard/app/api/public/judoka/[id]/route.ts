import { NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Pubblica: la scheda di un judoca della classifica, per il popup di
 *  /ranking (club/site.py::ranking_card). Solo lettura, niente sessione:
 *  l'API decide che cosa si può mostrare (con o senza consenso). */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
    return NextResponse.json({ detail: "Judoca non trovato." }, { status: 404 });
  }
  const res = await fetch(`${API_INTERNAL_URL}/api/public-site/ranking/judoka/${id}`, { cache: "no-store" });
  return new NextResponse(await res.text(), {
    status: res.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
