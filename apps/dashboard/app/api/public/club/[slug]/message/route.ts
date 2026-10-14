import { NextRequest } from "next/server";
import { forwardPublicPost } from "@/lib/public-forward";

/** Pubblica: "Envie uma mensagem ao clube" dalla pagina del club
 *  (apps/api/app/domains/club/contact.py). */
export async function POST(request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return forwardPublicPost(request, `/public-site/clubs/${encodeURIComponent(slug)}/message`);
}
