import "server-only";
import { getLocale } from "@/lib/i18n/server";
import { makeFormatters, makeTranslator, type Formatters, type Translator } from "@/lib/i18n/translate";

export type SiteI18n = { t: Translator; fmt: Formatters; locale: Awaited<ReturnType<typeof getLocale>> };

/** Traduttore e formati per le pagine del sito, che sono server component:
 *  la lingua è quella del cookie, come nel resto dell'app, così chi arriva
 *  da un link condiviso legge già in portoghese. */
export async function siteI18n(): Promise<SiteI18n> {
  const locale = await getLocale();
  return { t: makeTranslator(locale), fmt: makeFormatters(locale), locale };
}

/** "8 – 12 anos", "6+ anos", o niente: la fascia d'età di un corso. */
export function ageRange(t: Translator, min: number | null, max: number | null): string | null {
  if (min == null && max == null) return null;
  if (max == null) return t("site.agesFrom", { min: min ?? 0 });
  if (min == null) return t("site.agesUpTo", { max });
  return t("site.agesRange", { min, max });
}

/** Il nome di una fascia del ranking, di un livello di gara, di un piazzamento:
 *  arrivano come codice dall'API e si traducono qui. */
export function ageBandLabel(t: Translator, code: string): string {
  return t.dyn(`club.ageBand.${code}`, code);
}

export function levelLabel(t: Translator, code: string): string {
  return t.dyn(`club.level.${code}`, code);
}

export function placementLabel(t: Translator, placement: number): string {
  return t.dyn(`club.placement.${placement}`, String(placement));
}

/** Le date di un evento: un giorno, o dal primo all'ultimo. */
export function eventDates(fmt: Formatters, startsOn: string, endsOn: string): string {
  return startsOn === endsOn ? fmt.shortDate(startsOn) : `${fmt.shortDate(startsOn)} – ${fmt.shortDate(endsOn)}`;
}
