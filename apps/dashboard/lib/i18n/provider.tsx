"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { LOCALE_COOKIE, type Locale } from "@/lib/i18n/config";
import { makeFormatters, makeTranslator } from "@/lib/i18n/translate";

const I18nContext = createContext<{ locale: Locale; setLocale: (l: Locale) => void } | null>(null);

/** `initialLocale` comes from the cookie, read by the root layout: server
 *  and browser render the same language, so nothing flashes on hydration. */
export function I18nProvider({ initialLocale, children }: { initialLocale: Locale; children: ReactNode }) {
  const [locale, setLocaleState] = useState(initialLocale);
  const router = useRouter();

  function setLocale(next: Locale) {
    document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
    document.documentElement.lang = next;
    setLocaleState(next);
    // Server components (page titles, <html lang>) read the cookie: re-render
    // them too, without a full reload that would lose what is on screen.
    router.refresh();
  }

  return <I18nContext.Provider value={{ locale, setLocale }}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  const { locale, setLocale } = ctx;
  const t = useMemo(() => makeTranslator(locale), [locale]);
  const fmt = useMemo(() => makeFormatters(locale), [locale]);
  return { locale, setLocale, t, fmt };
}
