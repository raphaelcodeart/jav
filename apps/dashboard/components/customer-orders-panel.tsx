"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { friendlyApiError } from "@/lib/api-error";
import { vatLineLabel } from "@/lib/product-audience";
import type { JavMarketOrderItemRead, JavMarketOrderRead, OrderRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";
import { javCash as javCashIn } from "@/components/marketplace-checkout-bits";

type T = ReturnType<typeof useI18n>["t"];
const STATUS_COLORS: Record<string, string> = {
  AWAITING_PAYMENT: "bg-amber-500/10 text-amber-700 border-amber-500/20",
  PAID: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  CANCELLED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
};
type OrderFilter = "ALL" | "PAID" | "AWAITING_PAYMENT" | "CANCELLED";

const FILTER_TABS: { key: OrderFilter; label: "shopx.orders.filter.all" | "shopx.orders.filter.paid" | "shopx.orders.filter.awaiting" | "shopx.orders.filter.cancelled" }[] = [
  { key: "ALL", label: "shopx.orders.filter.all" },
  { key: "PAID", label: "shopx.orders.filter.paid" },
  { key: "AWAITING_PAYMENT", label: "shopx.orders.filter.awaiting" },
  { key: "CANCELLED", label: "shopx.orders.filter.cancelled" },
];

/** A purchase, whichever of the two order tables actually backs it --
    orders.id for a product of the internal catalog, jav_market_orders.id
    for one from the Shop. Everywhere (this screen, admin-orders-panel.tsx,
    Contabilità) the two are merged into one continuous history and behave
    identically -- `source` is purely an internal routing detail (which
    backend endpoint an action call goes to), never surfaced in the UI.
    Cashback fields don't exist on a Shop order at all, normalized to their
    "not applicable" values here so the rest of this component never has to
    branch on `source` beyond picking the right API path. */
type UnifiedOrder = {
  id: string;
  source: "standard" | "jav_market";
  order_code?: string;
  product_name: string;
  /** Session 75: le righe, quando l'ordine ne ha più d'una (carrello). */
  items?: JavMarketOrderItemRead[];
  /** Shop only: what travels to the customer's door. */
  shipping?: Pick<
    JavMarketOrderRead,
    | "delivery_status" | "tracking_number" | "tracking_url" | "shipping_days" | "shipped_at" | "delivered_at"
    | "recipient_name" | "address_line1" | "address_line2" | "postal_code" | "city" | "province"
  >;
  product_image_url: string | null;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  /** Shop orders: taken off for paying by bank transfer, already out of
      residual_amount_cents. 0 everywhere else. */
  bank_transfer_discount_cents: number;
  /** Shop orders (Session 74): the VAT already contained in the
      total, frozen on the order. 0 on a catalog order and on every order
      placed before the rule existed -- then nothing is written at all. */
  vat_amount_cents: number;
  vat_percentage: number;
  cashback_requested: boolean;
  cashback_surcharge_cents: number;
  cashback_credited_at: string | null;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER";
  payment_proof_uploaded_at: string | null;
  note: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
};

/** Which backend this order's actions (upload proof, view proof...) route
    to -- the one and only place `source` matters. */
function ordersBasePath(source: UnifiedOrder["source"]): string {
  return source === "jav_market" ? "/api/proxy/jav-market/orders" : "/api/proxy/orders";
}

/** Where a paid Shop order is, in the customer's words. */
function shippingState(order: UnifiedOrder, t: T): { label: string; className: string } | null {
  if (!order.shipping || order.status !== "PAID") return null;
  switch (order.shipping.delivery_status) {
    case "SHIPPED":
      return { label: t("shopx.club.shipped"), className: "bg-sky-500/10 border-sky-500/30 text-sky-400" };
    case "DELIVERED":
      return { label: t("shopx.club.delivered"), className: "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" };
    case "PROBLEM":
      return { label: t("shopx.orders.shipProblem"), className: "bg-rose-500/10 border-rose-500/30 text-rose-400" };
    case "PREPARING":
      return { label: t("shopx.orders.preparing"), className: "bg-amber-500/10 border-amber-500/30 text-amber-700" };
    default:
      return { label: t("shopx.orders.received"), className: "bg-slate-50 border-slate-300 text-slate-600" };
  }
}

/** Money, JavCash and dates in the reader's language. Wallet credit is
 *  JavCash, never plain EUR; bonifico amounts always stay euro(). */
function useOrderFormat() {
  const { t, fmt } = useI18n();
  const formatDateTime = (iso: string) =>
    new Date(iso).toLocaleString(fmt.tag, { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });
  return {
    t,
    euro: fmt.euro,
    javCash: (cents: number) => javCashIn(cents, fmt.tag),
    formatDate: formatDateTime,
    formatDateTime,
  };
}

/** Short, human-typeable reference for an order -- there is no dedicated
    sequential order number in the schema, so (like the bank-transfer
    causale already did) this is derived consistently from the UUID
    everywhere an order needs to be identified at a glance: here, in
    admin-orders-panel.tsx, and in the "Pagamento confermato" email. Same
    derivation regardless of source, so a customer reading their order
    history never sees the two tables behind it as anything other than one
    continuous list. */
/** Come si chiama un ordine a schermo. Dalla Session 76 e' un numero
 *  progressivo (`order_code`); gli ordini piu' vecchi di quella sequenza
 *  ripiegano sulle prime cifre dell'UUID, che e' come si sono sempre
 *  chiamati -- rinominarli a posteriori li renderebbe irrintracciabili. */
function orderCode(order: { id: string; order_code?: string }): string {
  return order.order_code ?? order.id.slice(0, 8).toUpperCase();
}

async function fetchMyOrders(t: T): Promise<UnifiedOrder[]> {
  const [standardRes, javMarketRes] = await Promise.all([
    fetch("/api/proxy/orders/mine"),
    // Session 79: lo Shop. Un 404 (negozio mai aperto) non deve far sparire
    // l'elenco: si legge come lista vuota.
    fetch("/api/proxy/jav-market/orders/mine"),
  ]);
  if (!standardRes.ok) throw new Error(t("shopx.orders.loadFailed"));
  const standard: OrderRead[] = await standardRes.json();
  const javMarket: JavMarketOrderRead[] = javMarketRes.ok ? await javMarketRes.json() : [];
  const merged: UnifiedOrder[] = [
    ...standard.map((o) => ({
      ...o,
      source: "standard" as const,
      bank_transfer_discount_cents: 0,
      // Un contratto o un pacchetto del catalogo ha la sua IVA nel prezzo
      // del prodotto, non qui: questa riga riguarda solo lo Shop.
      vat_amount_cents: 0,
      vat_percentage: 0,
    })),
    ...javMarket.map((o) => ({
      ...o,
      source: "jav_market" as const,
      product_name: orderTitle(o, t),
      residual_amount_cents: o.amount_due_cents,
      vat_amount_cents: o.vat_amount_cents ?? 0,
      vat_percentage: o.vat_percentage ?? 0,
      cashback_requested: false,
      cashback_surcharge_cents: 0,
      cashback_credited_at: null,
      shipping: o,
    })),
  ];
  merged.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  return merged;
}

/** Come si chiama un ordine in elenco. Con più righe (carrello, Session 75)
 *  il nome del primo articolo farebbe credere che gli altri siano andati
 *  persi, quindi si riassume: "Cuffie BT + altri 2". */
function orderTitle(o: {
  id: string;
  order_code?: string;
  product_name: string;
  quantity?: number;
  items?: { product_name: string }[];
}, t: T): string {
  const items = o.items ?? [];
  const first = items[0];
  if (items.length > 1 && first) return t("shopx.orders.titleMore", { name: first.product_name, n: items.length - 1 });
  return (o.quantity ?? 1) > 1 ? `${o.product_name} × ${o.quantity}` : o.product_name;
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string; instructions: string | null }> {
  const res = await fetch("/api/proxy/organizations/me/payment-info");
  if (!res.ok) throw new Error("payment-info");
  return res.json();
}

function OrderDetailModal({ order, onClose, onViewProof, viewProofLoading }: {
  order: UnifiedOrder;
  onClose: () => void;
  onViewProof: () => void;
  viewProofLoading: boolean;
}) {
  const { t, euro, javCash, formatDate, formatDateTime } = useOrderFormat();
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-lg max-h-[85vh] overflow-y-auto glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-14 h-14 rounded-xl overflow-hidden shrink-0 border border-slate-200">
              <ProductThumbnail imageUrl={order.product_image_url} alt={order.product_name} iconClassName="w-6 h-6 text-brand-600/40" />
            </div>
            <div className="min-w-0">
              <h3 className="text-lg font-bold text-slate-900 truncate">{order.product_name}</h3>
              <p className="text-xs text-slate-500">{t("shopx.orders.order")} <span className="font-mono text-slate-600">#{orderCode(order)}</span></p>
            </div>
          </div>
          <button onClick={onClose} aria-label={t("common.close")} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-900 transition cursor-pointer shrink-0">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {(order.items ?? []).length > 1 && (
          <div className="mb-5 rounded-xl border border-slate-200 divide-y divide-slate-200">
            {(order.items ?? []).map((line) => (
              <div key={line.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-slate-900 truncate">{line.product_name}</p>
                  {line.variant_label && <p className="text-[11px] text-slate-500 truncate">{line.variant_label}</p>}
                </div>
                <div className="text-right shrink-0">
                  <p className="text-[11px] text-slate-500">× {line.quantity}</p>
                  <p className="text-xs font-bold text-slate-900 tabular-nums">{euro(line.line_total_cents)}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2 mb-5 flex-wrap">
          <span className={`px-2.5 py-1 rounded-full text-[11px] font-bold border ${STATUS_COLORS[order.status]}`}>
            {t.dyn(`shopx.orders.status.${order.status}`, order.status)}
          </span>
          <span className="px-2.5 py-1 rounded-full font-bold border bg-slate-900/5 border-slate-300 text-slate-600">
            {t.dyn(`shopx.orders.method.${order.payment_method}`, order.payment_method)}
          </span>
        </div>

        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3 p-4 rounded-xl bg-slate-900/5 border border-slate-200">
            <div>
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">{t("shopx.cart.total")}</p>
              <p className="font-bold text-slate-900">{euro(order.amount_cents)}</p>
            </div>
            {order.vat_amount_cents > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">{vatLineLabel(order.vat_percentage)}</p>
                <p className="font-bold text-slate-700">{euro(order.vat_amount_cents)}</p>
              </div>
            )}
            {order.credit_applied_cents > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">{t("shopx.checkout.javCashUsed")}</p>
                <p className="font-bold text-emerald-400">-{javCash(order.credit_applied_cents)}</p>
              </div>
            )}
            {order.cashback_surcharge_cents > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">{t("shopx.orders.cashbackRequested")}</p>
                <p className="font-bold text-brand-600">+{euro(order.cashback_surcharge_cents)}</p>
              </div>
            )}
            {order.bank_transfer_discount_cents > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">{t("shopx.orders.bankDiscount")}</p>
                <p className="font-bold text-emerald-400">-{euro(order.bank_transfer_discount_cents)}</p>
              </div>
            )}
            {order.status === "AWAITING_PAYMENT" && (
              <div>
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">{t("shopx.orders.residualDue")}</p>
                <p className="font-bold text-amber-700">{euro(order.residual_amount_cents)}</p>
              </div>
            )}
          </div>

          <div className="space-y-1.5 text-xs text-slate-500">
            <p>{t("shopx.orders.orderedOn")} <span className=" text-slate-800">{formatDateTime(order.created_at)}</span></p>
            {order.paid_at && <p>{t("shopx.orders.paidOn")} <span className="text-emerald-400">{formatDateTime(order.paid_at)}</span></p>}
            {order.cancelled_at && (
              <p>{t("shopx.orders.cancelledOn")} <span className="text-rose-400">{formatDateTime(order.cancelled_at)}</span>{order.cancellation_reason && ` -- ${order.cancellation_reason}`}</p>
            )}
            {order.payment_method === "BANK_TRANSFER" && (
              <p>{t("shopx.orders.transferReference")} <span className="font-mono text-brand-600">{t("shopx.bank.referenceValue", { code: orderCode(order) })}</span></p>
            )}
            {order.cashback_requested && (
              <p>
                {t("shopx.orders.cashbackLabel")}{" "}
                {order.cashback_credited_at ? (
                  <span className="text-emerald-400">
                    {t("shopx.orders.cashbackCreditedOn", { date: formatDateTime(order.cashback_credited_at), amount: javCash(order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents) })}
                  </span>
                ) : (
                  <span className="text-amber-700">{t("shopx.orders.cashbackPending")}</span>
                )}
              </p>
            )}
          </div>

          {order.shipping && (
            <div className="p-4 rounded-xl bg-slate-900/5 border border-slate-200 space-y-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">{t("shopx.checkout.shipping")}</p>
                {shippingState(order, t) && (
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${shippingState(order, t)!.className}`}>
                    {shippingState(order, t)!.label}
                  </span>
                )}
              </div>
              <p className=" text-slate-700">
                {order.shipping.recipient_name}, {order.shipping.address_line1}
                {order.shipping.address_line2 ? `, ${order.shipping.address_line2}` : ""}, {order.shipping.postal_code} {order.shipping.city} ({order.shipping.province})
              </p>
              {order.shipping.shipped_at && <p className=" text-slate-500">{t("shopx.orders.shippedOn")} <span className="text-sky-400">{formatDateTime(order.shipping.shipped_at)}</span></p>}
              {order.shipping.delivered_at && <p className=" text-slate-500">{t("shopx.orders.deliveredOn")} <span className="text-emerald-400">{formatDateTime(order.shipping.delivered_at)}</span></p>}
              {!order.shipping.shipped_at && order.status === "PAID" && order.shipping.shipping_days && (
                <p className="text-slate-500">{t("shopx.orders.estimatedDelivery", { days: order.shipping.shipping_days })}</p>
              )}
              {order.shipping.tracking_number && (
                <p className=" text-slate-500">
                  {t("shopx.orders.tracking")} <span className="font-mono text-slate-800">{order.shipping.tracking_number}</span>
                  {order.shipping.tracking_url && (
                    <a href={order.shipping.tracking_url} target="_blank" rel="noopener noreferrer" className="ml-2 font-semibold text-brand-600 hover:text-brand-600">
                      {t("shopx.orders.followShipment")} →
                    </a>
                  )}
                </p>
              )}
            </div>
          )}

          {order.payment_proof_uploaded_at && (
            <button
              onClick={onViewProof}
              disabled={viewProofLoading}
              className="w-full px-4 py-2 rounded-xl bg-sky-600/10 hover:bg-sky-600/20 border border-sky-500/20 text-sky-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
            >
              {viewProofLoading ? "..." : t("shopx.orders.viewProof", { date: formatDate(order.payment_proof_uploaded_at) })}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** "I miei ordini": every product purchase the customer has made -- both a
    DROPSHIPPING/PARTNER product of the catalog AND one from the Shop,
    merged into one continuous, indistinguishable list (see UnifiedOrder's docstring).
    Never shows Jav contracts (see business-rules.md -- those are
    Contract rows, not Order rows, tracked in "I miei Contratti" instead). */
export function CustomerOrdersPanel() {
  const { t, euro, javCash, formatDate } = useOrderFormat();
  const { locale } = useI18n();
  const queryClient = useQueryClient();
  const { data: orders, isLoading, error } = useQuery({
    queryKey: ["customer", "orders", "mine", locale],
    queryFn: () => fetchMyOrders(t),
  });
  const [filter, setFilter] = useState<OrderFilter>("ALL");
  const [search, setSearch] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [bankDetailsFor, setBankDetailsFor] = useState<string | null>(null);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [proofTarget, setProofTarget] = useState<UnifiedOrder | null>(null);
  const [detailOrderId, setDetailOrderId] = useState<string | null>(null);
  const [viewProofLoading, setViewProofLoading] = useState(false);
  const { data: paymentInfo } = useQuery({
    queryKey: ["customer", "payment-info"],
    queryFn: fetchPaymentInfo,
    enabled: bankDetailsFor !== null,
  });

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["customer", "orders"] });
  }

  function toggleBankDetails(order: UnifiedOrder) {
    setBankDetailsFor(bankDetailsFor === order.id ? null : order.id);
  }

  function openProofPicker(order: UnifiedOrder) {
    setActionError(null);
    setProofTarget(order);
    fileInputRef.current?.click();
  }

  async function handleProofSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file later
    if (!file || !proofTarget) return;
    setUploadingId(proofTarget.id);
    setActionError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`${ordersBasePath(proofTarget.source)}/mine/${proofTarget.id}/payment-proof`, { method: "POST", body });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await invalidate();
    } catch (err: any) {
      setActionError(err.message || t("shopx.orders.proofUploadFailed"));
    } finally {
      setUploadingId(null);
      setProofTarget(null);
    }
  }

  async function handleViewProof(order: UnifiedOrder) {
    setViewProofLoading(true);
    setActionError(null);
    try {
      const res = await fetch(`${ordersBasePath(order.source)}/mine/${order.id}/payment-proof-url`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { url } = await res.json();
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err: any) {
      setActionError(err.message || t("shopx.orders.proofOpenFailed"));
    } finally {
      setViewProofLoading(false);
    }
  }

  // Computed before the early returns below: usePagination is a hook, so it
  // has to run on every render, including the loading/error/empty ones.
  const list = orders ?? [];
  const normalizedSearch = search.trim().toLowerCase();
  const filteredList = list.filter((o) => {
    if (filter !== "ALL" && o.status !== filter) return false;
    if (!normalizedSearch) return true;
    return (
      o.product_name.toLowerCase().includes(normalizedSearch) ||
      orderCode(o).toLowerCase().includes(normalizedSearch)
    );
  });
  const pagination = usePagination(filteredList);

  if (isLoading) {
    return <div className="glass-card rounded-2xl p-6 border-slate-200 animate-pulse h-40" />;
  }

  if (error) {
    return (
      <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
        {t("shopx.orders.loadFailed")}
      </div>
    );
  }

  if (list.length === 0) {
    return (
      <div className="glass-card rounded-2xl p-12 text-center border-slate-200">
        <svg className="w-12 h-12 text-slate-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
        </svg>
        <h3 className="text-lg font-semibold text-slate-900">{t("shopx.orders.emptyTitle")}</h3>
        <p className="text-sm text-slate-500 mt-1">
          {t("shopx.orders.emptyText")}
        </p>
      </div>
    );
  }

  const detailOrder = detailOrderId ? list.find((o) => o.id === detailOrderId) ?? null : null;

  return (
    <div className="space-y-4">
      <input ref={fileInputRef} type="file" accept="application/pdf,image/jpeg,image/png" className="hidden" onChange={handleProofSelected} />

      <div className="relative">
        <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
        </svg>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("shopx.orders.searchPlaceholder")}
          className="w-full pl-10 pr-9 py-2.5 rounded-xl bg-slate-900/5 border border-slate-300 text-sm text-slate-900 placeholder:text-slate-500 focus:outline-none focus:border-brand-500/50 transition"
        />
        {search && (
          <button
            type="button"
            onClick={() => setSearch("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 rounded-full text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition cursor-pointer"
            title={t("shopx.clearSearch")}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTER_TABS.map((tab) => {
          const count = tab.key === "ALL"
            ? list.length
            : list.filter((o) => o.status === tab.key).length;
          return (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                filter === tab.key
                  ? "bg-brand-600 border-brand-600 text-white"
                  : " bg-slate-900/5 border-slate-300 text-slate-600 hover:bg-slate-100"
              }`}
            >
              {t(tab.label)}
              <span className="ml-1.5 opacity-70">({count})</span>
            </button>
          );
        })}
      </div>

      {actionError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{actionError}</div>
      )}

      {filteredList.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-10">{t("shopx.orders.noneInCategory")}</p>
      ) : (
        pagination.pageItems.map((o) => {
          const awaiting = o.status === "AWAITING_PAYMENT";
          const busy = uploadingId === o.id;
          return (
            <div key={o.id} className="glass-card rounded-2xl border-slate-200 bg-white/70 p-5">
              <div className="flex flex-wrap items-start gap-4">
                <button
                  type="button"
                  onClick={() => setDetailOrderId(o.id)}
                  className="w-16 h-16 rounded-xl overflow-hidden shrink-0 border border-slate-200 cursor-pointer"
                  title={t("shopx.orders.viewDetails")}
                >
                  <ProductThumbnail imageUrl={o.product_image_url} alt={o.product_name} iconClassName="w-7 h-7 text-brand-600/40" />
                </button>
                <div className="flex-1 min-w-[180px]">
                  <div className="flex items-center gap-2 flex-wrap">
                    <button
                      type="button"
                      onClick={() => setDetailOrderId(o.id)}
                      className="font-semibold text-slate-900 hover:text-brand-600 transition cursor-pointer text-left"
                    >
                      {o.product_name}
                    </button>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_COLORS[o.status]}`}>
                      {t.dyn(`shopx.orders.status.${o.status}`, o.status)}
                    </span>
                    {shippingState(o, t) && (
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${shippingState(o, t)!.className}`}>
                        {shippingState(o, t)!.label}
                      </span>
                    )}
                    {o.shipping?.tracking_url && (
                      <a href={o.shipping.tracking_url} target="_blank" rel="noopener noreferrer" className="text-[11px] font-semibold text-sky-400 hover:text-sky-300">
                        {t("shopx.orders.trackParcel")} →
                      </a>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {t("shopx.orders.order")} <span className="font-mono text-slate-600">#{orderCode(o)}</span> · {t("shopx.orders.orderedOn")} {formatDate(o.created_at)}
                  </p>
                  <div className="flex items-center gap-3 mt-2 text-xs flex-wrap">
                    <span className=" text-slate-500">{t("shopx.cart.total")} <strong className=" text-slate-900">{euro(o.amount_cents)}</strong></span>
                    {o.vat_amount_cents > 0 && (
                      <span className="text-slate-500">{vatLineLabel(o.vat_percentage)} {euro(o.vat_amount_cents)}</span>
                    )}
                    {o.credit_applied_cents > 0 && (
                      <span className="text-emerald-400">-{javCash(o.credit_applied_cents)}</span>
                    )}
                    {o.cashback_requested && (
                      <span className="text-brand-600" title={o.cashback_credited_at ? t("shopx.orders.cashbackCredited") : t("shopx.orders.cashbackRequested")}>
                        {o.cashback_credited_at ? `✓ ${t("shopx.orders.cashbackCredited")}` : t("shopx.orders.cashbackRequested")}
                      </span>
                    )}
                    {awaiting && (
                      <span className="text-amber-700">
                        {t("shopx.orders.residual", { amount: euro(o.residual_amount_cents) })}
                        {o.bank_transfer_discount_cents > 0 && ` (${t("shopx.orders.transferDiscountShort")} -${euro(o.bank_transfer_discount_cents)})`}
                      </span>
                    )}
                    {!awaiting && o.bank_transfer_discount_cents > 0 && (
                      <span className=" text-slate-500">-{euro(o.bank_transfer_discount_cents)} {t("shopx.orders.transferDiscountShort")}</span>
                    )}
                    <button
                      type="button"
                      onClick={() => setDetailOrderId(o.id)}
                      className="text-brand-600 hover:text-brand-600 font-semibold cursor-pointer"
                    >
                      {t("shopx.orders.details")} →
                    </button>
                  </div>
                  {o.cancellation_reason && (
                    <p className="text-[11px] text-rose-400 mt-1">{t("shopx.orders.cancelReason", { reason: o.cancellation_reason })}</p>
                  )}
                </div>

                {awaiting && (
                  <div className="flex flex-col gap-2 w-full sm:w-52 shrink-0">
                    <button
                      onClick={() => toggleBankDetails(o)}
                      className="w-full px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold transition cursor-pointer"
                    >
                      {t("shopx.orders.viewBankDetails")}
                    </button>
                    <button
                      onClick={() => openProofPicker(o)}
                      disabled={busy}
                      className="w-full px-4 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                    >
                      {uploadingId === o.id
                        ? t("shopx.loading")
                        : o.payment_proof_uploaded_at
                          ? t("shopx.orders.replaceProof")
                          : t("shopx.orders.addProof")}
                    </button>
                    {o.payment_proof_uploaded_at && (
                      <p className="text-[10px] text-emerald-400 text-center">
                        ✓ {t("shopx.orders.proofUploadedOn", { date: formatDate(o.payment_proof_uploaded_at) })}
                      </p>
                    )}
                  </div>
                )}
              </div>

              {bankDetailsFor === o.id && (() => {
                // Un ordine dello shop di un club si paga al club.
                const info = (o as { payee?: { iban: string | null; holder: string; instructions: string | null } | null }).payee ?? paymentInfo;
                return (
                <div className="mt-4 pt-4 border-t border-slate-200 p-4 rounded-xl bg-slate-900/5 text-xs space-y-1.5">
                  {info?.iban ? (
                    <>
                      <p><span className="text-slate-500">IBAN:</span> <span className="font-mono">{info.iban}</span></p>
                      <p><span className="text-slate-500">{t("shopx.bank.holder")}</span> {info.holder}</p>
                      {info.instructions && <p className=" text-slate-500 pt-1">{info.instructions}</p>}
                    </>
                  ) : (
                    <p className="text-slate-500">{t("shopx.bank.contactAdmin")}</p>
                  )}
                  <p className="pt-1"><span className="text-slate-500">{t("shopx.bank.referenceSuggested")}</span> <span className="font-mono text-brand-600">{t("shopx.bank.referenceValue", { code: orderCode(o) })}</span></p>
                </div>
                );
              })()}
            </div>
          );
        })
      )}

      <Pagination {...pagination} label={t("shopx.orders.paginationLabel")} />

      {detailOrder && (
        <OrderDetailModal
          order={detailOrder}
          onClose={() => setDetailOrderId(null)}
          onViewProof={() => handleViewProof(detailOrder)}
          viewProofLoading={viewProofLoading}
        />
      )}
    </div>
  );
}
