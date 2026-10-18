import { NextRequest, NextResponse } from "next/server";
import { clearSession, getSession, refreshSession, type Session } from "@/lib/session";
import { CLUB_COOKIE, STAFF_CLUB_COOKIE } from "@/lib/club-cookie";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Il club in cui lo staff della piattaforma è "entrato" (pannello Club):
 * l'API lo legge da questa intestazione (club/scope.py). Per un account di
 * un club l'API la ignora, quindi inoltrarla sempre non apre niente. */
function clubHeader(request: NextRequest): Record<string, string> {
  const club = request.cookies.get(CLUB_COOKIE)?.value;
  // Il club scelto dal treinador di più club: l'API lo guarda solo sulle
  // rotte del treinador e lo controlla contro le sue appartenenze.
  const staffClub = request.cookies.get(STAFF_CLUB_COOKIE)?.value;
  return {
    ...(club ? { "X-Jav-Club": club } : {}),
    ...(staffClub ? { "X-Jav-Staff-Club": staffClub } : {}),
  };
}

/** True only for this app's own "your access token is bad/expired" 401 --
 * never for a permission (403) or a business-rule 401 from elsewhere -- so a
 * refresh is attempted exactly when it can actually help. See core/deps.py's
 * get_current_user for where these three strings come from. */
async function isExpiredTokenResponse(apiRes: Response): Promise<boolean> {
  if (apiRes.status !== 401) return false;
  const body = await apiRes.clone().text().catch(() => "");
  return /Invalid or expired token|Missing bearer token|Wrong token type/.test(body);
}

/** The session is over for good: no cookie, or the refresh token itself
 * refused. The cookie is dropped and the answer says so in a header the
 * browser acts on (app/providers.tsx::SessionExpiryGuard sends the user to
 * the login page) -- before, each button just printed "Sessione scaduta"
 * under itself and left a dead page on screen (Session 85). */
async function sessionExpired(): Promise<NextResponse> {
  await clearSession();
  return NextResponse.json(
    { detail: "Invalid or expired token" },
    { status: 401, headers: { "X-Session-Expired": "1" } }
  );
}

/**
 * Same-origin proxy for client components that need TanStack Query's
 * client-side caching/refetching. The browser only ever talks to this route;
 * the access token is attached here, server-side, and never reaches client JS.
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const session = await getSession();
  if (!session) return sessionExpired();

  const { path } = await params;
  const search = request.nextUrl.search;
  const url = `${API_INTERNAL_URL}/api/${path.join("/")}${search}`;

  let apiRes = await fetch(url, {
    headers: { Authorization: `Bearer ${session.accessToken}`, ...clubHeader(request) },
    cache: "no-store",
  });

  if (await isExpiredTokenResponse(apiRes)) {
    const refreshed: Session | null = await refreshSession(session);
    if (!refreshed) return sessionExpired();
    apiRes = await fetch(url, {
      headers: { Authorization: `Bearer ${refreshed.accessToken}`, ...clubHeader(request) },
      cache: "no-store",
    });
    if (await isExpiredTokenResponse(apiRes)) return sessionExpired();
  }

  // arrayBuffer(), non text(): da questa rotta passano anche download
  // binari (lo zip del fascicolo contratto, GET /contracts/{id}/dossier.zip),
  // e decodificarli come testo li distrugge -- ogni sequenza non valida in
  // UTF-8 diventa U+FFFD e l'archivio arriva corrotto. Per il JSON non
  // cambia niente: sono gli stessi byte.
  const body = await apiRes.arrayBuffer();
  const headers = new Headers({
    "Content-Type": apiRes.headers.get("content-type") ?? "application/json",
  });
  // Il nome con cui il file viene salvato vive solo qui dentro: senza
  // inoltrare questo header il browser lo inventa dal percorso.
  const disposition = apiRes.headers.get("content-disposition");
  if (disposition) headers.set("Content-Disposition", disposition);

  if (apiRes.status === 204 || apiRes.status === 205 || apiRes.status === 304) {
    return new NextResponse(null, { status: apiRes.status, headers });
  }
  return new NextResponse(body, { status: apiRes.status, headers });
}

/** Shared by every body-carrying method (POST/PATCH/PUT/DELETE) -- forwarding
 * logic is identical regardless of verb, only the HTTP method sent upstream
 * differs. Multipart (file uploads, e.g. photo-upload.tsx, document-
 * upload.tsx) must be forwarded as raw bytes with the ORIGINAL content-type
 * (including its boundary) -- reading it as text() and re-sending as
 * application/json would corrupt the binary body and lose the boundary
 * entirely. */
async function proxyWithBody(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
  method: string
) {
  const session = await getSession();
  if (!session) return sessionExpired();

  const { path } = await params;
  const search = request.nextUrl.search;
  const requestContentType = request.headers.get("content-type") ?? "";
  const isMultipart = requestContentType.startsWith("multipart/form-data");
  // Read the incoming body exactly once -- request.text()/arrayBuffer() can't
  // be replayed, but a possible retry-after-refresh below needs the same
  // bytes sent twice.
  const requestBody = isMultipart ? await request.arrayBuffer() : await request.text().catch(() => undefined);

  const url = `${API_INTERNAL_URL}/api/${path.join("/")}${search}`;
  const upstreamHeaders = (token: string) => ({
    Authorization: `Bearer ${token}`,
    ...clubHeader(request),
    "Content-Type": isMultipart ? requestContentType : "application/json",
  });

  let apiRes = await fetch(url, {
    method,
    headers: upstreamHeaders(session.accessToken),
    body: requestBody,
    cache: "no-store",
  });

  if (await isExpiredTokenResponse(apiRes)) {
    const refreshed: Session | null = await refreshSession(session);
    if (!refreshed) return sessionExpired();
    apiRes = await fetch(url, {
      method,
      headers: upstreamHeaders(refreshed.accessToken),
      body: requestBody,
      cache: "no-store",
    });
    if (await isExpiredTokenResponse(apiRes)) return sessionExpired();
  }

  const body = await apiRes.text();
  const headers = { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" };
  // A 204/205/304 response must not carry a body -- the Response constructor
  // throws "Response with null body status cannot have body" even for an
  // empty string, which silently 500s every no-content response (e.g.
  // DELETE /support/tickets/{id}) despite the upstream call having already
  // succeeded. Confirmed live: a ticket delete removed the row but the
  // proxy call surfaced as a failure until this branch was added.
  if (apiRes.status === 204 || apiRes.status === 205 || apiRes.status === 304) {
    return new NextResponse(null, { status: apiRes.status, headers });
  }
  return new NextResponse(body, { status: apiRes.status, headers });
}

export async function POST(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody(request, ctx, "POST");
}

// Real bug, fixed here: PATCH had never been implemented on this route at
// all (only GET/POST existed) -- every "save changes" edit form that PATCHes
// through this proxy (customer edit, promoter edit, product edit, contract
// IBAN, holder data, document review, ...) was silently 405ing since
// the day each was built. Confirmed live before this fix.
export async function PATCH(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody(request, ctx, "PATCH");
}

export async function PUT(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody(request, ctx, "PUT");
}

export async function DELETE(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody(request, ctx, "DELETE");
}
