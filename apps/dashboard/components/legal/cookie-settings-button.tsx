"use client";

import { reopenCookieBanner } from "@/lib/cookie-consent";

/** «Gerir cookies»: riapre il banner della scelta. */
export function CookieSettingsButton({ variant = "button" }: { variant?: "button" | "link" }) {
  return variant === "link" ? (
    <button type="button" onClick={reopenCookieBanner} className="cursor-pointer hover:text-white">Gerir cookies</button>
  ) : (
    <button type="button" onClick={reopenCookieBanner}
      className="h-11 cursor-pointer rounded-2xl bg-brand-600 px-5 text-sm font-semibold text-white hover:bg-brand-700">🍪 Gerir cookies</button>
  );
}
