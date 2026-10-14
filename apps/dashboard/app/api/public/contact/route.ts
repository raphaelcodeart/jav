import { NextRequest } from "next/server";
import { forwardPublicPost } from "@/lib/public-forward";

/** Pubblica: il modulo di /contactos, un messaggio a JudoArteVida
 *  (apps/api/app/domains/club/contact.py). */
export async function POST(request: NextRequest) {
  return forwardPublicPost(request, "/public-site/contact");
}
