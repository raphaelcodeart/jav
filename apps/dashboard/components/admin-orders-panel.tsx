"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { friendlyApiError } from "@/lib/api-error";
import { vatLineLabel } from "@/lib/product-audience";
import type {
  CustomerRead,
  JavMarketOrderItemRead,
  JavMarketOrderRead,
  OrderRead,
  ProductCatalogRead,
} from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  AWAITING_PAYMENT: "Attesa pagamento residuo",
  PAID: "Pagato",
  CANCELLED: "Annullato",
};
const STATUS_COLORS: Record<string, string> = {
  AWAITING_PAYMENT: "bg-amber-500/10 text-amber-700 border-amber-500/20",
  PAID: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  CANCELLED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
};
const PAYMENT_METHOD_LABELS: Record<string, string> = {
  BANK_TRANSFER: "Bonifico",
};

/** Same unification as customer-orders-panel.tsx::UnifiedOrder -- an order
    of the internal catalog (orders.id) and one of the Shop
    (jav_market_orders.id) are two different tables internally, but this
    admin screen merges them into one continuous list and manages them
    identically -- `source` only ever decides which backend endpoint an
    action call goes to. */
type UnifiedOrder = {
  id: string;
  source: "standard" | "jav_market";
  /** Shop: shipping state, shown as a hint here; address, sending to the
      producers and tracking are handled in the Shop's own page. */
  fulfillment_status?: string;
  customer_display_name: string;
  product_name: string;
  /** Session 75: le righe di un ordine nato dal carrello. */
  items?: JavMarketOrderItemRead[];
  order_code?: string;
  product_image_url: string | null;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  /** Shop orders: bank-transfer discount, already out of residual_amount_cents. */
  bank_transfer_discount_cents?: number;
  /** Shop orders (Session 74): the VAT frozen on the order. Missing on an
      order without it -- nothing shown. */
  vat_amount_cents?: number;
  vat_percentage?: number;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER";
  payment_proof_uploaded_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
};

type UnifiedQuote = {
  product_name: string;
  amount_cents: number;
  credit_discount_percentage: number;
  max_creditable_cents: number;
  customer_wallet_balance_cents: number;
  bank_transfer_available: boolean;
};

function ordersBasePath(source: UnifiedOrder["source"]): string {
  return source === "jav_market" ? "/api/proxy/jav-market/orders" : "/api/proxy/orders";
}

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

