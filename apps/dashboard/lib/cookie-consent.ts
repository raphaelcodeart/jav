"use client";

import { useSyncExternalStore } from "react";

/** La scelta sui cookie (docs/legal.md, «Cookie»): `all` = anche i contenuti
 *  di terzi (video YouTube e Vimeo, miniature), `essential` = solo i cookie
 *  tecnici del sito (sessione, lingua, club). Si ricorda 6 mesi, poi si chiede
 *  di nuovo; senza scelta valgono solo gli essenziali. */
export type CookieChoice = "all" | "essential";
export const CONSENT_COOKIE = "jav_cookies";
const MAX_AGE = 60 * 60 * 24 * 182;
const EVENT = "jav-cookie-consent";

function read(): CookieChoice | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(/(?:^|;\s*)jav_cookies=(all|essential)/);
  return (m?.[1] as CookieChoice | undefined) ?? null;
}

export function setCookieChoice(choice: CookieChoice | null) {
  document.cookie = choice
    ? `${CONSENT_COOKIE}=${choice}; path=/; Max-Age=${MAX_AGE}; SameSite=Lax; Secure`
    : `${CONSENT_COOKIE}=; path=/; Max-Age=0; SameSite=Lax`;
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  return () => window.removeEventListener(EVENT, cb);
}

/** La scelta corrente: `undefined` sul server (prima dell'idratazione). */
export function useCookieChoice(): CookieChoice | null | undefined {
  return useSyncExternalStore(subscribe, read, () => undefined);
}

/** True solo se chi guarda ha accettato i contenuti di terzi. */
export function useThirdPartyAllowed(): boolean {
  return useCookieChoice() === "all";
}

/** Riapre il banner (il link «Gerir cookies» del footer). */
export function reopenCookieBanner() {
  setCookieChoice(null);
}
