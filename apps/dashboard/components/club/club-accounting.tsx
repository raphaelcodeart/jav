"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { ProgressBar } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import {
  AgingBars, DeltaBadge, IncomeCostChart, KindBreakdown, Kpi, RankBars, SeriesTable, StatementLine,
} from "@/components/club/accounting-charts";
import { cn } from "@/lib/cn";
import { clubGet, clubSend, hoursLabel } from "@/lib/club";
import {
  CHART, EXPENSE_CATEGORIES, FEE_KINDS, PAYMENT_METHODS, currentMonth, delta, monthLong, pctLabel, toCents,
  type ClubSummary, type Debts, type Expense, type Figures, type Ledger, type RecurringExpense, type StaffCost,
} from "@/lib/club-accounting";
import { downloadCsv } from "@/lib/csv-export";
import { useI18n } from "@/lib/i18n/provider";

// La contabilità del club: la home con i numeri che contano e la pagina
// "Contabilità" con conto economico, libro cassa, spese, costi fissi, costo
// dello staff e debiti. Tutto calcolato dal server (club/accounting.py):
// qui si sceglie il periodo e si scrivono le spese.

const ACC = (path: string) => `/admin/accounting${path}`;

function useSummary(period: string) {
  return useQuery({
    queryKey: ["club", "accounting", "summary", period],
    queryFn: () => clubGet<ClubSummary>(ACC(`/summary?period=${period}`)),
    // Cambiando periodo i numeri vecchi restano (sbiaditi) finché arrivano i nuovi.
    placeholderData: (prev) => prev,
  });
}

function useAct() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { t } = useI18n();
  return async function act(fn: () => Promise<unknown>, ok: string) {
    try {
      await fn();
      await queryClient.invalidateQueries({ queryKey: ["club", "accounting"] });
      toast({ tone: "success", title: ok });
      return true;
    } catch (e) {
      toast({ tone: "error", title: t("acc.failed"), text: (e as Error).message });
      return false;
    }
  };
}

/** Il nome di un periodo per una frase: "ottobre 2026" o "2026". */
function usePeriodName() {
  const { fmt } = useI18n();
  return (period: string) => (period.length === 4 ? period : monthLong(period, fmt.tag));
}

// --- La home del club ----------------------------------------------------------------------------

/** La prima schermata della segreteria: quanto è entrato questo mese,
 *  quanto è uscito, cosa resta, chi deve ancora pagare. Ogni numero dice
 *  come è calcolato. */
export function ClubMoneyHome({ onGo, athletesActive }: { onGo: (section: "accounting" | "fees" | "proofs" | "absence" | "athletes") => void; athletesActive?: number }) {
  const { t, fmt } = useI18n();
  const month = currentMonth();
  const { data, isLoading, error } = useSummary(month);
  const periodName = usePeriodName();
  if (isLoading) return <Skeleton className="h-96" />;
  if (error || !data) return <EmptyState title={t("acc.unavailable")} text={(error as Error)?.message} />;
  const m = data.totals;
  const pct = Number(data.platform_fee_pct);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 xl:grid-cols-5 gap-4">
        <Kpi tone="income" label={t("acc.kpi.collected")} value={fmt.euro(m.income_cents)}
          explain={t("acc.kpi.collectedExplain", { month: periodName(month) })} onClick={() => onGo("accounting")} />
        <Kpi tone="costs" label={t("acc.kpi.costs")} value={fmt.euro(m.costs_cents)}
          explain={t("acc.kpi.costsExplain")} onClick={() => onGo("accounting")} />
        <Kpi tone="fee" label={t("acc.kpi.fee", { pct: pctLabel(pct, fmt.tag) })} value={fmt.euro(m.platform_fee_cents)}
          explain={t("acc.kpi.feeExplain", { pct: pctLabel(pct, fmt.tag) })} />
        <Kpi tone={m.result_cents >= 0 ? "good" : "bad"} label={t("acc.kpi.result")} value={fmt.euro(m.result_cents)}
          explain={t("acc.kpi.resultExplain")} />
        <Kpi tone="bad" label={t("acc.kpi.overdue")} value={fmt.euro(data.debts.overdue_cents)}
          explain={t("acc.kpi.overdueExplain", { n: data.debts.families })} onClick={() => onGo("fees")} />
      </div>

      <div className="grid lg:grid-cols-[1.6fr_1fr] gap-6">
        <section className="glass-card rounded-3xl p-5">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div>
              <h3 className="text-base text-ink-900">{t("acc.trendTitle")}</h3>
              <p className="text-xs text-ink-500">{t("acc.trendExplain")}</p>
            </div>
            <Button size="sm" variant="secondary" onClick={() => onGo("accounting")}>{t("acc.openAccounting")}</Button>
          </div>
          <IncomeCostChart series={data.series} />
          <SeriesTable series={data.series} />
        </section>
        <section className="glass-card rounded-3xl p-5 space-y-5">
          <div>
            <h3 className="text-base text-ink-900">{t("acc.collectionTitle")}</h3>
            <p className="text-xs text-ink-500 mb-3">{t("acc.collectionExplain")}</p>
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="font-display text-3xl text-ink-900">{m.collection_rate === null ? "—" : `${m.collection_rate}%`}</span>
              <span className="text-xs text-ink-500">{t("acc.collectionOf", { paid: fmt.euro(m.issued_paid_cents), issued: fmt.euro(m.issued_cents) })}</span>
            </div>
            <ProgressBar value={m.collection_rate ?? 0} tone="success" label={t("acc.collectionTitle")} />
          </div>
          {data.forecast && (
            <div className="rounded-2xl bg-ink-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">{t("acc.forecastTitle")}</p>
              <p className="font-display text-2xl text-ink-900 mt-1">{fmt.euro(data.forecast.income_cents)}</p>
              <p className="text-xs text-ink-500 mt-1">{t("acc.forecastExplain", { amount: fmt.euro(data.forecast.expected_cents) })}</p>
              <p className="text-xs text-ink-600 mt-2">{t("acc.forecastResult")} <strong className={cn(data.forecast.result_cents < 0 && "text-rose-700")}>{fmt.euro(data.forecast.result_cents)}</strong></p>
            </div>
          )}
          <div>
            <h4 className="text-sm font-semibold text-ink-900 mb-2">{t("acc.byKindTitle")}</h4>
            <KindBreakdown byKind={m.income_by_kind} />
          </div>
        </section>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("acc.agingTitle")}</h3>
          <p className="text-xs text-ink-500 mb-4">{t("acc.agingExplain")}</p>
          <AgingBars aging={data.debts.aging} />
        </section>
        <section className="glass-card rounded-3xl p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base text-ink-900">{t("acc.topDebtors")}</h3>
              <p className="text-xs text-ink-500 mb-3">{t("acc.topDebtorsExplain")}</p>
            </div>
            <Button size="sm" variant="ghost" onClick={() => onGo("fees")}>{t("acc.goFees")}</Button>
          </div>
          <DebtorList debts={data.debts} limit={6} />
        </section>
      </div>

      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {([
          ["accounting", "📒", t("acc.link.accounting")],
          ["proofs", "🧾", t("acc.link.proofs")],
          ["absence", "📉", t("acc.link.absence")],
          ["athletes", "🥋", athletesActive !== undefined ? t("acc.link.athletes", { n: athletesActive }) : t("acc.link.athletesPlain")],
        ] as const).map(([key, icon, label]) => (
          <button key={key} onClick={() => onGo(key)} className="glass-card rounded-2xl px-4 py-3 text-left text-sm font-semibold text-ink-800 hover:text-brand-700 cursor-pointer flex items-center gap-2">
            <span aria-hidden="true">{icon}</span>{label}
          </button>
        ))}
      </section>
    </div>
  );
}

