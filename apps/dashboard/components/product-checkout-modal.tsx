"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { OrderQuoteRead, OrderRead } from "@/lib/types";
import { JavCashConfirmCode } from "@/components/javcash-confirm-code";
import { javCash as javCashIn } from "@/components/marketplace-checkout-bits";
import { useI18n } from "@/lib/i18n/provider";

async function fetchQuote(productVersionId: string): Promise<OrderQuoteRead> {
  const res = await fetch(`/api/proxy/orders/quote/mine?product_version_id=${productVersionId}`);
  if (!res.ok) throw new Error("Impossibile calcolare il preventivo.");
  return res.json();
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string; instructions: string | null }> {
  const res = await fetch("/api/proxy/organizations/me/payment-info");
  if (!res.ok) throw new Error("Impossibile caricare le coordinate di pagamento.");
  return res.json();
}

/** A small numbered-circle badge used to mark each step of the checkout as
    a distinct, ordered decision -- "usa i crediti?", "conferma OTP",
    "cashback?", "come paghi?" -- instead of one flat, undifferentiated
    block of controls. Purely visual, no navigation between steps: every
    section that applies is shown at once (a short, optional-heavy form),
    just clearly delineated. */
function StepBadge({ n, done }: { n: number; done?: boolean }) {
  return (
    <span
      className={`flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-bold shrink-0 ${
        done ? "bg-emerald-500 text-white" : "bg-brand-600 text-white"
      }`}
    >
      {done ? (
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        n
      )}
    </span>
  );
}

/** A big, obvious on/off switch -- used for "usa i JavCash" and "riscuoti
    subito cashback", both previously a small checkbox easy to miss. */
