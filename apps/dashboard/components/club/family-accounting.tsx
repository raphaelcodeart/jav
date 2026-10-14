"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { KindBreakdown, Kpi } from "@/components/club/accounting-charts";
import { FeeStatusPill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { clubGet } from "@/lib/club";
import { CHART, monthShort, type PersonalAccount } from "@/lib/club-accounting";
import { useI18n } from "@/lib/i18n/provider";
import { usePrefersReducedMotion } from "@/lib/motion";

// I conti di chi usa il portale: un genitore, un atleta adulto, o un atleta
// che è anche genitore. Un conto solo; persona per persona solo se ci sono
// figli. Tutto calcolato dal server (/club/accounting/mine).

function useAccount(year: number) {
  return useQuery({
    queryKey: ["club", "accounting", "mine", year],
    queryFn: () => clubGet<PersonalAccount>(`/accounting/mine?year=${year}`),
    placeholderData: (prev) => prev,
  });
}

/** La pagina "I miei conti". */
export function FamilyAccounting({ onNavigate }: { onNavigate: (key: string) => void }) {
  const { t, fmt } = useI18n();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const { data, isLoading, error, isFetching } = useAccount(year);
  if (isLoading) return <Skeleton className="h-96" />;
  if (error || !data) return <EmptyState title={t("famAcc.unavailable")} text={(error as Error)?.message} />;
  const tot = data.totals;
  return (
    <div className={cn("space-y-8 transition-opacity", isFetching && "opacity-70")}>
      <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-[32px] bg-gradient-to-br from-ink-900 via-ink-800 to-brand-800 text-white p-6 sm:p-8">
        <div className="absolute inset-0 opacity-25 bg-[radial-gradient(circle_at_85%_15%,#2a78d6,transparent_40%),radial-gradient(circle_at_10%_100%,#e43f21,transparent_45%)]" aria-hidden="true" />
        <div className="relative flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-accent-300">{t("famAcc.eyebrow")}</p>
            <h2 className="text-3xl sm:text-4xl mt-2">{t("famAcc.title")}</h2>
            <p className="text-white/75 mt-2 text-sm max-w-lg">
              {tot.overdue_cents > 0 ? t("famAcc.heroOverdue", { amount: fmt.euro(tot.overdue_cents) })
                : tot.due_cents > 0 ? t("famAcc.heroDue", { amount: fmt.euro(tot.due_cents) })
                  : t("famAcc.heroClear")}
            </p>
          </div>
          <Select value={String(year)} onChange={(e) => setYear(Number(e.target.value))} className="w-32 text-ink-900" aria-label={t("famAcc.year")}>
            {Array.from({ length: 4 }, (_, i) => thisYear - i).map((y) => <option key={y} value={y}>{y}</option>)}
          </Select>
        </div>
      </motion.section>

      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi tone="income" label={t("famAcc.paidYear", { year })} value={fmt.euro(tot.paid_year_cents)} explain={t("famAcc.paidYearExplain")} />
        <Kpi tone={tot.overdue_cents ? "bad" : "ink"} label={t("famAcc.dueNow")} value={fmt.euro(tot.due_cents)}
          explain={tot.overdue_cents ? t("famAcc.dueNowOverdue", { amount: fmt.euro(tot.overdue_cents) }) : t("famAcc.dueNowExplain")}
          onClick={tot.due_cents ? () => onNavigate("club") : undefined} />
        <Kpi tone="good" label={t("famAcc.savings", { year })} value={fmt.euro(tot.savings_year_cents)} explain={t("famAcc.savingsExplain")} />
        <Kpi label={t("famAcc.allTime")} value={fmt.euro(tot.paid_all_time_cents)} explain={t("famAcc.allTimeExplain")} />
      </section>

      <div className="grid lg:grid-cols-[1.5fr_1fr] gap-6">
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("famAcc.monthsTitle", { year })}</h3>
          <p className="text-xs text-ink-500 mb-2">{t("famAcc.monthsExplain")}</p>
          <MonthsChart data={data} />
        </section>
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("famAcc.byKind")}</h3>
          <p className="text-xs text-ink-500 mb-3">{t("famAcc.byKindExplain")}</p>
          <KindBreakdown byKind={tot.paid_by_kind} />
        </section>
      </div>

      {data.has_children && (
        <section>
          <h3 className="text-xl text-ink-900">{t("famAcc.peopleTitle")}</h3>
          <p className="text-sm text-ink-500 mb-4">{t("famAcc.peopleExplain")}</p>
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {data.people.map((p) => (
              <div key={p.athlete_id ?? "family"} className="glass-card rounded-3xl p-5">
                <p className="font-semibold text-ink-900">{p.athlete_id ? p.name : t("famAcc.membership")}{p.is_self && <span className="text-xs text-ink-500 font-normal"> · {t("famAcc.you")}</span>}</p>
                {!p.athlete_id && <p className="text-xs text-ink-500">{t("famAcc.membershipExplain")}</p>}
                <dl className="mt-3 grid grid-cols-2 gap-y-2 text-sm">
                  <dt className="text-ink-500">{t("famAcc.paidYear", { year })}</dt><dd className="text-right font-semibold tabular-nums">{fmt.euro(p.paid_year_cents)}</dd>
                  <dt className="text-ink-500">{t("famAcc.dueNow")}</dt><dd className={cn("text-right font-semibold tabular-nums", p.overdue_cents > 0 && "text-rose-700")}>{fmt.euro(p.due_cents)}</dd>
                  <dt className="text-ink-500">{t("famAcc.savingsShort")}</dt><dd className="text-right tabular-nums text-emerald-700">{fmt.euro(p.savings_year_cents)}</dd>
                  {p.athlete_id && <><dt className="text-ink-500">{t("famAcc.shopShort")}</dt><dd className="text-right tabular-nums">{fmt.euro(p.shop_year_cents)}</dd></>}
                </dl>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        <section className="glass-card rounded-3xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-base text-ink-900">{t("famAcc.next")}</h3>
            {data.next_payments.length > 0 && <Button size="sm" onClick={() => onNavigate("club")}>{t("famAcc.payNow")}</Button>}
          </div>
          {data.next_payments.length === 0 ? <p className="text-sm text-ink-500 py-6 text-center">{t("famAcc.nothingDue")}</p> : (
            <ul className="space-y-2">
              {data.next_payments.map((f) => (
                <li key={f.id} className="flex items-center justify-between gap-3 rounded-2xl bg-white ring-1 ring-ink-100 px-4 py-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-ink-900 truncate">{f.description}</p>
                    <p className="text-xs text-ink-500">{f.athlete_name ?? t("famAcc.membership")} · {t("club.dueOn", { date: fmt.shortDate(f.due_date) })}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="font-display text-ink-900">{fmt.euro(f.amount_cents)}</p>
                    <FeeStatusPill status={f.status} overdue={f.overdue} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("famAcc.walletTitle")}</h3>
          <p className="text-xs text-ink-500 mb-3">{t("famAcc.walletExplain")}</p>
          <p className="font-display text-3xl text-ink-900">{fmt.euro(data.wallet.balance_cents)}</p>
          <dl className="mt-3 space-y-2 text-sm">
            {([
              [t("famAcc.referrals"), data.wallet.referral_credits_cents, t("famAcc.referralsExplain"), true],
              [t("famAcc.investments"), data.wallet.investments_cents, t("famAcc.investmentsExplain"), true],
              [t("famAcc.creditFees"), data.wallet.credit_spent_on_fees_cents, t("famAcc.creditFeesExplain"), false],
              [t("famAcc.creditShop"), data.wallet.credit_spent_on_shop_cents, t("famAcc.creditShopExplain"), false],
            ] as const).map(([label, cents, explain, plus]) => (
              <div key={label} className="flex items-start justify-between gap-3 border-t border-ink-100 pt-2">
                <div><dt className="text-ink-800 font-semibold">{label}</dt><dd className="text-xs text-ink-500">{explain}</dd></div>
                <dd className={cn("tabular-nums font-semibold shrink-0", plus ? "text-emerald-700" : "text-ink-900")}>{plus ? "+" : "−"}{fmt.euro(cents)}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("famAcc.discountsTitle", { year })}</h3>
          <p className="text-xs text-ink-500 mb-3">{t("famAcc.discountsExplain")}</p>
          {data.discounts.length === 0 ? <p className="text-sm text-ink-500 py-4 text-center">{t("famAcc.noDiscounts")}</p> : (
            <ul className="divide-y divide-ink-100">
              {data.discounts.map((f) => (
                <li key={f.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <p className="text-sm text-ink-900 truncate">{f.description}{f.athlete_name ? ` · ${f.athlete_name}` : ""}</p>
                    <p className="text-xs text-ink-500 truncate">{f.discount_note ?? f.waive_reason ?? (f.absence_adjustment ? t("famAcc.absence") : "")}</p>
                  </div>
                  <span className="text-sm font-semibold text-emerald-700 tabular-nums shrink-0">−{fmt.euro(f.saved_cents)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("famAcc.shopTitle")}</h3>
          <p className="text-xs text-ink-500 mb-3">{t("famAcc.shopExplain")}</p>
          <div className="grid grid-cols-2 gap-4">
            <div><p className="text-xs text-ink-500">{t("famAcc.shopYear", { year })}</p><p className="font-display text-2xl text-ink-900">{fmt.euro(data.shop.year_cents)}</p><p className="text-xs text-ink-500">{t("famAcc.orders", { n: data.shop.orders_year })}</p></div>
            <div><p className="text-xs text-ink-500">{t("famAcc.allTime")}</p><p className="font-display text-2xl text-ink-900">{fmt.euro(data.shop.all_time_cents)}</p></div>
          </div>
          <Button size="sm" variant="secondary" className="mt-4" onClick={() => onNavigate("orders")}>{t("famAcc.openOrders")}</Button>
        </section>
      </div>
    </div>
  );
}

function MonthsChart({ data }: { data: PersonalAccount }) {
  const { t, fmt } = useI18n();
  const reduced = usePrefersReducedMotion();
  const points = data.series.map((p) => ({ label: monthShort(p.month, fmt.tag), fees: p.fees_cents / 100, shop: p.shop_cents / 100 }));
  const names: Record<string, string> = { fees: t("famAcc.series.fees"), shop: t("famAcc.series.shop") };
  return (
    <>
      <div className="h-60" role="img" aria-label={t("famAcc.monthsExplain")}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="label" stroke={CHART.axis} fontSize={11} tickLine={false} axisLine={false} />
            <YAxis stroke={CHART.axis} fontSize={11} tickLine={false} axisLine={false} width={52}
              tickFormatter={(v: number) => fmt.euroUnits(v, { maximumFractionDigits: 0 })} />
            <Tooltip contentStyle={{ background: "#fff", border: "1px solid #d9d8d8", borderRadius: 12, fontSize: 12 }}
              cursor={{ fill: "rgba(22,21,21,0.04)" }}
              formatter={(value, name) => [fmt.euroUnits(Number(value)), names[String(name)] ?? String(name)]} />
            <Legend formatter={(value: string) => <span className="text-xs text-ink-600">{names[value] ?? value}</span>} iconSize={10} />
            <Bar dataKey="fees" stackId="m" fill={CHART.income} maxBarSize={22} isAnimationActive={!reduced} stroke="#fff" strokeWidth={1} />
            <Bar dataKey="shop" stackId="m" fill={CHART.costs} radius={[4, 4, 0, 0]} maxBarSize={22} isAnimationActive={!reduced} stroke="#fff" strokeWidth={1} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2">
        <summary className="text-xs font-semibold text-ink-500 cursor-pointer hover:text-ink-800">{t("acc.showTable")}</summary>
        <table className="mt-2 w-full text-xs tabular-nums">
          <thead><tr className="text-ink-500 text-left"><th className="py-1">{t("acc.colMonth")}</th><th className="py-1 text-right">{names.fees}</th><th className="py-1 text-right">{names.shop}</th></tr></thead>
          <tbody>{data.series.map((p) => (
            <tr key={p.month} className="border-t border-ink-100"><td className="py-1">{monthShort(p.month, fmt.tag)}</td><td className="py-1 text-right">{fmt.euro(p.fees_cents)}</td><td className="py-1 text-right">{fmt.euro(p.shop_cents)}</td></tr>
          ))}</tbody>
        </table>
      </details>
    </>
  );
}

/** Il riquadro sulla home della famiglia: tre numeri e la strada per i conti. */
export function FamilyAccountingCard({ onOpen }: { onOpen: () => void }) {
  const { t, fmt } = useI18n();
  const year = new Date().getFullYear();
  const { data } = useAccount(year);
  if (!data) return null;
  return (
    <section className="glass-card rounded-3xl p-5 flex flex-col sm:flex-row sm:items-center gap-4">
      <div className="flex-1 min-w-0">
        <h3 className="text-base text-ink-900">{t("famAcc.cardTitle")}</h3>
        <p className="text-xs text-ink-500">{t("famAcc.cardExplain")}</p>
      </div>
      <dl className="grid grid-cols-3 gap-4 text-sm">
        <div><dt className="text-xs text-ink-500">{t("famAcc.paidYear", { year })}</dt><dd className="font-display text-lg text-ink-900 tabular-nums">{fmt.euro(data.totals.paid_year_cents)}</dd></div>
        <div><dt className="text-xs text-ink-500">{t("famAcc.dueNow")}</dt><dd className={cn("font-display text-lg tabular-nums", data.totals.overdue_cents ? "text-rose-700" : "text-ink-900")}>{fmt.euro(data.totals.due_cents)}</dd></div>
        <div><dt className="text-xs text-ink-500">{t("famAcc.savingsShort")}</dt><dd className="font-display text-lg text-emerald-700 tabular-nums">{fmt.euro(data.totals.savings_year_cents)}</dd></div>
      </dl>
      <Button variant="secondary" onClick={onOpen}>{t("famAcc.cardOpen")}</Button>
    </section>
  );
}
