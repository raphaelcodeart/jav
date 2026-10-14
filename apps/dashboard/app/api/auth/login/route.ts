import { NextRequest, NextResponse } from "next/server";
import { friendlyApiError } from "@/lib/api-error";
import { decodeOrganizationIdFromAccessToken, decodeRolesFromAccessToken, setSession } from "@/lib/session";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

// auth/router.py::login: 401 wrong credentials (or a disabled account, told
// apart by its message), 423 locked after too many attempts, 429 rate limit.
const LOGIN_ERROR_CODES: Record<number, string> = { 401: "invalid", 423: "locked", 429: "rate" };

export async function POST(request: NextRequest) {
  const body = await request.json();
  // No organization id from the form: the API resolves it (one club per
  // installation) and returns it inside the access token.
  const { email, password } = body as { email: string; password: string };

  const apiRes = await fetch(`${API_INTERNAL_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!apiRes.ok) {
    // `code` lets the login page say it in the reader's language; `error`
    // stays the Italian sentence for anything without a code.
    const code = LOGIN_ERROR_CODES[apiRes.status];
    const message = await friendlyApiError(apiRes, "Accesso non riuscito. Riprova.");
    const disabled = message === "Questo account è stato disabilitato. Contatta l'amministratore.";
    return NextResponse.json({ error: message, code: disabled ? "disabled" : code }, { status: apiRes.status });
  }

  const setCookieHeader = apiRes.headers.get("set-cookie") ?? "";
  const refreshMatch = /jav_refresh_token=([^;]+)/.exec(setCookieHeader);
  const refreshToken = refreshMatch?.[1] ?? "";

  const { access_token: accessToken } = (await apiRes.json()) as { access_token: string };

  const organizationId = decodeOrganizationIdFromAccessToken(accessToken);
  await setSession({ accessToken, refreshToken, organizationId, email });

  // The access token already carries the roles the API assigned at login
  // (see auth/service.py:authenticate); read them back out of its payload so
  // the client can route to the right dashboard instead of guessing from the
  // email address (which broke for real customers whose address doesn't
  // happen to contain the word "customer").
  const roles = decodeRolesFromAccessToken(accessToken);

  return NextResponse.json({ ok: true, roles });
}
