import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/** Which build the server is running (Session 85), read from disk on every
 *  call -- not baked into the bundle, or it could never differ from the
 *  page asking. components/new-version-banner.tsx compares it with the one
 *  the page was loaded from. */
export async function GET() {
  const buildId = await readFile(path.join(process.cwd(), ".next", "BUILD_ID"), "utf8")
    .then((s) => s.trim())
    .catch(() => "dev");
  return NextResponse.json({ build_id: buildId }, { headers: { "Cache-Control": "no-store" } });
}
