"use client";

import type { ProductCatalogRead } from "@/lib/types";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { contractPrices, isRecurringProductType } from "@/lib/product-audience";

const BILLING_LABELS: Record<string, string> = {
  MONTHLY: "/mese",
  QUARTERLY: "/trimestre",
  ANNUAL: "/anno",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

// Wallet credit is JavCash, never plain EUR -- see wallet-panel.tsx's
// identical helper.
function javCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} JavCash`;
}

/** Full product page shown before checkout -- an e-commerce shopping cart
    never sends the buyer straight from a grid card to payment, it shows the
    product page first.

    Also the "Anteprima" of a Jav package while configuring a point
    of a pratica (Session 52): there `customerKind` is known, the price is
    the canone times the months of the contract, VAT only for a business,
    and the button chooses the package instead of buying it. */
export function ProductDetailModal({
  product,
  onClose,
  onBuy,
  ctaLabel = "Acquista ora",
  customerKind,
}: {
  product: ProductCatalogRead;
  onClose: () => void;
  onBuy: (versionId: string, name: string) => void;
  ctaLabel?: string;
  customerKind?: string | null;
}) {
  const v = product.current_version!;
  const isContract = product.category === "INTERNAL";
  const contractPrice = contractPrices(v, customerKind ?? null, { assumeBusinessWhenUnknown: false });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-2xl glass-card rounded-2xl border-slate-300 bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
        <div className="relative h-64 sm:h-72">
          <ProductThumbnail imageUrl={v.image_url} alt={v.name} iconClassName="w-16 h-16 text-brand-600/40" />
          <button
            onClick={onClose}
            className="absolute top-3 right-3 p-1.5 rounded-lg bg-slate-950/60 hover:bg-slate-950/80 text-slate-900 transition cursor-pointer"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          {product.category !== "INTERNAL" && v.credit_discount_percentage > 0 && (
            <span className="absolute bottom-3 left-3 px-2.5 py-1 rounded-full text-[11px] font-bold border bg-emerald-500/90 text-white border-emerald-400/50 shadow-lg">
              Fino al {v.credit_discount_percentage}% pagabile in JavCash
            </span>
          )}
        </div>

        <div className="p-6 space-y-5">
          <div>
            <h2 className="text-xl font-bold text-slate-900">{v.name}</h2>
            {v.description && (
              <p className="text-sm text-slate-500 mt-2 whitespace-pre-wrap">{v.description}</p>
            )}
          </div>

          {isContract ? (
            <div className="flex flex-wrap items-end gap-6 p-5 rounded-xl bg-slate-900/5 border border-slate-200">
              <div>
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Unica soluzione</p>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-3xl font-extrabold text-slate-900 tabular-nums">
                    {euro(contractPrice.oneGo.grossCents)}
                  </span>
                  {v.contract_duration_months ? (
                    <span className="text-xs text-slate-500">per {v.contract_duration_months} mesi</span>
                  ) : null}
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  {contractPrice.oneGo.vatCents > 0
                    ? `${euro(contractPrice.oneGo.netCents)} + IVA ${contractPrice.oneGo.vatRate}%`
                    : "IVA non applicata"}
                </p>
              </div>
              <div className="pl-6 border-l border-slate-300">
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">A rate</p>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-3xl font-extrabold text-slate-900 tabular-nums">
                    {euro(contractPrice.monthlyGrossCents)}
                  </span>
                  <span className="text-xs text-slate-500">/mese × 12</span>
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  totale {euro(contractPrice.instalments.grossCents)}
                  {contractPrice.instalments.vatCents > 0 ? " IVA incl." : ""}, anche in 3 rate
                </p>
              </div>
              {v.contract_cashback_percentage > 0 && (
                <div className="pl-6 border-l border-slate-300">
                  <p className="text-[10px] font-semibold text-emerald-500 uppercase tracking-wide">Cashback</p>
                  <p className="text-3xl font-extrabold text-emerald-400 tabular-nums">{v.contract_cashback_percentage}%</p>
                  <p className="text-[10px] text-slate-500 mt-0.5">in JavCash, a ogni pagamento</p>
                </div>
              )}
            </div>
          ) : (
          <div className="flex flex-wrap items-end gap-6 p-5 rounded-xl bg-slate-900/5 border border-slate-200">
            <div>
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Prezzo</p>
              <div className="flex items-baseline gap-1.5">
                <span className="text-3xl font-extrabold text-slate-900 tabular-nums">{euro(v.base_price_cents)}</span>
                <span className="text-xs text-slate-500">{isRecurringProductType(product.product_type) ? BILLING_LABELS[v.billing_period] ?? "" : ""}</span>
              </div>
              {v.vat_percentage != null && (
                <p className="text-[10px] text-slate-500 mt-0.5">
                  + IVA {v.vat_percentage}% ({euro(Math.round(v.base_price_cents * (1 + v.vat_percentage / 100)))} tot.)
                </p>
              )}
              {v.initial_fee_cents > 0 && (
                <p className="text-[10px] text-slate-500 mt-0.5">
                  + {euro(v.initial_fee_cents)} contributo di attivazione
                </p>
              )}
            </div>
            {product.category !== "INTERNAL" && v.credit_discount_percentage > 0 && (
              <div className="pl-6 border-l border-slate-300">
                <p className="text-[10px] font-semibold text-emerald-500 uppercase tracking-wide">JavCash usabili</p>
                <p className="text-3xl font-extrabold text-emerald-400 tabular-nums">
                  {javCash(Math.round((v.base_price_cents * v.credit_discount_percentage) / 100))}
                </p>
                <p className="text-[10px] text-slate-500 mt-0.5">dal tuo wallet Jav</p>
              </div>
            )}
          </div>
          )}

          <button
            onClick={() => onBuy(v.id, v.name)}
            className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 text-white text-sm font-bold shadow-lg shadow-brand-500/20 transition-all duration-200 cursor-pointer active:scale-[0.98]"
          >
            <svg className="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 11H4L5 9z" />
            </svg>
            {ctaLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
