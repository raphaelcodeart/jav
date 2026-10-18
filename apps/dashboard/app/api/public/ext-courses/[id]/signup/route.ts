import { NextRequest } from "next/server";
import { forwardPublicPost } from "@/lib/public-forward";

/** Pubblica: l'iscrizione a un corso esterno di chi non ha un account
 *  (extcourses/router.py::public_signup). 409: l'email ha già un account. */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return forwardPublicPost(request, `/public/ext-courses/${encodeURIComponent(id)}/signup`);
}
