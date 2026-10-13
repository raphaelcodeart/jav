"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { useMarketplaceConfig } from "@/components/marketplace-rules-card";
import { useCartActions } from "@/components/shop-cart";
import { vatLineLabel } from "@/lib/product-audience";
import type { CustomerRead, AliexpressOrderRead, AliexpressProductRead, AliexpressQuoteRead } from "@/lib/types";
import { JavCashConfirmCode } from "@/components/javcash-confirm-code";

const MAX_QUANTITY = 10;

/** Mirrors rules.bank_transfer_discount_cents: % of the residual, half up to the cent. */
function bankTransferDiscount(residualCents: number, percentage: number): number {
  if (residualCents <= 0 || percentage <= 0) return 0;
  return Math.floor((residualCents * percentage + 50) / 100);
}

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function javCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} JavCash`;
}

async function fetchQuote(variantId: string, quantity: number): Promise<AliexpressQuoteRead> {
  const res = await fetch(`/api/proxy/aliexpress/orders/quote/mine?variant_id=${variantId}&quantity=${quantity}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

async function fetchMyCustomer(): Promise<CustomerRead | null> {
  const res = await fetch("/api/proxy/customers/me");
  if (!res.ok) return null;
  return res.json();
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string; instructions: string | null }> {
  const res = await fetch("/api/proxy/invoice-redemptions/payment-info");
  if (!res.ok) throw new Error("Impossibile caricare le coordinate di pagamento.");
  return res.json();
}

type Address = {
  recipient_name: string;
  recipient_phone: string;
  address_line1: string;
  address_line2: string;
  city: string;
  province: string;
  postal_code: string;
};

const inputClass =
  "w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500";

function Field({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="block text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-1">{label}</span>
      {children}
    </label>
  );
}

function Section({ n, title, done, children }: { n: number; title: string; done?: boolean; children: React.ReactNode }) {
  return (
    <div className="p-4 rounded-xl border border-white/10 light:border-slate-200 space-y-3">
      <div className="flex items-center gap-2.5">
        <span className={`flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-bold shrink-0 text-white ${done ? "bg-emerald-500" : "bg-orange-600"}`}>
          {done ? "✓" : n}
        </span>
        <p className="text-sm font-semibold text-white light:text-slate-900">{title}</p>
      </div>
      {children}
    </div>
  );
}

/** Marketplace 3 (AliExpress dropshipping API, Session 71): product page and
 *  checkout in one window, the same as the CJ and Shopify ones
 *  (cj-product-modal.tsx, shopify-product-modal.tsx) -- photos, variants,
 *  quantity, then JavCash with an email code (never the whole price),
 *  bonifico istantaneo (discounted) or card for the rest, and the delivery
 *  address. Every amount is recomputed by the server; the customer is never
 *  told where the product comes from.
 */
