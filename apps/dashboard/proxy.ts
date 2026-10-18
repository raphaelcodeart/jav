import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "jav_session";
const PROTECTED_PREFIXES = ["/customer", "/promoter", "/admin", "/staff", "/club", "/atleta", "/escola"];

export function proxy(request: NextRequest) {
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
  matcher: ["/customer/:path*", "/promoter/:path*", "/admin/:path*", "/staff/:path*", "/club/:path*", "/atleta/:path*", "/escola/:path*"],
};
