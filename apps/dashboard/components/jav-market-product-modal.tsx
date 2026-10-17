"use client";

import { useState } from "react";
import { AthletePicker } from "@/components/club/athlete-picker";
import { celebrate } from "@/lib/motion";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { useMarketplaceConfig } from "@/components/marketplace-rules-card";
import { useCartActions } from "@/components/shop-cart";
import { vatLineLabel } from "@/lib/product-audience";
import type { CustomerRead, JavMarketOrderRead, JavMarketProductRead, MarketQuoteRead } from "@/lib/types";
import { JavCashConfirmCode } from "@/components/javcash-confirm-code";
import { AddressFields, javCash as javCashIn } from "@/components/marketplace-checkout-bits";
import { useI18n } from "@/lib/i18n/provider";

const MAX_QUANTITY = 10;

/** Mirrors rules.bank_transfer_discount_cents: % of the residual, half up to the cent. */
function bankTransferDiscount(residualCents: number, percentage: number): number {
  if (residualCents <= 0 || percentage <= 0) return 0;
  return Math.floor((residualCents * percentage + 50) / 100);
}

async function fetchQuote(variantId: string, quantity: number): Promise<MarketQuoteRead> {
  const res = await fetch(`/api/proxy/jav-market/orders/quote/mine?variant_id=${variantId}&quantity=${quantity}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

async function fetchMyCustomer(): Promise<CustomerRead | null> {
  const res = await fetch("/api/proxy/customers/me");
  if (!res.ok) return null;
  return res.json();
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string; instructions: string | null }> {
  const res = await fetch("/api/proxy/organizations/me/payment-info");
  if (!res.ok) throw new Error("payment-info");
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

function Section({ n, title, done, children }: { n: number; title: string; done?: boolean; children: React.ReactNode }) {
  return (
    <div className="p-4 rounded-xl border border-slate-200 space-y-3">
      <div className="flex items-center gap-2.5">
        <span className={`flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-bold shrink-0 text-white ${done ? "bg-emerald-500" : "bg-brand-600"}`}>
          {done ? "✓" : n}
        </span>
        <p className="text-sm font-semibold text-slate-900">{title}</p>
      </div>
      {children}
    </div>
  );
}

/** «Fai la Spesa con Jav» (Session 79): scheda prodotto e checkout in una
 *  finestra -- photos, variants, quantity, then JavCash with an email code
 *  (never the whole price), bonifico istantaneo for the rest, and the
 *  delivery address. Every amount is recomputed by the server.
 */
export function JavMarketProductModal({ product, onClose }: { product: JavMarketProductRead; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const javCash = (cents: number) => javCashIn(cents, fmt.tag);
  const queryClient = useQueryClient();
  const { data: marketplaceConfig } = useMarketplaceConfig();
  const shopLabel = marketplaceConfig?.labels.jav_market ?? t("shopx.cart.labelJavMarket");
  const firstAvailable = product.variants.find((v) => v.in_stock) ?? product.variants[0];
  const [variantId, setVariantId] = useState<string>(firstAvailable?.id ?? "");
  const [quantity, setQuantity] = useState(1);
  const [imageIndex, setImageIndex] = useState(0);
  const [imageOverride, setImageOverride] = useState<string | null>(null);
  const [showFullDescription, setShowFullDescription] = useState(false);
  const [step, setStep] = useState<"product" | "checkout" | "bank_instructions" | "success">("product");

  const variant = product.variants.find((v) => v.id === variantId) ?? null;
  const gallery = product.images.length > 0 ? product.images : product.image_url ? [product.image_url] : [];
  const mainImage = imageOverride ?? gallery[imageIndex] ?? null;

  const { data: quote, error: quoteError, isFetching: quoteLoading } = useQuery({
    queryKey: ["customer", "jav-market", "quote", variantId, quantity],
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
  // Si paga solo con bonifico: se l'IBAN non è configurato non c'è modo.
  const paymentMethod = quote?.bank_transfer_available ? "BANK_TRANSFER" : null;
  const [otpCode, setOtpCode] = useState("");
  const [otpRequested, setOtpRequested] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [placedOrder, setPlacedOrder] = useState<JavMarketOrderRead | null>(null);
  // The family athlete the equipment is for (docs/club-portal.md); optional.
  const [athleteId, setAthleteId] = useState<string | null>(null);
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
  // Paying by bank transfer may carry a discount. Same formula
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
  const noMethodAvailable = quote ? !quote.bank_transfer_available : false;
  // «Fai la Spesa» ha un ordine minimo: il server rifiuterebbe comunque,
  // qui lo si dice prima e non si lascia premere il pulsante.
  const belowMinimum = (quote?.min_order_missing_cents ?? 0) > 0;
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
      const res = await fetch("/api/proxy/jav-market/orders/mine", {
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
          athlete_id: athleteId,
          credit_applied_cents: creditCents,
          otp_code: creditCents > 0 ? otpCode.trim() : null,
          payment_method: needsPaymentMethod ? paymentMethod : "BANK_TRANSFER",
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const order: JavMarketOrderRead = await res.json();
      void celebrate();
      setPlacedOrder(order);
      await queryClient.invalidateQueries({ queryKey: ["customer", "wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["customer", "orders"] });
      if (order.status === "PAID") {
        setStep("success");
        return;
      }
      setStep("bank_instructions");
    } catch (err: any) {
      setSubmitError(err.message || t("shopx.checkout.failed"));
    } finally {
      setSubmitLoading(false);
    }
  }

  const description = product.description || "";
  const longDescription = description.length > 280;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-3xl glass-card rounded-2xl border-slate-300 bg-white animate-scale-up max-h-[92vh] overflow-y-auto">
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-6 py-4 border-b border-slate-200 bg-white/95 backdrop-blur">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-wider text-brand-600">{shopLabel}</p>
            <h3 className="text-base font-bold text-slate-900 truncate">
              {step === "product" ? product.name : step === "checkout" ? t("shopx.checkout.title") : product.name}
            </h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-900/10 text-slate-400 transition cursor-pointer" aria-label={t("common.close")}>
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6">
          {step === "product" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-3">
                <div className="aspect-square rounded-2xl overflow-hidden border border-slate-200 bg-white">
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
                          !imageOverride && i === imageIndex ? "border-brand-500" : "border-transparent opacity-70 hover:opacity-100"
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
                  <h2 className="text-xl font-bold text-slate-900 leading-snug">{product.name}</h2>
                  <p className="text-3xl font-extrabold text-slate-900 mt-2 tabular-nums">
                    {euro((variant?.price_cents ?? product.min_price_cents) * quantity)}
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {quantity > 1 && variant ? `${t("shopx.product.each", { price: euro(variant.price_cents) })} · ` : ""}
                    {product.shipping_included ? t("shopx.product.shippingIncluded") : t("shopx.product.shippingAtCheckout")}
                  </p>
                  {product.bank_transfer_discount_percentage > 0 && (
                    <div className="mt-2 inline-flex flex-col gap-0.5 px-3 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-[11px]">
                      <span className="text-emerald-400">
                        {t("shopx.product.withInstantTransfer", { pct: product.bank_transfer_discount_percentage })}{" "}
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
                      {t("shopx.product.deliveryDays", { days: product.shipping_days })}
                    </span>
                  )}
                  {product.credit_discount_percentage > 0 && (
                    <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-semibold">
                      {t("shopx.product.payUpToJavCash", { pct: product.credit_discount_percentage })}
                    </span>
                  )}
                  {(product.min_order_cents ?? 0) > 0 && (
                    <span className="px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-700 font-semibold">
                      {t("shopx.product.minOrder", { amount: euro(product.min_order_cents ?? 0) })}
                    </span>
                  )}
                  {product.free_shipping_threshold_cents != null && (
                    <span className="px-2.5 py-1 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-400 font-semibold">
                      {product.shipping_flat_cents ? t("shopx.product.shippingFlatFreeFrom", { flat: euro(product.shipping_flat_cents), amount: euro(product.free_shipping_threshold_cents) }) : t("shopx.product.freeFrom", { amount: euro(product.free_shipping_threshold_cents) })}
                    </span>
                  )}
                </div>

                {product.variants.length > 1 && (
                  <div>
                    <p className=" font-semibold text-slate-500 uppercase tracking-wide mb-2">{t("shopx.club.variant")}</p>
                    <div className="flex flex-wrap gap-2">
                      {product.variants.map((v) => (
                        <button
                          key={v.id}
                          type="button"
                          disabled={!v.in_stock}
                          onClick={() => { setVariantId(v.id); setImageOverride(v.image_url); }}
                          title={v.in_stock ? euro(v.price_cents) : t("shopx.product.unavailable")}
                          className={`flex items-center gap-2 pl-1 pr-3 py-1 rounded-xl border text-xs font-semibold transition ${
                            !v.in_stock
                              ? "opacity-40 line-through cursor-not-allowed border-slate-300 text-slate-500"
                              : v.id === variantId
                                ? "cursor-pointer border-brand-500 bg-brand-500/10 text-slate-900"
                                : "cursor-pointer border-slate-300 text-slate-600 hover:border-brand-500/50"
                          }`}
                        >
                          <span className="w-7 h-7 rounded-lg overflow-hidden bg-white shrink-0">
                            <ProductThumbnail imageUrl={v.image_url} alt="" className="w-full h-full object-cover" iconClassName="w-4 h-4 text-brand-600/40" />
                          </span>
                          {v.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <p className=" font-semibold text-slate-500 uppercase tracking-wide mb-2">{t("shopx.product.quantity")}</p>
                  <div className="inline-flex items-center rounded-xl border border-slate-300 overflow-hidden">
                    <button type="button" onClick={() => changeQuantity(quantity - 1)} disabled={quantity <= 1} className="px-3.5 py-2 text-lg text-slate-600 hover:bg-slate-100 disabled:opacity-40 cursor-pointer">−</button>
                    <span className="w-10 text-center font-bold text-slate-900 tabular-nums">{quantity}</span>
                    <button type="button" onClick={() => changeQuantity(quantity + 1)} disabled={quantity >= MAX_QUANTITY} className="px-3.5 py-2 text-lg text-slate-600 hover:bg-slate-100 disabled:opacity-40 cursor-pointer">+</button>
                  </div>
                </div>

                {product.purchasable === false ? (
                  <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200">
                    🛍️ {t("shopx.product.comingSoon")}
                  </p>
                ) : (
                <div className="space-y-2">
                  <button
                    type="button"
                    disabled={!variant || !variant.in_stock}
                    onClick={() => setStep("checkout")}
                    className="w-full px-4 py-3 rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 text-sm font-bold text-white shadow-lg shadow-brand-500/20 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {variant && variant.in_stock ? t("shopx.product.buyNow") : t("shopx.product.unavailable")}
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
                        { shop: "jav_market", variantId: variant.id, quantity },
                        {
                          onSuccess: () => setCartMessage({ ok: true, text: t("shopx.product.addedToCart") }),
                          onError: (err: unknown) =>
                            setCartMessage({ ok: false, text: (err as Error).message || t("shopx.product.addFailed") }),
                        },
                      );
                    }}
                    className="w-full px-4 py-2.5 rounded-xl border border-brand-500/40 text-sm font-semibold text-brand-600 hover:bg-brand-500/10 transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {addToCart.isPending ? t("shopx.product.adding") : t("shopx.product.addToCart")}
                  </button>
                  {cartMessage && (
                    <p className={`text-[11px] ${cartMessage.ok ? "text-emerald-400" : "text-rose-400"}`}>
                      {cartMessage.text}
                    </p>
                  )}
                </div>
                )}

                {product.producer && (
                  <div className="p-3 rounded-xl bg-slate-900/5 border border-slate-200">
                    <p className=" font-semibold text-slate-500 uppercase tracking-wide mb-1">
                      {t("shopx.product.producedBy")}
                    </p>
                    <p className="text-sm font-semibold text-slate-900">{product.producer.name}</p>
                    {product.producer.description && (
                      <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                        {product.producer.description}
                      </p>
                    )}
                    {product.producer.website_url && (
                      <a
                        href={product.producer.website_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-block mt-1.5 text-[11px] font-semibold text-brand-600 hover:text-brand-600"
                      >
                        {t("shopx.product.companySite")} →
                      </a>
                    )}
                  </div>
                )}

                {description && (
                  <div className="pt-3 border-t border-slate-200">
                    <p className=" font-semibold text-slate-500 uppercase tracking-wide mb-1.5">{t("shopx.club.description")}</p>
                    <p className={`text-xs text-slate-600 whitespace-pre-line leading-relaxed ${!showFullDescription && longDescription ? "line-clamp-6" : ""}`}>
                      {description}
                    </p>
                    {longDescription && (
                      <button type="button" onClick={() => setShowFullDescription((v) => !v)} className="mt-1 text-[11px] font-semibold text-brand-600 hover:text-brand-600 cursor-pointer">
                        {showFullDescription ? t("shopx.product.showLess") : t("shopx.product.readAll")}
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {step === "checkout" && (
            <div className="space-y-4">
              <button type="button" onClick={() => setStep("product")} className="text-xs font-semibold text-brand-600 hover:text-brand-600 cursor-pointer">
                ← {t("shopx.product.backToProduct")}
              </button>
              <AthletePicker value={athleteId} onChange={setAthleteId} />

              <div className="flex items-center gap-3 p-3 rounded-xl bg-slate-900/5 border border-slate-200">
                <div className="w-14 h-14 rounded-lg overflow-hidden bg-white shrink-0">
                  <ProductThumbnail imageUrl={variant?.image_url ?? product.image_url} alt="" className="w-full h-full object-cover" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-900 truncate">{product.name}</p>
                  <p className="text-xs text-slate-500">{variant?.label} · {quantity === 1 ? t("shopx.pieces.one", { n: quantity }) : t("shopx.pieces.many", { n: quantity })}</p>
                </div>
              </div>

              {quoteError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{(quoteError as Error).message}</div>
              )}
              {!quote && !quoteError && (
                <div className="py-10 text-center text-sm text-slate-500">{t("shopx.product.calcShipping")}</div>
              )}

              {quote && (
                <>
                  <Section n={1} title={t("shopx.checkout.whereShip")} done={addressComplete}>
                    <AddressFields address={address} onChange={setAddress} />
                    <p className="text-[11px] text-slate-500">
                      {quote.shipping_days ? t("shopx.checkout.shippingItalyDays", { days: quote.shipping_days }) : t("shopx.checkout.shippingItaly")}
                    </p>
                  </Section>

                  {quote.max_creditable_cents > 0 && maxUsableCents > 0 && (
                    <Section n={2} title={t("shopx.checkout.useJavCashQ")} done={creditCents > 0 && !!otpCode.trim()}>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => { const next = !useCredit; setUseCredit(next); setCreditAmount(next ? (maxUsableCents / 100).toFixed(2) : "0.00"); resetOtp(); }}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer ${
                            useCredit ? "bg-brand-600 border-brand-600 text-white" : " bg-slate-900/5 border-slate-300 text-slate-600"
                          }`}
                        >
                          {useCredit ? t("shopx.checkout.usingJavCash") : t("shopx.checkout.useJavCash")}
                        </button>
                        {/* Stessa cura del carrello (Session 76): quando il
                            saldo e' piu' basso del tetto del prodotto vanno
                            mostrati entrambi i numeri, dicendo quale dei due
                            ferma il cliente. */}
                        <span className="block w-full text-[11px] text-slate-500">
                          {t("shopx.product.allowUpTo")}{" "}
                          <strong className=" text-slate-600">{javCash(quote.max_creditable_cents)}</strong>
                          {" "}{t("shopx.product.allowPctRest", { pct: quote.credit_discount_percentage })}
                        </span>
                        {quote.customer_wallet_balance_cents < quote.max_creditable_cents ? (
                          <div className="w-full flex items-start gap-2.5 p-3 rounded-xl bg-amber-500/10 border border-amber-500/30">
                            <svg className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                            </svg>
                            <div className="text-xs text-amber-700 leading-relaxed">
                              <p className="font-bold text-amber-800">
                                {t("shopx.checkout.maxUsable", { amount: javCash(maxUsableCents) })}
                              </p>
                              <p className="mt-0.5">
                                {t("shopx.product.walletShort", { allowed: javCash(quote.max_creditable_cents), balance: javCash(quote.customer_wallet_balance_cents) })}
                              </p>
                            </div>
                          </div>
                        ) : (
                          <span className="block w-full text-[11px] text-slate-500">
                            {t("shopx.checkout.balanceAll", { balance: javCash(quote.customer_wallet_balance_cents), amount: javCash(maxUsableCents) })}
                          </span>
                        )}
                      </div>
                      {useCredit && (
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center gap-2">
                            {[0.25, 0.5, 1].map((f) => (
                              <button key={f} type="button"
                                onClick={() => { setCreditAmount(((Math.round(maxUsableCents * f)) / 100).toFixed(2)); resetOtp(); }}
                                className="px-2.5 py-1 rounded-lg font-semibold border border-slate-300 text-slate-600 hover:bg-slate-100 cursor-pointer">
                                {f === 1 ? t("shopx.checkout.max") : `${f * 100}%`}
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
                                <p className="font-bold">{t("shopx.checkout.overCap", { amount: javCash(typedCents) })}</p>
                                <p className="mt-0.5">
                                  {quote.customer_wallet_balance_cents < quote.max_creditable_cents
                                    ? t("shopx.checkout.walletHas", { amount: javCash(quote.customer_wallet_balance_cents) })
                                    : t("shopx.checkout.orderMax", { amount: javCash(quote.max_creditable_cents) })}{" "}
                                  <button type="button"
                                    onClick={() => { setCreditAmount((maxUsableCents / 100).toFixed(2)); resetOtp(); }}
                                    className="font-bold underline underline-offset-2 hover:text-rose-200 cursor-pointer">
                                    {t("shopx.checkout.useMax", { amount: javCash(maxUsableCents) })}
                                  </button>
                                </p>
                              </div>
                            </div>
                          )}
                          {creditCents > 0 && !overTheCap && (
                            <JavCashConfirmCode
                              requestUrl="/api/proxy/jav-market/orders/mine/request-credit-otp"
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
                    <Section n={quote.max_creditable_cents > 0 && maxUsableCents > 0 ? 3 : 2} title={t("shopx.checkout.howPay")} done={!!paymentMethod}>
                      {noMethodAvailable ? (
                        <p className="text-xs text-rose-400">{t("shopx.product.noMethod")}</p>
                      ) : (
                        <div className="space-y-2">
                          <div className="flex gap-2.5">
                            {quote.bank_transfer_available && (
                              <div className="relative flex-1 px-3 py-3 rounded-xl text-sm font-semibold border-2 text-left bg-brand-600 border-brand-600 text-white">
                                {bankDiscountCents > 0 && (
                                  <span className="absolute -top-2 right-2 px-1.5 py-0.5 rounded-md bg-emerald-500 text-white text-[9px] font-bold uppercase tracking-wide">
                                    {t("shopx.product.discountPct", { pct: discountPercentage })}
                                  </span>
                                )}
                                <span className="block">{t("shopx.checkout.instantTransfer")}</span>
                                <span className="block text-base font-extrabold tabular-nums">{euro(residualCents - bankDiscountCents)}</span>
                              </div>
                            )}
                          </div>
                          {bankDiscountCents > 0 && quote.bank_transfer_available && (
                            <p className="text-[11px] text-emerald-400">
                              {t("shopx.product.instantDiscount", { pct: discountPercentage, amount: euro(bankDiscountCents) })}
                            </p>
                          )}
                        </div>
                      )}
                    </Section>
                  )}

                  <div className="p-4 rounded-xl bg-gradient-to-br from-brand-600/10 to-brand-400/5 border border-brand-500/20 space-y-1.5 text-xs">
                    <div className="flex justify-between text-slate-500">
                      <span>{quote.quantity} × {euro(quote.unit_price_cents)}</span><span>{euro(quote.items_cents)}</span>
                    </div>
                    <div className="flex justify-between text-slate-500">
                      <span>{t("shopx.checkout.shipping")}</span><span>{quote.free_shipping ? t("shopx.checkout.free") : quote.shipping_included || quote.shipping_cents === 0 ? t("shopx.checkout.included") : euro(quote.shipping_cents)}</span>
                    </div>
                    {(quote.free_shipping_missing_cents ?? 0) > 0 && (
                      <p className="text-[11px] text-sky-400">
                        {t("shopx.checkout.freeShippingMissing", { amount: euro(quote.free_shipping_missing_cents ?? 0) })}
                      </p>
                    )}
                    {creditCents > 0 && (
                      <div className="flex justify-between text-emerald-400">
                        <span>{t("shopx.checkout.javCashUsed")}</span><span>-{javCash(creditCents)}</span>
                      </div>
                    )}
                    {payingByBank && bankDiscountCents > 0 && (
                      <div className="flex justify-between text-emerald-400">
                        <span>{t("shopx.checkout.bankDiscount", { pct: discountPercentage })}</span><span>-{euro(bankDiscountCents)}</span>
                      </div>
                    )}
                    {/* L'IVA sta nell'elenco, sopra il totale, non appesa
                        sotto: e' il posto dove il cliente legge le voci. Non e'
                        un addendo -- e' gia' dentro i prezzi qui sopra -- e la
                        dicitura lo dice, perche' pagando in JavCash puo'
                        risultare piu' alta del totale da pagare. */}
                    {vatCents > 0 && (
                      <div className="flex justify-between text-slate-500">
                        <span>{vatLineLabel(vatPercentage)}</span><span className="tabular-nums">{euro(vatCents)}</span>
                      </div>
                    )}
                    <div className="flex items-center justify-between pt-1.5 border-t border-slate-300">
                      <span className="text-sm font-bold text-slate-900">{t("shopx.checkout.totalDue")}</span>
                      <span className={`text-xl font-extrabold tabular-nums ${residualCents > 0 ? "text-brand-600" : "text-emerald-400"}`}>
                        {quoteLoading ? "…" : euro(totalDueCents)}
                      </span>
                    </div>
                  </div>

                  {belowMinimum && quote && (
                    <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 text-xs">
                      {t("shopx.product.belowMinimum", { min: euro(quote.min_order_cents ?? 0), missing: euro(quote.min_order_missing_cents ?? 0) })}
                    </div>
                  )}

                  {submitError && (
                    <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{submitError}</div>
                  )}

                  <button
                    onClick={handleConfirm}
                    disabled={
                      submitLoading || !addressComplete || quoteLoading || belowMinimum
                      || (needsPaymentMethod && (noMethodAvailable || !paymentMethod))
                      || (creditCents > 0 && !otpCode.trim())
                      || overTheCap
                    }
                    className="w-full px-4 py-3 rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 text-sm font-bold text-white shadow-lg shadow-brand-500/20 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {submitLoading ? t("shopx.checkout.processing") : residualCents > 0 ? t("shopx.checkout.confirmPay") : t("shopx.checkout.confirmOrder")}
                  </button>
                  {!addressComplete && (
                    <p className="text-[11px] text-slate-500 text-center">{t("shopx.product.completeAddress")}</p>
                  )}
                </>
              )}
            </div>
          )}

          {step === "success" && placedOrder && (
            <div className="text-center py-8 space-y-3">
              <p className="text-4xl">🎉</p>
              <p className="text-sm text-slate-600">
                {t("shopx.checkout.paidWithJavCash")}
              </p>
              <button onClick={onClose} className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer">{t("common.close")}</button>
            </div>
          )}

          {step === "bank_instructions" && placedOrder && (
            <div className="space-y-3">
              <p className="text-sm text-slate-600">
                {t("shopx.checkout.createdPay")} <strong className="text-brand-600">{euro(placedOrder.amount_due_cents)}</strong> {t("shopx.checkout.createdPayTail")}
              </p>
              <div className="p-4 rounded-xl bg-slate-900/5 border border-slate-200 text-xs space-y-1.5">
                {paymentInfo?.iban ? (
                  <>
                    <p><span className="text-slate-500">IBAN:</span> <span className="font-mono">{paymentInfo.iban}</span></p>
                    <p><span className="text-slate-500">{t("shopx.bank.holder")}</span> {paymentInfo.holder}</p>
                    {paymentInfo.instructions && <p className=" text-slate-500 pt-1">{paymentInfo.instructions}</p>}
                  </>
                ) : (
                  <p className="text-slate-500">{t("shopx.bank.contactAdmin")}</p>
                )}
                <p className="pt-1"><span className="text-slate-500">{t("shopx.bank.reference")}</span> <span className="font-mono text-brand-600">{t("shopx.bank.referenceValue", { code: placedOrder.id.slice(0, 8).toUpperCase() })}</span></p>
              </div>
              <button onClick={onClose} className="w-full px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer">{t("shopx.gotIt")}</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
