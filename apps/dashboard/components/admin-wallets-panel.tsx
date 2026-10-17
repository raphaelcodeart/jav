"use client";

import { Fragment, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { WalletAdminListItemRead, WalletTransactionRead } from "@/lib/types";
import { friendlyApiError } from "@/lib/api-error";
import { downloadCsv } from "@/lib/csv-export";
import { Pagination, usePagination } from "@/components/pagination";
import { JavCashAmount } from "@/components/jav-cash-amount";
import { useI18n } from "@/lib/i18n/provider";

const TYPE_COLORS: Record<string, string> = {
  ADMIN_CREDIT: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  TRANSFER: "bg-sky-500/10 text-sky-400 border-sky-500/20",
  PURCHASE_DEBIT: "bg-amber-500/10 text-amber-700 border-amber-500/20",
  REVERSAL: "bg-rose-500/10 text-rose-400 border-rose-500/20",
};

// Same labels as wallet-panel.tsx: a finer-grained one per source when the
// type alone would not tell a plain top-up from an order cashback.
function transactionLabel(tx: { type: string; source: string | null }, t: ReturnType<typeof useI18n>["t"]): string {
  const sourceLabel = tx.source ? t.dyn(`acct.wallet.source.${tx.source}`, "") : "";
  return sourceLabel || t.dyn(`acct.wallet.type.${tx.type}`, tx.type);
}

// The wallet only ever holds JavCash, never real EUR -- see
// wallet-panel.tsx's identical helper.
function javCash(cents: number, tag: string): string {
  return `${(cents / 100).toLocaleString(tag, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} JavCash`;
}

async function fetchWallets(t: ReturnType<typeof useI18n>["t"]): Promise<WalletAdminListItemRead[]> {
  const res = await fetch("/api/proxy/wallets/admin");
  if (!res.ok) throw new Error(t("acct.adminWallets.loadError"));
  return res.json();
}

async function fetchTransactions(t: ReturnType<typeof useI18n>["t"], type?: string): Promise<WalletTransactionRead[]> {
  const search = new URLSearchParams();
  if (type && type !== "ALL") search.set("type", type);
  const qs = search.toString();
  const res = await fetch(`/api/proxy/wallets/admin/transactions${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(t("acct.stats.txError"));
  return res.json();
}

interface AdminWalletsPanelProps {
  /** Only SUPER_ADMIN may load/credit cashback ("Ricarica") -- the button and
      form below are hidden for a plain ADMIN. This is UX only: the real
      enforcement is the `wallet.credit` permission on POST
      /wallets/admin/topup (see wallets/router.py), which rejects the same
      call with 403 even if someone bypasses this UI gate. */
  isSuperAdmin?: boolean;
}

export function AdminWalletsPanel({ isSuperAdmin = false }: AdminWalletsPanelProps = {}) {
  const { t, fmt } = useI18n();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [reversingId, setReversingId] = useState<string | null>(null);
  const [reverseError, setReverseError] = useState<string | null>(null);
  const [topUpForUserId, setTopUpForUserId] = useState<string | null>(null);
  const [topUpAmount, setTopUpAmount] = useState("");
  const [topUpNote, setTopUpNote] = useState("");
  const [topUpLoading, setTopUpLoading] = useState(false);
  const [topUpError, setTopUpError] = useState<string | null>(null);
  const topUpKeyRef = useRef<string>("");

  const { data: wallets, error: walletsError } = useQuery({
    queryKey: ["admin", "wallets", "all"],
    queryFn: () => fetchWallets(t),
  });
  const { data: transactions, error: transactionsError, isLoading } = useQuery({
    queryKey: ["admin", "wallets", "transactions", typeFilter],
    queryFn: () => fetchTransactions(t, typeFilter),
  });

  const filteredWallets = (wallets ?? []).filter(
    (w) =>
      w.owner_display_name.toLowerCase().includes(search.toLowerCase()) ||
      w.owner_email.toLowerCase().includes(search.toLowerCase()) ||
      w.address.toLowerCase().includes(search.toLowerCase())
  );

  // Two independent lists on this screen, each with its own paging state.
  // Both CSV exports keep using the full arrays, never the visible page.
  const walletsPagination = usePagination(filteredWallets);
  const transactionsPagination = usePagination(transactions ?? []);

  const totalBalance = (wallets ?? []).reduce((sum, w) => sum + w.balance_cents, 0);
  const totalCredited = (transactions ?? [])
    .filter((tx) => tx.type === "ADMIN_CREDIT")
    .reduce((sum, tx) => sum + tx.amount_cents, 0);

  async function handleReverse(transactionId: string) {
    const reason = window.prompt(t("acct.adminWallets.reversePrompt"));
    if (!reason) return;
    setReversingId(transactionId);
    setReverseError(null);
    try {
      const res = await fetch(`/api/proxy/wallets/admin/transactions/${transactionId}/reverse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason, idempotency_key: crypto.randomUUID() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
    } catch (err: any) {
      setReverseError(err.message || t("acct.adminWallets.reverseError"));
    } finally {
      setReversingId(null);
    }
  }

  function openTopUp(userId: string) {
    setTopUpForUserId(topUpForUserId === userId ? null : userId);
    setTopUpAmount("");
    setTopUpNote("");
    setTopUpError(null);
    // One key per top-up the admin is composing, not per click. The backend
    // treats a repeat of the same key as the same top-up and returns the
    // original transaction, so pressing "Ricarica" again after an error can
    // never mint a second credit -- which a fresh crypto.randomUUID() per
    // click could, and did: the credit is committed before the confirmation
    // email is attempted, so an SMTP failure used to surface as an error on
    // a top-up that had already gone through. The server side of that is
    // fixed too (core/email.py::send_html_email_best_effort); this makes the
    // retry safe regardless of what else ever fails after the commit.
    topUpKeyRef.current = crypto.randomUUID();
  }

  async function handleTopUp(e: React.FormEvent, userId: string) {
    e.preventDefault();
    const amountCents = Math.round(parseFloat(topUpAmount.replace(",", ".")) * 100);
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      setTopUpError(t("acct.wallet.invalidAmount"));
      return;
    }
    setTopUpLoading(true);
    setTopUpError(null);
    try {
      const res = await fetch("/api/proxy/wallets/admin/topup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          amount_cents: amountCents,
          note: topUpNote || null,
          idempotency_key: topUpKeyRef.current,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setTopUpForUserId(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
    } catch (err: any) {
      setTopUpError(err.message || t("acct.adminWallets.topUpError"));
    } finally {
      setTopUpLoading(false);
    }
  }

  function handleExportCsv() {
    downloadCsv(
      `wallet_transazioni_${new Date().toISOString().slice(0, 10)}`,
      ["ID", t("acct.col.type"), t("acct.col.from"), t("acct.col.to"), t("acct.wallet.amountLabel"), t("acct.col.note"), t("acct.col.date")],
      (transactions ?? []).map((tx) => [
        tx.id, transactionLabel(tx, t), tx.from_display_name ?? t("acct.wallet.system"), tx.to_display_name ?? t("acct.wallet.system"),
        (tx.amount_cents / 100).toFixed(2), tx.note ?? "", tx.created_at,
      ])
    );
  }

  return (
    <div className="space-y-6">
      {/* KPI */}
      <div className="grid grid-cols-2 gap-4">
        <div className="glass-card rounded-2xl p-4 border-slate-200 bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("acct.adminWallets.totalBalance")}</p>
          <p className="text-xl font-bold text-slate-900">{javCash(totalBalance, fmt.tag)}</p>
        </div>
        <div className="glass-card rounded-2xl p-4 border-slate-200 bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("acct.adminWallets.totalCredited")}</p>
          <p className="text-xl font-bold text-emerald-400">{javCash(totalCredited, fmt.tag)}</p>
        </div>
      </div>

      {/* Wallet balances */}
      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="p-5 pb-3 flex items-center justify-between gap-4">
          <h3 className="text-sm font-semibold text-slate-900">{t("acct.adminWallets.balances")}</h3>
          <input
            type="text"
            placeholder={t("acct.adminWallets.search")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-xl glass-input px-3 py-1.5 text-xs max-w-xs focus:border-brand-500"
          />
        </div>
        {walletsError && <p className="px-5 pb-3 text-sm text-rose-400">{t("acct.adminWallets.loadError")}</p>}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                <th className="py-2 px-5">{t("acct.col.user")}</th>
                <th className="py-2 px-5">{t("acct.col.roles")}</th>
                <th className="py-2 px-5">{t("acct.col.address")}</th>
                <th className="py-2 px-5 text-right">{t("acct.col.balance")}</th>
                <th className="py-2 px-5 text-right">{t("acct.col.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {wallets === undefined ? (
                <tr><td colSpan={5} className="text-center py-6 text-slate-500">{t("acct.common.loading")}</td></tr>
              ) : filteredWallets.length === 0 ? (
                <tr><td colSpan={5} className="text-center py-6 text-slate-500">{t("acct.adminWallets.none")}</td></tr>
              ) : (
                walletsPagination.pageItems.map((w) => (
                  <Fragment key={w.id}>
                    <tr className=" text-slate-600">
                      <td className="py-2 px-5">
                        <div className="font-medium text-slate-900">{w.owner_display_name}</div>
                        <div className="text-[10px] text-slate-500">{w.owner_email}</div>
                      </td>
                      <td className="py-2 px-5">{w.owner_roles.join(", ") || "—"}</td>
                      <td className="py-2 px-5 font-mono text-[10px]">{w.address}</td>
                      <td className="py-2 px-5 text-right font-semibold text-brand-600"><JavCashAmount cents={w.balance_cents} /></td>
                      <td className="py-2 px-5 text-right">
                        {isSuperAdmin ? (
                          <button
                            onClick={() => openTopUp(w.user_id)}
                            className="px-2.5 py-1 rounded-lg bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-600 text-[11px] font-semibold transition cursor-pointer"
                          >
                            {topUpForUserId === w.user_id ? t("common.cancel") : t("acct.adminWallets.topUp")}
                          </button>
                        ) : (
                          <span className="text-[10px] text-slate-500" title={t("acct.adminWallets.superOnly")}>—</span>
                        )}
                      </td>
                    </tr>
                    {isSuperAdmin && topUpForUserId === w.user_id && (
                      <tr className=" bg-slate-900/[0.02]">
                        <td colSpan={5} className="px-5 py-3">
                          <form onSubmit={(e) => handleTopUp(e, w.user_id)} className="flex items-end gap-2">
                            <div className="space-y-1 flex-1 max-w-[160px]">
                              <label className=" font-semibold text-slate-600 uppercase block">{t("acct.wallet.amountLabel")}</label>
                              <input
                                required
                                autoFocus
                                inputMode="decimal"
                                value={topUpAmount}
                                onChange={(e) => setTopUpAmount(e.target.value)}
                                placeholder="0,00"
                                className="w-full rounded-lg glass-input px-3 py-1.5 text-sm focus:border-brand-500"
                              />
                            </div>
                            <div className="space-y-1 flex-1">
                              <label className=" font-semibold text-slate-600 uppercase block">{t("acct.wallet.noteLabel")}</label>
                              <input
                                value={topUpNote}
                                onChange={(e) => setTopUpNote(e.target.value)}
                                placeholder={t("acct.adminWallets.notePlaceholder")}
                                className="w-full rounded-lg glass-input px-3 py-1.5 text-sm focus:border-brand-500"
                              />
                            </div>
                            <button type="submit" disabled={topUpLoading}
                              className="px-4 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50 shrink-0">
                              {topUpLoading ? "..." : t("common.confirm")}
                            </button>
                          </form>
                          {topUpError && (
                            <div className="mt-2 p-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{topUpError}</div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="px-5 pb-4">
          <Pagination {...walletsPagination} label={t("acct.adminWallets.walletPlural")} />
        </div>
      </div>

      {/* Filters + export */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-xl glass-input px-3 py-2 text-xs bg-white focus:border-brand-500"
        >
          <option value="ALL">{t("acct.adminWallets.allTypes")}</option>
          <option value="ADMIN_CREDIT">{t("acct.adminWallets.onlyCredits")}</option>
          <option value="TRANSFER">{t("acct.adminWallets.onlyTransfers")}</option>
          <option value="REVERSAL">{t("acct.adminWallets.onlyReversals")}</option>
        </select>
        <button
          onClick={handleExportCsv}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          {t("acct.common.exportCsv")}
        </button>
      </div>

      {reverseError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{reverseError}</div>
      )}
      {transactionsError && <p className="text-sm text-rose-400">{t("acct.stats.txError")}</p>}

      {/* Global transaction ledger */}
      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                <th className="py-3 px-5">{t("acct.col.from")}</th>
                <th className="py-3 px-5">{t("acct.col.to")}</th>
                <th className="py-3 px-5">{t("acct.col.type")}</th>
                <th className="py-3 px-5 text-right">{t("acct.col.amount")}</th>
                <th className="py-3 px-5">{t("acct.col.date")}</th>
                <th className="py-3 px-5 text-right">{t("acct.col.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {isLoading && (
                <tr><td colSpan={6} className="text-center py-8 text-slate-500">{t("acct.common.loading")}</td></tr>
              )}
              {!isLoading && (transactions ?? []).length === 0 && (
                <tr><td colSpan={6} className="text-center py-8 text-slate-500">{t("acct.wallet.noTx")}</td></tr>
              )}
              {transactionsPagination.pageItems.map((tx) => (
                <Fragment key={tx.id}>
                  <tr
                    className=" text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer"
                    onClick={() => setExpandedId(expandedId === tx.id ? null : tx.id)}
                  >
                    <td className="py-3 px-5">{tx.from_display_name ?? t("acct.wallet.system")}</td>
                    <td className="py-3 px-5">{tx.to_display_name ?? t("acct.wallet.system")}</td>
                    <td className="py-3 px-5">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${TYPE_COLORS[tx.type] ?? ""}`}>
                        {transactionLabel(tx, t)}
                      </span>
                    </td>
                    <td className="py-3 px-5 text-right font-semibold text-brand-600"><JavCashAmount cents={tx.amount_cents} /></td>
                    <td className="py-3 px-5">{new Date(tx.created_at).toLocaleString(fmt.tag)}</td>
                    <td className="py-3 px-5 text-right">
                      {tx.type !== "REVERSAL" && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handleReverse(tx.id); }}
                          disabled={reversingId === tx.id}
                          className="px-2.5 py-1 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
                        >
                          {reversingId === tx.id ? "..." : t("acct.adminWallets.reverse")}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expandedId === tx.id && (
                    <tr className=" bg-slate-900/[0.02]">
                      <td colSpan={6} className="px-5 py-4 text-xs space-y-1.5">
                        {tx.note && <p><span className="text-slate-500">{t("acct.adminWallets.noteColon")}</span> <span className=" text-slate-600">{tx.note}</span></p>}
                        {tx.reference_contract_id && (
                          <p><span className="text-slate-500">{t("acct.adminWallets.linkedContract")}</span> <span className="font-mono text-slate-600">{tx.reference_contract_id}</span></p>
                        )}
                        {tx.reference_order_id && (
                          <p><span className="text-slate-500">{t("acct.adminWallets.linkedOrder")}</span> <span className="font-mono text-slate-600">{tx.reference_order_id}</span> <span className="text-slate-600">{t("acct.adminWallets.seeOrders")}</span></p>
                        )}
                        {tx.from_address && <p><span className="text-slate-500">{t("acct.adminWallets.fromAddress")}</span> <span className="font-mono text-slate-600">{tx.from_address}</span></p>}
                        {tx.to_address && <p><span className="text-slate-500">{t("acct.adminWallets.toAddress")}</span> <span className="font-mono text-slate-600">{tx.to_address}</span></p>}
                        <p className="font-mono text-[10px] text-slate-500">{tx.id}</p>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-5 pb-4">
          <Pagination {...transactionsPagination} label={t("acct.wallet.txPlural")} />
        </div>
      </div>
    </div>
  );
}
