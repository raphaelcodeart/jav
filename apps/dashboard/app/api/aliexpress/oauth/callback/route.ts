import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Callback pubblico dell'app AliExpress (Session 71): è l'indirizzo
 * registrato nel portale openservice.aliexpress.com, quindi non può più
 * cambiare. Il codice di autorizzazione lo scambia il backend, l'unico che
 * conosce l'App Secret.
 *
 * Due percorsi perché il collegamento è nato dentro il plugin
 * imported-products ed è passato al dominio aliexpress: si prova il nuovo
 * e, se non risponde, si ricade sul vecchio. Così l'indirizzo registrato su
 * AliExpress resta valido in entrambi i casi. */
const BACKEND_PATHS = [
  "/api/aliexpress/oauth/callback",
  "/api/imported-products/oauth/aliexpress/callback",
];

export async function GET(request: NextRequest) {
  let apiRes: Response | null = null;
  for (const path of BACKEND_PATHS) {
    apiRes = await fetch(`${API_INTERNAL_URL}${path}${request.nextUrl.search}`, {
      redirect: "manual",
      cache: "no-store",
    });
    if (apiRes.status !== 404) break;
  }
  if (!apiRes) return new NextResponse("Not found", { status: 404 });
  const location = apiRes.headers.get("location");
  if (location) return NextResponse.redirect(location, 302);
  return new NextResponse(await apiRes.text(), { status: apiRes.status });
}
