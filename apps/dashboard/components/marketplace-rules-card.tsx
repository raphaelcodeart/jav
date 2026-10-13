"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { addedVatCents } from "@/lib/product-audience";
import type { MarketplaceConfigRead, ShopSectionKey } from "@/lib/types";

export const MARKETPLACE_SOURCES: { key: "aliexpress" | "cj" | "shopify" | "jav_market" | "kappa_market" | "vaitto_market" | "symphonya_market" | "soleil_market"; source: string }[] = [
  { key: "aliexpress", source: "AliExpress" },
  { key: "cj", source: "CJ Dropshipping" },
  { key: "shopify", source: "Shopify" },
  // Session 79: l'unico senza fornitore -- il catalogo lo scriviamo noi.
  { key: "jav_market", source: "catalogo nostro" },
  // Session 87: come il quarto, ma solo Kappa e Robe di Kappa.
  { key: "kappa_market", source: "Kappa e Robe di Kappa" },
  // Session 88: moda di lusso dal feed di Vaitto.
  { key: "vaitto_market", source: "Vaitto" },
  // Session 89: profumi e cosmetici dall'API di Symphonya.
  { key: "symphonya_market", source: "Symphonya" },
  // Session 90: il catalogo affiliato di SoleilDrop, dall'Excel del portale.
  { key: "soleil_market", source: "SoleilDrop" },
];

async function fetchConfig(): Promise<MarketplaceConfigRead> {
  const res = await fetch("/api/proxy/marketplaces/config");
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** The names of the three Marketplace tabs and the bank-transfer discount, used by
 *  the customer Shop and every checkout of imported products. */
export function useMarketplaceConfig() {
  return useQuery({ queryKey: ["marketplaces", "config"], queryFn: fetchConfig, staleTime: 60_000 });
}

/** "Regole dei Marketplace" (Session 68): what the three shops of imported
 *  products (AliExpress, CJ Dropshipping, Shopify) have in common, set once:
 *  the name each one has in the customer's Shop, and how much less a bank
 *  transfer costs than a card (a discount, never a card surcharge: that is
 *  forbidden in Italy), and (Session 74) the VAT rate the shown prices
 *  already contain -- a consumer price in Italy has to be the final one, so
 *  nothing is ever added on top of it. The JavCash rules are shown, not
 *  editable here: 30% on a new product, never 100%. */
export function MarketplaceRulesCard({ highlight }: { highlight?: "aliexpress" | "cj" | "shopify" | "jav_market" | "kappa_market" | "vaitto_market" | "symphonya_market" | "soleil_market" }) {
  const queryClient = useQueryClient();
  const { data: config, error } = useMarketplaceConfig();
  const [open, setOpen] = useState(false);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [vat, setVat] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!config) return;
    // Syncing the form with the server copy once it arrives.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLabels(config.labels);
    setVat(config.vat_percentage === undefined ? "" : String(config.vat_percentage));
  }, [config]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/api/proxy/marketplaces/config", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          labels,
          // Il campo vuoto significa "il server non me l'ha ancora mandata":
          // rimandarla come 0 azzererebbe l'aliquota vera.
          ...(vat === "" ? {} : { vat_percentage: Number(vat) || 0 }),
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      queryClient.setQueryData(["marketplaces", "config"], await res.json());
      setMessage({ ok: true, text: "Salvato." });
    } catch (err: any) {
      setMessage({ ok: false, text: err.message || "Salvataggio non riuscito." });
    } finally {
      setBusy(false);
    }
  }

  const vatPct = Number(vat) || 0;
  const label = highlight && config ? config.labels[highlight] : null;

  return (
    <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex flex-wrap items-center justify-between gap-2 px-5 py-4 text-left cursor-pointer">
        <span>
          <span className="block text-sm font-bold text-white light:text-slate-900">
            Regole dei Marketplace{label ? ` · per i clienti si chiama “${label}”` : ""}
          </span>
          <span className="block text-xs text-slate-400 light:text-slate-500 mt-0.5">
            {config
              ? `${config.vat_percentage ? `Prezzi IVA ${config.vat_percentage}% inclusa · ` : ""}Stesso prezzo con carta e bonifico · JavCash ${config.default_credit_percentage}% sui nuovi prodotti, mai 100% (max ${config.max_credit_percentage}%) · nessun cashback`
              : "Caricamento..."}
          </span>
        </span>
        <span className="text-xs font-semibold text-orange-400">{open ? "Chiudi" : "Modifica"}</span>
      </button>
      {error && <p className="px-5 pb-4 text-xs text-rose-400">{(error as Error).message}</p>}
      {open && config && (
        <form onSubmit={save} className="px-5 pb-5 space-y-4 border-t border-white/5 light:border-slate-200 pt-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {MARKETPLACE_SOURCES.map((m) => (
              <label key={m.key} className="block">
                <span className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">
                  Nome nello Shop · {m.source}
                </span>
                <input
                  value={labels[m.key] ?? ""}
                  maxLength={40}
                  onChange={(e) => setLabels({ ...labels, [m.key]: e.target.value })}
                  className="w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500"
                />
              </label>
            ))}
          </div>
          {/* Session 86: nessuno sconto per chi paga con bonifico -- non si
              può fare. Il campo per impostarlo è stato tolto. */}
          <label className="block max-w-xs">
            <span className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">
              Aliquota IVA dei prodotti (%)
            </span>
            <input
              inputMode="numeric"
              value={vat}
              onChange={(e) => setVat(e.target.value.replace(/\D/g, ""))}
              className="w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500"
            />
            <span className="block text-[10px] text-slate-500 mt-1">
              {vatPct > 0
                ? `I prezzi dei prodotti dei Marketplace sono imponibili: questa è l'aliquota che si aggiunge al checkout. Esempio: 100,00 € diventano ${((10000 + addedVatCents(10000, vatPct)) / 100).toFixed(2).replace(".", ",")} € per il cliente.`
                : "0 = nessuna IVA mostrata al cliente. Di norma 22%: il prezzo resta quello, l'IVA è dentro."}
            </span>
          </label>
          <p className="text-[11px] text-slate-500">
            Il cliente non vede mai la fonte (AliExpress, CJ, Shopify): solo il nome scelto qui. I prodotti dei
            Marketplace non danno cashback: permettono solo di spendere il JavCash, al massimo per la percentuale di
            ogni prodotto (30% quando entra, modificabile fino al {config.max_credit_percentage}%).
          </p>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={busy}
              className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
            >
              {busy ? "Salvataggio..." : "Salva"}
            </button>
            {message && <span className={`text-xs ${message.ok ? "text-emerald-400" : "text-rose-400"}`}>{message.text}</span>}
          </div>
        </form>
      )}
    </div>
  );
}


