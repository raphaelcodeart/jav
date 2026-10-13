import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "jav_session";
const PROTECTED_PREFIXES = ["/customer", "/promoter", "/admin"];

export function proxy(request: NextRequest) {
  // Shopify apre l'URL dell'app (la home) con ?shop=&hmac= quando si installa
  // l'app sul negozio: quella richiesta va al flusso di installazione.
  const { pathname, searchParams } = request.nextUrl;
  if (pathname === "/" && searchParams.has("shop") && searchParams.has("hmac")) {
    const target = new URL(`/api/shopify/oauth/install${request.nextUrl.search}`, request.url);
    return NextResponse.redirect(target);
  }
  const isProtected = PROTECTED_PREFIXES.some((p) => request.nextUrl.pathname.startsWith(p));
  if (!isProtected) return NextResponse.next();

  const hasSession = request.cookies.has(SESSION_COOKIE);
  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    // Session 88: dopo il login si torna dove si stava andando -- il link
    // «paga la tua pratica» che il promoter manda al cliente deve portarlo
    // alla pratica, non alla home della sua area.
    loginUrl.searchParams.set("next", `${request.nextUrl.pathname}${request.nextUrl.search}`);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/customer/:path*", "/promoter/:path*", "/admin/:path*"],
};
