"use client";

import { useQuery } from "@tanstack/react-query";
import type { ContractStatusHistoryRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

async function fetchStatusHistory(contractId: string): Promise<ContractStatusHistoryRead[]> {
  const res = await fetch(`/api/proxy/contracts/${contractId}/status-history`);
  if (!res.ok) throw new Error("status-history fetch failed");
  return res.json();
}

export function ContractStatusHistoryModal({
  contractId,
  onClose,
}: {
  contractId: string;
  onClose: () => void;
}) {
  const { t, fmt } = useI18n();
  const label = (status: string) => t.dyn(`ctr.status.${status}`, status);
  const { data: history, error, isLoading } = useQuery({
    queryKey: ["admin", "contracts", "status-history", contractId],
    queryFn: () => fetchStatusHistory(contractId),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-lg max-h-[85vh] overflow-y-auto glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up">
        <div className="flex items-start justify-between mb-4 gap-3">
          <div>
            <h3 className="text-lg font-bold text-slate-900">{t("ctr.history.title")}</h3>
            <div className="font-mono text-[10px] text-slate-500 mt-1">{contractId}</div>
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

        {error && (
          <p className="text-sm text-rose-400 mb-4">{t("ctr.history.loadError")}</p>
        )}
        {isLoading && <p className="text-sm text-slate-500 py-8 text-center">{t("ctr.common.loading")}</p>}
        {!isLoading && history && history.length === 0 && (
          <p className="text-sm text-slate-500 py-8 text-center">{t("ctr.history.empty")}</p>
        )}

        {!isLoading && history && history.length > 0 && (
          <ol className="relative border-l border-slate-300 ml-2 space-y-6">
            {history.map((h) => (
              <li key={h.id} className="ml-4">
                <span className="absolute -left-[5px] mt-1.5 w-2.5 h-2.5 rounded-full bg-brand-500" />
                <div className="flex items-center gap-2 flex-wrap">
                  {h.from_status && (
                    <>
                      <span className="text-xs text-slate-500">{label(h.from_status)}</span>
                      <span className="text-slate-600">→</span>
                    </>
                  )}
                  <span className="text-sm font-semibold text-slate-900">{label(h.to_status)}</span>
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  {new Date(h.created_at).toLocaleString(fmt.tag)} · {h.actor_name}
                </div>
                {h.reason && (
                  <div className="text-xs text-slate-600 mt-1">
                    <span className="text-slate-500">{t("ctr.history.reason")} </span>{h.reason}
                  </div>
                )}
                {h.notes && (
                  <div className="text-xs text-slate-500 mt-1">
                    <span className="text-slate-500">{t("ctr.history.notes")} </span>{h.notes}
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
