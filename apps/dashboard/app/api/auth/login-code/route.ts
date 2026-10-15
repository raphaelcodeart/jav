import { NextRequest, NextResponse } from "next/server";
import { friendlyApiError } from "@/lib/api-error";
import { decodeOrganizationIdFromAccessToken, decodeRolesFromAccessToken, setSession } from "@/lib/session";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

// Il QR dell'atleta (auth/router.py::login_with_code): come /api/auth/login,
// ma con il codice del link al posto di nome utente e password.
export async function POST(request: NextRequest) {
  const { code } = (await request.json()) as { code: string };
  const apiRes = await fetch(`${API_INTERNAL_URL}/api/auth/login-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  if (!apiRes.ok) {
    return NextResponse.json({ error: await friendlyApiError(apiRes, "Questo QR non vale più.") }, { status: apiRes.status });
  }
  const refreshToken = /jav_refresh_token=([^;]+)/.exec(apiRes.headers.get("set-cookie") ?? "")?.[1] ?? "";
  const { access_token: accessToken } = (await apiRes.json()) as { access_token: string };
  await setSession({ accessToken, refreshToken, organizationId: decodeOrganizationIdFromAccessToken(accessToken), email: "" });
  return NextResponse.json({ ok: true, roles: decodeRolesFromAccessToken(accessToken) });
}
