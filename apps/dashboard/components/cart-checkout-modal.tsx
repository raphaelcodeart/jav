"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { useMarketplaceConfig } from "@/components/marketplace-rules-card";
import { useCartActions } from "@/components/shop-cart";
import {
  AddressFields,
  DeliveryAddress,
  Section,
  addressComplete,
  bankTransferDiscount,
  euro,
  inputClass,
  javCash,
} from "@/components/marketplace-checkout-bits";
import { vatLineLabel } from "@/lib/product-audience";
import type { AliexpressOrderRead, CartSectionRead, CustomerRead } from "@/lib/types";
import { JavCashConfirmCode } from "@/components/javcash-confirm-code";

/** Il checkout del carrello (Session 75).
 *
 *  Un ordine solo per tutte le righe di un negozio: una spedizione, un
 *  pagamento, un codice OTP. Il browser non manda mai cosa si sta
 *  comprando -- lo legge il server dal carrello di chi ha fatto la
 *  richiesta -- né quanto costa: ogni importo qui è un'anteprima di ciò che
 *  il server ricalcola e congela sull'ordine.
 *
 *  Oggi serve AliExpress. Quando CJ e Shopify avranno il carrello, le rotte
 *  cambiano di prefisso e il resto resta questo: è il motivo per cui il
 *  negozio arriva come proprietà invece di essere scritto qui dentro. */

type Step = "checkout" | "bank_instructions" | "card_redirect" | "success";

/** Le rotte sono le stesse su ogni negozio, cambia il prefisso: e' il
 *  motivo per cui questa finestra serve tutti e tre senza saperne nulla. */
const shopRoutes = (shop: string) => ({
  quote: `/api/proxy/${shop}/orders/quote/mine/cart`,
  otp: `/api/proxy/${shop}/orders/mine/cart/request-credit-otp`,
  create: `/api/proxy/${shop}/orders/mine/cart`,
  session: (id: string) => `/api/proxy/${shop}/orders/mine/${id}/checkout-session`,
});

const ROUTES = {
  aliexpress: shopRoutes("aliexpress"),
  cj: shopRoutes("cj"),
  shopify: shopRoutes("shopify"),
  jav_market: shopRoutes("jav-market"),
  kappa_market: shopRoutes("kappa-market"),
  vaitto_market: shopRoutes("vaitto-market"),
  symphonya_market: shopRoutes("symphonya-market"),
  soleil_market: shopRoutes("soleil-market"),
} as const;

export type CartCheckoutShop = keyof typeof ROUTES;

