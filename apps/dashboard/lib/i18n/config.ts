// The interface languages. Portuguese first: it is the default for anyone who
// has not chosen yet, and the first flag in the switcher.

export const LOCALES = ["pt", "en", "it", "es", "fr", "de"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "pt";

/** The choice lives in a cookie, not in the URL: every link, redirect and
 *  bookmark of the app keeps working unchanged, and the server can render
 *  the right language on the very first request. */
export const LOCALE_COOKIE = "jav_lang";

/** BCP 47 tags for Intl (dates, money). pt-PT, not pt-BR: the club chose
 *  European Portuguese. */
export const INTL_TAGS: Record<Locale, string> = {
  pt: "pt-PT",
  en: "en-GB",
  it: "it-IT",
  es: "es-ES",
  fr: "fr-FR",
  de: "de-DE",
};

export const LOCALE_NAMES: Record<Locale, string> = {
  pt: "Português",
  en: "English",
  it: "Italiano",
  es: "Español",
  fr: "Français",
  de: "Deutsch",
};

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}