function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex items-center gap-2.5 cursor-pointer group"
    >
      <span
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
          checked ? "bg-brand-600" : " bg-slate-300"
        }`}
      >
        <span
          className={`inline-block h-4.5 w-4.5 transform rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-6" : "translate-x-1"
          }`}
          style={{ height: "18px", width: "18px" }}
        />
      </span>
      <span className="text-sm font-semibold text-slate-900">{label}</span>
    </button>
  );
}

/** Self-checkout for a DROPSHIPPING/PARTNER product (never INTERNAL, which
    has no "Acquista" button at all -- see customer-products-panel.tsx).
    Every optional decision (spend JavCash, confirm via OTP, request
    return cashback, pick a payment method) is laid out as its own clearly
    numbered section with a live-updating price summary, rather than one
    flat block of controls -- so a first-time buyer can see, at a glance,
    what each choice actually costs/saves before confirming. See
    docs/cashback-partner-invoices-plan.md for the business logic (unchanged
    here, only the presentation). */
export function ProductCheckoutModal({
  productVersionId,
  productName,
  onClose,
}: {
  productVersionId: string;
  productName: string;
  onClose: () => void;
}) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const javCash = (cents: number) => javCashIn(cents, fmt.tag);
  const queryClient = useQueryClient();
  const { data: quote, error: quoteError } = useQuery({
    queryKey: ["customer", "orders", "quote", productVersionId],
    queryFn: () => fetchQuote(productVersionId),
  });

  const [creditAmount, setCreditAmount] = useState("0.00");
  const [useCredit, setUseCredit] = useState(false);
  const [cashbackRequested, setCashbackRequested] = useState(false);
  const [step, setStep] = useState<"choose" | "bank_instructions" | "success">("choose");
  const [placedOrder, setPlacedOrder] = useState<OrderRead | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Spending existing JavCash needs a fresh OTP emailed to the customer
  // first -- see orders/service.py::create_order's otp_code parameter and
  // POST /orders/mine/request-credit-otp. Irrelevant (and never shown) when
  // no wallet credit is being applied to this order.
  const [otpCode, setOtpCode] = useState("");
  const [otpRequested, setOtpRequested] = useState(false);

  const { data: orgPaymentInfo } = useQuery({
    queryKey: ["customer", "payment-info"],
    queryFn: fetchPaymentInfo,
    enabled: step === "bank_instructions",
  });
  // Un ordine dello shop di un club si paga al club (quote.payee), non a JudoArteVida.
  const payee = (quote as { payee?: { iban: string | null; holder: string; instructions: string | null } | null } | undefined)?.payee;
  const paymentInfo = payee ?? orgPaymentInfo;

  const maxUsableCents = quote ? Math.min(quote.max_creditable_cents, quote.customer_wallet_balance_cents) : 0;
  // Si paga solo con bonifico: se l'IBAN non è configurato non c'è modo.
  const paymentMethod = quote?.bank_transfer_available ? "BANK_TRANSFER" : null;

  useEffect(() => {
    if (!quote) return;
    // Credit starts OFF -- the buyer makes a conscious choice to spend
    // JavCash rather than having it silently pre-applied to the maximum.
    setUseCredit(false);
    setCreditAmount("0.00");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quote?.product_version_id]);

  const creditCents = quote && useCredit
    ? Math.min(
        Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100),
        quote.max_creditable_cents,
        quote.customer_wallet_balance_cents
      )
    : 0;
  // The discount % this specific JavCash amount is worth on THIS product --
  // distinct from quote.credit_discount_percentage, which is the product's
  // configured CAP, not what the buyer is actually about to spend.
  const effectiveDiscountPct = quote && quote.amount_cents > 0 ? Math.round((creditCents / quote.amount_cents) * 100) : 0;
  const residualCents = quote ? quote.amount_cents - creditCents : 0;
  const canRequestCashback = !!quote?.cashback_available && residualCents > 0;
  const cashbackSurchargeCents = canRequestCashback && cashbackRequested
    ? Math.round((residualCents * (quote?.cashback_percentage ?? 0)) / 100)
    : 0;
  const totalToPayCents = residualCents + cashbackSurchargeCents;
  const needsPaymentMethod = totalToPayCents > 0;
  const noMethodAvailable = quote ? !quote.bank_transfer_available : false;
  const otpConfirmed = creditCents === 0 || !!otpCode.trim();

  function setCreditFraction(fraction: number) {
    const cents = Math.round(maxUsableCents * fraction);
    setCreditAmount((cents / 100).toFixed(2));
    setOtpRequested(false);
    setOtpCode("");
  }

  function handleToggleCredit(next: boolean) {
    setUseCredit(next);
    setOtpRequested(false);
    setOtpCode("");
    if (next) {
      // Turning it on defaults to the maximum usable -- one click ("100%"
      // is already selected) covers the common "use as much as I can" case,
      // still freely adjustable via the other preset chips or the field.
      setCreditAmount((maxUsableCents / 100).toFixed(2));
    } else {
      setCreditAmount("0.00");
    }
  }

  async function handleConfirm() {
    if (!quote) return;
    if (needsPaymentMethod && !paymentMethod) {
      setSubmitError(t("shopx.checkout.selectMethod"));
      return;
    }
    if (creditCents > 0 && !otpCode.trim()) {
      setSubmitError(t("shopx.checkout.enterCode"));
      return;
    }
    setSubmitLoading(true);
    setSubmitError(null);
    try {
      const res = await fetch("/api/proxy/orders/mine", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_version_id: productVersionId,
          credit_applied_cents: creditCents,
          cashback_requested: cashbackRequested,
          otp_code: creditCents > 0 ? otpCode.trim() : null,
          payment_method: needsPaymentMethod ? paymentMethod : "BANK_TRANSFER",
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const order: OrderRead = await res.json();
      setPlacedOrder(order);
      await queryClient.invalidateQueries({ queryKey: ["customer", "wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["wallet"] });

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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-xl glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-slate-900">{quote ? t("shopx.checkout.buy") : t("shopx.checkout.buyName", { name: productName })}</h3>
          <button
            onClick={onClose}
            aria-label={t("common.close")}
            className="p-1.5 rounded-lg hover:bg-slate-900/10 text-slate-400 transition cursor-pointer"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {quoteError && <p className="text-sm text-rose-400">{t("shopx.checkout.quoteFailed")}</p>}
        {step === "choose" && !quote && !quoteError && (
          <div className="py-10 text-center text-sm text-slate-500">{t("shopx.checkout.quoteLoading")}</div>
        )}

        {step === "success" && placedOrder && (
          <div className="text-center py-6 space-y-3">
            <svg className="w-14 h-14 text-emerald-400 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm text-slate-600">
              {t("shopx.checkout.paidFully")}
            </p>
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer"
            >
              {t("common.close")}
            </button>
          </div>
        )}

        {step === "bank_instructions" && placedOrder && (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              {t("shopx.checkout.createdPay")} <strong className="text-brand-600">{euro(placedOrder.residual_amount_cents)}</strong> {t("shopx.checkout.createdPayConfirm")}
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
              <p className="pt-1"><span className="text-slate-500">{t("shopx.bank.referenceSuggested")}</span> <span className="font-mono text-brand-600">{t("shopx.bank.referenceValue", { code: placedOrder.id.slice(0, 8).toUpperCase() })}</span></p>
            </div>
            <button
              onClick={onClose}
              className="w-full px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer"
            >
              {t("shopx.gotIt")}
            </button>
          </div>
        )}

        {step === "choose" && quote && (
          <div className="space-y-5">
            {/* Product + headline price, with a live "prezzo scontato" once JavCash is applied */}
            <div className="p-4 rounded-xl bg-slate-900/5 border border-slate-200">
              <p className="text-sm font-semibold text-slate-900 mb-2">{quote.product_name}</p>
              <div className="flex items-end gap-3 flex-wrap">
                <div>
                  <p className="text-[10px] text-slate-500 uppercase tracking-wide">
                    {creditCents > 0 ? t("shopx.checkout.discountedPrice") : t("shopx.checkout.price")}
                  </p>
                  <p className={`text-2xl font-extrabold ${creditCents > 0 ? "text-emerald-400" : " text-slate-900"}`}>
                    {euro(Math.max(residualCents, 0))}
                  </p>
                </div>
                {creditCents > 0 && (
                  <div className="pb-1">
                    <p className="text-[10px] text-slate-500 uppercase tracking-wide">{t("shopx.checkout.fullPrice")}</p>
                    <p className="text-sm text-slate-500 line-through">{euro(quote.amount_cents)}</p>
                  </div>
                )}
                {creditCents > 0 && (
                  <span className="mb-1 px-2 py-1 rounded-full text-[11px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                    -{effectiveDiscountPct}%
                  </span>
                )}
              </div>
              {quote.max_creditable_cents > 0 && (
                <p className="text-[11px] text-slate-500 mt-2">
                  {t("shopx.checkout.yourBalance")} <strong className=" text-slate-900">{javCash(quote.customer_wallet_balance_cents)}</strong>
                  {" "}· {t("shopx.checkout.productUpTo", { amount: javCash(maxUsableCents), pct: quote.credit_discount_percentage })}
                </p>
              )}
            </div>

            {/* Step 1 -- spend JavCash */}
            {quote.max_creditable_cents > 0 && (
              <div className="p-4 rounded-xl border border-slate-200 space-y-3">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-2.5">
                    <StepBadge n={1} />
                    <Toggle checked={useCredit} onChange={handleToggleCredit} label={t("shopx.checkout.useToLower")} />
                  </div>
                </div>

                {useCredit && (
                  <div className="pl-8 space-y-3">
                    <p className="text-[11px] text-slate-500">
                      {t("shopx.checkout.oneToOne")}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {[0.25, 0.5, 0.75, 1].map((fraction) => {
                        const presetCents = Math.round(maxUsableCents * fraction);
                        const isActive = Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100) === presetCents;
                        return (
                          <button
                            key={fraction}
                            type="button"
                            onClick={() => setCreditFraction(fraction)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer ${
                              isActive
                                ? "bg-brand-600 border-brand-600 text-white"
                                : " bg-slate-900/5 border-slate-300 text-slate-600 hover:bg-slate-100"
                            }`}
                          >
                            {fraction === 1 ? t("shopx.checkout.max") : `${Math.round(fraction * 100)}%`}
                          </button>
                        );
                      })}
                    </div>
                    <div className="flex items-center gap-2">
                      <label className=" font-semibold text-slate-600 uppercase shrink-0">
                        {t("shopx.checkout.customAmount")}
                      </label>
                      <input
                        inputMode="decimal"
                        value={creditAmount}
                        onChange={(e) => { setCreditAmount(e.target.value); setOtpRequested(false); setOtpCode(""); }}
                        className="w-full max-w-[140px] rounded-lg glass-input px-3 py-1.5 text-sm focus:border-brand-500"
                      />
                      <span className="text-xs text-slate-500 shrink-0">JavCash</span>
                    </div>
                    <p className="text-xs px-3 py-2 rounded-lg bg-brand-500/10 border border-brand-500/20 text-brand-600">
                      {t("shopx.checkout.usingPrefix")} <strong>{javCash(creditCents)}</strong> = <strong>{t("shopx.checkout.pctDiscount", { pct: effectiveDiscountPct })}</strong> {t("shopx.checkout.onThisOrder")}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Step 2 -- OTP confirmation, only when spending credit */}
            {creditCents > 0 && (
              <div className="p-4 rounded-xl border border-slate-200 space-y-2.5">
                <div className="flex items-center gap-2.5">
                  <StepBadge n={2} done={!!otpCode.trim()} />
                  <p className="text-sm font-semibold text-slate-900">{t("shopx.checkout.confirmJavCash")}</p>
                </div>
                <p className="text-[11px] text-slate-500 pl-8">
                  {t("shopx.checkout.confirmJavCashText")}
                </p>
                <div className="pl-8">
                  <JavCashConfirmCode
                    requestUrl="/api/proxy/orders/mine/request-credit-otp"
                    requestBody={{ product_version_id: productVersionId, credit_applied_cents: creditCents }}
                    code={otpCode}
                    onCodeChange={setOtpCode}
                    requested={otpRequested}
                    onRequestedChange={setOtpRequested}
                    showSentNotice
                  />
                </div>
              </div>
            )}

            {/* Step 3 -- optional return cashback */}
            {canRequestCashback && (
              <div className="p-4 rounded-xl border border-slate-200 space-y-2.5">
                <div className="flex items-center gap-2.5">
                  <StepBadge n={creditCents > 0 ? 3 : 2} />
                  <Toggle checked={cashbackRequested} onChange={setCashbackRequested} label={t("shopx.checkout.cashbackNow")} />
                </div>
                <p className="text-[11px] text-slate-500 pl-8">
                  {t("shopx.checkout.cashbackText", { pct: quote.cashback_percentage, amount: euro(Math.round((residualCents * quote.cashback_percentage) / 100)) })}
                </p>
              </div>
            )}

            {/* Step 4 -- payment method for whatever is still owed in real money */}
            {needsPaymentMethod && (
              <div className="p-4 rounded-xl border border-slate-200 space-y-2.5">
                <div className="flex items-center gap-2.5">
                  <StepBadge n={[creditCents > 0, canRequestCashback].filter(Boolean).length + 2} done={!!paymentMethod} />
                  <p className="text-sm font-semibold text-slate-900">{t("shopx.checkout.howPayRest")}</p>
                </div>
                {noMethodAvailable ? (
                  <p className="text-xs text-rose-400 pl-8">
                    {t("shopx.checkout.noMethodNow")}
                  </p>
                ) : (
                  <div className="pl-8 flex gap-2.5">
                    <div className="flex-1 flex items-center justify-center gap-2 px-3 py-3 rounded-xl text-sm font-semibold border-2 bg-brand-600 border-brand-600 text-white shadow-lg shadow-brand-500/20">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M3 21h18M4 10h16M4 10l8-6 8 6M6 10v9m4-9v9m4-9v9m4-9v9" />
                      </svg>
                      {t("shopx.checkout.bankTransfer")}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Always-visible running total */}
            <div className="p-4 rounded-xl bg-gradient-to-br from-brand-600/10 to-brand-400/5 border border-brand-500/20 space-y-1.5">
              <div className="flex items-center justify-between">
                <p className="text-xs text-slate-500">{t("shopx.checkout.productPrice")}</p>
                <p className="text-xs text-slate-500">{euro(quote.amount_cents)}</p>
              </div>
              {creditCents > 0 && (
                <div className="flex items-center justify-between">
                  <p className="text-xs text-slate-500">{t("shopx.checkout.javCashUsed")}</p>
                  <p className="text-xs text-emerald-400">-{javCash(creditCents)}</p>
                </div>
              )}
              {cashbackSurchargeCents > 0 && (
                <div className="flex items-center justify-between">
                  <p className="text-xs text-slate-500">{t("shopx.checkout.cashbackPct", { pct: quote.cashback_percentage })}</p>
                  <p className="text-xs text-brand-600">+{euro(cashbackSurchargeCents)}</p>
                </div>
              )}
              <div className="flex items-center justify-between pt-1.5 border-t border-slate-300">
                <p className="text-sm font-bold text-slate-900">{t("shopx.checkout.totalNow")}</p>
                <p className={`text-xl font-extrabold ${totalToPayCents > 0 ? "text-brand-600" : "text-emerald-400"}`}>
                  {euro(Math.max(totalToPayCents, 0))}
                </p>
              </div>
              {totalToPayCents <= 0 && (
                <p className="text-[11px] text-emerald-400 text-right">{t("shopx.checkout.coveredJavCash")}</p>
              )}
            </div>

            {submitError && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{submitError}</div>
            )}

            <button
              onClick={handleConfirm}
              disabled={
                submitLoading
                || (needsPaymentMethod && (noMethodAvailable || !paymentMethod))
                || !otpConfirmed
              }
              className="w-full px-4 py-3 rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 text-sm font-bold text-white shadow-lg shadow-brand-500/20 transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.99]"
            >
              {submitLoading ? t("shopx.checkout.processing") : totalToPayCents > 0 ? t("shopx.checkout.confirmProceed") : t("shopx.checkout.confirmOrder")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
