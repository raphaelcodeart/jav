"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { JavCashAmount } from "@/components/jav-cash-amount";
import { friendlyApiError } from "@/lib/api-error";
import {
  movementCategory, movementDetailRef, movementDirection, movementEntity, movementReferenceLink,
  movementsOfEntity, shortCode,
} from "@/lib/accounting-format";
import { useI18n } from "@/lib/i18n/provider";
import type { AccountingDetailRead, FinancialMovementRead } from "@/lib/types";

const TONE_BADGE: Record<string, string> = {
  success: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
  warning: "bg-amber-500/10 text-amber-700 border-amber-500/25",
  danger: "bg-rose-500/10 text-rose-400 border-rose-500/25",
  neutral: "bg-slate-500/10 text-slate-400 border-slate-500/25",
};

const INSTALMENT_CLASS: Record<string, string> = {
  PAID: "text-emerald-400",
  SCHEDULED: "text-slate-400",
};

type Translate = ReturnType<typeof useI18n>["t"];

/** lib/accounting-format.ts in the reader's language: the same dates, amounts
    and movement labels, with the locale and the words taken from i18n instead
    of fixed Italian. Shared by every "Contabilità" screen (this modal,
    accounting-panel.tsx, admin-accounting-panel.tsx). */
export function makeAccountingFormat(t: Translate, tag: string) {
  const ref = (kind: "order" | "contract", id: string) =>
    kind === "order"
      ? t("acct.wallet.orderRef", { code: shortCode(id) })
      : t("acct.mv.contractRef", { code: shortCode(id) });
  return {
    euro: (cents: number) => (cents / 100).toLocaleString(tag, { style: "currency", currency: "EUR" }),
    javCash: (cents: number) =>
      `${(cents / 100).toLocaleString(tag, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} JavCash`,
    plainAmount: (cents: number) =>
      (cents / 100).toLocaleString(tag, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    formatDate: (iso: string) => new Date(iso).toLocaleString(tag, { dateStyle: "medium", timeStyle: "short" }),
    formatDateOnly: (iso: string) => new Date(iso).toLocaleDateString(tag),
    formatDateTimeFull: (iso: string) =>
      new Date(iso).toLocaleString(tag, {
        day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
      }),
    formatDayShort: (iso: string) => new Date(iso).toLocaleDateString(tag, { day: "2-digit", month: "short" }),
    formatTime: (iso: string) => new Date(iso).toLocaleTimeString(tag, { hour: "2-digit", minute: "2-digit" }),
    monthLabel: (key: string) => {
      const [year, month] = key.split("-").map(Number);
      const label = new Date(year!, month! - 1, 1).toLocaleDateString(tag, { month: "long", year: "numeric" });
      return label.charAt(0).toUpperCase() + label.slice(1);
    },
    /** movementCategory() stays the code the screens match on; this is its label. */
    categoryLabel: (m: FinancialMovementRead) => {
      const category = movementCategory(m);
      return t.dyn(`acct.category.${category}`, category);
    },
    paymentMethodLabel: (method: string) => t.dyn(`acct.paymentMethod.${method}`, method),
    movementLabel: (m: FinancialMovementRead) => {
      if (m.kind === "ORDER_PAYMENT") {
        const method = m.payment_method ? t.dyn(`acct.paymentMethod.${m.payment_method}`, m.payment_method) : null;
        return method ? t("acct.mv.orderPaymentWith", { method }) : t("acct.mv.orderPayment");
      }
      if (m.kind === "CONTRACT_PAYMENT") {
        return m.note ? t("acct.mv.contractPaymentNote", { note: m.note }) : t("acct.mv.contractPayment");
      }
      const sourceLabel = m.source ? t.dyn(`acct.wallet.source.${m.source}`, "") : "";
      return sourceLabel || (m.type ? t.dyn(`acct.mv.type.${m.type}`, m.type) : t("acct.mv.walletMovement"));
    },
    movementEntity: (m: FinancialMovementRead) => {
      const entity = movementEntity(m);
      if (!entity) return null;
      return { ...entity, label: m.order_id ? ref("order", m.order_id) : ref("contract", m.contract_id!) };
    },
    movementReferenceLink: (m: FinancialMovementRead, basePath: "/customer" | "/promoter") => {
      const link = movementReferenceLink(m, basePath);
      if (!link) return null;
      return { ...link, label: m.order_id ? ref("order", m.order_id) : ref("contract", m.contract_id!) };
    },
    relatedRefLabel: (related: string) =>
      ref(related.startsWith("order:") ? "order" : "contract", related.split(":")[1]!),
  };
}

export function useAccountingFormat() {
  const { t, fmt } = useI18n();
  return useMemo(() => makeAccountingFormat(t, fmt.tag), [t, fmt.tag]);
}

/** The detail of one movement -- or of the order or contract it belongs to
    (Session 54).

    Everything is linked: a JavCash movement shows the order it paid, the
    order shows every movement it produced (bank transfer, JavCash used,
    cashback), and each of those opens in place, with "Indietro" to return.
    The timeline carries the exact time of every step and who did it -- the
    administrator who confirmed a transfer, for instance. */
export function AccountingDetailModal({
  initialRef,
  scope,
  movements,
  onClose,
  onOpenTab,
}: {
  initialRef: string;
  /** "mine" for the customer's own things, "admin" for the back office. */
  scope: "mine" | "admin";
  /** The list on screen, to show the movements tied to the opened thing. */
  movements: FinancialMovementRead[];
  onClose: () => void;
  onOpenTab?: (tab: string) => void;
}) {
  const { t } = useI18n();
  const { euro, formatDateOnly, formatDateTimeFull, movementLabel, relatedRefLabel } = useAccountingFormat();
  const [stack, setStack] = useState<string[]>([initialRef]);
  const ref = stack[stack.length - 1]!;
  const { data, error, isLoading } = useQuery<AccountingDetailRead>({
    queryKey: ["accounting", scope, "detail", ref],
    queryFn: async () => {
      const res = await fetch(`/api/proxy/accounting/${scope}/detail?ref=${encodeURIComponent(ref)}`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
  });

  function open(next: string) {
    if (next !== ref) setStack((s) => [...s, next]);
  }

  const linked = data
    ? movementsOfEntity(movements, data).filter((m) => movementDetailRef(m) !== ref || m.kind === "WALLET")
    : [];

  return (
    <div
      className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center sm:p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full sm:max-w-2xl max-h-[92vh] overflow-y-auto rounded-t-3xl sm:rounded-2xl border border-slate-200 bg-white shadow-2xl animate-scale-up"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-5 py-3 border-b border-slate-200 bg-white/95 backdrop-blur">
          <div className="flex items-center gap-2 min-w-0">
            {stack.length > 1 && (
              <button
                onClick={() => setStack((s) => s.slice(0, -1))}
                className="px-2.5 py-1 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-900/5 cursor-pointer"
              >
                ← {t("acct.detail.back")}
              </button>
            )}
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 truncate">
              {data ? t.dyn(`acct.detail.kind.${data.kind}`, data.kind) : t("acct.detail.detail")}
            </span>
          </div>
          <button onClick={onClose} aria-label={t("common.close")} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-900 hover:bg-slate-100 cursor-pointer">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {isLoading && <div className="m-5 h-48 rounded-2xl bg-slate-900/5 animate-pulse" />}
        {error && <p className="m-5 text-sm text-rose-400">{(error as Error).message}</p>}

        {data && (
          <div className="p-5 space-y-6">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="text-xl font-bold text-slate-900 leading-tight">{data.title}</h3>
                {data.subtitle && <p className="text-xs text-slate-500 mt-1">{data.subtitle}</p>}
                {data.status && (
                  <span className={`inline-block mt-2 px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${TONE_BADGE[data.status_tone]}`}>
                    {data.status}
                  </span>
                )}
              </div>
              {data.amount_cents != null && (
                <div className={`text-right text-2xl font-extrabold tabular-nums shrink-0 ${
                  data.direction === "in" ? "text-emerald-400" : " text-slate-900"
                }`}>
                  {data.currency === "JAVCASH" ? (
                    <JavCashAmount cents={Math.abs(data.amount_cents)} sign={data.direction === "out" ? "-" : "+"} />
                  ) : (
                    euro(Math.abs(data.amount_cents))
                  )}
                </div>
              )}
            </div>

            {data.facts.length > 0 && (
              <section>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">{t("acct.detail.details")}</h4>
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 rounded-2xl border border-slate-200 px-4">
                  {data.facts.map((fact) => (
                    <div key={fact.label} className="py-2.5 border-b border-slate-100 min-w-0">
                      <dt className="text-[11px] text-slate-500">{fact.label}</dt>
                      <dd className={`text-sm font-semibold text-slate-800 break-words ${fact.mono ? "font-mono text-xs" : ""}`}>
                        {fact.value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}

            {data.timeline.length > 0 && (
              <section>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-3">{t("acct.detail.timeline")}</h4>
                <ol className="relative ml-2 border-l border-slate-200 space-y-4">
                  {data.timeline.map((event, i) => (
                    <li key={`${event.label}-${i}`} className="ml-4">
                      <span
                        className={`absolute -left-[5px] mt-1.5 w-2.5 h-2.5 rounded-full ${
                          event.tone === "pending"
                            ? "bg-slate-600 ring-2 ring-slate-500/30"
                            : event.tone === "warning"
                              ? "bg-amber-400"
                              : "bg-emerald-400"
                        }`}
                      />
                      <p className={`text-sm font-semibold ${event.tone === "pending" ? "text-slate-400" : " text-slate-900"}`}>
                        {event.label}
                      </p>
                      <p className="text-[11px] text-slate-500">
                        {event.at ? <span className="font-bold tabular-nums">{formatDateTimeFull(event.at)}</span> : t("acct.detail.pending")}
                        {event.by && <> · {event.by}</>}
                      </p>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {data.instalments.length > 0 && (
              <section>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
                  {data.instalments.length === 1 ? t("acct.detail.payment") : t("acct.detail.instalmentsPaid", { paid: data.instalments.filter((r) => r.status === "PAID").length, total: data.instalments.length })}
                </h4>
                <div className="overflow-x-auto rounded-2xl border border-slate-200">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-slate-500 border-b border-slate-200">
                        <th className="py-2 px-3">#</th>
                        <th className="py-2 px-3">{t("acct.detail.due")}</th>
                        <th className="py-2 px-3 text-right">{t("acct.col.amount")}</th>
                        <th className="py-2 px-3">{t("acct.col.status")}</th>
                        <th className="py-2 px-3">{t("acct.detail.collected")}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {data.instalments.map((row) => (
                        <tr key={row.number}>
                          <td className="py-2 px-3 font-bold text-slate-600">{row.number}</td>
                          <td className="py-2 px-3 text-slate-400">{formatDateOnly(row.due_date)}</td>
                          <td className="py-2 px-3 text-right font-semibold text-slate-900 tabular-nums">{euro(row.amount_cents)}</td>
                          <td className={`py-2 px-3 font-semibold ${INSTALMENT_CLASS[row.status] ?? ""}`}>
                            {t.dyn(`acct.detail.instalment.${row.status}`, row.status)}
                          </td>
                          <td className="py-2 px-3 text-slate-400">
                            {row.paid_at ? (
                              <>
                                <span className="font-bold tabular-nums">{formatDateTimeFull(row.paid_at)}</span>
                                {row.source && <span className="block text-[10px]">{row.source}{row.confirmed_by ? ` · ${row.confirmed_by}` : ""}</span>}
                              </>
                            ) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {(linked.length > 0 || data.related_refs.length > 0) && (
              <section>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">{t("acct.detail.linked")}</h4>
                <div className="space-y-1.5">
                  {data.related_refs.map((related) => (
                    <button
                      key={related}
                      onClick={() => open(related)}
                      className="w-full flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl border border-brand-500/25 bg-brand-500/5 hover:bg-brand-500/10 text-left cursor-pointer"
                    >
                      <span className="text-sm font-semibold text-brand-700">
                        {relatedRefLabel(related)}
                      </span>
                      <span className="text-brand-600">→</span>
                    </button>
                  ))}
                  {linked.map((m) => {
                    const target = movementDetailRef(m);
                    const out = movementDirection(m) === "out";
                    return (
                      <button
                        key={m.id}
                        onClick={() => target && open(target)}
                        disabled={!target || target === ref}
                        className="w-full flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-left cursor-pointer disabled:cursor-default"
                      >
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-slate-900 truncate">{movementLabel(m)}</span>
                          <span className="block text-[11px] text-slate-500 font-bold tabular-nums">{formatDateTimeFull(m.created_at)}</span>
                        </span>
                        <span className={`text-sm font-bold tabular-nums shrink-0 ${out ? "text-rose-400" : "text-emerald-400"}`}>
                          {m.currency === "JAVCASH" ? (
                            <JavCashAmount cents={Math.abs(m.amount_cents)} sign={out ? "-" : "+"} />
                          ) : (
                            `${out ? "-" : "+"}${euro(Math.abs(m.amount_cents))}`
                          )}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>
            )}

            {onOpenTab && data.tab && (
              <button
                onClick={() => onOpenTab(data.tab!)}
                className="w-full rounded-xl bg-slate-900/5 hover:bg-slate-900/10 py-2.5 text-xs font-semibold text-slate-700 cursor-pointer"
              >
                {t.dyn(`acct.detail.tab.${data.tab}`, data.tab)}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
