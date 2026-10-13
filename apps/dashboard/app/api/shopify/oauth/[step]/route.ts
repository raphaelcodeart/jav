import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Installazione dell'app Shopify (Session 70): Shopify chiama questi due
 * indirizzi pubblici (install = URL dell'app, callback = URL di
 * reindirizzamento consentito). Tutto il lavoro -- firma hmac, state, scambio
 * del code col Client secret -- lo fa il backend; qui si inoltra la query e
 * si restituisce il redirect che il backend decide. */
export async function GET(request: NextRequest, { params }: { params: Promise<{ step: string }> }) {
  const { step } = await params;
  if (step !== "install" && step !== "callback") {
    return new NextResponse("Not found", { status: 404 });
  }
  const apiRes = await fetch(`${API_INTERNAL_URL}/api/shopify/oauth/${step}${request.nextUrl.search}`, {
    redirect: "manual",
    cache: "no-store",
  });
  const location = apiRes.headers.get("location");
  if (location) return NextResponse.redirect(location, 302);
  return new NextResponse(await apiRes.text(), { status: apiRes.status });
}
