import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/**
 * Public (no session) resolver for a shared referral link -- validates the
 * promoter code exists and is active, and forwards the attribution cookie the
 * backend sets (read later if/when this visitor registers).
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  // Optional: without it the API resolves the installation's only club.
  const organizationId = request.nextUrl.searchParams.get("org");
  const query = organizationId ? `?organization_id=${encodeURIComponent(organizationId)}` : "";

  const apiRes = await fetch(`${API_INTERNAL_URL}/api/r/${encodeURIComponent(code)}${query}`, {
    cache: "no-store",
  });

  const body = await apiRes.text();
  const response = new NextResponse(body, {
    status: apiRes.status,
    headers: { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" },
  });
  const setCookieHeader = apiRes.headers.get("set-cookie");
  if (setCookieHeader) {
    response.headers.set("set-cookie", setCookieHeader);
  }
  return response;
}
