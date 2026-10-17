"use client";

import { Fragment, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import type { CommissionLevelTotalsRead, CommissionMovementDetailRead } from "@/lib/types";
import { friendlyApiError } from "@/lib/api-error";
import { downloadCsv } from "@/lib/csv-export";
import { useI18n } from "@/lib/i18n/provider";

// Movement types (net.adminComm.type.*): FIRST_REFERRER_BONUS is paid once
// per contract to the promoter who ORIGINALLY brought the customer in --
// never to the upline, never to whoever filled the contract in. Additive to
// the other movements, not a replacement.

async function fetchMovements(params: { agentId?: string; status?: string }): Promise<CommissionMovementDetailRead[]> {
  const search = new URLSearchParams();
  if (params.agentId) search.set("agent_id", params.agentId);
  if (params.status) search.set("status_filter", params.status);
  const qs = search.toString();
  const res = await fetch(`/api/proxy/commissions/movements${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error("Impossibile caricare il registro provvigioni.");
  return res.json();
}

async function fetchLevelTotals(): Promise<CommissionLevelTotalsRead[]> {
  const res = await fetch("/api/proxy/commissions/movements/by-level");
  if (!res.ok) throw new Error("Impossibile caricare il riepilogo per livello.");
  return res.json();
}

export function AdminCommissionsPanel({ initialStatusFilter }: { initialStatusFilter?: string }) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const typeLabel = (code: string) => t.dyn(`net.adminComm.type.${code}`, code);
  const statusLabel = (code: string) => t.dyn(`net.adminComm.status.${code}`, code);
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState(initialStatusFilter ?? "ALL");
  const [agentFilter, setAgentFilter] = useState("ALL");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [payingId, setPayingId] = useState<string | null>(null);
  const [payError, setPayError] = useState<string | null>(null);

  const { data: movements, error: movementsError, isLoading } = useQuery({
    queryKey: ["admin", "commissions", "movements"],
    queryFn: () => fetchMovements({}),
  });
  const { data: levelTotals } = useQuery({
    queryKey: ["admin", "commissions", "by-level"],
    queryFn: fetchLevelTotals,
  });

  const agents = useMemo(() => {
    const map = new Map<string, string>();
    (movements ?? []).forEach((m) => map.set(m.agent_id, `${m.agent_name} (${m.agent_promoter_code})`));
    return Array.from(map.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [movements]);

  const filtered = (movements ?? []).filter(
    (m) => (statusFilter === "ALL" || m.status === statusFilter) && (agentFilter === "ALL" || m.agent_id === agentFilter)
  );

  // Paginates the filtered ledger; the CSV export below deliberately keeps
  // using `filtered` so it always exports the whole filtered set.
  const pagination = usePagination(filtered);

  const totalAccrued = filtered.filter((m) => m.status === "ACCRUED").reduce((sum, m) => sum + m.amount_cents, 0);
  const totalPaid = filtered.filter((m) => m.status === "PAID").reduce((sum, m) => sum + m.amount_cents, 0);

  async function handlePay(movementId: string) {
    setPayingId(movementId);
    setPayError(null);
    try {
      const res = await fetch(`/api/proxy/commissions/movements/${movementId}/pay`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: "Segnata come pagata da amministrazione" }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "commissions"] });
    } catch (err: any) {
      setPayError(err.message || t("net.adminComm.payError"));
    } finally {
      setPayingId(null);
    }
  }

  function handleExportCsv() {
    downloadCsv(
      `${t("net.adminComm.csv.filename")}_${new Date().toISOString().slice(0, 10)}`,
      [t("net.adminComm.csv.movementId"), t("net.adminComm.csv.contract"), t("net.adminComm.csv.customer"), t("net.adminComm.csv.product"), t("net.adminComm.csv.promoter"), t("net.adminComm.csv.promoterCode"), t("net.adminComm.csv.depth"), t("net.adminComm.csv.rankAtCalc"), t("net.adminComm.csv.type"), t("net.adminComm.csv.amount"), t("net.adminComm.csv.status"), t("net.adminComm.csv.accrualDate"), t("net.adminComm.csv.paymentDate")],
      filtered.map((m) => [
        m.id, m.contract_id, m.customer_name, m.product_name, m.agent_name, m.agent_promoter_code,
        m.depth_from_producer ?? "", m.rank_at_calculation ?? "", typeLabel(m.movement_type),
        (m.amount_cents / 100).toFixed(2), statusLabel(m.status), m.effective_date, m.paid_date ?? "",
      ])
    );
  }

  return (
    <div className="space-y-6">
      {/* Per-level rollup -- "per ogni livello: contratti attivi, fatturato, provvigioni" */}
      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="p-5 pb-3">
          <h3 className="text-sm font-semibold text-slate-900">{t("net.adminComm.byLevel.title")}</h3>
          <p className="text-[11px] text-slate-500 mt-1">
            {t("net.adminComm.byLevel.hint")}
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                <th className="py-2 px-5">{t("net.adminComm.col.level")}</th>
                <th className="py-2 px-5 text-right">{t("net.adminComm.col.contracts")}</th>
                <th className="py-2 px-5 text-right">{t("net.adminComm.col.revenue")}</th>
                <th className="py-2 px-5 text-right">{t("net.adminComm.col.generated")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {(levelTotals ?? []).map((row) => (
                <tr key={row.depth} className=" text-slate-600">
                  <td className="py-2 px-5 font-semibold text-slate-900">
                    {row.depth === 0 ? t("net.adminComm.depthZero") : row.depth}
                  </td>
                  <td className="py-2 px-5 text-right">{row.contracts}</td>
                  <td className="py-2 px-5 text-right">{euro(row.value_cents)}</td>
                  <td className="py-2 px-5 text-right font-semibold text-brand-600">{euro(row.commission_cents)}</td>
                </tr>
              ))}
              {(levelTotals ?? []).length === 0 && (
                <tr><td colSpan={4} className="text-center py-6 text-slate-500">{t("net.adminComm.noData")}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* KPI + filters + export */}
      <div className="flex flex-col lg:flex-row gap-4">
        <div className="flex-1 grid grid-cols-2 gap-4">
          <div className="glass-card rounded-2xl p-4 border-slate-200 bg-white/70">
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("net.adminComm.kpi.accrued")}</p>
            <p className="text-xl font-bold text-sky-400">{euro(totalAccrued)}</p>
          </div>
          <div className="glass-card rounded-2xl p-4 border-slate-200 bg-white/70">
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("net.adminComm.kpi.paid")}</p>
            <p className="text-xl font-bold text-emerald-400">{euro(totalPaid)}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-xl glass-input px-3 py-2 text-xs bg-white focus:border-brand-500"
          >
            <option value="ALL">{t("net.adminComm.filter.allStatuses")}</option>
            <option value="ACCRUED">{t("net.adminComm.filter.accrued")}</option>
            <option value="PAID">{t("net.adminComm.filter.paid")}</option>
          </select>
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="rounded-xl glass-input px-3 py-2 text-xs bg-white focus:border-brand-500 max-w-[220px]"
          >
            <option value="ALL">{t("net.adminComm.filter.allPromoters")}</option>
            {agents.map(([id, label]) => (
              <option key={id} value={id}>{label}</option>
            ))}
          </select>
          <button
            onClick={handleExportCsv}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            {t("net.adminComm.exportCsv")}
          </button>
        </div>
      </div>

      {payError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{payError}</div>
      )}
      {movementsError && (
        <p className="text-sm text-rose-400">{t("net.adminComm.loadError")}</p>
      )}

      {/* Movement ledger with full traceability */}
      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                <th className="py-3 px-5">{t("net.adminComm.col.customerContract")}</th>
                <th className="py-3 px-5">{t("net.adminComm.col.beneficiary")}</th>
                <th className="py-3 px-5">{t("net.adminComm.col.level")}</th>
                <th className="py-3 px-5">{t("net.adminComm.col.type")}</th>
                <th className="py-3 px-5 text-right">{t("net.adminComm.col.amount")}</th>
                <th className="py-3 px-5">{t("net.adminComm.col.status")}</th>
                <th className="py-3 px-5 text-right">{t("net.adminComm.col.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {isLoading && (
                <tr><td colSpan={7} className="text-center py-8 text-slate-500">{t("net.adminComm.loading")}</td></tr>
              )}
              {!isLoading && filtered.length === 0 && (
                <tr><td colSpan={7} className="text-center py-8 text-slate-500">{t("net.adminComm.noMatch")}</td></tr>
              )}
              {pagination.pageItems.map((m) => (
                <Fragment key={m.id}>
                  <tr
                    className=" text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer"
                    onClick={() => setExpandedId(expandedId === m.id ? null : m.id)}
                  >
                    <td className="py-3 px-5">
                      <div className="font-medium text-slate-900">{m.customer_name}</div>
                      <div className="text-[10px] text-slate-500 font-mono">{m.contract_id}</div>
                    </td>
                    <td className="py-3 px-5">
                      <div>{m.agent_name}</div>
                      <div className="text-[10px] text-slate-500 font-mono">{m.agent_promoter_code}</div>
                    </td>
                    <td className="py-3 px-5">
                      {m.depth_from_producer === 0 ? t("net.adminComm.producer") : t("net.adminComm.levelN", { n: m.depth_from_producer ?? "—" })}
                    </td>
                    <td className="py-3 px-5">{typeLabel(m.movement_type)}</td>
                    <td className="py-3 px-5 text-right font-semibold text-brand-600">{euro(m.amount_cents)}</td>
                    <td className="py-3 px-5">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                        m.status === "PAID"
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                          : "bg-sky-500/10 text-sky-400 border-sky-500/20"
                      }`}>
                        {statusLabel(m.status)}
                      </span>
                    </td>
                    <td className="py-3 px-5 text-right">
                      {m.status === "ACCRUED" && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handlePay(m.id); }}
                          disabled={payingId === m.id}
                          className="px-2.5 py-1 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
                        >
                          {payingId === m.id ? "..." : t("net.adminComm.markPaid")}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expandedId === m.id && (
                    <tr className=" bg-slate-900/[0.02]">
                      <td colSpan={7} className="px-5 py-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                          <div className="space-y-1.5">
                            <p><span className="text-slate-500">{t("net.adminComm.d.product")}</span> <span className=" text-slate-600">{m.product_name}</span></p>
                            <p><span className="text-slate-500">{t("net.adminComm.d.value")}</span> <span className=" text-slate-600">{euro(m.value_cents)}</span></p>
                            <p><span className="text-slate-500">{t("net.adminComm.d.producer")}</span> <span className=" text-slate-600">{m.producer_name}</span></p>
                            <p><span className="text-slate-500">{t("net.adminComm.d.rankAtCalc")}</span> <span className="font-semibold text-brand-600">{m.rank_at_calculation ?? "—"}</span></p>
                            <p><span className="text-slate-500">{t("net.adminComm.d.currentRank")}</span> <span className=" text-slate-600">{m.agent_current_rank_code ?? "—"}</span></p>
                          </div>
                          <div className="space-y-1.5">
                            {m.base_amount_cents !== null && (
                              <p><span className="text-slate-500">{t("net.adminComm.d.baseToken")}</span> <span className=" text-slate-600">{euro(m.base_amount_cents)}</span></p>
                            )}
                            {m.already_distributed_cents !== null && m.already_distributed_cents > 0 && (
                              <p><span className="text-slate-500">{t("net.adminComm.d.alreadyDistributed")}</span> <span className=" text-slate-600">{euro(m.already_distributed_cents)}</span></p>
                            )}
                            {m.entrepreneurial_difference_cents !== null && m.entrepreneurial_difference_cents > 0 && (
                              <p><span className="text-slate-500">{t("net.adminComm.d.entrepreneurial")}</span> <span className=" text-slate-600">{euro(m.entrepreneurial_difference_cents)}</span></p>
                            )}
                            <p><span className="text-slate-500">{t("net.adminComm.d.accrualDate")}</span> <span className=" text-slate-600">{fmt.shortDate(m.effective_date)}</span></p>
                            {m.paid_date && (
                              <p><span className="text-slate-500">{t("net.adminComm.d.paymentDate")}</span> <span className="text-emerald-400">{fmt.shortDate(m.paid_date)}</span></p>
                            )}
                          </div>
                        </div>
                        {m.explanation && (
                          <div className="mt-3 p-3 rounded-xl bg-brand-500/5 border border-brand-500/15 text-brand-700">
                            <span className="font-bold uppercase tracking-wider text-[10px] block mb-1">{t("net.adminComm.d.why")}</span>
                            {m.explanation}
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-5 pb-4">
          <Pagination {...pagination} label={t("net.adminComm.pagLabel")} />
        </div>
      </div>
    </div>
  );
}
