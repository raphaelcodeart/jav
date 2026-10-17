"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";
import type { CommissionPreviewRead, ContractCommissionLogRead } from "@/lib/types";

/** The commission preview, as the administrator reads it before approving.
 *
 *  Every figure comes from the server (commissions/services/preview.py): who
 *  is above the customer, what each of them earns, and how that is spread
 *  over the customer's payments. This component only lays it out -- the
 *  same rendering is reused, read-only, in the log afterwards. */
export function CommissionPreviewView({ preview }: { preview: CommissionPreviewRead }) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(fmt.tag) : "—");
  const { payment } = preview;
  const payees = preview.beneficiaries.filter((b) => b.total_cents > 0).length + (preview.first_referrer_bonus ? 1 : 0);
  const split = payment.paid && (payment.instalments ?? 1) > 1;
  const firstRow = payment.schedule[0];

  return (
    <div className="space-y-4">
      <div className="p-4 rounded-xl bg-brand-500/10 border border-brand-500/20">
        <p className="text-sm text-slate-900">
          {t("ctr.preview.totalLabel")}{" "}
          <strong className="text-brand-600 tabular-nums">{euro(preview.total_commission_cents)}</strong>
          {" "}{t("ctr.preview.toPromoters", { n: payees })}
        </p>
        <p className="text-xs text-slate-600 mt-1">
          {!payment.paid
            ? t("ctr.preview.notPaidYet")
            : split
              ? t("ctr.preview.splitPayment", { n: payment.instalments ?? 0, first: euro(firstRow?.commission_cents ?? 0), until: formatDate(payment.last_release_date) })
              : t("ctr.preview.singlePayment")}
        </p>
      </div>

      {preview.warnings.length > 0 && (
        <ul className="space-y-1.5">
          {preview.warnings.map((w) => (
            <li key={w} className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 text-xs">{w}</li>
          ))}
        </ul>
      )}

      <div>
        <p className=" font-semibold text-slate-500 uppercase mb-2">
          {t("ctr.preview.whoGetsWhat")}
        </p>
        <div className="space-y-1.5">
          {preview.beneficiaries.map((b) => (
            <div
              key={b.agent_id}
              className={`flex items-center justify-between gap-3 p-3 rounded-xl border ${
                b.total_cents > 0
                  ? " bg-slate-900/5 border-slate-200"
                  : "border-dashed border-slate-200 opacity-60"
              }`}
            >
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-900 truncate">{b.name}</p>
                <p className=" text-slate-500">
                  {b.role} · {t("ctr.preview.rank")} <span className="text-brand-600 font-semibold">{b.rank_code}</span> · {b.movement_label}
                </p>
                <p className="text-[10px] text-slate-500 mt-0.5">{b.explanation}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-base font-bold text-brand-600 tabular-nums">{euro(b.total_cents)}</p>
                {split && b.total_cents > 0 && firstRow && (
                  <p className="text-[10px] text-slate-500">
                    {t("ctr.preview.perInstalment", { amount: euro(firstRow.per_beneficiary_cents[b.agent_id] ?? 0), n: payment.instalments ?? 0 })}
                  </p>
                )}
              </div>
            </div>
          ))}
          {preview.first_referrer_bonus && (
            <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-900/5 border border-slate-200">
              <div>
                <p className="text-sm font-semibold text-slate-900">{preview.first_referrer_bonus.name}</p>
                <p className=" text-slate-500">
                  {t("ctr.preview.firstReferrerBonus")} · {preview.first_referrer_bonus.note}
                </p>
              </div>
              <p className="text-base font-bold text-brand-600 tabular-nums">{euro(preview.first_referrer_bonus.amount_cents)}</p>
            </div>
          )}
          {preview.beneficiaries.length === 0 && (
            <p className="text-xs text-slate-500">{t("ctr.preview.noChain")}</p>
          )}
        </div>
      </div>

      <div>
        <p className=" font-semibold text-slate-500 uppercase mb-2">
          {t("ctr.preview.howReleased")}
        </p>
        {payment.paid ? (
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className=" text-slate-500 border-b border-slate-200">
                  <th className="py-2 px-3">{t("ctr.preview.col.instalment")}</th>
                  <th className="py-2 px-3">{t("ctr.preview.col.dueDate")}</th>
                  <th className="py-2 px-3 text-right">{t("ctr.preview.col.customerAmount")}</th>
                  <th className="py-2 px-3 text-right">{t("ctr.preview.col.commissions")}</th>
                  <th className="py-2 px-3">{t("ctr.preview.col.whenReleased")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-600">
                {payment.schedule.map((row) => (
                  <tr key={row.number}>
                    <td className="py-2 px-3 font-semibold">{t("ctr.preview.nOfTotal", { n: row.number, total: payment.instalments ?? 0 })}</td>
                    <td className="py-2 px-3">{formatDate(row.due_date)}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{euro(row.customer_amount_cents)}</td>
                    <td className="py-2 px-3 text-right tabular-nums font-semibold text-brand-600">{euro(row.commission_cents)}</td>
                    <td className="py-2 px-3 text-[11px]">{row.release}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {payment.scenarios.map((s) => (
              <div key={s.plan_key} className="p-3 rounded-xl bg-slate-900/5 border border-slate-200">
                <p className="text-xs font-semibold text-slate-900">{t("ctr.preview.ifPays", { plan: s.plan_label.toLowerCase() })}</p>
                <p className="text-sm font-bold text-brand-600 tabular-nums mt-1">{euro(s.commission_per_instalment_cents)}</p>
                <p className="text-[10px] text-slate-500">
                  {s.instalments === 1 ? t("ctr.preview.allAtOnce") : t("ctr.preview.eachInstalment", { n: s.instalments })}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {preview.customer_cashback_cents > 0 && (
        <p className=" text-slate-500">
          {t("ctr.preview.cashbackBefore")}{" "}
          <strong className="text-emerald-400 tabular-nums">
            {(preview.customer_cashback_cents / 100).toLocaleString(fmt.tag, { minimumFractionDigits: 2 })} JavCash
          </strong>{" "}
          {t("ctr.preview.cashbackAfter")}
        </p>
      )}
    </div>
  );
}

async function fetchLog(contractId: string): Promise<ContractCommissionLogRead> {
  const res = await fetch(`/api/proxy/contracts/${contractId}/commission-log`);
  if (!res.ok) throw new Error("commission log fetch failed");
  return res.json();
}

/** "Registro provvigioni" of one contract: the preview the administrator
 *  accepted (who, when, exactly what they saw), and the instalment schedule
 *  with what each payment has released so far. Every instalment is
 *  confirmed here by hand, when its bank transfer arrives. */
export function ContractCommissionLog({ contractId }: { contractId: string }) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(fmt.tag) : "—");
  const queryClient = useQueryClient();
  const { data, error } = useQuery({ queryKey: ["admin", "commission-log", contractId], queryFn: () => fetchLog(contractId) });
  const [showPreview, setShowPreview] = useState(false);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  async function handleConfirm(number: number) {
    if (!window.confirm(t("ctr.log.confirmInstalment", { n: number }))) return;
    setConfirming(number);
    setConfirmError(null);
    try {
      const res = await fetch(`/api/proxy/contracts/${contractId}/instalments/${number}/confirm`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "commission-log", contractId] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "commissions"] });
    } catch (err: any) {
      setConfirmError(err.message || t("ctr.log.confirmError"));
    } finally {
      setConfirming(null);
    }
  }

  if (error) return <p className="text-sm text-rose-400">{t("ctr.log.loadError")}</p>;
  if (!data) return <div className="h-20 rounded-xl bg-slate-900/5 animate-pulse" />;

  return (
    <div className="space-y-4">
      {data.accepted_plan ? (
        <div className="p-3 rounded-xl bg-slate-900/5 border border-slate-200">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-xs text-slate-600">
              {t("ctr.log.acceptedOn")} <strong>{new Date(data.accepted_plan.accepted_at).toLocaleString(fmt.tag)}</strong>
              {data.accepted_plan.accepted_by && <> {t("ctr.log.by")} <strong>{data.accepted_plan.accepted_by}</strong></>} · {t("ctr.log.total")}{" "}
              <strong className="text-brand-600">{euro(data.accepted_plan.total_commission_cents)}</strong>
            </p>
            <button
              onClick={() => setShowPreview((v) => !v)}
              className="px-2.5 py-1 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 font-semibold text-slate-600 transition cursor-pointer"
            >
              {showPreview ? t("ctr.log.hidePreview") : t("ctr.log.openPreview")}
            </button>
          </div>
          {showPreview && (
            <div className="mt-4">
              <CommissionPreviewView preview={data.accepted_plan.preview} />
            </div>
          )}
        </div>
      ) : (
        <p className="text-xs text-slate-500">
          {t("ctr.log.noPreview")}
        </p>
      )}

      {data.instalments.length > 0 && (
        <div>
          <p className=" font-semibold text-slate-500 uppercase mb-2">{t("ctr.log.instalmentsTitle")}</p>
          {confirmError && (
            <div className="p-2.5 mb-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{confirmError}</div>
          )}
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className=" text-slate-500 border-b border-slate-200">
                  <th className="py-2 px-3">{t("ctr.preview.col.instalment")}</th>
                  <th className="py-2 px-3">{t("ctr.log.col.due")}</th>
                  <th className="py-2 px-3 text-right">{t("ctr.comm.col.amount")}</th>
                  <th className="py-2 px-3">{t("ctr.log.col.payment")}</th>
                  <th className="py-2 px-3">{t("ctr.preview.col.commissions")}</th>
                  <th className="py-2 px-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-600">
                {data.instalments.map((r) => (
                  <tr key={r.number}>
                    <td className="py-2 px-3 font-semibold">{t("ctr.preview.nOfTotal", { n: r.number, total: r.instalments_total })}</td>
                    <td className="py-2 px-3">{formatDate(r.due_date)}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{euro(r.amount_cents)}</td>
                    <td className="py-2 px-3">
                      {r.status === "PAID" ? (
                        <span className="text-emerald-400">
                          {t("ctr.log.paidOn", { date: formatDate(r.paid_at) })}
                          <span className="block text-[10px] text-slate-500">
                            {r.payment_source ? t.dyn(`ctr.log.source.${r.payment_source}`, r.payment_source) : null}
                            {r.confirmed_by ? ` · ${r.confirmed_by}` : ""}
                          </span>
                        </span>
                      ) : (
                        <span className="text-slate-500">{t("ctr.log.pending")}</span>
                      )}
                    </td>
                    <td className="py-2 px-3">
                      {r.commission_released_at ? (
                        <span className="text-emerald-400">{t("ctr.log.releasedOn", { date: formatDate(r.commission_released_at) })}</span>
                      ) : r.commission_pending ? (
                        <span className="text-sky-400">{t("ctr.log.calculating")}</span>
                      ) : r.status === "PAID" ? (
                        <span className="text-amber-700">{t("ctr.log.onActivation")}</span>
                      ) : (
                        <span className="text-slate-500">{t("ctr.log.onInstalmentPaid")}</span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right">
                      {r.status !== "PAID" && (
                        <button
                          onClick={() => handleConfirm(r.number)}
                          disabled={confirming === r.number}
                          className="px-2.5 py-1 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50 whitespace-nowrap"
                        >
                          {confirming === r.number ? "..." : t("ctr.log.confirmReceived")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
