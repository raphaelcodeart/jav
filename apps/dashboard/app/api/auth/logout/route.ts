import { NextResponse } from "next/server";
import { clearSession } from "@/lib/session";
import { STAFF_CLUB_COOKIE } from "@/lib/club-cookie";

export async function POST() {
  await clearSession();
  const res = NextResponse.json({ ok: true });
  // Il club scelto nell'area del treinador non deve passare a chi entra dopo
  // dallo stesso browser.
  res.cookies.set(STAFF_CLUB_COOKIE, "", { path: "/", maxAge: 0, sameSite: "lax" });
  return res;
}
