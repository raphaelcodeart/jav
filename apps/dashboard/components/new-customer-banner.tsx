"use client";

import { useI18n } from "@/lib/i18n/provider";

/** Il riquadro in home promoter che porta dritto al form «Nuovo cliente» di
 *  «Miei Clienti» -- stessa forma del riquadro «Non hai trovato ciò che
 *  cercavi?» dello Shop (product-requests.tsx), perché l'azione principale
 *  di un promoter deve stare a un clic dalla home, non a due. */
export function NewCustomerBanner({ onClick }: { onClick: () => void }) {
  const { t } = useI18n();
  return (
    <div className="relative overflow-hidden rounded-2xl border border-brand-500/30 bg-gradient-to-br from-brand-600/15 via-brand-400/10 to-transparent p-5 sm:p-6">
      <div className="absolute -right-10 -top-10 w-40 h-40 rounded-full bg-brand-500/10 blur-2xl pointer-events-none" />
      <div className="relative flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="w-12 h-12 rounded-2xl bg-brand-500/15 border border-brand-500/30 flex items-center justify-center shrink-0">
          <svg className="w-6 h-6 text-brand-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-base sm:text-lg font-bold text-slate-900 leading-snug">
            {t("net.newCustBanner.title")}
          </h3>
          <p className="text-sm text-slate-600 mt-0.5">
            {t("net.newCustBanner.body")}
          </p>
        </div>
        <button
          type="button"
          onClick={onClick}
          className="px-5 py-2.5 rounded-xl text-sm font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-500/20 transition cursor-pointer shrink-0"
        >
          {t("net.newCustBanner.cta")}
        </button>
      </div>
    </div>
  );
}
