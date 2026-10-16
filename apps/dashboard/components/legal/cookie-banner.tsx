"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { setCookieChoice, useCookieChoice } from "@/lib/cookie-consent";
import { useI18n } from "@/lib/i18n/provider";

/** Il banner dei cookie, la prima volta che si apre il sito (e quando si
 *  riapre dal footer). «Rejeitar» vale quanto «Aceitar»: stessi bottoni,
 *  stessa evidenza, come chiede la CNPD. Finché non si sceglie restano solo i
 *  cookie tecnici. */
export function CookieBanner() {
  const { t } = useI18n();
  const choice = useCookieChoice();
  const open = choice === null;
  return (
    <AnimatePresence>
      {open && (
        <motion.div role="dialog" aria-live="polite" aria-label={t("cookies.title")}
          initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 40, opacity: 0 }}
          className="fixed inset-x-3 bottom-3 z-[100] mx-auto max-w-3xl rounded-3xl bg-white p-5 shadow-[0_20px_60px_rgba(0,0,0,0.25)] ring-1 ring-ink-900/10 sm:inset-x-6 sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex-1">
              <p className="flex items-center gap-2 font-display text-lg text-ink-900"><span aria-hidden="true">🍪</span> {t("cookies.title")}</p>
              <p className="mt-1 text-sm text-ink-600">
                {t("cookies.text")}{" "}
                <Link href="/cookies" className="font-semibold text-brand-700 underline">{t("cookies.more")}</Link>
                {" · "}
                <Link href="/privacidade" className="font-semibold text-brand-700 underline">{t("legal.privacy")}</Link>
              </p>
            </div>
            <div className="flex shrink-0 flex-col gap-2 sm:w-56">
              <button type="button" onClick={() => setCookieChoice("all")}
                className="h-11 cursor-pointer rounded-2xl bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700">{t("cookies.acceptAll")}</button>
              <button type="button" onClick={() => setCookieChoice("essential")}
                className="h-11 cursor-pointer rounded-2xl bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700">{t("cookies.onlyEssential")}</button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Al posto di un video o di un'immagine di un altro sito (YouTube, Vimeo)
 *  finché non si accettano i contenuti di terzi: un clic li accetta. */
export function ThirdPartyGate({ provider, className }: { provider: string; className?: string }) {
  const { t } = useI18n();
  return (
    <div className={`flex flex-col items-center justify-center gap-2 bg-gradient-to-br from-ink-800 to-ink-950 p-4 text-center text-white ${className ?? ""}`}>
      <span className="text-3xl" aria-hidden="true">▶</span>
      <p className="max-w-xs text-xs text-white/80">{t("cookies.gate", { provider })}</p>
      <button type="button" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setCookieChoice("all"); }}
        className="cursor-pointer rounded-full bg-white px-4 py-1.5 text-xs font-bold text-ink-900 hover:bg-accent-100">{t("cookies.gateAccept")}</button>
    </div>
  );
}
