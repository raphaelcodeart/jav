"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";
import { addedVatCents } from "@/lib/product-audience";
import type { MarketplaceConfigRead, ShopSectionKey } from "@/lib/types";

export const MARKETPLACE_SOURCES: { key: "jav_market"; source: string }[] = [
  // Session 79: senza fornitore -- il catalogo lo scrive l'amministratore.
  { key: "jav_market", source: "catalogo nostro" },
];

async function fetchConfig(): Promise<MarketplaceConfigRead> {
  const res = await fetch("/api/proxy/marketplaces/config");
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** The name of the Shop tab and the bank-transfer discount, used by the
 *  customer Shop and its checkout. */
export function useMarketplaceConfig() {
  return useQuery({ queryKey: ["marketplaces", "config"], queryFn: fetchConfig, staleTime: 60_000 });
}

/** "Regole dei Marketplace" (Session 68): the rules of the Shop, set once:
 *  the name it has in the customer's Shop and (Session 78) the VAT rate
 *  added on top of the shown prices. The JavCash rules are shown, not
 *  editable here: 30% on a new product, never 100%. */
export function MarketplaceRulesCard({ highlight }: { highlight?: "jav_market" }) {
  const { t } = useI18n();
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
      setMessage({ ok: true, text: t("mkt.rules.saved") });
    } catch (err: any) {
      setMessage({ ok: false, text: err.message || t("mkt.rules.saveFailed") });
    } finally {
      setBusy(false);
    }
  }

  const vatPct = Number(vat) || 0;
  const label = highlight && config ? config.labels[highlight] : null;

  return (
    <div className="glass-card rounded-2xl border-slate-200 bg-white/70">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex flex-wrap items-center justify-between gap-2 px-5 py-4 text-left cursor-pointer">
        <span>
          <span className="block text-sm font-bold text-slate-900">
            {t("mkt.rules.title")}{label ? t("mkt.rules.calledForCustomers", { label }) : ""}
          </span>
          <span className="block text-xs text-slate-500 mt-0.5">
            {config
              ? `${config.vat_percentage ? t("mkt.rules.vatIncluded", { n: config.vat_percentage }) : ""}${t("mkt.rules.summary", { def: config.default_credit_percentage, max: config.max_credit_percentage })}`
              : t("mkt.rules.loading")}
          </span>
        </span>
        <span className="text-xs font-semibold text-brand-600">{open ? t("common.close") : t("mkt.rules.edit")}</span>
      </button>
      {error && <p className="px-5 pb-4 text-xs text-rose-400">{(error as Error).message}</p>}
      {open && config && (
        <form onSubmit={save} className="px-5 pb-5 space-y-4 border-t border-slate-200 pt-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {MARKETPLACE_SOURCES.map((m) => (
              <label key={m.key} className="block">
                <span className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">
                  {t("mkt.rules.nameInShop")} · {t.dyn(`mkt.rules.source.${m.key}`, m.source)}
                </span>
                <input
                  value={labels[m.key] ?? ""}
                  maxLength={40}
                  onChange={(e) => setLabels({ ...labels, [m.key]: e.target.value })}
                  className="w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-brand-500"
                />
              </label>
            ))}
          </div>
          {/* Session 86: nessuno sconto per chi paga con bonifico -- non si
              può fare. Il campo per impostarlo è stato tolto. */}
          <label className="block max-w-xs">
            <span className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">
              {t("mkt.rules.vatRate")}
            </span>
            <input
              inputMode="numeric"
              value={vat}
              onChange={(e) => setVat(e.target.value.replace(/\D/g, ""))}
              className="w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-brand-500"
            />
            <span className="block text-[10px] text-slate-500 mt-1">
              {vatPct > 0
                ? t("mkt.rules.vatHelp", { example: ((10000 + addedVatCents(10000, vatPct)) / 100).toFixed(2).replace(".", ",") })
                : t("mkt.rules.vatZeroHelp")}
            </span>
          </label>
          <p className="text-[11px] text-slate-500">
            {t("mkt.rules.footer", { max: config.max_credit_percentage })}
          </p>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={busy}
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
            >
              {busy ? t("mkt.rules.saving") : t("common.save")}
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

/** "Sezioni dello Shop" (Session 72): le schede del catalogo nello Shop del
 *  cliente. Ognuna si accende, si spegne e si rinomina, perché
 *  un'organizzazione può semplicemente non vendere una di queste tre cose.
 *  «Fai la Spesa con Jav» ha il proprio interruttore nelle sue impostazioni. */
export function ShopSectionsCard() {
  const { t } = useI18n();
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
      setMessage({ ok: true, text: t("mkt.rules.saved") });
    } catch (err: any) {
      setMessage({ ok: false, text: err.message || t("mkt.rules.saveFailed") });
    } finally {
      setBusy(false);
    }
  }

  const summary = config
    ? SHOP_SECTIONS.map((s) => `${config.sections[s.key].label}${config.sections[s.key].enabled ? "" : ` (${t("mkt.sections.offLower")})`}`).join(" · ")
    : t("mkt.rules.loading");

  return (
    <div className="glass-card rounded-2xl border-slate-200 bg-white/70">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex flex-wrap items-center justify-between gap-2 px-5 py-4 text-left cursor-pointer">
        <span>
          <span className="block text-sm font-bold text-slate-900">{t("mkt.sections.title")}</span>
          <span className="block text-xs text-slate-500 mt-0.5">{summary}</span>
        </span>
        <span className="text-xs font-semibold text-brand-600">{open ? t("common.close") : t("mkt.rules.edit")}</span>
      </button>
      {error && <p className="px-5 pb-4 text-xs text-rose-400">{(error as Error).message}</p>}
      {open && config && (
        <form onSubmit={save} className="px-5 pb-5 space-y-4 border-t border-slate-200 pt-4">
          {SHOP_SECTIONS.map((section) => {
            const value = draft[section.key] ?? config.sections[section.key];
            return (
              <div key={section.key} className="flex flex-wrap items-end gap-3">
                <label className="block flex-1 min-w-[180px]">
                  <span className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">
                    {t("mkt.rules.nameInShop")} · {t.dyn(`mkt.sections.what.${section.key}`, section.what)}
                  </span>
                  <input
                    value={value.label}
                    maxLength={40}
                    onChange={(e) => setDraft({ ...draft, [section.key]: { ...value, label: e.target.value } })}
                    className="w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-brand-500"
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
                  {value.enabled ? t("mkt.sections.visible") : t("mkt.sections.off")}
                </button>
              </div>
            );
          })}
          <p className="text-[11px] text-slate-500">
            {t("mkt.sections.footer")}
          </p>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={busy}
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
            >
              {busy ? t("mkt.rules.saving") : t("common.save")}
            </button>
            {message && <span className={`text-xs ${message.ok ? "text-emerald-400" : "text-rose-400"}`}>{message.text}</span>}
          </div>
        </form>
      )}
    </div>
  );
}
