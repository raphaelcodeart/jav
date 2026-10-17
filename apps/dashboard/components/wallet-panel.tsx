"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { JavCashAmount } from "@/components/jav-cash-amount";
import { friendlyApiError } from "@/lib/api-error";
import type { WalletRead, WalletTransactionRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

// Labels per transaction type, and a finer-grained one per source --
// distinguishes a plain admin top-up from the lines a product-order cashback
// request always writes together (see orders/service.py::_credit_order_cashback),
// without needing to read the free-text note.
function transactionLabel(tx: { type: string; source: string | null }, t: ReturnType<typeof useI18n>["t"]): string {
  const sourceLabel = tx.source ? t.dyn(`acct.wallet.source.${tx.source}`, "") : "";
  return sourceLabel || t.dyn(`acct.wallet.type.${tx.type}`, tx.type);
}

function shortCode(id: string): string {
  return id.slice(0, 8).toUpperCase();
}

/** Every order cashback/bonus credit carries reference_order_id (see
    wallets/schemas.py::WalletTransactionRead) -- shown here as a clickable
    chip so it's never just an anonymous "+X JavCash" with no way to trace
    where it came from. Deep-links into "I miei Ordini" on whichever
    dashboard this panel is mounted in (customer or promoter both use this
    component). */
function referenceLink(tx: WalletTransactionRead, t: ReturnType<typeof useI18n>["t"]): { label: string; href: string } | null {
  const basePath = typeof window !== "undefined" && window.location.pathname.startsWith("/promoter") ? "/promoter" : "/customer";
  if (tx.reference_order_id) {
    return { label: t("acct.wallet.orderRef", { code: shortCode(tx.reference_order_id) }), href: `${basePath}?tab=orders` };
  }
  return null;
}

// The wallet only ever holds JavCash, Jav's internal credit -- see
// docs/business-rules.md#internal-wallet. Never format a wallet
// balance/transaction amount as plain EUR; real-money payments (bonifico)
// are formatted separately, with euro(), wherever they appear
// (e.g. customer-orders-panel.tsx, admin-orders-panel.tsx).
function javCash(cents: number, tag: string): string {
  return `${(cents / 100).toLocaleString(tag, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} JavCash`;
}

async function fetchMyWallet(t: ReturnType<typeof useI18n>["t"]): Promise<WalletRead> {
  const res = await fetch("/api/proxy/wallets/me");
  if (!res.ok) throw new Error(t("acct.stats.walletError"));
  return res.json();
}

async function fetchMyTransactions(t: ReturnType<typeof useI18n>["t"]): Promise<WalletTransactionRead[]> {
  const res = await fetch("/api/proxy/wallets/me/transactions");
  if (!res.ok) throw new Error(t("acct.stats.txError"));
  return res.json();
}

export function WalletPanel() {
  const { t, fmt } = useI18n();
  const queryClient = useQueryClient();
  const [toAddress, setToAddress] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState(false);
  const [sendLoading, setSendLoading] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sendSuccess, setSendSuccess] = useState(false);

  const { data: wallet, error: walletError } = useQuery({
    queryKey: ["wallet", "me"],
    queryFn: () => fetchMyWallet(t),
  });
  const { data: transactions, error: transactionsError } = useQuery({
    queryKey: ["wallet", "me", "transactions"],
    queryFn: () => fetchMyTransactions(t),
  });

  const pagination = usePagination(transactions ?? []);

  async function handleCopyAddress() {
    if (!wallet) return;
    try {
      await navigator.clipboard.writeText(wallet.address);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can fail (permissions, non-HTTPS context) -- the
      // address is still visible on screen to copy manually, so this is a
      // silent no-op, not an error worth surfacing.
    }
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const amountCents = Math.round(parseFloat(amount.replace(",", ".")) * 100);
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      setSendError(t("acct.wallet.invalidAmount"));
      return;
    }
    setSendLoading(true);
    setSendError(null);
    try {
      const res = await fetch("/api/proxy/wallets/transfer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to_address: toAddress.trim(),
          amount_cents: amountCents,
          note: note || null,
          idempotency_key: crypto.randomUUID(),
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setSendSuccess(true);
      setToAddress("");
      setAmount("");
      setNote("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["wallet", "me"] }),
        queryClient.invalidateQueries({ queryKey: ["wallet", "me", "transactions"] }),
      ]);
      setTimeout(() => setSendSuccess(false), 3000);
    } catch (err: any) {
      setSendError(err.message || t("acct.wallet.sendError"));
    } finally {
      setSendLoading(false);
    }
  }

  if (walletError) {
    return <p className="text-sm text-rose-400">{t("acct.stats.walletError")}</p>;
  }

  return (
    <div className="space-y-6">
      {/* Balance + address */}
      <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
        {wallet === undefined ? (
          <p className="text-sm text-slate-500">{t("acct.common.loading")}</p>
        ) : (
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("acct.wallet.available")}</p>
              <p className="text-3xl font-bold text-slate-900">{javCash(wallet.balance_cents, fmt.tag)}</p>
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("acct.wallet.yourAddress")}</p>
              <button
                onClick={handleCopyAddress}
                title={t("acct.wallet.copyAddress")}
                className="flex max-w-full items-center gap-2 font-mono text-xs text-slate-600 bg-slate-900/5 border border-slate-200 rounded-lg px-3 py-2 hover:bg-slate-100 transition cursor-pointer"
              >
                <span className="min-w-0 truncate">{wallet.address}</span>
                <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  {copied ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  )}
                </svg>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Send form -- only for wallets with can_transfer enabled (denied by
          default, turned on per promoter by an admin) */}
      {wallet && !wallet.can_transfer ? (
        <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
          <h3 className="text-sm font-semibold text-slate-900 mb-2">{t("acct.wallet.sendTitle")}</h3>
          <p className="text-xs text-slate-500">{t("acct.wallet.sendDisabled")}</p>
        </div>
      ) : wallet ? (
      <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
        <h3 className="text-sm font-semibold text-slate-900 mb-4">{t("acct.wallet.sendTitle")}</h3>
        <form onSubmit={handleSend} className="grid grid-cols-1 sm:grid-cols-[2fr_1fr_2fr_auto] gap-3 items-end">
          <div className="space-y-1">
            <label className=" font-semibold text-slate-600 uppercase block">{t("acct.wallet.toAddress")}</label>
            <input
              required
              value={toAddress}
              onChange={(e) => setToAddress(e.target.value)}
              placeholder="0x..."
              className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-brand-500"
            />
          </div>
          <div className="space-y-1">
            <label className=" font-semibold text-slate-600 uppercase block">{t("acct.wallet.amountLabel")}</label>
            <input
              required
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0,00"
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500"
            />
          </div>
          <div className="space-y-1">
            <label className=" font-semibold text-slate-600 uppercase block">{t("acct.wallet.noteLabel")}</label>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500"
            />
          </div>
          <button
            type="submit"
            disabled={sendLoading}
            className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50 whitespace-nowrap"
          >
            {sendLoading ? t("acct.wallet.sending") : t("acct.wallet.send")}
          </button>
        </form>
        {sendError && (
          <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{sendError}</div>
        )}
        {sendSuccess && (
          <div className="mt-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">{t("acct.wallet.sent")}</div>
        )}
      </div>
      ) : null}

      {/* Transaction history */}
      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="p-5 pb-3">
          <h3 className="text-sm font-semibold text-slate-900">{t("acct.wallet.history")}</h3>
        </div>
        {transactionsError && <p className="px-5 pb-3 text-sm text-rose-400">{t("acct.stats.txError")}</p>}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                <th className="py-2 px-5">{t("acct.col.type")}</th>
                <th className="py-2 px-5">{t("acct.col.counterparty")}</th>
                <th className="py-2 px-5">{t("acct.col.reference")}</th>
                <th className="py-2 px-5">{t("acct.col.note")}</th>
                <th className="py-2 px-5 text-right">{t("acct.col.amount")}</th>
                <th className="py-2 px-5">{t("acct.col.date")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {transactions === undefined ? (
                <tr><td colSpan={6} className="text-center py-6 text-slate-500">{t("acct.common.loading")}</td></tr>
              ) : transactions.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-6 text-slate-500">{t("acct.wallet.noTx")}</td></tr>
              ) : (
                pagination.pageItems.map((tx) => {
                  const isOutgoing = tx.from_wallet_id === wallet?.id;
                  const ref = referenceLink(tx, t);
                  return (
                    <tr key={tx.id} className=" text-slate-600">
                      <td className="py-2 px-5">{transactionLabel(tx, t)}</td>
                      <td className="py-2 px-5">
                        {isOutgoing ? (tx.to_display_name ?? t("acct.wallet.system")) : (tx.from_display_name ?? t("acct.wallet.system"))}
                      </td>
                      <td className="py-2 px-5">
                        {ref ? (
                          <a
                            href={ref.href}
                            className="inline-flex items-center gap-1 font-mono text-[11px] px-2 py-0.5 rounded-full bg-brand-500/10 text-brand-600 border border-brand-500/20 hover:bg-brand-500/20 transition"
                          >
                            {ref.label}
                            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                          </a>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>
                      <td className="py-2 px-5 text-slate-500">{tx.note ?? "—"}</td>
                      <td className={`py-2 px-5 text-right font-semibold ${isOutgoing ? "text-rose-400" : "text-emerald-400"}`}>
                        <JavCashAmount cents={tx.amount_cents} sign={isOutgoing ? "-" : "+"} />
                      </td>
                      <td className="py-2 px-5">{new Date(tx.created_at).toLocaleString(fmt.tag)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="px-5 pb-4">
          <Pagination {...pagination} label={t("acct.wallet.txPlural")} />
        </div>
      </div>
    </div>
  );
}
