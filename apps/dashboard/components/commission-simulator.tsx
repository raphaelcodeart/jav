"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { BranchContractRead, BranchMemberRead, SimulationStepRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

const RANKS = ["S1", "S2", "S3", "TL1", "TL2", "TL3", "TL4", "MD1", "MD2", "MD3", "MD4", "MD5"];

async function fetchBranchContracts(agentId: string): Promise<BranchContractRead[]> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch-contracts`);
  if (!res.ok) throw new Error("Impossibile caricare i contratti della tua rete.");
  return res.json();
}

async function fetchBranch(agentId: string): Promise<BranchMemberRead[]> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch`);
  if (!res.ok) throw new Error("Impossibile caricare la tua rete.");
  return res.json();
}

export function CommissionSimulator({ agentId }: { agentId: string }) {
  const { t, fmt } = useI18n();
  const { data: branchContracts } = useQuery({
    queryKey: ["promoter", "simulator", "branch-contracts", agentId],
    queryFn: () => fetchBranchContracts(agentId),
  });
  const { data: branch } = useQuery({
    queryKey: ["promoter", "simulator", "branch", agentId],
    queryFn: () => fetchBranch(agentId),
  });

  const nameByAgentId = useMemo(() => {
    const map = new Map<string, string>();
    (branch ?? []).forEach((m) => map.set(m.agent_id, `${m.display_name} (${m.promoter_code})`));
    return map;
  }, [branch]);

  const [contractId, setContractId] = useState("");
  const [customContractId, setCustomContractId] = useState("");
  const [useCustom, setUseCustom] = useState(false);

  // Rank override state: key = agent_id, value = rank_code
  const [overrideAgentId, setOverrideAgentId] = useState("");
  const [overrideRank, setOverrideRank] = useState("MD5");
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<SimulationStepRead[] | null>(null);

  const addOverride = () => {
    if (!overrideAgentId) return;
    setOverrides((prev) => ({ ...prev, [overrideAgentId]: overrideRank }));
    setOverrideAgentId("");
  };

  const removeOverride = (agentId: string) => {
    setOverrides((prev) => {
      const copy = { ...prev };
      delete copy[agentId];
      return copy;
    });
  };

  const runSimulation = async () => {
    setError(null);
    setResults(null);
    setLoading(true);

    const targetId = useCustom ? customContractId.trim() : contractId;
    if (!targetId) {
      setError(useCustom ? t("net.sim.err.enterId") : t("net.sim.err.selectContract"));
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`/api/proxy/commissions/contracts/${targetId}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rank_overrides: Object.keys(overrides).length > 0 ? overrides : null,
        }),
      });

      if (!res.ok) {
        throw new Error(await friendlyApiError(res, t("net.sim.err.simulation")));
      }

      const data = (await res.json()) as SimulationStepRead[];
      setResults(data);
    } catch (err: any) {
      setError(err.message || t("net.sim.err.load"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-amber-500/10 rounded-xl border border-amber-500/20 text-amber-700">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
        </div>
        <div>
          <h3 className="text-lg font-semibold text-slate-900">{t("net.sim.title")}</h3>
          <p className="text-xs text-slate-500">
            {t("net.sim.subtitle")}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        {/* Left column: Configuration */}
        <div className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wider block mb-2">
              {t("net.sim.step1")}
            </label>
            <div className="flex flex-col gap-3">
              {!useCustom ? (
                <select
                  value={contractId}
                  onChange={(e) => setContractId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-white focus:border-brand-500"
                >
                  <option value="">{t("net.sim.selectContract")}</option>
                  {(branchContracts ?? []).map((c) => (
                    <option key={c.contract_id} value={c.contract_id} className=" bg-white">
                      {t("net.sim.contractOption", { customer: c.customer_name, product: c.product_name, status: t.dyn(`net.sim.cstatus.${c.status}`, c.status), producer: c.producer_name })}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  placeholder={t("net.sim.pasteId")}
                  value={customContractId}
                  onChange={(e) => setCustomContractId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-brand-500"
                />
              )}
              <button
                type="button"
                onClick={() => setUseCustom((v) => !v)}
                className="self-start text-[11px] text-brand-600 hover:text-brand-600 transition cursor-pointer"
              >
                {useCustom ? t("net.sim.backToList") : t("net.sim.haveId")}
              </button>
            </div>
          </div>

          {/* Rank Overrides Section */}
          <div className="border-t border-slate-200 pt-4">
            <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-2">
              {t("net.sim.step2")}
            </h4>
            <p className=" text-slate-500 mb-3">
              {t("net.sim.step2Hint")}
            </p>

            <div className="flex flex-col sm:flex-row gap-2 mb-3">
              <select
                value={overrideAgentId}
                onChange={(e) => setOverrideAgentId(e.target.value)}
                className="flex-1 rounded-xl glass-input px-3 py-2 text-xs bg-white focus:border-brand-500"
              >
                <option value="">{t("net.sim.selectPerson")}</option>
                {(branch ?? [])
                  .filter((m) => m.depth > 0)
                  .map((m) => (
                    <option key={m.agent_id} value={m.agent_id} className=" bg-white">
                      {t("net.sim.personOption", { name: m.display_name, code: m.promoter_code, rank: m.rank_code ?? "—" })}
                    </option>
                  ))}
              </select>
              <div className="flex gap-2">
                <select
                  value={overrideRank}
                  onChange={(e) => setOverrideRank(e.target.value)}
                  className="w-24 rounded-xl glass-input px-2 py-2 text-xs bg-white focus:border-brand-500"
                >
                  {RANKS.map((r) => (
                    <option key={r} value={r} className=" bg-white">{r}</option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={addOverride}
                  disabled={!overrideAgentId}
                  className="px-3 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                >
                  {t("net.sim.add")}
                </button>
              </div>
            </div>

            {/* List of current overrides */}
            {Object.keys(overrides).length > 0 && (
              <div className="flex flex-wrap gap-2 p-3 rounded-xl bg-slate-900/5 border border-slate-200 max-h-32 overflow-y-auto">
                {Object.entries(overrides).map(([agent, rank]) => (
                  <span
                    key={agent}
                    className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-100 border border-slate-300 text-xs text-slate-700"
                  >
                    <span className=" text-slate-600">{nameByAgentId.get(agent) ?? agent}</span>
                    <span className="text-slate-500">→</span>
                    <span className="font-bold text-brand-600">{rank}</span>
                    <button
                      type="button"
                      onClick={() => removeOverride(agent)}
                      className="text-rose-400 hover:text-rose-300 font-bold ml-1 cursor-pointer"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={runSimulation}
            disabled={loading}
            className="w-full mt-4 rounded-xl bg-gradient-to-r from-accent-400 to-brand-600 hover:from-accent-400 hover:to-brand-500 py-3 text-sm font-semibold text-white shadow-lg hover:shadow-brand-600/20 transition-all duration-300 disabled:opacity-50 cursor-pointer"
          >
            {loading ? t("net.sim.running") : t("net.sim.run")}
          </button>
        </div>

        {/* Right column: Results */}
        <div className="rounded-xl bg-white/60 border border-slate-200 p-4 flex flex-col justify-between min-h-[300px]">
          {loading && (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-500">
              <svg className="animate-spin h-8 w-8 text-amber-700 mb-3" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <p className="text-sm">{t("net.sim.analysing")}</p>
            </div>
          )}

          {!loading && error && (
            <div className="flex-1 flex flex-col items-center justify-center text-rose-400 text-center px-4">
              <svg className="w-10 h-10 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-sm font-semibold">{t("net.sim.errorTitle")}</p>
              <p className="text-xs text-slate-500 mt-1">{error}</p>
            </div>
          )}

          {!loading && !error && !results && (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-500 text-center">
              <svg className="w-12 h-12 text-slate-600 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              <p className="text-sm">{t("net.sim.emptyTitle")}</p>
              <p className="text-[11px] text-slate-600 mt-1">{t("net.sim.emptyHint")}</p>
            </div>
          )}

          {!loading && !error && results && (
            <div className="flex-1 space-y-4">
              <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
                {t("net.sim.resultTitle")}
              </h4>

              {results.length === 0 ? (
                <p className="text-xs text-slate-500 italic">{t("net.sim.noResults")}</p>
              ) : (
                <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
                  {results.map((step, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-xl bg-slate-900/5 border border-slate-200 hover:bg-slate-100 transition-all"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-slate-600">
                            {nameByAgentId.get(step.beneficiary_agent_id) ?? t("net.sim.agentFallback", { id: step.beneficiary_agent_id.substring(0, 6) })}
                          </span>
                          <span className="px-1.5 py-0.5 text-[9px] font-bold bg-brand-500/10 text-brand-600 border border-brand-500/20 rounded">
                            {step.rank_code}
                          </span>
                        </div>
                        <span className="text-sm font-semibold text-emerald-400">
                          +{fmt.euro(step.gross_amount_cents)}
                        </span>
                      </div>
                      <p className=" text-slate-500 mt-1 font-medium">
                        {t.dyn(`net.adminComm.type.${step.movement_type}`, step.movement_type)}
                      </p>
                      <p className="text-[10px] text-slate-500 mt-0.5 italic">
                        {step.explanation}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {results.length > 0 && (
                <div className="border-t border-slate-200 pt-3 flex items-center justify-between text-sm">
                  <span className=" text-slate-500 font-medium">{t("net.sim.total")}</span>
                  <span className="font-bold text-emerald-400 text-base">
                    {fmt.euro(results.reduce((sum, r) => sum + r.gross_amount_cents, 0))}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
