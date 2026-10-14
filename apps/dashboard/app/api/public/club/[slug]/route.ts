import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Pubblica: il nome del club a cui porta un link di registrazione /c/<slug>. */
export async function GET(_request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const apiRes = await fetch(`${API_INTERNAL_URL}/api/clubs/public/${encodeURIComponent(slug)}`, { cache: "no-store" });
  return new NextResponse(await apiRes.text(), {
    status: apiRes.status,
    headers: { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" },
  });
}