export function AliexpressProductModal({ product: listed, onClose }: { product: AliexpressProductRead; onClose: () => void }) {
  const queryClient = useQueryClient();
  // Session 87: la scheda si rilegge da AliExpress appena si apre (il server
  // lo fa solo se l'ultima lettura ha più di dieci minuti). Nel frattempo si
  // mostra quella della griglia; se il prodotto non c'è più, lo si dice qui e
  // non al pagamento, e la griglia si ricarica senza di lui.
  const { data: live } = useQuery({
    queryKey: ["customer", "aliexpress", "live", listed.id],
    queryFn: async (): Promise<{ available: boolean; product: AliexpressProductRead | null }> => {
      const res = await fetch(`/api/proxy/aliexpress/products/active/${listed.id}`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const data = await res.json();
      if (!data.available) queryClient.invalidateQueries({ queryKey: ["customer", "aliexpress-products"] });
      return data;
    },
    staleTime: 60_000,
    retry: false,
  });
  const noLongerSold = live !== undefined && !live.available;
  const product: AliexpressProductRead = noLongerSold
    ? { ...listed, variants: listed.variants.map((v) => ({ ...v, in_stock: false })) }
    : live?.product ?? listed;
  const { data: marketplaceConfig } = useMarketplaceConfig();
  const shopLabel = marketplaceConfig?.labels.aliexpress ?? "Marketplace 3";
  const firstAvailable = product.variants.find((v) => v.in_stock) ?? product.variants[0];
  const [variantId, setVariantId] = useState<string>(firstAvailable?.id ?? "");
  const [quantity, setQuantity] = useState(1);
  const [imageIndex, setImageIndex] = useState(0);
  const [imageOverride, setImageOverride] = useState<string | null>(null);
  const [showFullDescription, setShowFullDescription] = useState(false);
  const [step, setStep] = useState<"product" | "checkout" | "bank_instructions" | "card_redirect" | "success">("product");

  const variant = product.variants.find((v) => v.id === variantId) ?? null;
  const gallery = product.images.length > 0 ? product.images : product.image_url ? [product.image_url] : [];
  const mainImage = imageOverride ?? gallery[imageIndex] ?? null;

  const { data: quote, error: quoteError, isFetching: quoteLoading } = useQuery({
    queryKey: ["customer", "aliexpress", "quote", variantId, quantity],
    queryFn: () => fetchQuote(variantId, quantity),
    enabled: step === "checkout" && !!variantId,
    retry: false,
  });
  const { data: me } = useQuery({ queryKey: ["customer", "me", "record"], queryFn: fetchMyCustomer, enabled: step === "checkout" });

  // Prefilled from the customer's record; what they type wins.
  const [addressEdits, setAddressEdits] = useState<Partial<Address>>({});
  const address: Address = {
    recipient_name: [me?.first_name, me?.last_name].filter(Boolean).join(" "),
    recipient_phone: me?.phone ?? "",
    address_line1: quote?.default_address.street ?? "",
    address_line2: "",
    city: quote?.default_address.city ?? "",
    province: quote?.default_address.province ?? "",
    postal_code: quote?.default_address.postal_code ?? "",
    ...addressEdits,
  };
  const setAddress = (next: Address) => setAddressEdits(next);

  const [useCredit, setUseCredit] = useState(false);
  const [creditAmount, setCreditAmount] = useState("0.00");
  const [chosenMethod, setPaymentMethod] = useState<"BANK_TRANSFER" | "CARD" | null>(null);
  const paymentMethod = chosenMethod
    ?? (quote?.bank_transfer_available ? "BANK_TRANSFER" : quote?.card_available ? "CARD" : null);
  const [otpCode, setOtpCode] = useState("");
  const [otpRequested, setOtpRequested] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [placedOrder, setPlacedOrder] = useState<AliexpressOrderRead | null>(null);
  const { add: addToCart } = useCartActions();
  const [cartMessage, setCartMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const { data: paymentInfo } = useQuery({
    queryKey: ["customer", "payment-info"],
    queryFn: fetchPaymentInfo,
    enabled: step === "bank_instructions",
  });

  const maxUsableCents = quote ? Math.min(quote.max_creditable_cents, quote.customer_wallet_balance_cents) : 0;
  const creditCents = quote && useCredit
    ? Math.max(0, Math.min(Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100), maxUsableCents))
    : 0;
  const residualCents = quote ? quote.amount_cents - creditCents : 0;
  const needsPaymentMethod = residualCents > 0;
  // Paying by bank transfer costs less (never a card surcharge). Same formula
  // as the server (rules.bank_transfer_discount_cents), which recomputes it
  // on the order anyway.
  const discountPercentage = quote?.bank_transfer_discount_percentage ?? product.bank_transfer_discount_percentage ?? 0;
  const bankDiscountCents = bankTransferDiscount(residualCents, discountPercentage);
  const payingByBank = needsPaymentMethod && paymentMethod === "BANK_TRANSFER";
  const totalDueCents = Math.max(residualCents, 0) - (payingByBank ? bankDiscountCents : 0);
  // Session 78: l'IVA si **aggiunge** al prezzo esposto, e il preventivo del
  // server la manda gia' calcolata dentro amount_cents. Qui non si scorpora
  // e non si somma niente: si mostra la riga che il server ha deciso.
  const vatPercentage = quote?.vat_percentage ?? marketplaceConfig?.vat_percentage ?? 0;
  const vatCents = quote?.vat_cents ?? 0;
  const noMethodAvailable = quote ? !quote.bank_transfer_available && !quote.card_available : false;
  // Quanto il cliente ha scritto, prima del taglio al massimo: serve solo a
  // dirgli che ha ecceduto, non a decidere l'importo.
  const typedCents = Math.max(0, Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100));
  const overTheCap = useCredit && typedCents > maxUsableCents;
  const addressComplete =
    address.recipient_name.trim().length >= 2 && address.recipient_phone.trim().length >= 6 &&
    address.address_line1.trim().length >= 3 && !!address.city.trim() && !!address.province.trim() &&
    address.postal_code.trim().length >= 3;

  function resetOtp() {
    setOtpRequested(false);
    setOtpCode("");
  }

  function changeQuantity(next: number) {
    setQuantity(Math.max(1, Math.min(MAX_QUANTITY, next)));
    setUseCredit(false);
    setCreditAmount("0.00");
    resetOtp();
  }

  async function handleConfirm() {
    if (!quote) return;
    setSubmitLoading(true);
    setSubmitError(null);
    try {
      const res = await fetch("/api/proxy/aliexpress/orders/mine", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          variant_id: variantId,
          quantity,
          address: {
            recipient_name: address.recipient_name.trim(),
            recipient_phone: address.recipient_phone.trim(),
            address_line1: address.address_line1.trim(),
            address_line2: address.address_line2.trim() || null,
            city: address.city.trim(),
            province: address.province.trim(),
            postal_code: address.postal_code.trim(),
          },
          credit_applied_cents: creditCents,
          otp_code: creditCents > 0 ? otpCode.trim() : null,
          payment_method: needsPaymentMethod ? paymentMethod : "BANK_TRANSFER",
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const order: AliexpressOrderRead = await res.json();
      setPlacedOrder(order);
      await queryClient.invalidateQueries({ queryKey: ["customer", "wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["customer", "orders"] });
      if (order.status === "PAID") {
        setStep("success");
        return;
      }
      if (order.payment_method === "CARD") {
        const returnUrl = window.location.href;
        const sessionRes = await fetch(
          `/api/proxy/aliexpress/orders/mine/${order.id}/checkout-session?success_url=${encodeURIComponent(returnUrl)}&cancel_url=${encodeURIComponent(returnUrl)}`,
          { method: "POST" }
        );
        if (!sessionRes.ok) throw new Error(await friendlyApiError(sessionRes));
        const { checkout_url } = await sessionRes.json();
        window.open(checkout_url, "_blank", "noopener,noreferrer");
        setStep("card_redirect");
        return;
      }
      setStep("bank_instructions");
    } catch (err: any) {
      setSubmitError(err.message || "Impossibile completare l'acquisto.");
    } finally {
      setSubmitLoading(false);
    }
  }

  const description = product.description || "";
  const longDescription = description.length > 280;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-3xl glass-card rounded-2xl border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[92vh] overflow-y-auto">
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-6 py-4 border-b border-white/5 light:border-slate-200 bg-slate-950/95 light:bg-white/95 backdrop-blur">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-wider text-orange-400">{shopLabel}</p>
            <h3 className="text-base font-bold text-white light:text-slate-900 truncate">
              {step === "product" ? product.name : step === "checkout" ? "Completa l'acquisto" : product.name}
            </h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 light:hover:bg-slate-900/10 text-slate-400 transition cursor-pointer" aria-label="Chiudi">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6">
          {step === "product" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-3">
                <div className="aspect-square rounded-2xl overflow-hidden border border-white/10 light:border-slate-200 bg-white">
                  <ProductThumbnail imageUrl={mainImage} alt={product.name} className="w-full h-full object-contain" />
                </div>
                {gallery.length > 1 && (
                  <div className="flex gap-2 overflow-x-auto pb-1">
                    {gallery.map((src, i) => (
                      <button
                        key={src}
                        type="button"
                        onClick={() => { setImageIndex(i); setImageOverride(null); }}
                        className={`w-14 h-14 shrink-0 rounded-lg overflow-hidden border-2 bg-white cursor-pointer transition ${
                          !imageOverride && i === imageIndex ? "border-orange-500" : "border-transparent opacity-70 hover:opacity-100"
                        }`}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element -- supplier images */}
                        <img src={src} alt="" className="w-full h-full object-cover" />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-4">
                <div>
                  <h2 className="text-xl font-bold text-white light:text-slate-900 leading-snug">{product.name}</h2>
                  <p className="text-3xl font-extrabold text-white light:text-slate-900 mt-2 tabular-nums">
                    {euro((variant?.price_cents ?? product.min_price_cents) * quantity)}
                  </p>
                  <p className="text-xs text-slate-400 light:text-slate-500 mt-0.5">
                    {quantity > 1 && variant ? `${euro(variant.price_cents)} cad. · ` : ""}
                    {product.shipping_included ? "Spedizione inclusa" : "+ spedizione, calcolata al checkout"}
                  </p>
                  {product.bank_transfer_discount_percentage > 0 && (
                    <div className="mt-2 inline-flex flex-col gap-0.5 px-3 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-[11px]">
                      <span className="text-emerald-400">
                        Con bonifico istantaneo -{product.bank_transfer_discount_percentage}%:{" "}
                        <strong className="tabular-nums">
                          {euro(
                            ((variant?.price_cents ?? product.min_price_cents) * quantity)
                              - bankTransferDiscount((variant?.price_cents ?? product.min_price_cents) * quantity, product.bank_transfer_discount_percentage)
                          )}
                        </strong>
                      </span>
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap gap-2 text-[11px]">
                  {product.shipping_days && (
                    <span className="px-2.5 py-1 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-400 font-semibold">
                      Consegna in {product.shipping_days} giorni
                    </span>
                  )}
                  {product.credit_discount_percentage > 0 && (
                    <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-semibold">
                      Paghi fino al {product.credit_discount_percentage}% in JavCash
                    </span>
                  )}
                </div>

                {product.variants.length > 1 && (
                  <div>
                    <p className="text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-2">Variante</p>
                    <div className="flex flex-wrap gap-2">
                      {product.variants.map((v) => (
                        <button
                          key={v.id}
                          type="button"
                          disabled={!v.in_stock}
                          onClick={() => { setVariantId(v.id); setImageOverride(v.image_url); }}
                          title={v.in_stock ? euro(v.price_cents) : "Non disponibile"}
                          className={`flex items-center gap-2 pl-1 pr-3 py-1 rounded-xl border text-xs font-semibold transition ${
                            !v.in_stock
                              ? "opacity-40 line-through cursor-not-allowed border-white/10 light:border-slate-300 text-slate-500"
                              : v.id === variantId
                                ? "cursor-pointer border-orange-500 bg-orange-500/10 text-white light:text-slate-900"
                                : "cursor-pointer border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:border-orange-500/50"
                          }`}
                        >
                          <span className="w-7 h-7 rounded-lg overflow-hidden bg-white shrink-0">
                            <ProductThumbnail imageUrl={v.image_url} alt="" className="w-full h-full object-cover" iconClassName="w-4 h-4 text-orange-400/40" />
                          </span>
                          {v.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <p className="text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-2">Quantità</p>
                  <div className="inline-flex items-center rounded-xl border border-white/10 light:border-slate-300 overflow-hidden">
                    <button type="button" onClick={() => changeQuantity(quantity - 1)} disabled={quantity <= 1} className="px-3.5 py-2 text-lg text-slate-300 light:text-slate-600 hover:bg-white/10 disabled:opacity-40 cursor-pointer">−</button>
                    <span className="w-10 text-center font-bold text-white light:text-slate-900 tabular-nums">{quantity}</span>
                    <button type="button" onClick={() => changeQuantity(quantity + 1)} disabled={quantity >= MAX_QUANTITY} className="px-3.5 py-2 text-lg text-slate-300 light:text-slate-600 hover:bg-white/10 disabled:opacity-40 cursor-pointer">+</button>
                  </div>
                </div>

                <div className="space-y-2">
                  {noLongerSold && (
                    <p className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300 light:text-rose-700">
                      Questo articolo non è più disponibile presso il fornitore e non si può acquistare. Lo togliamo
                      dal negozio.
                    </p>
                  )}
                  <button
                    type="button"
                    disabled={!variant || !variant.in_stock}
                    onClick={() => setStep("checkout")}
                    className="w-full px-4 py-3 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-sm font-bold text-white shadow-lg shadow-orange-500/20 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {variant && variant.in_stock ? "Acquista subito" : "Non disponibile"}
                  </button>
                  {/* Session 75: chi vuole comprare una cosa sola continua a
                      farlo in tre clic con «Acquista subito»; il carrello
                      serve a chi ne prende più d'una e paga una volta. */}
                  <button
                    type="button"
                    disabled={!variant || !variant.in_stock || addToCart.isPending}
                    onClick={() => {
                      if (!variant) return;
                      setCartMessage(null);
                      addToCart.mutate(
                        { shop: "aliexpress", variantId: variant.id, quantity },
                        {
                          onSuccess: () => setCartMessage({ ok: true, text: "Aggiunto al carrello." }),
                          onError: (err: unknown) =>
                            setCartMessage({ ok: false, text: (err as Error).message || "Non è stato possibile aggiungerlo." }),
                        },
                      );
                    }}
                    className="w-full px-4 py-2.5 rounded-xl border border-orange-500/40 text-sm font-semibold text-orange-400 hover:bg-orange-500/10 transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {addToCart.isPending ? "Aggiungo…" : "Aggiungi al carrello"}
                  </button>
                  {cartMessage && (
                    <p className={`text-[11px] ${cartMessage.ok ? "text-emerald-400" : "text-rose-400"}`}>
                      {cartMessage.text}
                    </p>
                  )}
                </div>

                {description && (
                  <div className="pt-3 border-t border-white/5 light:border-slate-200">
                    <p className="text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-1.5">Descrizione</p>
                    <p className={`text-xs text-slate-300 light:text-slate-600 whitespace-pre-line leading-relaxed ${!showFullDescription && longDescription ? "line-clamp-6" : ""}`}>
                      {description}
                    </p>
                    {longDescription && (
                      <button type="button" onClick={() => setShowFullDescription((v) => !v)} className="mt-1 text-[11px] font-semibold text-orange-400 hover:text-orange-300 cursor-pointer">
                        {showFullDescription ? "Mostra meno" : "Leggi tutto"}
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {step === "checkout" && (
            <div className="space-y-4">
              <button type="button" onClick={() => setStep("product")} className="text-xs font-semibold text-orange-400 hover:text-orange-300 cursor-pointer">
                ← Torna al prodotto
              </button>

              <div className="flex items-center gap-3 p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
                <div className="w-14 h-14 rounded-lg overflow-hidden bg-white shrink-0">
                  <ProductThumbnail imageUrl={variant?.image_url ?? product.image_url} alt="" className="w-full h-full object-cover" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-white light:text-slate-900 truncate">{product.name}</p>
                  <p className="text-xs text-slate-400 light:text-slate-500">{variant?.label} · {quantity} {quantity === 1 ? "pezzo" : "pezzi"}</p>
                </div>
              </div>

              {quoteError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{(quoteError as Error).message}</div>
              )}
              {!quote && !quoteError && (
                <div className="py-10 text-center text-sm text-slate-500">Calcolo della spedizione in corso...</div>
              )}

              {quote && (
                <>
                  <Section n={1} title="Dove lo spediamo?" done={addressComplete}>
                    <div className="grid grid-cols-1 sm:grid-cols-6 gap-3">
                      <Field label="Nome e cognome" className="sm:col-span-3">
                        <input className={inputClass} value={address.recipient_name} maxLength={50} autoComplete="name"
                          onChange={(e) => setAddress({ ...address, recipient_name: e.target.value })} />
                      </Field>
                      <Field label="Telefono (per il corriere)" className="sm:col-span-3">
                        <input className={inputClass} value={address.recipient_phone} maxLength={20} inputMode="tel" autoComplete="tel"
                          onChange={(e) => setAddress({ ...address, recipient_phone: e.target.value })} />
                      </Field>
                      <Field label="Indirizzo e numero civico" className="sm:col-span-4">
                        <input className={inputClass} value={address.address_line1} maxLength={255} autoComplete="address-line1"
                          onChange={(e) => setAddress({ ...address, address_line1: e.target.value })} />
                      </Field>
                      <Field label="Scala, interno (facoltativo)" className="sm:col-span-2">
                        <input className={inputClass} value={address.address_line2} maxLength={255} autoComplete="address-line2"
                          onChange={(e) => setAddress({ ...address, address_line2: e.target.value })} />
                      </Field>
                      <Field label="CAP" className="sm:col-span-2">
                        <input className={inputClass} value={address.postal_code} maxLength={12} inputMode="numeric" autoComplete="postal-code"
                          onChange={(e) => setAddress({ ...address, postal_code: e.target.value })} />
                      </Field>
                      <Field label="Città" className="sm:col-span-3">
                        <input className={inputClass} value={address.city} maxLength={50} autoComplete="address-level2"
                          onChange={(e) => setAddress({ ...address, city: e.target.value })} />
                      </Field>
                      <Field label="Provincia" className="sm:col-span-1">
                        <input className={inputClass} value={address.province} maxLength={50} placeholder="MI"
                          onChange={(e) => setAddress({ ...address, province: e.target.value.toUpperCase() })} />
                      </Field>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Spedizione in Italia{quote.shipping_days ? ` · consegna stimata in ${quote.shipping_days} giorni lavorativi` : ""}.
                    </p>
                  </Section>

                  {quote.max_creditable_cents > 0 && maxUsableCents > 0 && (
                    <Section n={2} title="Vuoi usare i tuoi JavCash?" done={creditCents > 0 && !!otpCode.trim()}>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => { const next = !useCredit; setUseCredit(next); setCreditAmount(next ? (maxUsableCents / 100).toFixed(2) : "0.00"); resetOtp(); }}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer ${
                            useCredit ? "bg-orange-600 border-orange-600 text-white" : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600"
                          }`}
                        >
                          {useCredit ? "Sì, uso i JavCash" : "Usa i JavCash"}
                        </button>
                        {/* Stessa cura del carrello (Session 76): quando il
                            saldo e' piu' basso del tetto del prodotto vanno
                            mostrati entrambi i numeri, dicendo quale dei due
                            ferma il cliente. */}
                        <span className="block w-full text-[11px] text-slate-500">
                          Questo prodotto concede fino a{" "}
                          <strong className="text-slate-300 light:text-slate-600">{javCash(quote.max_creditable_cents)}</strong>
                          {" "}({quote.credit_discount_percentage}% del suo prezzo): il resto lo paghi con bonifico o carta.
                        </span>
                        {quote.customer_wallet_balance_cents < quote.max_creditable_cents ? (
                          <div className="w-full flex items-start gap-2.5 p-3 rounded-xl bg-amber-500/10 border border-amber-500/30">
                            <svg className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                            </svg>
                            <div className="text-xs text-amber-200 light:text-amber-700 leading-relaxed">
                              <p className="font-bold text-amber-300 light:text-amber-800">
                                Puoi usarne al massimo {javCash(maxUsableCents)}
                              </p>
                              <p className="mt-0.5">
                                Questo prodotto ne concederebbe {javCash(quote.max_creditable_cents)}, ma nel tuo wallet
                                ce ne sono {javCash(quote.customer_wallet_balance_cents)}. Il resto lo paghi con bonifico o carta.
                              </p>
                            </div>
                          </div>
                        ) : (
                          <span className="block w-full text-[11px] text-slate-500">
                            Saldo {javCash(quote.customer_wallet_balance_cents)}: puoi usarli tutti fino a {javCash(maxUsableCents)}.
                          </span>
                        )}
                      </div>
                      {useCredit && (
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center gap-2">
                            {[0.25, 0.5, 1].map((f) => (
                              <button key={f} type="button"
                                onClick={() => { setCreditAmount(((Math.round(maxUsableCents * f)) / 100).toFixed(2)); resetOtp(); }}
                                className="px-2.5 py-1 rounded-lg text-[11px] font-semibold border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10 cursor-pointer">
                                {f === 1 ? "Massimo" : `${f * 100}%`}
                              </button>
                            ))}
                            <input inputMode="decimal" value={creditAmount}
                              onChange={(e) => { setCreditAmount(e.target.value); resetOtp(); }}
                              className={`w-28 rounded-lg glass-input px-3 py-1.5 text-sm ${overTheCap ? "border-rose-500 text-rose-300" : ""}`} />
                            <span className="text-xs text-slate-500">JavCash</span>
                          </div>
                          {/* Fermare, non correggere di nascosto: il pulsante
                              del codice resta spento finché l'importo non
                              rientra. Il server ricontrolla comunque. */}
                          {overTheCap && (
                            <div className="flex items-start gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30">
                              <svg className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                              </svg>
                              <div className="text-xs text-rose-300 leading-relaxed">
                                <p className="font-bold">Hai scritto {javCash(typedCents)}, ma non puoi usarne così tanti.</p>
                                <p className="mt-0.5">
                                  {quote.customer_wallet_balance_cents < quote.max_creditable_cents
                                    ? `Nel tuo wallet ci sono ${javCash(quote.customer_wallet_balance_cents)}.`
                                    : `Su questo ordine il massimo è ${javCash(quote.max_creditable_cents)}.`}{" "}
                                  <button type="button"
                                    onClick={() => { setCreditAmount((maxUsableCents / 100).toFixed(2)); resetOtp(); }}
                                    className="font-bold underline underline-offset-2 hover:text-rose-200 cursor-pointer">
                                    Usa il massimo ({javCash(maxUsableCents)})
                                  </button>
                                </p>
                              </div>
                            </div>
                          )}
                          {creditCents > 0 && !overTheCap && (
                            <JavCashConfirmCode
                              requestUrl="/api/proxy/aliexpress/orders/mine/request-credit-otp"
                              requestBody={{ variant_id: variantId, quantity, credit_applied_cents: creditCents }}
                              code={otpCode}
                              onCodeChange={setOtpCode}
                              requested={otpRequested}
                              onRequestedChange={setOtpRequested}
                            />
                          )}
                        </div>
                      )}
                    </Section>
                  )}

                  {needsPaymentMethod && (
                    <Section n={quote.max_creditable_cents > 0 && maxUsableCents > 0 ? 3 : 2} title="Come vuoi pagare?" done={!!paymentMethod}>
                      {noMethodAvailable ? (
                        <p className="text-xs text-rose-400">Nessun metodo di pagamento disponibile. Contatta l&apos;assistenza.</p>
                      ) : (
                        <div className="space-y-2">
                          <div className="flex gap-2.5">
                            {quote.bank_transfer_available && (
                              <button type="button" onClick={() => setPaymentMethod("BANK_TRANSFER")}
                                className={`relative flex-1 px-3 py-3 rounded-xl text-sm font-semibold border-2 transition cursor-pointer text-left ${
                                  paymentMethod === "BANK_TRANSFER" ? "bg-orange-600 border-orange-600 text-white" : "bg-white/5 light:bg-slate-900/5 border-emerald-500/40 text-slate-300 light:text-slate-600"
                                }`}>
                                {bankDiscountCents > 0 && (
                                  <span className="absolute -top-2 right-2 px-1.5 py-0.5 rounded-md bg-emerald-500 text-white text-[9px] font-bold uppercase tracking-wide">
                                    Sconto {discountPercentage}%
                                  </span>
                                )}
                                <span className="block">Bonifico istantaneo</span>
                                <span className="block text-base font-extrabold tabular-nums">{euro(residualCents - bankDiscountCents)}</span>
                              </button>
                            )}
                            {quote.card_available && (
                              <button type="button" onClick={() => setPaymentMethod("CARD")}
                                className={`flex-1 px-3 py-3 rounded-xl text-sm font-semibold border-2 transition cursor-pointer text-left ${
                                  paymentMethod === "CARD" ? "bg-orange-600 border-orange-600 text-white" : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600"
                                }`}>
                                <span className="block">Carta di credito</span>
                                <span className="block text-base font-extrabold tabular-nums">{euro(residualCents)}</span>
                              </button>
                            )}
                          </div>
                          {bankDiscountCents > 0 && quote.bank_transfer_available && (
                            <p className="text-[11px] text-emerald-400">
                              Pagando con bonifico istantaneo hai uno sconto del {discountPercentage}% (-{euro(bankDiscountCents)}).
                            </p>
                          )}
                        </div>
                      )}
                    </Section>
                  )}

                  <div className="p-4 rounded-xl bg-gradient-to-br from-orange-600/10 to-amber-500/5 border border-orange-500/20 space-y-1.5 text-xs">
                    <div className="flex justify-between text-slate-400 light:text-slate-500">
                      <span>{quote.quantity} × {euro(quote.unit_price_cents)}</span><span>{euro(quote.items_cents)}</span>
                    </div>
                    <div className="flex justify-between text-slate-400 light:text-slate-500">
                      <span>Spedizione</span><span>{quote.shipping_included || quote.shipping_cents === 0 ? "Inclusa" : euro(quote.shipping_cents)}</span>
                    </div>
                    {creditCents > 0 && (
                      <div className="flex justify-between text-emerald-400">
                        <span>JavCash usati</span><span>-{javCash(creditCents)}</span>
                      </div>
                    )}
                    {payingByBank && bankDiscountCents > 0 && (
                      <div className="flex justify-between text-emerald-400">
                        <span>Sconto pagamento con bonifico (-{discountPercentage}%)</span><span>-{euro(bankDiscountCents)}</span>
                      </div>
                    )}
                    {/* L'IVA sta nell'elenco, sopra il totale, non appesa
                        sotto: e' il posto dove il cliente legge le voci. Non e'
                        un addendo -- e' gia' dentro i prezzi qui sopra -- e la
                        dicitura lo dice, perche' pagando in JavCash puo'
                        risultare piu' alta del totale da pagare. */}
                    {vatCents > 0 && (
                      <div className="flex justify-between text-slate-400 light:text-slate-500">
                        <span>{vatLineLabel(vatPercentage)}</span><span className="tabular-nums">{euro(vatCents)}</span>
                      </div>
                    )}
                    <div className="flex items-center justify-between pt-1.5 border-t border-white/10 light:border-slate-300">
                      <span className="text-sm font-bold text-white light:text-slate-900">Totale da pagare</span>
                      <span className={`text-xl font-extrabold tabular-nums ${residualCents > 0 ? "text-orange-400" : "text-emerald-400"}`}>
                        {quoteLoading ? "…" : euro(totalDueCents)}
                      </span>
                    </div>
                  </div>

                  {submitError && (
                    <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{submitError}</div>
                  )}

                  <button
                    onClick={handleConfirm}
                    disabled={
                      submitLoading || !addressComplete || quoteLoading
                      || (needsPaymentMethod && (noMethodAvailable || !paymentMethod))
                      || (creditCents > 0 && !otpCode.trim())
                      || overTheCap
                    }
                    className="w-full px-4 py-3 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-sm font-bold text-white shadow-lg shadow-orange-500/20 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {submitLoading ? "Elaborazione..." : residualCents > 0 ? "Conferma e paga" : "Conferma ordine"}
                  </button>
                  {!addressComplete && (
                    <p className="text-[11px] text-slate-500 text-center">Completa l&apos;indirizzo di spedizione per continuare.</p>
                  )}
                </>
              )}
            </div>
          )}

          {step === "success" && placedOrder && (
            <div className="text-center py-8 space-y-3">
              <p className="text-4xl">🎉</p>
              <p className="text-sm text-slate-300 light:text-slate-600">
                Ordine confermato, pagato con i tuoi JavCash. Ti avvisiamo appena parte: lo segui da &ldquo;I miei Ordini&rdquo;.
              </p>
              <button onClick={onClose} className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer">Chiudi</button>
            </div>
          )}

          {step === "card_redirect" && placedOrder && (
            <div className="text-center py-8 space-y-3">
              <p className="text-sm text-slate-300 light:text-slate-600">
                Abbiamo aperto il pagamento con carta in una nuova scheda: <strong className="text-orange-400">{euro(placedOrder.amount_due_cents)}</strong>.
              </p>
              <p className="text-xs text-slate-500">L&apos;ordine è anche in &ldquo;I miei Ordini&rdquo;, dove puoi pagarlo e seguirne la spedizione.</p>
              <button onClick={onClose} className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer">Chiudi</button>
            </div>
          )}

          {step === "bank_instructions" && placedOrder && (
            <div className="space-y-3">
              <p className="text-sm text-slate-300 light:text-slate-600">
                Ordine creato. Paga <strong className="text-orange-400">{euro(placedOrder.amount_due_cents)}</strong> con bonifico: lo spediamo appena riceviamo il pagamento.
              </p>
              <div className="p-4 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200 text-xs space-y-1.5">
                {paymentInfo?.iban ? (
                  <>
                    <p><span className="text-slate-500">IBAN:</span> <span className="font-mono">{paymentInfo.iban}</span></p>
                    <p><span className="text-slate-500">Intestatario:</span> {paymentInfo.holder}</p>
                    {paymentInfo.instructions && <p className="text-slate-400 light:text-slate-500 pt-1">{paymentInfo.instructions}</p>}
                  </>
                ) : (
                  <p className="text-slate-500">Contatta l&apos;amministrazione per le coordinate bancarie.</p>
                )}
                <p className="pt-1"><span className="text-slate-500">Causale:</span> <span className="font-mono text-orange-400">Ordine {placedOrder.id.slice(0, 8).toUpperCase()}</span></p>
              </div>
              <button onClick={onClose} className="w-full px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer">Ho capito</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
