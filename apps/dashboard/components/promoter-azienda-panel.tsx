"use client";

import { Fragment, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BranchContractRead, BranchSummaryRead, RankProgressRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

async function fetchBranchSummary(agentId: string): Promise<BranchSummaryRead> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch-summary`);
  if (!res.ok) throw new Error("Impossibile caricare il riepilogo della rete.");
  return res.json();
}

async function fetchBranchContracts(agentId: string): Promise<BranchContractRead[]> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch-contracts`);
  if (!res.ok) throw new Error("Impossibile caricare i contratti della rete.");
  return res.json();
}

async function fetchRankProgress(agentId: string): Promise<RankProgressRead> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/rank-progress`);
  if (!res.ok) throw new Error("Impossibile caricare l'avanzamento qualifica.");
  return res.json();
}

function ProgressBar({ current, target }: { current: number; target: number }) {
  const pct = target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 100;
  return (
    <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${pct >= 100 ? "bg-emerald-500" : "bg-gradient-to-r from-accent-400 to-brand-600"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function PromoterAziendaPanel({ agentId }: { agentId: string }) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const { data: summary, error: summaryError, isLoading: summaryLoading } = useQuery({
    queryKey: ["promoter", "branch-summary", agentId],
    queryFn: () => fetchBranchSummary(agentId),
  });
  const { data: contracts, error: contractsError } = useQuery({
    queryKey: ["promoter", "branch-contracts", agentId],
    queryFn: () => fetchBranchContracts(agentId),
  });
  const { data: rankProgress } = useQuery({
    queryKey: ["promoter", "rank-progress", agentId],
    queryFn: () => fetchRankProgress(agentId),
  });
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [selectedLevel, setSelectedLevel] = useState<number | null>(null);

  const perLevel = useMemo(() => {
    if (!summary) return [];
    const map = new Map<number, { depth: number; agentCount: number; contracts: number; commission: number }>();
    for (const a of summary.agents) {
      const entry = map.get(a.depth) ?? { depth: a.depth, agentCount: 0, contracts: 0, commission: 0 };
      entry.agentCount += 1;
      entry.contracts += a.contracts_total;
      entry.commission += a.commission_cents;
      map.set(a.depth, entry);
    }
    return Array.from(map.values()).sort((a, b) => a.depth - b.depth);
  }, [summary]);

  const chartData = useMemo(
    () =>
      perLevel
        .filter((row) => row.depth > 0) // "Tu" (depth 0) skews the scale and isn't part of the downline
        .map((row) => ({
          name: t("net.azienda.levelShort", { n: row.depth }),
          people: row.agentCount,
          contracts: row.contracts,
        })),
    [perLevel, t]
  );

  const directCount = summary?.agents.filter((a) => a.depth === 1).length ?? 0;
  const totalProblems = summary?.agents.reduce((sum, a) => sum + a.contracts_problem, 0) ?? 0;
  const totals = summary?.totals;

  const levelDetail = useMemo(() => {
    if (selectedLevel === null || !summary) return null;
    const agents = summary.agents.filter((a) => a.depth === selectedLevel);
    return {
      depth: selectedLevel,
      agents,
      contracts: agents.reduce((sum, a) => sum + a.contracts_total, 0),
      closed: agents.reduce((sum, a) => sum + a.contracts_processed, 0),
      problem: agents.reduce((sum, a) => sum + a.contracts_problem, 0),
      inProgress: agents.reduce((sum, a) => sum + a.contracts_in_progress, 0),
      commission: agents.reduce((sum, a) => sum + a.commission_cents, 0),
    };
  }, [selectedLevel, summary]);

  const filteredContracts = (contracts ?? []).filter((c) => !onlyProblems || c.is_problem);
  const agentsForTable = selectedLevel === null ? (summary?.agents ?? []) : (levelDetail?.agents ?? []);

  return (
    <div className="space-y-6">
      {(summaryError || contractsError) && (
        <p className="text-sm text-rose-400">{t("net.azienda.loadError")}</p>
      )}

      {/* KPI cards -- top-level totals across the whole downline, promoter can
          only ever see below themselves (branch-scoped by the API). */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-card rounded-2xl p-5 border-slate-200 bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("net.azienda.kpi.people")}</p>
          <p className="text-xl font-bold text-slate-900">{summaryLoading ? "…" : totals?.people_total ?? 0}</p>
          <p className="text-[10px] text-slate-500 mt-1">{t("net.azienda.kpi.direct", { n: directCount })}</p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-slate-200 bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("net.azienda.kpi.levels")}</p>
          <p className="text-xl font-bold text-slate-900">{summaryLoading ? "…" : totals?.levels_below ?? 0}</p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-slate-200 bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("net.azienda.kpi.closed")}</p>
          <p className="text-xl font-bold text-emerald-400">{summaryLoading ? "…" : totals?.contracts_closed ?? 0}</p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-slate-200 bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("net.azienda.kpi.commission")}</p>
          <p className="text-xl font-bold text-brand-600">{summaryLoading ? "…" : euro(totals?.commission_cents ?? 0)}</p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-slate-200 bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("net.azienda.kpi.rejected")}</p>
          <p className="text-xl font-bold text-rose-400">{summaryLoading ? "…" : totals?.contracts_rejected ?? 0}</p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-slate-200 bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("net.azienda.kpi.pending")}</p>
          <p className="text-xl font-bold text-amber-700">{summaryLoading ? "…" : totals?.contracts_pending ?? 0}</p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-slate-200 bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("net.azienda.inProgress")}</p>
          <p className="text-xl font-bold text-sky-400">{summaryLoading ? "…" : totals?.contracts_in_progress ?? 0}</p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-slate-200 bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{t("net.azienda.kpi.total")}</p>
          <p className="text-xl font-bold text-slate-900">{summaryLoading ? "…" : totals?.contracts ?? 0}</p>
        </div>
      </div>

      {totalProblems > 0 && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-700 text-sm">
          <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {totalProblems === 1 ? t("net.azienda.problemsOne") : t("net.azienda.problemsMany", { n: totalProblems })}
        </div>
      )}

      {/* Rank promotion progress -- placeholder thresholds, see
          docs/business-rules.md#rank-promotion-progress-placeholder */}
      {rankProgress && (
        <div className="glass-card rounded-2xl p-5 border-slate-200 bg-white/70">
          {rankProgress.is_max_rank ? (
            <div className="flex items-center gap-3">
              <div className="p-2 bg-emerald-500/10 rounded-xl border border-emerald-500/20 text-emerald-400 shrink-0">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <p className="text-sm text-slate-600">
                {t("net.azienda.maxRank")} (<span className="font-bold text-brand-600">{rankProgress.current_rank_name}</span>).
              </p>
            </div>
          ) : rankProgress.next_rank_code ? (
            <>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-slate-900">
                  {t("net.azienda.towardsRank")} <span className="text-brand-600">{rankProgress.next_rank_code}</span> — {rankProgress.next_rank_name}
                </h3>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <div>
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span className=" text-slate-500">{t("net.azienda.personalVolume")}</span>
                    <span className="font-semibold text-slate-600">
                      {euro(rankProgress.personal_volume_cents)} / {euro(rankProgress.personal_volume_threshold_cents)}
                    </span>
                  </div>
                  <ProgressBar current={rankProgress.personal_volume_cents} target={rankProgress.personal_volume_threshold_cents} />
                </div>
                <div>
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span className=" text-slate-500">{t("net.azienda.groupVolume")}</span>
                    <span className="font-semibold text-slate-600">
                      {euro(rankProgress.group_volume_cents)} / {euro(rankProgress.group_volume_threshold_cents)}
                    </span>
                  </div>
                  <ProgressBar current={rankProgress.group_volume_cents} target={rankProgress.group_volume_threshold_cents} />
                </div>
              </div>
              <p className="text-[10px] text-slate-500 mt-4">
                {t("net.azienda.rankDisclaimer")}
              </p>
            </>
          ) : null}
        </div>
      )}

      {/* Per-level breakdown + chart + drill-down */}
      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="p-5 pb-0 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900">{t("net.azienda.byLevel")}</h3>
          <p className="text-[11px] text-slate-500">{t("net.azienda.clickLevel")}</p>
        </div>
        {chartData.length > 0 && (
          <div className="h-56 px-5 pt-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.15)" />
                <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid rgba(148,163,184,0.2)", borderRadius: 8, fontSize: 12 }} />
                <Bar dataKey="people" name={t("net.azienda.col.people")} fill="#38bdf8" radius={[4, 4, 0, 0]} />
                <Bar dataKey="contracts" name={t("net.azienda.col.contracts")} fill="#f97316" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className="overflow-x-auto p-5">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                <th className="py-2 pr-4">{t("net.adminComm.col.level")}</th>
                <th className="py-2 pr-4">{t("net.azienda.col.people")}</th>
                <th className="py-2 pr-4">{t("net.azienda.col.contracts")}</th>
                <th className="py-2 pr-4 text-right">{t("net.azienda.col.commissions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {perLevel.filter((row) => row.depth > 0).map((row) => (
                <tr
                  key={row.depth}
                  onClick={() => setSelectedLevel(selectedLevel === row.depth ? null : row.depth)}
                  className={` text-slate-600 cursor-pointer transition ${
                    selectedLevel === row.depth ? "bg-brand-500/10" : "hover:bg-slate-100"
                  }`}
                >
                  <td className="py-2 pr-4 font-medium text-slate-900">{t("net.azienda.levelN", { n: row.depth })}</td>
                  <td className="py-2 pr-4">{row.agentCount}</td>
                  <td className="py-2 pr-4">{row.contracts}</td>
                  <td className="py-2 pr-4 text-right font-semibold text-brand-600">{euro(row.commission)}</td>
                </tr>
              ))}
              {perLevel.filter((row) => row.depth > 0).length === 0 && !summaryLoading && (
                <tr><td colSpan={4} className="text-center py-6 text-slate-500">{t("net.adminComm.noData")}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Per-agent breakdown, filtered to the selected level's drill-down when set */}
      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="p-5 pb-0 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900">
            {selectedLevel === null ? t("net.azienda.perPerson") : t("net.azienda.levelDetail", { n: selectedLevel })}
          </h3>
          {selectedLevel !== null && (
            <button
              onClick={() => setSelectedLevel(null)}
              className="text-xs text-brand-600 hover:text-brand-600 transition cursor-pointer"
            >
              {t("net.azienda.backToOverview")}
            </button>
          )}
        </div>
        {levelDetail && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 px-5 pt-4">
            <div className="rounded-xl bg-slate-900/5 p-3 text-center">
              <p className="text-[10px] text-slate-500 uppercase">{t("net.azienda.col.people")}</p>
              <p className="text-lg font-bold text-slate-900">{levelDetail.agents.length}</p>
            </div>
            <div className="rounded-xl bg-slate-900/5 p-3 text-center">
              <p className="text-[10px] text-slate-500 uppercase">{t("net.azienda.closed")}</p>
              <p className="text-lg font-bold text-emerald-400">{levelDetail.closed}</p>
            </div>
            <div className="rounded-xl bg-slate-900/5 p-3 text-center">
              <p className="text-[10px] text-slate-500 uppercase">{t("net.azienda.inProgress")}</p>
              <p className="text-lg font-bold text-sky-400">{levelDetail.inProgress}</p>
            </div>
            <div className="rounded-xl bg-slate-900/5 p-3 text-center">
              <p className="text-[10px] text-slate-500 uppercase">{t("net.azienda.problems")}</p>
              <p className="text-lg font-bold text-rose-400">{levelDetail.problem}</p>
            </div>
          </div>
        )}
        <div className="overflow-x-auto p-5">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                <th className="py-2 pr-4">{t("net.azienda.col.name")}</th>
                <th className="py-2 pr-4">{t("net.adminComm.col.level")}</th>
                <th className="py-2 pr-4">{t("net.azienda.col.total")}</th>
                <th className="py-2 pr-4">{t("net.azienda.col.processed")}</th>
                <th className="py-2 pr-4">{t("net.azienda.inProgress")}</th>
                <th className="py-2 pr-4">{t("net.azienda.problems")}</th>
                <th className="py-2 pr-4 text-right">{t("net.azienda.col.commissions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {agentsForTable.map((a) => (
                <tr key={a.agent_id} className=" text-slate-600">
                  <td className="py-2 pr-4 font-medium text-slate-900">{a.display_name}</td>
                  <td className="py-2 pr-4">{a.depth === 0 ? t("net.azienda.you") : a.depth}</td>
                  <td className="py-2 pr-4">{a.contracts_total}</td>
                  <td className="py-2 pr-4 text-emerald-400">{a.contracts_processed}</td>
                  <td className="py-2 pr-4 text-amber-700">{a.contracts_in_progress}</td>
                  <td className="py-2 pr-4">
                    {a.contracts_problem > 0 ? (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-rose-500/10 text-rose-400 border-rose-500/20">
                        {a.contracts_problem}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="py-2 pr-4 text-right font-semibold text-brand-600">{euro(a.commission_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Contract-level detail with contact action */}
      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="p-5 pb-0 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900">{t("net.azienda.networkContracts")}</h3>
          <label className="flex items-center gap-2 text-xs text-slate-500 cursor-pointer">
            <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} className="cursor-pointer" />
            {t("net.azienda.onlyProblems")}
          </label>
        </div>
        <div className="overflow-x-auto p-5">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                <th className="py-2 pr-4">{t("net.adminComm.csv.customer")}</th>
                <th className="py-2 pr-4">{t("net.adminComm.csv.product")}</th>
                <th className="py-2 pr-4">{t("net.azienda.col.seller")}</th>
                <th className="py-2 pr-4">{t("net.adminComm.col.status")}</th>
                <th className="py-2 pr-4 text-right">{t("net.azienda.col.commission")}</th>
                <th className="py-2 pr-4 text-right">{t("net.adminComm.col.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {filteredContracts.map((c) => (
                <Fragment key={c.contract_id}>
                  <tr className=" text-slate-600">
                    <td className="py-2 pr-4">
                      <div className="font-medium text-slate-900">{c.customer_name}</div>
                      <div className="font-mono text-[10px] text-slate-500">{c.customer_id}</div>
                    </td>
                    <td className="py-2 pr-4">
                      <div>{c.product_name}</div>
                    </td>
                    <td className="py-2 pr-4">{c.producer_name}</td>
                    <td className="py-2 pr-4">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                        c.is_problem
                          ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                          : c.status === "ACTIVE" || c.status === "RENEWED"
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                            : "bg-amber-500/10 text-amber-700 border-amber-500/20"
                      }`}>
                        {t.dyn(`net.sim.cstatus.${c.status}`, c.status)}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-right font-semibold text-brand-600">{euro(c.commission_cents)}</td>
                    <td className="py-2 pr-4 text-right">
                      {c.customer_email && (
                        <a
                          href={`mailto:${c.customer_email}${c.is_problem ? `?subject=${encodeURIComponent(t("net.azienda.mail.subject"))}&body=${encodeURIComponent(c.admin_note ? t("net.azienda.mail.bodyNote", { note: c.admin_note }) : t("net.azienda.mail.bodyDocs"))}` : ""}`}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-600 text-xs font-semibold transition cursor-pointer"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                          </svg>
                          {t("net.azienda.contact")}
                        </a>
                      )}
                    </td>
                  </tr>
                  {c.is_problem && c.admin_note && (
                    <tr className="bg-rose-500/5">
                      <td colSpan={6} className="px-4 py-2 text-xs text-rose-300">
                        <span className="font-bold uppercase tracking-wider mr-2">{t("net.azienda.adminNote")}</span>
                        {c.admin_note}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {filteredContracts.length === 0 && (
                <tr><td colSpan={6} className="text-center py-6 text-slate-500">{t("net.azienda.noContracts")}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
