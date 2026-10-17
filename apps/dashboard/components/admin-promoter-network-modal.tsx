"use client";

import { useQuery } from "@tanstack/react-query";
import type { BranchMemberRead } from "@/lib/types";
import { BranchVisualizer } from "@/components/branch-visualizer";
import { PromoterAziendaPanel } from "@/components/promoter-azienda-panel";
import { useI18n } from "@/lib/i18n/provider";

async function fetchBranch(agentId: string): Promise<BranchMemberRead[]> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch`);
  if (!res.ok) throw new Error("Impossibile caricare la rete di questo promoter.");
  return res.json();
}

/** Admin-only drill-down into a SPECIFIC promoter's own network -- everything
    that promoter would see logging into their own "La mia Azienda"/"Rete
    Commerciale" tabs (same components, same data, same branch-ownership
    ABAC -- admin roles bypass it, see network/router.py::_assert_branch_access),
    minus the rest of the promoter dashboard shell (shop-sharing, commission
    simulator, support tickets) which isn't relevant from an admin's
    perspective looking in from outside. */
export function AdminPromoterNetworkModal({
  agentId,
  displayName,
  onClose,
}: {
  agentId: string;
  displayName: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const { data: branch, error: branchError, isLoading: branchLoading } = useQuery({
    queryKey: ["admin", "promoter-network", "branch", agentId],
    queryFn: () => fetchBranch(agentId),
  });

  const self = branch?.find((m) => m.depth === 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-6xl max-h-[92vh] overflow-y-auto glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up">
        <div className="flex items-start justify-between mb-6 gap-3">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-brand-600 to-brand-400 flex items-center justify-center text-white font-bold text-lg shrink-0">
              {displayName.trim().charAt(0).toUpperCase() || "?"}
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-900">{t("net.adminPromNet.title", { name: displayName })}</h3>
              <div className="flex items-center gap-2 mt-0.5">
                {self?.promoter_code && (
                  <span className="font-mono text-[10px] text-slate-500">{self.promoter_code}</span>
                )}
                {self?.rank_code && (
                  <span className="px-2 py-0.5 font-bold rounded-md border bg-slate-900/5 text-slate-600 border-slate-300">
                    {self.rank_code}
                  </span>
                )}
                <span className="text-[11px] text-slate-500">
                  {t("net.adminPromNet.adminView")}
                </span>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-900 transition cursor-pointer shrink-0"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-6">
          <PromoterAziendaPanel agentId={agentId} />

          <div>
            <h4 className="text-sm font-semibold text-slate-900 mb-3">{t("net.adminPromNet.tree")}</h4>
            {branchLoading ? (
              <p className="text-sm text-slate-500">{t("net.adminPromNet.loading")}</p>
            ) : branchError ? (
              <p className="text-sm text-rose-400">{t("net.adminPromNet.error")}</p>
            ) : branch && branch.length > 0 ? (
              <BranchVisualizer members={branch} />
            ) : (
              <p className="text-sm text-slate-500">{t("net.adminPromNet.empty")}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