export const SHOP_SECTIONS: { key: ShopSectionKey; what: string }[] = [
  { key: "internal", what: "I contratti e i pacchetti Jav" },
  { key: "partner", what: "I prodotti dei fornitori partner" },
  { key: "dropshipping", what: "Le offerte del catalogo Jav" },
];

/** "Sezioni dello Shop" (Session 72): le schede dello Shop del cliente che
 *  NON vengono da un marketplace importato. Ognuna si accende, si spegne e
 *  si rinomina, perché un'organizzazione può semplicemente non vendere una
 *  di queste tre cose. Le tre schede dei Marketplace hanno il proprio
 *  interruttore nelle impostazioni del rispettivo shop. */
export function ShopSectionsCard() {
  const queryClient = useQueryClient();
  const { data: config, error } = useMarketplaceConfig();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, { label: string; enabled: boolean }>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!config) return;
    // Syncing the form with the server copy once it arrives.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(config.sections);
  }, [config]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/api/proxy/marketplaces/config", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sections: draft }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      queryClient.setQueryData(["marketplaces", "config"], await res.json());
      setMessage({ ok: true, text: "Salvato." });
    } catch (err: any) {
      setMessage({ ok: false, text: err.message || "Salvataggio non riuscito." });
    } finally {
      setBusy(false);
    }
  }

  const summary = config
    ? SHOP_SECTIONS.map((s) => `${config.sections[s.key].label}${config.sections[s.key].enabled ? "" : " (spenta)"}`).join(" · ")
    : "Caricamento...";

  return (
    <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex flex-wrap items-center justify-between gap-2 px-5 py-4 text-left cursor-pointer">
        <span>
          <span className="block text-sm font-bold text-white light:text-slate-900">Sezioni dello Shop del cliente</span>
          <span className="block text-xs text-slate-400 light:text-slate-500 mt-0.5">{summary}</span>
        </span>
        <span className="text-xs font-semibold text-orange-400">{open ? "Chiudi" : "Modifica"}</span>
      </button>
      {error && <p className="px-5 pb-4 text-xs text-rose-400">{(error as Error).message}</p>}
      {open && config && (
        <form onSubmit={save} className="px-5 pb-5 space-y-4 border-t border-white/5 light:border-slate-200 pt-4">
          {SHOP_SECTIONS.map((section) => {
            const value = draft[section.key] ?? config.sections[section.key];
            return (
              <div key={section.key} className="flex flex-wrap items-end gap-3">
                <label className="block flex-1 min-w-[180px]">
                  <span className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">
                    Nome nello Shop · {section.what}
                  </span>
                  <input
                    value={value.label}
                    maxLength={40}
                    onChange={(e) => setDraft({ ...draft, [section.key]: { ...value, label: e.target.value } })}
                    className="w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => setDraft({ ...draft, [section.key]: { ...value, enabled: !value.enabled } })}
                  className={`px-3 py-2 rounded-xl text-xs font-bold border cursor-pointer ${
                    value.enabled
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                      : "bg-slate-500/10 text-slate-400 border-slate-500/20"
                  }`}
                >
                  {value.enabled ? "Visibile" : "Spenta"}
                </button>
              </div>
            );
          })}
          <p className="text-[11px] text-slate-500">
            Una sezione spenta sparisce dallo Shop del cliente. I tre Marketplace hanno il proprio interruttore
            (&ldquo;Shop visibile ai clienti&rdquo;) nelle impostazioni di ciascuno, e il nome nella card
            &ldquo;Regole dei Marketplace&rdquo;: una scheda Marketplace compare solo se accesa **e** se ha almeno un
            prodotto in vendita.
          </p>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={busy}
              className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
            >
              {busy ? "Salvataggio..." : "Salva"}
            </button>
            {message && <span className={`text-xs ${message.ok ? "text-emerald-400" : "text-rose-400"}`}>{message.text}</span>}
          </div>
        </form>
      )}
    </div>
  );
}
