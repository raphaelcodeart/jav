"use client";

/** Il riquadro in home promoter che porta dritto al form «Nuovo cliente» di
 *  «Miei Clienti» -- stessa forma del riquadro «Non hai trovato ciò che
 *  cercavi?» dello Shop (product-requests.tsx), perché l'azione principale
 *  di un promoter deve stare a un clic dalla home, non a due. */
export function NewCustomerBanner({ onClick }: { onClick: () => void }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-orange-500/30 bg-gradient-to-br from-orange-600/15 via-amber-500/10 to-transparent p-5 sm:p-6">
      <div className="absolute -right-10 -top-10 w-40 h-40 rounded-full bg-orange-500/10 blur-2xl pointer-events-none" />
      <div className="relative flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="w-12 h-12 rounded-2xl bg-orange-500/15 border border-orange-500/30 flex items-center justify-center shrink-0">
          <svg className="w-6 h-6 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-base sm:text-lg font-bold text-white light:text-slate-900 leading-snug">
            Inserisci un nuovo cliente e attiva il suo contratto
          </h3>
          <p className="text-sm text-slate-300 light:text-slate-600 mt-0.5">
            Registralo adesso e compila la pratica: il cliente riceve un&apos;email e paga dalla sua area. Le provvigioni sono tue.
          </p>
        </div>
        <button
          type="button"
          onClick={onClick}
          className="px-5 py-2.5 rounded-xl text-sm font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer shrink-0"
        >
          Nuovo cliente
        </button>
      </div>
    </div>
  );
}