async function fetchCartQuote(shop: CartCheckoutShop): Promise<CartSectionRead> {
  const res = await fetch(ROUTES[shop].quote);
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

export function CartCheckoutModal({
  shop, onClose,
}: { shop: CartCheckoutShop; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { invalidate: invalidateCart } = useCartActions();
  const { data: marketplaceConfig } = useMarketplaceConfig();
  const [step, setStep] = useState<Step>("checkout");

  const { data: quote, error: quoteError } = useQuery({
    queryKey: ["customer", "cart", "quote", shop],
    queryFn: () => fetchCartQuote(shop),
    retry: false,
  });
  const { data: me } = useQuery({ queryKey: ["customer", "me", "record"], queryFn: fetchMyCustomer });
  const { data: paymentInfo } = useQuery({
    queryKey: ["customer", "payment-info"],
    queryFn: fetchPaymentInfo,
    enabled: step === "bank_instructions",
  });

  // Precompilato dalla scheda cliente; quello che il cliente scrive vince.
  const [addressEdits, setAddressEdits] = useState<Partial<DeliveryAddress>>({});
  const address: DeliveryAddress = {
    recipient_name: [me?.first_name, me?.last_name].filter(Boolean).join(" "),
    recipient_phone: me?.phone ?? "",
    address_line1: quote?.default_address.street ?? "",
    address_line2: "",
    city: quote?.default_address.city ?? "",
    province: quote?.default_address.province ?? "",
    postal_code: quote?.default_address.postal_code ?? "",
    ...addressEdits,
  };

  const [useCredit, setUseCredit] = useState(false);
  const [creditAmount, setCreditAmount] = useState("0.00");
  const [chosenMethod, setPaymentMethod] = useState<"BANK_TRANSFER" | "CARD" | null>(null);
  const [otpCode, setOtpCode] = useState("");
  const [otpRequested, setOtpRequested] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [placedOrder, setPlacedOrder] = useState<AliexpressOrderRead | null>(null);

  const paymentMethod = chosenMethod
    ?? (quote?.bank_transfer_available ? "BANK_TRANSFER" : quote?.card_available ? "CARD" : null);
  const maxUsableCents = quote ? Math.min(quote.max_creditable_cents, quote.customer_wallet_balance_cents) : 0;
  const creditCents = quote && useCredit
    ? Math.max(0, Math.min(Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100), maxUsableCents))
    : 0;
  const residualCents = quote ? quote.amount_cents - creditCents : 0;
  const needsPaymentMethod = residualCents > 0;
  const discountPercentage = quote?.bank_transfer_discount_percentage ?? 0;
  const bankDiscountCents = bankTransferDiscount(residualCents, discountPercentage);
  const payingByBank = needsPaymentMethod && paymentMethod === "BANK_TRANSFER";
  const totalDueCents = Math.max(residualCents, 0) - (payingByBank ? bankDiscountCents : 0);
  // Session 78: l'IVA si **aggiunge** al prezzo esposto, e il preventivo del
  // server la manda gia' calcolata dentro amount_cents. Qui non si scorpora
  // e non si somma niente: si mostra la riga che il server ha deciso.
  const vatPercentage = quote?.vat_percentage ?? marketplaceConfig?.vat_percentage ?? 0;
  const vatCents = quote?.vat_cents ?? 0;
  // Quanto il cliente ha scritto, prima di essere riportato entro il massimo:
  // serve solo a dirgli che ha ecceduto, non a decidere l'importo.
  const typedCents = Math.max(0, Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100));
  const overTheCap = useCredit && typedCents > maxUsableCents;

  const ready = !!quote && addressComplete(address) && (creditCents === 0 || !!otpCode.trim())
    && (!needsPaymentMethod || !!paymentMethod) && !overTheCap && !((quote?.min_order_missing_cents ?? 0) > 0);

  /** L'unico punto che scrive l'importo: sempre fra zero e il massimo
   *  spendibile, così il campo non può contenere una cifra che il server
   *  rifiuterebbe. Il server la ricontrolla comunque. */
  function setCredit(cents: number) {
    setCreditAmount((Math.max(0, Math.min(cents, maxUsableCents)) / 100).toFixed(2));
    setOtpRequested(false);
    setOtpCode("");
  }

  function toggleCredit(next: boolean) {
    setUseCredit(next);
    setOtpRequested(false);
    setOtpCode("");
    setCreditAmount(next ? (maxUsableCents / 100).toFixed(2) : "0.00");
  }

  async function handleConfirm() {
    if (!quote) return;
    setSubmitLoading(true);
    setSubmitError(null);
    try {
      const res = await fetch(ROUTES[shop].create, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
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
      // Il carrello lo ha già svuotato il server, dopo aver creato l'ordine.
      await invalidateCart();
      await queryClient.invalidateQueries({ queryKey: ["customer", "wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["customer", "orders"] });
      if (order.status === "PAID") return setStep("success");
      if (order.payment_method === "CARD") {
        const returnUrl = window.location.href;
        const sessionRes = await fetch(
          `${ROUTES[shop].session(order.id)}?success_url=${encodeURIComponent(returnUrl)}&cancel_url=${encodeURIComponent(returnUrl)}`,
          { method: "POST" },
        );
        if (!sessionRes.ok) throw new Error(await friendlyApiError(sessionRes));
        const { checkout_url } = await sessionRes.json();
        window.open(checkout_url, "_blank", "noopener,noreferrer");
        return setStep("card_redirect");
      }
      setStep("bank_instructions");
    } catch (err) {
      setSubmitError((err as Error).message || "Impossibile completare l'acquisto.");
    } finally {
      setSubmitLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-2xl glass-card rounded-2xl border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[92vh] overflow-y-auto">
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-6 py-4 border-b border-white/5 light:border-slate-200 bg-slate-950/95 light:bg-white/95 backdrop-blur">
          <h3 className="text-base font-bold text-white light:text-slate-900">Completa l&apos;acquisto</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 light:hover:bg-slate-900/10 text-slate-400 transition cursor-pointer" aria-label="Chiudi">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-4">
          {quoteError && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
              {(quoteError as Error).message}
            </div>
          )}
          {!quote && !quoteError && <p className="py-10 text-center text-sm text-slate-500">Calcolo in corso…</p>}

          {step === "checkout" && quote && (
            <>
              <div className="rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
                {quote.items.map((line) => (
                  <div key={line.cart_item_id} className="flex items-center gap-3 p-3">
                    <ProductThumbnail imageUrl={line.image_url} alt={line.product_name} className="w-11 h-11 rounded-lg shrink-0 object-cover" />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-semibold text-white light:text-slate-900 truncate">{line.product_name}</p>
                      <p className="text-[11px] text-slate-500 truncate">
                        {line.variant_label ? `${line.variant_label} · ` : ""}{line.quantity} {line.quantity === 1 ? "pezzo" : "pezzi"}
                      </p>
                      {/* Ogni prodotto porta la sua quota di JavCash: il
                          tetto dell'ordine è la somma di queste, quindi
                          mostrarle spiega da sole da dove viene il totale. */}
                      {!!line.max_creditable_cents && (
                        <p className="text-[11px] text-emerald-400/80 truncate">
                          fino a {javCash(line.max_creditable_cents)} ({line.credit_discount_percentage}%)
                        </p>
                      )}
                    </div>
                    <p className="text-xs font-bold text-white light:text-slate-900 tabular-nums">{euro(line.line_total_cents)}</p>
                  </div>
                ))}
              </div>

              <Section n={1} title="Dove lo spediamo?" done={addressComplete(address)}>
                <AddressFields address={address} onChange={setAddressEdits} />
                <p className="text-[11px] text-slate-500">
                  Spedizione in Italia{quote.shipping_days ? ` · consegna stimata in ${quote.shipping_days} giorni lavorativi` : ""}.
                  {" "}Un indirizzo solo per tutti gli articoli di questo ordine.
                </p>
              </Section>

              {quote.max_creditable_cents > 0 && maxUsableCents > 0 && (
                <Section n={2} title="Vuoi usare i tuoi JavCash?" done={creditCents > 0 && !!otpCode.trim()}>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => toggleCredit(!useCredit)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer ${
                        useCredit
                          ? "bg-orange-600 border-orange-600 text-white"
                          : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600"
                      }`}
                    >
                      {useCredit ? "Sì, uso i JavCash" : "Usa i JavCash"}
                    </button>
                    {/* Due numeri diversi, e va detto quale dei due comanda:
                        quanto i prodotti concedono, e quanto il wallet ha.
                        Mostrarne uno solo -- com'era -- fa sembrare sbagliata
                        la somma delle percentuali che il cliente legge sopra,
                        riga per riga. */}
                    <span className="block w-full text-[11px] text-slate-500">
                      I prodotti nel carrello concedono fino a{" "}
                      <strong className="text-slate-300 light:text-slate-600">{javCash(quote.max_creditable_cents)}</strong>
                      {" "}— la somma di quanto concede ciascuno, per la quantità che hai scelto.
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
                            I prodotti ne concederebbero {javCash(quote.max_creditable_cents)}, ma nel tuo wallet
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
                          <button
                            key={f}
                            type="button"
                            onClick={() => setCredit(Math.round(maxUsableCents * f))}
                            className="px-2.5 py-1 rounded-lg text-[11px] font-semibold border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10 cursor-pointer"
                          >
                            {f === 1 ? "Massimo" : `${f * 100}%`}
                          </button>
                        ))}
                        <input
                          inputMode="decimal"
                          value={creditAmount}
                          onChange={(e) => { setCreditAmount(e.target.value); setOtpRequested(false); setOtpCode(""); }}
                          className={`w-28 rounded-lg glass-input px-3 py-1.5 text-sm ${
                            overTheCap ? "border-rose-500 text-rose-300" : ""
                          }`}
                        />
                        <span className="text-xs text-slate-500">JavCash</span>
                      </div>
                      {/* Fermare, non correggere di nascosto: chi ha scritto
                          una cifra deve sapere perché non va bene, e il
                          pulsante del codice resta spento finché non la
                          sistema. Il server ricontrolla comunque. */}
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
                              <button
                                type="button"
                                onClick={() => setCredit(maxUsableCents)}
                                className="font-bold underline underline-offset-2 hover:text-rose-200 cursor-pointer"
                              >
                                Usa il massimo ({javCash(maxUsableCents)})
                              </button>
                            </p>
                          </div>
                        </div>
                      )}
                      {creditCents > 0 && !overTheCap && (
                        <JavCashConfirmCode
                          requestUrl={ROUTES[shop].otp}
                          requestBody={{ credit_applied_cents: creditCents }}
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
                  <div className="flex flex-wrap gap-2">
                    {quote.bank_transfer_available && (
                      <button
                        onClick={() => setPaymentMethod("BANK_TRANSFER")}
                        className={`flex-1 min-w-[180px] px-4 py-3 rounded-xl border text-xs font-semibold transition cursor-pointer ${
                          paymentMethod === "BANK_TRANSFER"
                            ? "border-orange-500 bg-orange-500/10 text-white light:text-slate-900"
                            : "border-white/10 light:border-slate-200 text-slate-400 light:text-slate-500"
                        }`}
                      >
                        Bonifico istantaneo · {euro(residualCents - bankDiscountCents)}
                        {bankDiscountCents > 0 && (
                          <span className="block text-[10px] font-bold text-emerald-400">Risparmi {euro(bankDiscountCents)}</span>
                        )}
                      </button>
                    )}
                    {quote.card_available && (
                      <button
                        onClick={() => setPaymentMethod("CARD")}
                        className={`flex-1 min-w-[180px] px-4 py-3 rounded-xl border text-xs font-semibold transition cursor-pointer ${
                          paymentMethod === "CARD"
                            ? "border-orange-500 bg-orange-500/10 text-white light:text-slate-900"
                            : "border-white/10 light:border-slate-200 text-slate-400 light:text-slate-500"
                        }`}
                      >
                        Carta · {euro(residualCents)}
                      </button>
                    )}
                  </div>
                  {!quote.bank_transfer_available && !quote.card_available && (
                    <p className="text-[11px] text-rose-400">
                      Nessun metodo di pagamento è configurato: contatta l&apos;amministrazione.
                    </p>
                  )}
                </Section>
              )}

              <div className="p-4 rounded-xl bg-gradient-to-br from-orange-600/10 to-amber-500/5 border border-orange-500/20 space-y-1.5 text-xs">
                <div className="flex justify-between text-slate-400 light:text-slate-500">
                  <span>Articoli ({quote.items.length})</span><span className="tabular-nums">{euro(quote.items_cents)}</span>
                </div>
                <div className="flex justify-between text-slate-400 light:text-slate-500">
                  <span>Spedizione</span>
                  <span className="tabular-nums">
                    {quote.free_shipping ? "Gratis" : quote.shipping_included || quote.shipping_cents === 0 ? "Inclusa" : euro(quote.shipping_cents)}
                  </span>
                </div>
                {(quote.free_shipping_missing_cents ?? 0) > 0 && (
                  <p className="text-[11px] text-sky-400">
                    Aggiungi altri {euro(quote.free_shipping_missing_cents ?? 0)} di prodotti e la spedizione è gratis.
                  </p>
                )}
                {creditCents > 0 && (
                  <div className="flex justify-between text-emerald-400">
                    <span>JavCash usati</span><span>-{javCash(creditCents)}</span>
                  </div>
                )}
                {payingByBank && bankDiscountCents > 0 && (
                  <div className="flex justify-between text-emerald-400">
                    <span>Sconto pagamento con bonifico (-{discountPercentage}%)</span>
                    <span>-{euro(bankDiscountCents)}</span>
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
                    {euro(totalDueCents)}
                  </span>
                </div>
              </div>

              {submitError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{submitError}</div>
              )}

              <button
                onClick={handleConfirm}
                disabled={!ready || submitLoading}
                className="w-full px-4 py-3 rounded-xl bg-orange-600 hover:bg-orange-500 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-semibold text-white transition cursor-pointer"
              >
                {submitLoading ? "Elaborazione…" : residualCents > 0 ? "Conferma e paga" : "Conferma ordine"}
              </button>
            </>
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
