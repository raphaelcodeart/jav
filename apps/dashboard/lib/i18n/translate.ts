// Shared by server and client: no React, no cookies.

import { INTL_TAGS, type Locale } from "@/lib/i18n/config";
import { en } from "@/lib/i18n/messages/en";
import { it, type MessageKey } from "@/lib/i18n/messages/it";
import { pt } from "@/lib/i18n/messages/pt";
import { es } from "@/lib/i18n/messages/es";
import { fr } from "@/lib/i18n/messages/fr";
import { de } from "@/lib/i18n/messages/de";
import { uk } from "@/lib/i18n/messages/uk";

export type { MessageKey };

const MESSAGES: Record<Locale, Record<MessageKey, string>> = { pt, en, it, es, fr, de, uk };

export type Vars = Record<string, string | number>;

function interpolate(text: string, vars?: Vars): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? String(vars[name]) : m));
}

export interface Translator {
  (key: MessageKey, vars?: Vars): string;
  /** For keys built from an API code (`belt.${code}`): a code the
   *  dictionaries do not know yet shows `fallback` -- usually the API's own
   *  label -- instead of a raw key. */
  dyn: (key: string, fallback: string, vars?: Vars) => string;
}

export function makeTranslator(locale: Locale): Translator {
  const dict = MESSAGES[locale];
  // Una chiave che manca in una lingua: prima l'inglese, poi l'italiano.
  const t = ((key: MessageKey, vars?: Vars) => interpolate(dict[key] ?? en[key] ?? it[key] ?? key, vars)) as Translator;
  t.dyn = (key, fallback, vars) => {
    const text = (dict as Record<string, string>)[key];
    return text === undefined ? fallback : interpolate(text, vars);
  };
  return t;
}

/** Money and dates in the reader's language. Euros always: the club bills in
 *  euros whatever language the parent reads. */
export function makeFormatters(locale: Locale) {
  const tag = INTL_TAGS[locale];
  return {
    tag,
    euro: (cents: number, opts?: Intl.NumberFormatOptions) =>
      (cents / 100).toLocaleString(tag, { style: "currency", currency: "EUR", ...opts }),
    /** Whole euros, for the big counters (already divided by 100). */
    euroUnits: (n: number, opts?: Intl.NumberFormatOptions) =>
      n.toLocaleString(tag, { style: "currency", currency: "EUR", ...opts }),
    shortDate: (iso: string | null | undefined) =>
      iso ? new Date(iso).toLocaleDateString(tag, { day: "numeric", month: "short", year: "numeric" }) : "—",
    date: (d: Date, opts: Intl.DateTimeFormatOptions) => d.toLocaleDateString(tag, opts),
  };
}

export type Formatters = ReturnType<typeof makeFormatters>;
