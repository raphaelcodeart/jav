"use client";

import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import type { CommissionMovementDetailRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

// Movement type / status labels: net.adminComm.type.* / net.adminComm.status.*
// (FIRST_REFERRER_BONUS is paid once per contract to the promoter who
// ORIGINALLY brought the customer in -- additive, not a replacement).

/** "Da dove arriva" questa provvigione, in termini che hanno senso per chi la
    riceve -- depth_from_producer è già relativo al beneficiario (te) quando
    la riga viene da /commissions/mine/detailed, quindi depth 0 = prodotto
    personalmente da te, depth 1 = da un tuo diretto, depth N = da N livelli
    sotto di te nella rete. */
function levelLabel(t: ReturnType<typeof useI18n>["t"], depth: number | null): string {
  if (depth === null) return "—";
  if (depth === 0) return t("net.myComm.level.self");
  if (depth === 1) return t("net.myComm.level.direct");
  return t("net.myComm.level.n", { n: depth });
}

function getStatusColor(status: string): string {
  if (status === "PAID") return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
  if (status === "REVERSED" || status === "CANCELLED") return "bg-rose-500/10 text-rose-400 border-rose-500/20";
  return "bg-sky-500/10 text-sky-400 border-sky-500/20";
}

async function fetchMyCommissionsDetailed(): Promise<CommissionMovementDetailRead[]> {
  const res = await fetch("/api/proxy/commissions/mine/detailed");
  if (!res.ok) throw new Error("Impossibile caricare le provvigioni");
  return res.json();
}

export function MyCommissions() {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const { data, isLoading, error } = useQuery({
    queryKey: ["commissions", "mine", "detailed"],
    queryFn: fetchMyCommissionsDetailed,
  });
  const [expandedId, setExpandedId] = useState<string | null>(null);
  // Declared before the loading/error/empty early returns below: a hook
  // must run on every render.
  const pagination = usePagination(data ?? []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-500 gap-2">
        <svg className="animate-spin h-5 w-5 text-brand-600" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <span>{t("net.myComm.loading")}</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
        {t("net.myComm.error")}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500 text-sm">
        {t("net.myComm.empty")}
      </div>
    );
  }

  const totalAccrued = data.filter((m) => m.status === "ACCRUED").reduce((sum, m) => sum + m.amount_cents, 0);
  const totalPaid = data.filter((m) => m.status === "PAID").reduce((sum, m) => sum + m.amount_cents, 0);

  return (
    <div className="space-y-6">
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500 font-semibold bg-slate-900/[0.02]">
              <th className="py-3 px-4">{t("net.adminComm.col.customerContract")}</th>
              <th className="py-3 px-4">{t("net.myComm.col.origin")}</th>
              <th className="py-3 px-4">{t("net.adminComm.col.type")}</th>
              <th className="py-3 px-4 text-right">{t("net.adminComm.col.amount")}</th>
              <th className="py-3 px-4">{t("net.adminComm.col.status")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {pagination.pageItems.map((m) => (
              <Fragment key={m.id}>
                <tr
                  className=" text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer"
                  onClick={() => setExpandedId(expandedId === m.id ? null : m.id)}
                >
                  <td className="py-3 px-4">
                    <div className="font-medium text-slate-900">{m.customer_name}</div>
                    <div className="text-[11px] text-slate-500">{m.product_name}</div>
                  </td>
                  <td className="py-3 px-4">{levelLabel(t, m.depth_from_producer)}</td>
                  <td className="py-3 px-4">{t.dyn(`net.adminComm.type.${m.movement_type}`, m.movement_type)}</td>
                  <td className="py-3 px-4 text-right font-semibold text-brand-600">{euro(m.amount_cents)}</td>
                  <td className="py-3 px-4">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border ${getStatusColor(m.status)}`}>
                      {t.dyn(`net.adminComm.status.${m.status}`, m.status)}
                    </span>
                  </td>
                </tr>
                {expandedId === m.id && (
                  <tr className=" bg-slate-900/[0.02]">
                    <td colSpan={5} className="px-4 py-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                        <div className="space-y-1.5">
                          <p><span className="text-slate-500">{t("net.myComm.d.contractId")}</span> <span className="font-mono text-[10px] text-slate-400">{m.contract_id}</span></p>
                          <p><span className="text-slate-500">{t("net.adminComm.d.value")}</span> <span className=" text-slate-600">{euro(m.value_cents)}</span></p>
                          <p><span className="text-slate-500">{t("net.myComm.d.producedBy")}</span> <span className=" text-slate-600">{m.producer_name}</span></p>
                          <p><span className="text-slate-500">{t("net.myComm.d.yourRank")}</span> <span className="font-semibold text-brand-600">{m.rank_at_calculation ?? "—"}</span></p>
                        </div>
                        <div className="space-y-1.5">
                          {m.base_amount_cents !== null && (
                            <p><span className="text-slate-500">{t("net.myComm.d.baseToken")}</span> <span className=" text-slate-600">{euro(m.base_amount_cents)}</span></p>
                          )}
                          {m.already_distributed_cents !== null && m.already_distributed_cents > 0 && (
                            <p><span className="text-slate-500">{t("net.adminComm.d.alreadyDistributed")}</span> <span className=" text-slate-600">{euro(m.already_distributed_cents)}</span></p>
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

      <Pagination {...pagination} label={t("net.myComm.pagLabel")} />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="flex items-center justify-between p-4 rounded-xl bg-gradient-to-r from-sky-600/20 to-sky-500/10 border border-sky-500/30">
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">{t("net.myComm.totalAccrued")}</h4>
            <p className=" text-slate-500">{t("net.myComm.notYetPaid")}</p>
          </div>
          <span className="text-xl font-bold text-sky-400">{euro(totalAccrued)}</span>
        </div>
        <div className="flex items-center justify-between p-4 rounded-xl bg-gradient-to-r from-brand-600/20 to-brand-400/20 border border-brand-500/30">
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">{t("net.myComm.totalPaid")}</h4>
            <p className=" text-slate-500">{t("net.myComm.alreadyReceived")}</p>
          </div>
          <span className="text-xl font-bold text-emerald-400">{euro(totalPaid)}</span>
        </div>
      </div>
    </div>
  );
}