function DebtorList({ debts, limit }: { debts: Debts; limit?: number }) {
  const { t, fmt } = useI18n();
  const rows = limit ? debts.top.slice(0, limit) : debts.top;
  if (!rows.length) return <p className="text-sm text-ink-500 py-6 text-center">{t("acc.noDebts")}</p>;
  return (
    <ul className="divide-y divide-ink-100">
      {rows.map((d) => (
        <li key={d.user_id} className="flex items-center justify-between gap-3 py-2.5">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink-900 truncate">{d.name || "—"}</p>
            <p className="text-xs text-ink-500">
              {t("acc.debtorLine", { n: d.fees, date: fmt.shortDate(d.oldest_due_date) })}
              {d.days_overdue > 0 && <> · <span className="text-rose-700">{t("acc.daysLate", { n: d.days_overdue })}</span></>}
            </p>
          </div>
          <div className="text-right shrink-0">
            <p className="font-semibold text-ink-900 tabular-nums">{fmt.euro(d.due_cents)}</p>
            {d.overdue_cents > 0 && <p className="text-xs text-rose-700 tabular-nums">{t("acc.ofWhichOverdue", { amount: fmt.euro(d.overdue_cents) })}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}

// --- La pagina Contabilità -----------------------------------------------------------------------

type AccTab = "statement" | "ledger" | "expenses" | "recurring" | "staff" | "debts";

export function ClubAccounting() {
  const { t } = useI18n();
  const [mode, setMode] = useState<"month" | "year">("month");
  const [month, setMonth] = useState(currentMonth);
  const [year, setYear] = useState(() => String(new Date().getFullYear()));
  const [tab, setTab] = useState<AccTab>("statement");
  const period = mode === "month" ? month : year;
  const thisYear = new Date().getFullYear();
  return (
    <div className="space-y-6">
      {/* Il periodo vale per tutto ciò che c'è sotto. */}
      <div className="flex flex-wrap items-end gap-3">
        <Tabs value={mode} onChange={(k) => setMode(k as "month" | "year")} items={[{ key: "month", label: t("acc.month") }, { key: "year", label: t("acc.year") }]} />
        {mode === "month" ? (
          <Input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} className="w-48" aria-label={t("acc.month")} />
        ) : (
          <Select value={year} onChange={(e) => setYear(e.target.value)} className="w-32" aria-label={t("acc.year")}>
            {Array.from({ length: 6 }, (_, i) => String(thisYear - i)).map((y) => <option key={y} value={y}>{y}</option>)}
          </Select>
        )}
      </div>
      <Tabs value={tab} onChange={(k) => setTab(k as AccTab)} items={(["statement", "ledger", "expenses", "recurring", "staff", "debts"] as const).map((k) => ({ key: k, label: t.dyn(`acc.tab.${k}`, k) }))} />
      {tab === "statement" && <Statement period={period} />}
      {tab === "ledger" && <LedgerPanel period={period} />}
      {tab === "expenses" && <ExpensesPanel period={period} />}
      {tab === "recurring" && <RecurringPanel />}
      {tab === "staff" && <StaffPanel period={period} />}
      {tab === "debts" && <DebtsPanel />}
    </div>
  );
}

function Statement({ period }: { period: string }) {
  const { t, fmt } = useI18n();
  const { data, isLoading, error, isFetching } = useSummary(period);
  const periodName = usePeriodName();
  if (isLoading) return <Skeleton className="h-96" />;
  if (error || !data) return <EmptyState title={t("acc.unavailable")} text={(error as Error)?.message} />;
  const f = data.totals;
  const pct = Number(data.platform_fee_pct);
  const categories = EXPENSE_CATEGORIES.filter((c) => f.expenses_by_category[c]);
  return (
    <div className={cn("space-y-6 transition-opacity", isFetching && "opacity-60")}>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi tone="income" label={t("acc.chart.income")} value={fmt.euro(f.income_cents)} explain={t("acc.incomeExplain")}
          extra={<DeltaBadge value={delta(data.current.income_cents, data.previous.income_cents)} label={t("acc.vsPrevious")} />} />
        <Kpi tone="costs" label={t("acc.chart.costs")} value={fmt.euro(f.costs_cents)} explain={t("acc.costsExplain")}
          extra={<DeltaBadge value={delta(data.current.costs_cents, data.previous.costs_cents)} goodWhenUp={false} label={t("acc.vsPrevious")} />} />
        <Kpi tone="fee" label={t("acc.kpi.fee", { pct: pctLabel(pct, fmt.tag) })} value={fmt.euro(f.platform_fee_cents)} explain={t("acc.kpi.feeExplain", { pct: pctLabel(pct, fmt.tag) })} />
        <Kpi tone={f.result_cents >= 0 ? "good" : "bad"} label={t("acc.kpi.result")} value={fmt.euro(f.result_cents)} explain={t("acc.kpi.resultExplain")}
          extra={<DeltaBadge value={delta(data.current.result_cents, data.previous.result_cents)} label={t("acc.vsPrevious")} />} />
      </div>

      <div className="grid xl:grid-cols-[1.25fr_1fr] gap-6">
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("acc.statementTitle", { period: periodName(period) })}</h3>
          <p className="text-xs text-ink-500 mb-3">{t("acc.statementExplain")}</p>
          <StatementLine label={t("acc.line.income")} explain={t("acc.incomeExplain")} cents={f.income_cents} />
          {FEE_KINDS.filter((k) => f.income_by_kind[k]).map((k) => (
            <StatementLine key={k} indent label={t.dyn(`acc.kind.${k}`, k)} cents={f.income_by_kind[k] ?? 0} />
          ))}
          {f.credit_cents > 0 && <StatementLine indent label={t("acc.line.credit")} explain={t("acc.line.creditExplain")} cents={f.credit_cents} />}
          <StatementLine label={t("acc.line.expenses")} explain={t("acc.line.expensesExplain")} cents={f.expenses_cents} sign={-1} />
          {categories.map((c) => (
            <StatementLine key={c} indent label={t.dyn(`acc.cat.${c}`, c)} cents={f.expenses_by_category[c] ?? 0} sign={-1} />
          ))}
          <StatementLine label={t("acc.line.staff")} explain={t("acc.line.staffExplain", { hours: hoursLabel(f.staff_minutes) })} cents={f.staff_cents} sign={-1} />
          {/* Corsi JAV: la parte dei treinador, calcolata quota per quota. */}
          {(f.coach_share_cents ?? 0) > 0 && (
            <StatementLine label={t("javCourses.coachShare")} explain={t("javCourses.coachShareExplain")} cents={f.coach_share_cents ?? 0} sign={-1} />
          )}
          <StatementLine label={t("acc.kpi.fee", { pct: pctLabel(pct, fmt.tag) })} explain={t("acc.kpi.feeExplain", { pct: pctLabel(pct, fmt.tag) })} cents={f.platform_fee_cents} sign={-1} />
          <StatementLine strong label={t("acc.kpi.result")} explain={t("acc.kpi.resultExplain")} cents={f.result_cents} />
        </section>

        <div className="space-y-6">
          <section className="glass-card rounded-3xl p-5">
            <h3 className="text-base text-ink-900">{t("acc.trendTitle")}</h3>
            <p className="text-xs text-ink-500 mb-2">{data.kind === "year" ? t("acc.trendYearExplain") : t("acc.trendExplain")}</p>
            <IncomeCostChart series={data.series} height={220} />
            <SeriesTable series={data.series} />
          </section>
          <section className="glass-card rounded-3xl p-5">
            <h3 className="text-base text-ink-900">{t("acc.costsByCategory")}</h3>
            <p className="text-xs text-ink-500 mb-3">{t("acc.costsByCategoryExplain")}</p>
            <RankBars empty={t("acc.noCosts")} rows={[
              ...EXPENSE_CATEGORIES.map((c) => ({ key: c, label: t.dyn(`acc.cat.${c}`, c), cents: f.expenses_by_category[c] ?? 0 })),
              { key: "clock", label: t("acc.line.staff"), cents: f.staff_cents, hint: hoursLabel(f.staff_minutes) },
              { key: "coach", label: t("javCourses.coachShare"), cents: f.coach_share_cents ?? 0 },
              { key: "fee", label: t("acc.chart.fee"), cents: f.platform_fee_cents },
            ]} />
          </section>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("acc.collectionTitle")}</h3>
          <p className="text-xs text-ink-500 mb-3">{t("acc.collectionExplain")}</p>
          <p className="font-display text-3xl text-ink-900">{f.collection_rate === null ? "—" : `${f.collection_rate}%`}</p>
          <ProgressBar value={f.collection_rate ?? 0} tone="success" className="my-2" label={t("acc.collectionTitle")} />
          <p className="text-xs text-ink-500">{t("acc.collectionOf", { paid: fmt.euro(f.issued_paid_cents), issued: fmt.euro(f.issued_cents) })}</p>
          <div className="mt-4"><KindBreakdown byKind={f.income_by_kind} /></div>
        </section>
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("acc.missedTitle")}</h3>
          <p className="text-xs text-ink-500 mb-2">{t("acc.missedExplain")}</p>
          <StatementLine label={t("acc.missed.discounts")} explain={t("acc.missed.discountsExplain")} cents={f.discounts_cents} />
          <StatementLine label={t("acc.missed.absence")} explain={t("acc.missed.absenceExplain")} cents={f.absence_cents} />
          <StatementLine label={t("acc.missed.waived")} explain={t("acc.missed.waivedExplain")} cents={f.waived_cents} />
          <StatementLine strong label={t("acc.missed.total")} cents={f.missed_cents} />
        </section>
        <Comparison data={data} />
      </div>
    </div>
  );
}

function Comparison({ data }: { data: ClubSummary }) {
  const { t, fmt } = useI18n();
  const rows: [string, keyof Figures, boolean][] = [
    [t("acc.chart.income"), "income_cents", true],
    [t("acc.chart.costs"), "costs_cents", false],
    [t("acc.chart.fee"), "platform_fee_cents", false],
    [t("acc.kpi.result"), "result_cents", true],
  ];
  const first = data.compared_months[0] ?? data.period;
  const last = data.compared_months[data.compared_months.length - 1] ?? data.period;
  const blocks: { title: string; now: Figures; before: Figures }[] = [
    { title: t("acc.compareTitle"), now: data.current, before: data.previous },
  ];
  if (data.ytd && data.ytd_previous) blocks.push({ title: t("acc.ytdTitle"), now: data.ytd, before: data.ytd_previous });
  return (
    <section className="glass-card rounded-3xl p-5">
      <h3 className="text-base text-ink-900">{t("acc.compareHeading")}</h3>
      <p className="text-xs text-ink-500 mb-3">{t("acc.compareExplain", { from: first, to: last })}</p>
      {blocks.map((b) => (
        <div key={b.title} className="mb-4 last:mb-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-500 mb-1">{b.title}</p>
          <table className="w-full text-sm tabular-nums">
            <thead><tr className="text-xs text-ink-400"><th className="text-left font-normal" /><th className="text-right font-normal">{t("acc.now")}</th><th className="text-right font-normal">{t("acc.before")}</th><th /></tr></thead>
            <tbody>
              {rows.map(([label, key, up]) => (
                <tr key={key} className="border-t border-ink-100">
                  <td className="py-1.5 text-ink-700">{label}</td>
                  <td className="py-1.5 text-right font-semibold text-ink-900">{fmt.euro(b.now[key] as number)}</td>
                  <td className="py-1.5 text-right text-ink-500">{fmt.euro(b.before[key] as number)}</td>
                  <td className="py-1.5 pl-2 text-right"><DeltaBadge value={delta(b.now[key] as number, b.before[key] as number)} goodWhenUp={up} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}

// --- Libro cassa ---------------------------------------------------------------------------------

function LedgerPanel({ period }: { period: string }) {
  const { t, fmt } = useI18n();
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const qs = new URLSearchParams({ period, ...(kind ? { kind } : {}), ...(q.trim() ? { q: q.trim() } : {}) }).toString();
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["club", "accounting", "ledger", qs],
    queryFn: () => clubGet<Ledger>(ACC(`/ledger?${qs}`)),
    placeholderData: (prev) => prev,
  });
  const openReceipt = useOpenReceipt();
  const typeLabel = (r: Ledger["rows"][number]) =>
    r.type === "INCOME" ? t.dyn(`acc.kind.${r.category}`, r.category)
      : r.type === "EXPENSE" ? t.dyn(`acc.cat.${r.category}`, r.category)
        : r.category === "COACH_SHARE" ? t("javCourses.coachShare")
          : r.type === "STAFF" ? t("acc.line.staff") : t("acc.chart.fee");
  const computedLabel = (r: Ledger["rows"][number]) =>
    r.category === "COACH_SHARE" ? t("javCourses.ledgerCoachRow") : r.type === "STAFF" ? t("acc.ledger.staffRow") : t("acc.ledger.feeRow");
  const description = (r: Ledger["rows"][number]) =>
    r.computed ? `${computedLabel(r)} ${monthLong(r.description, fmt.tag)}` : r.description;
  function exportCsv() {
    if (!data) return;
    downloadCsv(`contabilita-${period}`, [t("acc.col.date"), t("acc.col.type"), t("acc.col.category"), t("acc.col.description"), t("acc.col.who"), t("acc.col.method"), t("acc.col.amount")],
      data.rows.map((r) => [r.date, t.dyn(`acc.rowType.${r.type}`, r.type), typeLabel(r), description(r), r.counterparty || r.family, t.dyn(`acc.method.${r.method}`, r.method), (r.amount_cents / 100).toFixed(2)]));
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">{t("acc.ledgerIntro")}</p>
      <div className="flex flex-col sm:flex-row gap-3">
        <Select value={kind} onChange={(e) => setKind(e.target.value)} className="sm:w-56" aria-label={t("acc.col.type")}>
          <option value="">{t("acc.ledger.all")}</option>
          <option value="INCOME">{t("acc.ledger.income")}</option>
          <option value="EXPENSE">{t("acc.ledger.expense")}</option>
          <option value="COMPUTED">{t("acc.ledger.computed")}</option>
        </Select>
        <Input placeholder={t("acc.ledger.search")} value={q} onChange={(e) => setQ(e.target.value)} />
        <Button variant="secondary" onClick={exportCsv} disabled={!data?.rows.length}>{t("acc.exportCsv")}</Button>
      </div>
      {data && (
        <div className="flex flex-wrap gap-4 text-sm">
          <span>{t("acc.ledger.in")} <strong className="tabular-nums" style={{ color: CHART.income }}>{fmt.euro(data.in_cents)}</strong></span>
          <span>{t("acc.ledger.out")} <strong className="tabular-nums" style={{ color: CHART.costs }}>{fmt.euro(data.out_cents)}</strong></span>
          <span>{t("acc.ledger.balance")} <strong className={cn("tabular-nums", data.in_cents - data.out_cents < 0 && "text-rose-700")}>{fmt.euro(data.in_cents - data.out_cents)}</strong></span>
          {data.truncated && <Badge tone="warning">{t("acc.ledger.truncated")}</Badge>}
        </div>
      )}
      {isLoading ? <Skeleton className="h-64" /> : !data?.rows.length ? <EmptyState title={t("acc.ledger.empty")} text={t("acc.ledger.emptyText")} /> : (
        <div className={cn("transition-opacity", isFetching && "opacity-60")}>
          <Table>
            <THead><tr><TH>{t("acc.col.date")}</TH><TH>{t("acc.col.description")}</TH><TH>{t("acc.col.category")}</TH><TH>{t("acc.col.method")}</TH><TH className="text-right">{t("acc.col.amount")}</TH></tr></THead>
            <TBody>
              {data.rows.map((r) => (
                <TR key={`${r.type}-${r.id}`}>
                  <TD className="whitespace-nowrap">{fmt.shortDate(r.date)}</TD>
                  <TD>
                    <p className="font-semibold text-ink-900">{description(r)}</p>
                    {(r.counterparty || r.family) && <p className="text-xs text-ink-500">{r.counterparty}{r.family && r.family !== r.counterparty ? ` · ${r.family}` : ""}</p>}
                    {r.computed && <p className="text-[11px] text-ink-400">{t("acc.ledger.computedHint")}</p>}
                  </TD>
                  <TD>{typeLabel(r)}{r.recurring && <Badge tone="info" className="ml-1.5">{t("acc.recurringBadge")}</Badge>}</TD>
                  <TD className="text-xs">
                    {t.dyn(`acc.method.${r.method}`, r.method)}
                    {r.has_receipt && r.expense_id && <button className="block text-brand-700 hover:underline cursor-pointer" onClick={() => openReceipt(r.expense_id!)}>{t("acc.receipt")}</button>}
                  </TD>
                  <TD className={cn("text-right font-semibold tabular-nums whitespace-nowrap", r.amount_cents < 0 ? "text-rose-700" : "text-emerald-700")}>
                    {r.amount_cents < 0 ? "−" : "+"}{fmt.euro(Math.abs(r.amount_cents))}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </div>
      )}
    </div>
  );
}

function useOpenReceipt() {
  const toast = useToast();
  const { t } = useI18n();
  return async (expenseId: string) => {
    try {
      const { url } = await clubGet<{ url: string }>(ACC(`/expenses/${expenseId}/receipt-url`));
      window.open(url, "_blank", "noopener");
    } catch (e) {
      toast({ tone: "error", title: t("acc.failed"), text: (e as Error).message });
    }
  };
}

// --- Spese ---------------------------------------------------------------------------------------

function ExpensesPanel({ period }: { period: string }) {
  const { t, fmt } = useI18n();
  const [category, setCategory] = useState("");
  const qs = new URLSearchParams({ period, ...(category ? { category } : {}) }).toString();
  const { data, isLoading } = useQuery({ queryKey: ["club", "accounting", "expenses", qs], queryFn: () => clubGet<Expense[]>(ACC(`/expenses?${qs}`)) });
  const [editing, setEditing] = useState<Expense | "new" | null>(null);
  const act = useAct();
  const openReceipt = useOpenReceipt();
  const total = (data ?? []).reduce((s, e) => s + e.amount_cents, 0);
  return (
    <div className="space-y-4">
      <div className="rounded-2xl bg-sky-50 ring-1 ring-sky-200 p-4 text-sm text-sky-900">{t("acc.expensesIntro")}</div>
      <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
        <Select value={category} onChange={(e) => setCategory(e.target.value)} className="sm:w-56" aria-label={t("acc.col.category")}>
          <option value="">{t("acc.allCategories")}</option>
          {EXPENSE_CATEGORIES.map((c) => <option key={c} value={c}>{t.dyn(`acc.cat.${c}`, c)}</option>)}
        </Select>
        <span className="text-sm text-ink-500">{t("acc.expensesCount", { n: data?.length ?? 0 })} · <strong className="text-ink-900">{fmt.euro(total)}</strong></span>
        <Button className="sm:ml-auto" onClick={() => setEditing("new")} icon={<span>＋</span>}>{t("acc.newExpense")}</Button>
      </div>
      {isLoading ? <Skeleton className="h-64" /> : !(data ?? []).length ? (
        <EmptyState icon={<span className="text-3xl">🧾</span>} title={t("acc.noExpenses")} text={t("acc.noExpensesText")} action={<Button onClick={() => setEditing("new")}>{t("acc.newExpense")}</Button>} />
      ) : (
        <Table>
          <THead><tr><TH>{t("acc.col.date")}</TH><TH>{t("acc.col.description")}</TH><TH>{t("acc.col.category")}</TH><TH>{t("acc.col.method")}</TH><TH className="text-right">{t("acc.col.amount")}</TH><TH /></tr></THead>
          <TBody>
            {(data ?? []).map((e) => (
              <TR key={e.id}>
                <TD className="whitespace-nowrap">{fmt.shortDate(e.spent_on)}</TD>
                <TD><p className="font-semibold text-ink-900">{e.description}</p>{e.supplier && <p className="text-xs text-ink-500">{e.supplier}</p>}</TD>
                <TD>{t.dyn(`acc.cat.${e.category}`, e.category)}{e.recurring_id && <Badge tone="info" className="ml-1.5">{t("acc.recurringBadge")}</Badge>}</TD>
                <TD className="text-xs">{t.dyn(`acc.method.${e.payment_method}`, e.payment_method)}
                  {e.has_receipt && <button className="block text-brand-700 hover:underline cursor-pointer" onClick={() => openReceipt(e.id)}>{t("acc.receipt")}</button>}
                </TD>
                <TD className="text-right font-semibold tabular-nums">{fmt.euro(e.amount_cents)}</TD>
                <TD className="text-right whitespace-nowrap">
                  <Button size="sm" variant="secondary" onClick={() => setEditing(e)}>{t("acc.edit")}</Button>{" "}
                  {!e.recurring_id && (
                    <Button size="sm" variant="ghost" onClick={() => window.confirm(t("acc.deleteExpenseConfirm", { what: e.description })) && act(() => clubSend(ACC(`/expenses/${e.id}`), "DELETE"), t("acc.expenseDeleted"))}>{t("acc.delete")}</Button>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {editing && <ExpenseModal expense={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ExpenseModal({ expense, onClose }: { expense: Expense | null; onClose: () => void }) {
  const { t } = useI18n();
  const [spentOn, setSpentOn] = useState(expense?.spent_on ?? new Date().toISOString().slice(0, 10));
  const [category, setCategory] = useState(expense?.category ?? "RENT");
  const [amount, setAmount] = useState(expense ? String(expense.amount_cents / 100) : "");
  const [description, setDescription] = useState(expense?.description ?? "");
  const [supplier, setSupplier] = useState(expense?.supplier ?? "");
  const [method, setMethod] = useState(expense?.payment_method ?? "BANK_TRANSFER");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const act = useAct();
  const cents = toCents(amount);
  const valid = cents > 0 && description.trim().length >= 2;
  async function save() {
    setBusy(true);
    const body = { spent_on: spentOn, category, amount_cents: cents, description: description.trim(), supplier: supplier.trim() || null, payment_method: method };
    const ok = await act(async () => {
      const saved = expense
        ? await clubSend<Expense>(ACC(`/expenses/${expense.id}`), "PATCH", body)
        : await clubSend<Expense>(ACC("/expenses"), "POST", body);
      if (file) {
        const form = new FormData();
        form.append("file", file);
        await clubSend(ACC(`/expenses/${saved.id}/receipt`), "POST", form);
      }
    }, expense ? t("acc.expenseSaved") : t("acc.expenseCreated"));
    setBusy(false);
    if (ok) onClose();
  }
  return (
    <Modal open onClose={onClose} title={expense ? t("acc.editExpense") : t("acc.newExpense")} subtitle={expense?.recurring_id ? t("acc.fromRecurring") : undefined}
      footer={<><Button variant="ghost" onClick={onClose}>{t("acc.cancel")}</Button><Button loading={busy} disabled={!valid} onClick={save}>{t("acc.save")}</Button></>}>
      <div className="space-y-4">
        <Field label={t("acc.field.description")} hint={t("acc.field.descriptionHint")} htmlFor="ex-desc"><Input id="ex-desc" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("acc.field.amount")} htmlFor="ex-amount"><Input id="ex-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0,00" /></Field>
          <Field label={t("acc.field.date")} htmlFor="ex-date"><Input id="ex-date" type="date" value={spentOn} onChange={(e) => setSpentOn(e.target.value)} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("acc.col.category")} htmlFor="ex-cat">
            <Select id="ex-cat" value={category} onChange={(e) => setCategory(e.target.value)}>
              {EXPENSE_CATEGORIES.map((c) => <option key={c} value={c}>{t.dyn(`acc.cat.${c}`, c)}</option>)}
            </Select>
          </Field>
          <Field label={t("acc.col.method")} htmlFor="ex-method">
            <Select id="ex-method" value={method} onChange={(e) => setMethod(e.target.value)}>
              {PAYMENT_METHODS.map((m) => <option key={m} value={m}>{t.dyn(`acc.method.${m}`, m)}</option>)}
            </Select>
          </Field>
        </div>
        {category === "STAFF" && <p className="text-xs text-amber-800 bg-amber-50 rounded-xl p-3">{t("acc.staffDoubleCount")}</p>}
        <Field label={t("acc.field.supplier")} htmlFor="ex-sup"><Input id="ex-sup" value={supplier} onChange={(e) => setSupplier(e.target.value)} /></Field>
        <Field label={t("acc.field.receipt")} hint={expense?.has_receipt ? t("acc.field.receiptReplace") : t("acc.field.receiptHint")} htmlFor="ex-file">
          <Input id="ex-file" type="file" accept="image/jpeg,image/png,application/pdf" capture="environment" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="pt-2" />
        </Field>
      </div>
    </Modal>
  );
}

// --- Costi fissi ---------------------------------------------------------------------------------

function RecurringPanel() {
  const { t, fmt } = useI18n();
  const { data, isLoading } = useQuery({ queryKey: ["club", "accounting", "recurring"], queryFn: () => clubGet<RecurringExpense[]>(ACC("/recurring")) });
  const [editing, setEditing] = useState<RecurringExpense | "new" | null>(null);
  const act = useAct();
  const monthly = (data ?? []).filter((r) => r.active).reduce((s, r) => s + r.amount_cents, 0);
  return (
    <div className="space-y-4">
      <div className="rounded-2xl bg-sky-50 ring-1 ring-sky-200 p-4 text-sm text-sky-900">{t("acc.recurringIntro")}</div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-ink-500">{t("acc.recurringMonthly")} <strong className="text-ink-900">{fmt.euro(monthly)}</strong></span>
        <Button variant="ghost" size="sm" onClick={() => act(() => clubSend(ACC("/jobs/recurring"), "POST"), t("acc.recurringRun"))}>{t("acc.recurringRunNow")}</Button>
        <Button className="ml-auto" onClick={() => setEditing("new")} icon={<span>＋</span>}>{t("acc.newRecurring")}</Button>
      </div>
      {isLoading ? <Skeleton className="h-48" /> : !(data ?? []).length ? (
        <EmptyState icon={<span className="text-3xl">🔁</span>} title={t("acc.noRecurring")} text={t("acc.noRecurringText")} action={<Button onClick={() => setEditing("new")}>{t("acc.newRecurring")}</Button>} />
      ) : (
        <Table>
          <THead><tr><TH>{t("acc.col.description")}</TH><TH>{t("acc.col.category")}</TH><TH>{t("acc.col.when")}</TH><TH className="text-right">{t("acc.col.amount")}</TH><TH /></tr></THead>
          <TBody>
            {(data ?? []).map((r) => (
              <TR key={r.id} className={cn(!r.active && "opacity-60")}>
                <TD><p className="font-semibold text-ink-900">{r.description}</p>{r.supplier && <p className="text-xs text-ink-500">{r.supplier}</p>}</TD>
                <TD>{t.dyn(`acc.cat.${r.category}`, r.category)}</TD>
                <TD className="text-xs">
                  {t("acc.everyMonthOn", { day: r.day_of_month })}
                  <p className="text-ink-500">{t("acc.fromTo", { from: fmt.shortDate(r.starts_on), to: r.ends_on ? fmt.shortDate(r.ends_on) : t("acc.noEnd") })}</p>
                  {!r.active && <Badge tone="neutral">{t("acc.stopped")}</Badge>}
                </TD>
                <TD className="text-right font-semibold tabular-nums">{fmt.euro(r.amount_cents)}</TD>
                <TD className="text-right whitespace-nowrap">
                  <Button size="sm" variant="secondary" onClick={() => setEditing(r)}>{t("acc.edit")}</Button>{" "}
                  {r.active && (
                    <Button size="sm" variant="ghost" onClick={() => window.confirm(t("acc.stopRecurringConfirm", { what: r.description })) && act(() => clubSend(ACC(`/recurring/${r.id}`), "DELETE"), t("acc.recurringStopped"))}>{t("acc.stop")}</Button>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {editing && <RecurringModal recurring={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function RecurringModal({ recurring, onClose }: { recurring: RecurringExpense | null; onClose: () => void }) {
  const { t } = useI18n();
  const [description, setDescription] = useState(recurring?.description ?? "");
  const [category, setCategory] = useState(recurring?.category ?? "RENT");
  const [amount, setAmount] = useState(recurring ? String(recurring.amount_cents / 100) : "");
  const [supplier, setSupplier] = useState(recurring?.supplier ?? "");
  const [method, setMethod] = useState(recurring?.payment_method ?? "BANK_TRANSFER");
  const [day, setDay] = useState(String(recurring?.day_of_month ?? 1));
  const [startsOn, setStartsOn] = useState(recurring?.starts_on ?? `${currentMonth()}-01`);
  const [endsOn, setEndsOn] = useState(recurring?.ends_on ?? "");
  const [active, setActive] = useState(recurring?.active ?? true);
  const [busy, setBusy] = useState(false);
  const act = useAct();
  const cents = toCents(amount);
  const valid = cents > 0 && description.trim().length >= 2 && Number(day) >= 1 && Number(day) <= 28;
  async function save() {
    setBusy(true);
    const body = {
      description: description.trim(), category, amount_cents: cents, supplier: supplier.trim() || null, payment_method: method,
      day_of_month: Number(day), starts_on: startsOn, ends_on: endsOn || null, ...(recurring ? { active } : {}),
    };
    const ok = await act(
      () => (recurring ? clubSend(ACC(`/recurring/${recurring.id}`), "PATCH", body) : clubSend(ACC("/recurring"), "POST", body)),
      recurring ? t("acc.recurringSaved") : t("acc.recurringCreated"),
    );
    setBusy(false);
    if (ok) onClose();
  }
  return (
    <Modal open onClose={onClose} title={recurring ? t("acc.editRecurring") : t("acc.newRecurring")} subtitle={recurring ? t("acc.recurringEditHint") : t("acc.recurringNewHint")}
      footer={<><Button variant="ghost" onClick={onClose}>{t("acc.cancel")}</Button><Button loading={busy} disabled={!valid} onClick={save}>{t("acc.save")}</Button></>}>
      <div className="space-y-4">
        <Field label={t("acc.field.description")} hint={t("acc.field.recurringHint")} htmlFor="rc-desc"><Input id="rc-desc" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("acc.field.monthlyAmount")} htmlFor="rc-amount"><Input id="rc-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0,00" /></Field>
          <Field label={t("acc.field.day")} hint={t("acc.field.dayHint")} htmlFor="rc-day"><Input id="rc-day" type="number" min={1} max={28} value={day} onChange={(e) => setDay(e.target.value)} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("acc.col.category")} htmlFor="rc-cat">
            <Select id="rc-cat" value={category} onChange={(e) => setCategory(e.target.value)}>
              {EXPENSE_CATEGORIES.map((c) => <option key={c} value={c}>{t.dyn(`acc.cat.${c}`, c)}</option>)}
            </Select>
          </Field>
          <Field label={t("acc.col.method")} htmlFor="rc-method">
            <Select id="rc-method" value={method} onChange={(e) => setMethod(e.target.value)}>
              {PAYMENT_METHODS.map((m) => <option key={m} value={m}>{t.dyn(`acc.method.${m}`, m)}</option>)}
            </Select>
          </Field>
        </div>
        {category === "STAFF" && <p className="text-xs text-amber-800 bg-amber-50 rounded-xl p-3">{t("acc.staffDoubleCount")}</p>}
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("acc.field.startsOn")} hint={recurring ? undefined : t("acc.field.startsOnHint")} htmlFor="rc-start"><Input id="rc-start" type="date" value={startsOn} onChange={(e) => setStartsOn(e.target.value)} /></Field>
          <Field label={t("acc.field.endsOn")} hint={t("acc.field.endsOnHint")} htmlFor="rc-end"><Input id="rc-end" type="date" value={endsOn} onChange={(e) => setEndsOn(e.target.value)} /></Field>
        </div>
        <Field label={t("acc.field.supplier")} htmlFor="rc-sup"><Input id="rc-sup" value={supplier} onChange={(e) => setSupplier(e.target.value)} /></Field>
        {recurring && (
          <label className="flex items-center gap-2 text-sm text-ink-700"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="accent-brand-500 h-4 w-4" /> {t("acc.field.active")}</label>
        )}
      </div>
    </Modal>
  );
}

// --- Costo dello staff ---------------------------------------------------------------------------

function StaffPanel({ period }: { period: string }) {
  const { t, fmt } = useI18n();
  const { data, isLoading } = useQuery({ queryKey: ["club", "accounting", "staff", period], queryFn: () => clubGet<StaffCost[]>(ACC(`/staff-costs?period=${period}`)) });
  const [editing, setEditing] = useState<StaffCost | null>(null);
  const total = (data ?? []).reduce((s, r) => s + r.cost_cents, 0);
  const minutes = (data ?? []).reduce((s, r) => s + r.minutes, 0);
  return (
    <div className="space-y-4">
      <div className="rounded-2xl bg-sky-50 ring-1 ring-sky-200 p-4 text-sm text-sky-900 space-y-1.5">
        <p>{t("acc.staffIntro")}</p>
        <p className="font-semibold">{t("acc.staffDoubleCount")}</p>
      </div>
      <p className="text-sm text-ink-500">{t("acc.staffTotal", { hours: hoursLabel(minutes) })} <strong className="text-ink-900">{fmt.euro(total)}</strong></p>
      {isLoading ? <Skeleton className="h-48" /> : !(data ?? []).length ? <EmptyState title={t("acc.noStaff")} text={t("acc.noStaffText")} /> : (
        <Table>
          <THead><tr><TH>{t("acc.col.person")}</TH><TH>{t("acc.col.hours")}</TH><TH>{t("acc.col.rate")}</TH><TH className="text-right">{t("acc.col.cost")}</TH><TH /></tr></THead>
          <TBody>
            {(data ?? []).map((r) => (
              <TR key={r.user_id}>
                <TD className="font-semibold text-ink-900">{r.name}</TD>
                <TD className="tabular-nums">{hoursLabel(r.minutes)}</TD>
                <TD>
                  {r.hourly_rate_cents === null ? <Badge tone="warning">{t("acc.noRate")}</Badge> : <span className="tabular-nums">{t("acc.perHour", { amount: fmt.euro(r.hourly_rate_cents) })}</span>}
                  {r.rate_valid_from && <p className="text-[11px] text-ink-400">{t("acc.rateFrom", { date: fmt.shortDate(r.rate_valid_from) })}</p>}
                </TD>
                <TD className="text-right font-semibold tabular-nums">{fmt.euro(r.cost_cents)}</TD>
                <TD className="text-right"><Button size="sm" variant="secondary" onClick={() => setEditing(r)}>{t("acc.setRate")}</Button></TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {editing && <RateModal person={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function RateModal({ person, onClose }: { person: StaffCost; onClose: () => void }) {
  const { t } = useI18n();
  const [rate, setRate] = useState(person.hourly_rate_cents !== null ? String(person.hourly_rate_cents / 100) : "");
  const [from, setFrom] = useState(`${currentMonth()}-01`);
  const [busy, setBusy] = useState(false);
  const act = useAct();
  const cents = toCents(rate);
  async function save() {
    setBusy(true);
    const ok = await act(() => clubSend(ACC("/staff-rates"), "PUT", { user_id: person.user_id, hourly_rate_cents: cents, valid_from: from }), t("acc.rateSaved"));
    setBusy(false);
    if (ok) onClose();
  }
  return (
    <Modal open onClose={onClose} size="sm" title={t("acc.rateTitle", { name: person.name })} subtitle={t("acc.rateHint")}
      footer={<><Button variant="ghost" onClick={onClose}>{t("acc.cancel")}</Button><Button loading={busy} disabled={!(cents >= 0)} onClick={save}>{t("acc.save")}</Button></>}>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t("acc.field.rate")} htmlFor="rt-rate"><Input id="rt-rate" inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} placeholder="0,00" /></Field>
        <Field label={t("acc.field.validFrom")} htmlFor="rt-from"><Input id="rt-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

// --- Debiti --------------------------------------------------------------------------------------

function DebtsPanel() {
  const { t, fmt } = useI18n();
  const { data, isLoading } = useQuery({ queryKey: ["club", "accounting", "debts"], queryFn: () => clubGet<Debts>(ACC("/debts")) });
  if (isLoading || !data) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-6">
      <div className="grid sm:grid-cols-3 gap-4">
        <Kpi tone="bad" label={t("acc.debts.total")} value={fmt.euro(data.total_cents)} explain={t("acc.debts.totalExplain")} />
        <Kpi tone="bad" label={t("acc.kpi.overdue")} value={fmt.euro(data.overdue_cents)} explain={t("acc.debts.overdueExplain")} />
        <Kpi label={t("acc.debts.families")} value={String(data.families)} explain={t("acc.debts.familiesExplain")} />
      </div>
      <div className="grid lg:grid-cols-[1fr_1.4fr] gap-6">
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("acc.agingTitle")}</h3>
          <p className="text-xs text-ink-500 mb-4">{t("acc.agingExplain")}</p>
          <AgingBars aging={data.aging} />
        </section>
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("acc.debts.list")}</h3>
          <p className="text-xs text-ink-500 mb-3">{t("acc.topDebtorsExplain")}</p>
          <DebtorList debts={data} />
        </section>
      </div>
    </div>
  );
}