// Wallet credit is JavCash, never plain EUR -- see wallet-panel.tsx's
// identical helper. Bonifico amounts always stay euro().
function javCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} JavCash`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Same derivation as customer-orders-panel.tsx::orderCode -- must stay
    identical so a customer reading their own "Ordine #XXXXXXXX" and an
    admin looking it up here see the same code, regardless of source. */
/** Come si chiama un ordine a schermo. Dalla Session 76 e' un numero
 *  progressivo (`order_code`); gli ordini piu' vecchi di quella sequenza
 *  ripiegano sulle prime cifre dell'UUID, che e' come si sono sempre
 *  chiamati -- rinominarli a posteriori li renderebbe irrintracciabili. */
function orderCode(order: { id: string; order_code?: string }): string {
  return order.order_code ?? order.id.slice(0, 8).toUpperCase();
}

async function fetchCustomers(): Promise<CustomerRead[]> {
  const res = await fetch("/api/proxy/customers");
  if (!res.ok) throw new Error("Impossibile caricare i clienti.");
  return res.json();
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti.");
  return res.json();
}

async function fetchOrders(statusFilter: string): Promise<UnifiedOrder[]> {
  const qs = statusFilter !== "ALL" ? `?status_filter=${statusFilter}` : "";
  const [standardRes, shopRes] = await Promise.all([
    fetch(`/api/proxy/orders${qs}`),
    // Lo Shop non filtra per stato lato server: si filtra qui.
    fetch("/api/proxy/jav-market/orders"),
  ]);
  if (!standardRes.ok) throw new Error("Impossibile caricare gli ordini.");
  const standard: OrderRead[] = await standardRes.json();
  const shop: UnifiedOrder[] = [];
  for (const o of shopRes.ok ? ((await shopRes.json()) as JavMarketOrderRead[]) : []) {
    if (statusFilter !== "ALL" && o.status !== statusFilter) continue;
    const lines = o.items ?? [];
    // Con più righe il totale degli articoli, non il nome del primo: un
    // ordine da carrello deve leggersi per quello che è (Session 75).
    shop.push({
      ...o,
      product_name: (lines.length > 1
        ? `${lines.length} articoli`
        : `${o.product_name}${lines[0] && lines[0].quantity > 1 ? ` × ${lines[0].quantity}` : ""}`) + " (Shop)",
      source: "jav_market",
      residual_amount_cents: o.amount_due_cents,
      items: lines,
    });
  }
  const merged: UnifiedOrder[] = [
    ...standard.map((o) => ({ ...o, source: "standard" as const })),
    ...shop,
  ];
  merged.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  return merged;
}

async function fetchQuote(customerUserId: string, productVersionId: string): Promise<UnifiedQuote> {
  const res = await fetch(
    `/api/proxy/orders/quote?customer_user_id=${customerUserId}&product_version_id=${productVersionId}`
  );
  if (!res.ok) throw new Error("Impossibile calcolare il preventivo.");
  return res.json();
}

/** Ordini dei prodotti dropshipping/partner del catalogo e dello Shop --
    vedi UnifiedOrder qui sopra: un unico elenco, gestiti in modo identico.
    Il form di creazione vale per il catalogo; MAI per prodotti Interno Jav,
    che restano contratti (vedi "Nuovo Contratto"). Gli ordini dello Shop
    li crea il cliente dal suo carrello. */
export function AdminOrdersPanel() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("AWAITING_PAYMENT");
  const [showCreate, setShowCreate] = useState(false);
  const [customerUserId, setCustomerUserId] = useState("");
  const [productVersionId, setProductVersionId] = useState("");
  const [creditAmount, setCreditAmount] = useState("0.00");
  const [note, setNote] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState("");

  const { data: customers } = useQuery({ queryKey: ["admin", "customers"], queryFn: fetchCustomers });
  const { data: allProducts } = useQuery({ queryKey: ["admin", "products"], queryFn: fetchProducts });
  const { data: orders, error: loadError } = useQuery({
    queryKey: ["admin", "orders", statusFilter],
    queryFn: () => fetchOrders(statusFilter),
  });

  const orderableCustomers = (customers ?? []).filter((c) => !!c.user_id);
  const orderableProducts = (allProducts ?? []).filter((p) => p.category !== "INTERNAL" && p.current_version);

  const { data: quote } = useQuery({
    queryKey: ["admin", "orders", "quote", customerUserId, productVersionId],
    queryFn: () => fetchQuote(customerUserId, productVersionId),
    enabled: !!customerUserId && !!productVersionId,
  });

  // Default the credit field to the maximum usable amount whenever the
  // quote changes, so the common case ("use all available credit") needs
  // no typing -- the admin only has to lower it if they want less applied.
  useEffect(() => {
    if (!quote) return;
    const maxUsable = Math.min(quote.max_creditable_cents, quote.customer_wallet_balance_cents);
    setCreditAmount((maxUsable / 100).toFixed(2));
  }, [quote]);

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["admin", "orders"] });
    await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!productVersionId) return;
    const creditCents = Math.round(parseFloat(creditAmount.replace(",", ".")) * 100);
    if (!Number.isFinite(creditCents) || creditCents < 0) {
      setCreateError("Importo in JavCash non valido.");
      return;
    }
    setCreateLoading(true);
    setCreateError(null);
    try {
      const body = {
        customer_user_id: customerUserId, product_version_id: productVersionId, credit_applied_cents: creditCents,
        note: note || null,
      };
      const res = await fetch("/api/proxy/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setShowCreate(false);
      setCustomerUserId("");
      setProductVersionId("");
      setCreditAmount("0.00");
      setNote("");
      await invalidate();
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare l'ordine.");
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleConfirmPayment(order: UnifiedOrder) {
    setActionLoadingId(order.id);
    try {
      const res = await fetch(`${ordersBasePath(order.source)}/${order.id}/confirm-payment`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await invalidate();
    } finally {
      setActionLoadingId(null);
    }
  }

  async function handleCancel(order: UnifiedOrder) {
    if (!cancelReason.trim()) return;
    setActionLoadingId(order.id);
    try {
      const res = await fetch(`${ordersBasePath(order.source)}/${order.id}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: cancelReason.trim() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setCancellingId(null);
      setCancelReason("");
      await invalidate();
    } finally {
      setActionLoadingId(null);
    }
  }

  async function handleViewPaymentProof(order: UnifiedOrder) {
    setActionLoadingId(order.id);
    try {
      const res = await fetch(`${ordersBasePath(order.source)}/${order.id}/payment-proof-url`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { url } = await res.json();
      window.open(url, "_blank", "noopener,noreferrer");
    } finally {
      setActionLoadingId(null);
    }
  }

  // The order list is already narrowed by the status tabs above; this pages
  // whatever that leaves.
  const pagination = usePagination(orders ?? []);

  const residualPreview = quote
    ? quote.amount_cents - Math.min(
        Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100),
        quote.max_creditable_cents,
        quote.customer_wallet_balance_cents
      )
    : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-slate-500">
          Acquisti di prodotti dropshipping/partner e dello Shop, con sconto in JavCash opzionale -- un unico elenco.
        </p>
        <button
          onClick={() => { setShowCreate(!showCreate); setCreateError(null); }}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-500/20 transition cursor-pointer shrink-0"
        >
          {showCreate ? "Annulla" : "+ Nuovo Ordine"}
        </button>
      </div>

      {showCreate && (
        <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">Cliente</label>
                <select required value={customerUserId} onChange={(e) => setCustomerUserId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-white focus:border-brand-500">
                  <option value="">Seleziona...</option>
                  {orderableCustomers.map((c) => (
                    <option key={c.id} value={c.user_id!}>{c.display_name}</option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-500">Solo clienti con un account collegato compaiono qui.</p>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">Prodotto</label>
                <select
                  required
                  value={productVersionId}
                  onChange={(e) => setProductVersionId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-white focus:border-brand-500"
                >
                  <option value="">Seleziona...</option>
                  {orderableProducts.map((p) => (
                    <option key={p.id} value={p.current_version!.id}>
                      {p.current_version!.name} ({euro(p.current_version!.base_price_cents)})
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-500">Solo prodotti dropshipping/partner -- i prodotti Interno Jav si vendono come contratto.</p>
              </div>
            </div>

            {quote && (
              <div className="p-4 rounded-xl bg-slate-900/5 border border-slate-200 space-y-3">
                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div>
                    <p className="text-[10px] text-slate-500 uppercase">Prezzo prodotto</p>
                    <p className="font-semibold text-slate-900">{euro(quote.amount_cents)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 uppercase">Sconto max in JavCash</p>
                    <p className="font-semibold text-brand-600">{quote.credit_discount_percentage}% ({euro(quote.max_creditable_cents)})</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 uppercase">Saldo cliente</p>
                    <p className="font-semibold text-slate-900">{euro(quote.customer_wallet_balance_cents)}</p>
                  </div>
                </div>
                <div className="space-y-1 pt-2 border-t border-slate-200">
                  <label className=" font-semibold text-slate-600 uppercase block">JavCash da applicare</label>
                  <input
                    inputMode="decimal"
                    value={creditAmount}
                    onChange={(e) => setCreditAmount(e.target.value)}
                    className="w-full max-w-[160px] rounded-lg glass-input px-3 py-1.5 text-sm focus:border-brand-500"
                  />
                </div>
                {residualPreview != null && (
                  <p className="text-xs text-slate-600">
                    Residuo da bonifico: <strong className="text-brand-600">{euro(Math.max(residualPreview, 0))}</strong>
                    {residualPreview <= 0 && <span className="text-emerald-400"> -- copre l&apos;intero importo, nessun bonifico necessario</span>}
                  </p>
                )}
              </div>
            )}

            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-600 uppercase block">Nota (opzionale)</label>
              <input value={note} onChange={(e) => setNote(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
            </div>

            <button type="submit" disabled={createLoading || !quote}
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
              {createLoading ? "Creazione..." : "Crea Ordine"}
            </button>
            {createError && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{createError}</div>
            )}
          </form>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {["AWAITING_PAYMENT", "PAID", "CANCELLED", "ALL"].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer ${
              statusFilter === s
                ? "bg-brand-600 border-brand-600 text-white"
                : " bg-slate-900/5 border-slate-300 text-slate-600 hover:bg-slate-100"
            }`}
          >
            {s === "ALL" ? "Tutti" : STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      {loadError && <p className="text-sm text-rose-400">Impossibile caricare gli ordini.</p>}

      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 divide-y divide-slate-200 overflow-hidden">
        {orders === undefined ? (
          <p className="text-center py-8 text-slate-500 text-sm">Caricamento...</p>
        ) : orders.length === 0 ? (
          <p className="text-center py-8 text-slate-500 text-sm">Nessun ordine in questo stato.</p>
        ) : (
          pagination.pageItems.map((o) => (
            <div key={o.id} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex items-start gap-3 min-w-0">
                  <div className="w-12 h-12 rounded-lg overflow-hidden shrink-0 border border-slate-200">
                    <ProductThumbnail imageUrl={o.product_image_url} alt={o.product_name} iconClassName="w-5 h-5 text-brand-600/40" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-medium text-slate-900">{o.customer_display_name}</span>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_COLORS[o.status]}`}>
                        {STATUS_LABELS[o.status]}
                      </span>
                      <span className="px-2 py-0.5 rounded-full font-bold border bg-slate-900/5 border-slate-300 text-slate-600">
                        {PAYMENT_METHOD_LABELS[o.payment_method] ?? o.payment_method}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      Ordine <span className="font-mono text-slate-600">#{orderCode(o)}</span> · {formatDate(o.created_at)}
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {o.product_name} · Totale {euro(o.amount_cents)}
                      {o.credit_applied_cents > 0 && <> · {javCash(o.credit_applied_cents)}</>}
                      {" "}· {o.status === "AWAITING_PAYMENT" ? "Residuo" : "Pagato in euro"} {euro(o.residual_amount_cents)}
                      {(o.bank_transfer_discount_cents ?? 0) > 0 && <> (sconto bonifico -{euro(o.bank_transfer_discount_cents!)})</>}
                      {(o.vat_amount_cents ?? 0) > 0 && <> · {vatLineLabel(o.vat_percentage ?? 0)} {euro(o.vat_amount_cents!)}</>}
                    </p>
                    {(o.items ?? []).length > 1 && (
                      <ul className="mt-1 space-y-0.5">
                        {(o.items ?? []).map((line) => (
                          <li key={line.id} className="text-[11px] text-slate-500">
                            · {line.quantity} × {line.product_name}
                            {line.variant_label ? ` (${line.variant_label})` : ""} — {euro(line.line_total_cents)}
                          </li>
                        ))}
                      </ul>
                    )}
                    {o.cancellation_reason && (
                      <p className="text-[11px] text-rose-400 mt-1">Motivo annullamento: {o.cancellation_reason}</p>
                    )}
                    {o.source === "jav_market" && o.status === "PAID" && (
                      <p className={`text-[11px] mt-1 ${o.fulfillment_status === "SHIPPED" || o.fulfillment_status === "DELIVERED" ? "text-sky-400" : "text-amber-700"}`}>
                        {o.fulfillment_status === "DELIVERED"
                          ? "Consegnato"
                          : o.fulfillment_status === "SHIPPED"
                            ? "Spedito"
                            : "Da spedire: indirizzo, invio al fornitore e tracking in Fai la Spesa con Jav → Ordini"}
                      </p>
                    )}
                  </div>
                </div>
                {o.status === "AWAITING_PAYMENT" && (
                  <div className="flex flex-col gap-2 w-full sm:w-56 shrink-0">
                    <button
                      onClick={() => handleConfirmPayment(o)}
                      disabled={actionLoadingId === o.id}
                      className="w-full px-4 py-2 rounded-xl bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                    >
                      {actionLoadingId === o.id ? "..." : "Conferma bonifico ricevuto"}
                    </button>
                    {o.payment_proof_uploaded_at && (
                      <button
                        onClick={() => handleViewPaymentProof(o)}
                        disabled={actionLoadingId === o.id}
                        className="w-full px-4 py-2 rounded-xl bg-sky-600/10 hover:bg-sky-600/20 border border-sky-500/20 text-sky-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                      >
                        Vedi prova di pagamento
                      </button>
                    )}
                    <button
                      onClick={() => setCancellingId(cancellingId === o.id ? null : o.id)}
                      className="w-full px-4 py-2 rounded-xl bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-xs font-semibold transition cursor-pointer"
                    >
                      Annulla
                    </button>
                  </div>
                )}
              </div>
              {cancellingId === o.id && (
                <div className="mt-3 pt-3 border-t border-slate-200 flex items-end gap-2">
                  <div className="space-y-1 flex-1 max-w-sm">
                    <label className=" font-semibold text-slate-600 uppercase block">Motivo annullamento</label>
                    <input autoFocus value={cancelReason} onChange={(e) => setCancelReason(e.target.value)}
                      className="w-full rounded-lg glass-input px-3 py-1.5 text-sm focus:border-brand-500" />
                  </div>
                  <button
                    onClick={() => handleCancel(o)}
                    disabled={actionLoadingId === o.id}
                    className="px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                  >
                    {actionLoadingId === o.id ? "..." : "Conferma annullamento"}
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
      <Pagination {...pagination} label="ordini" />
    </div>
  );
}
