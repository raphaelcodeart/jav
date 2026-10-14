"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { IncomeCostChart, Kpi, RankBars, SeriesTable } from "@/components/club/accounting-charts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CountUp } from "@/components/ui/count-up";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { CHART, monthShort, pctLabel, platformGet, platformSend, type PlatformClub, type PlatformSummary } from "@/lib/club-accounting";
import { useI18n } from "@/lib/i18n/provider";
import { usePrefersReducedMotion } from "@/lib/motion";

// I conti della piattaforma JudoArteVida: quanto spetta alla piattaforma
// (la percentuale degli incassi di ogni club), i numeri di tutti i club
// insieme e uno per uno, la crescita della rete, le vendite dello Shop.
// Tutto calcolato da /clubs/accounting (club/accounting.py).

const TOOLTIP_STYLE = { background: "#ffffff", border: "1px solid #d9d8d8", borderRadius: 12, fontSize: 12 };

export function PlatformMoney({ canEdit, onEnter }: { canEdit: boolean; onEnter: (clubId: string) => void }) {
  const { t, fmt } = useI18n();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["clubs", "accounting", year],
    queryFn: () => platformGet<PlatformSummary>(`/accounting?year=${year}`),
    placeholderData: (prev) => prev,
  });
  const [editing, setEditing] = useState<PlatformClub | null>(null);
  if (isLoading) return <Skeleton className="h-96" />;
  if (error || !data) return <EmptyState title={t("hq.unavailable")} text={(error as Error)?.message} />;
  const e = data.earnings;
  const m = data.totals.month;
  const y = data.totals.year;
  const euroUnits = (n: number) => fmt.euroUnits(n, { maximumFractionDigits: 2 });
  return (
    <div className={cn("space-y-6 transition-opacity", isFetching && "opacity-70")}>
      {/* Il contatore: quanto spetta alla piattaforma. */}
      <motion.section
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-[32px] bg-gradient-to-br from-ink-900 via-ink-800 to-emerald-900 text-white p-6 sm:p-8"
      >
        <div className="absolute inset-0 opacity-25 bg-[radial-gradient(circle_at_85%_10%,#1baf7a,transparent_40%),radial-gradient(circle_at_0%_100%,#f9e40f,transparent_40%)]" aria-hidden="true" />
        <div className="relative grid lg:grid-cols-[1.3fr_1fr] gap-6 items-end">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-300">{t("hq.counterEyebrow")}</p>
            <p className="font-display text-5xl sm:text-6xl mt-3 tabular-nums" aria-live="polite">
              <CountUp value={e.all_time_cents / 100} format={euroUnits} duration={2.2} />
            </p>
            <p className="text-white/70 text-sm mt-2 max-w-xl">{t("hq.counterExplain")}</p>
          </div>
          <dl className="grid grid-cols-3 gap-3">
            {([
              [t("hq.counterMonth"), e.month_cents, t("hq.counterMonthHint", { amount: fmt.euro(e.month_forecast_cents) })],
              [t("hq.counterYear", { year: data.year }), e.year_cents, t("hq.counterYearHint")],
              [t("hq.shopYear", { year: data.year }), data.shop.year_cents, t("hq.shopYearHint", { n: data.shop.orders_year })],
            ] as const).map(([label, cents, hint]) => (
              <div key={label} className="rounded-2xl bg-white/10 ring-1 ring-white/15 p-3">
                <dt className="text-[11px] uppercase tracking-wider text-white/60">{label}</dt>
                <dd className="font-display text-xl mt-1 tabular-nums"><CountUp value={cents / 100} format={euroUnits} /></dd>
                <dd className="text-[11px] text-white/55 mt-1">{hint}</dd>
              </div>
            ))}
          </dl>
        </div>
      </motion.section>

      {data.courses_unit && <CoursesUnitLine unit={data.courses_unit} year={data.year} onEnter={onEnter} />}

      <div className="flex flex-wrap items-center gap-3">
        <Select value={String(year)} onChange={(ev) => setYear(Number(ev.target.value))} className="w-32" aria-label={t("hq.year")}>
          {Array.from({ length: 5 }, (_, i) => thisYear - i).map((yy) => <option key={yy} value={yy}>{yy}</option>)}
        </Select>
        <p className="text-xs text-ink-500">{t("hq.yearHint")}</p>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-5 gap-4">
        <Kpi tone="income" label={t("hq.kpi.collectedMonth")} value={fmt.euro(m.income_cents)} explain={t("hq.kpi.collectedMonthExplain")} />
        <Kpi tone="income" label={t("hq.kpi.collectedYear", { year: data.year })} value={fmt.euro(y.income_cents)} explain={t("hq.kpi.collectedYearExplain")} />
        <Kpi tone="costs" label={t("hq.kpi.costsYear", { year: data.year })} value={fmt.euro(y.costs_cents)} explain={t("hq.kpi.costsYearExplain")} />
        <Kpi tone={y.result_cents >= 0 ? "good" : "bad"} label={t("hq.kpi.resultYear", { year: data.year })} value={fmt.euro(y.result_cents)} explain={t("hq.kpi.resultYearExplain")} />
        <Kpi tone="bad" label={t("hq.kpi.overdue")} value={fmt.euro(data.totals.overdue_cents)} explain={t("hq.kpi.overdueExplain", { amount: fmt.euro(data.totals.debt_cents) })} />
      </div>
      <div className="grid grid-cols-3 gap-4">
        <Kpi label={t("hq.kpi.clubs")} value={String(data.totals.clubs_active)} explain={t("hq.kpi.clubsExplain")} />
        <Kpi label={t("hq.kpi.athletes")} value={String(data.totals.athletes_active)} explain={t("hq.kpi.athletesExplain")} />
        <Kpi label={t("hq.kpi.families")} value={String(data.totals.families)} explain={t("hq.kpi.familiesExplain")} />
      </div>

      <div className="grid xl:grid-cols-2 gap-6">
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("hq.earningsTrend")}</h3>
          <p className="text-xs text-ink-500 mb-2">{t("hq.earningsTrendExplain")}</p>
          <EarningsChart data={data} />
        </section>
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("hq.networkTrend")}</h3>
          <p className="text-xs text-ink-500 mb-2">{t("hq.networkTrendExplain")}</p>
          <IncomeCostChart series={e.series} height={240} />
          <SeriesTable series={e.series} />
        </section>
      </div>

      <div className="grid xl:grid-cols-3 gap-6">
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("hq.byClubIncome", { year: data.year })}</h3>
          <p className="text-xs text-ink-500 mb-3">{t("hq.byClubIncomeExplain")}</p>
          <RankBars color={CHART.income} empty={t("hq.nothingYet")} rows={data.clubs.map((c) => ({ key: c.id, label: c.name, cents: c.year.income_cents }))} />
        </section>
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("hq.byClubFee", { year: data.year })}</h3>
          <p className="text-xs text-ink-500 mb-3">{t("hq.byClubFeeExplain")}</p>
          <RankBars color={CHART.fee} empty={t("hq.nothingYet")} rows={data.clubs.map((c) => ({ key: c.id, label: c.name, cents: c.year.platform_fee_cents, hint: pctLabel(Number(c.platform_fee_pct), fmt.tag) }))} />
        </section>
        <section className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900">{t("hq.growth")}</h3>
          <p className="text-xs text-ink-500 mb-2">{t("hq.growthExplain")}</p>
          <GrowthChart data={data} />
        </section>
      </div>

      <section className="glass-card rounded-3xl p-5">
        <h3 className="text-base text-ink-900">{t("hq.clubsTable")}</h3>
        <p className="text-xs text-ink-500 mb-3">{canEdit ? t("hq.clubsTableExplainEdit") : t("hq.clubsTableExplain")}</p>
        {data.clubs.length === 0 ? <p className="text-sm text-ink-500">{t("hq.nothingYet")}</p> : (
          <Table>
            <THead>
              <tr>
                <TH>{t("hq.col.club")}</TH><TH>{t("hq.col.pct")}</TH><TH>{t("hq.col.people")}</TH>
                <TH className="text-right">{t("hq.col.month")}</TH><TH className="text-right">{t("hq.col.year", { year: data.year })}</TH>
                <TH className="text-right">{t("hq.col.result")}</TH><TH className="text-right">{t("hq.col.fee")}</TH>
                <TH className="text-right">{t("hq.col.overdue")}</TH><TH />
              </tr>
            </THead>
            <TBody>
              {data.clubs.map((c) => (
                <TR key={c.id}>
                  <TD><p className="font-semibold text-ink-900">{c.name}</p>{c.status !== "ACTIVE" && <Badge tone="danger">{t("clubs.statusSuspended")}</Badge>}</TD>
                  <TD>
                    {canEdit ? (
                      <button onClick={() => setEditing(c)} className="font-semibold text-brand-700 hover:underline cursor-pointer tabular-nums" title={t("hq.editPct")}>
                        {pctLabel(Number(c.platform_fee_pct), fmt.tag)} ✎
                      </button>
                    ) : <span className="tabular-nums">{pctLabel(Number(c.platform_fee_pct), fmt.tag)}</span>}
                  </TD>
                  <TD className="text-xs">{t("hq.peopleLine", { a: c.athletes_active, f: c.families })}</TD>
                  <TD className="text-right tabular-nums">{fmt.euro(c.month.income_cents)}</TD>
                  <TD className="text-right tabular-nums">{fmt.euro(c.year.income_cents)}<p className="text-[11px] text-ink-400">{t("hq.costsLine", { amount: fmt.euro(c.year.costs_cents) })}</p></TD>
                  <TD className={cn("text-right font-semibold tabular-nums", c.year.result_cents < 0 && "text-rose-700")}>{fmt.euro(c.year.result_cents)}</TD>
                  <TD className="text-right tabular-nums">{fmt.euro(c.year.platform_fee_cents)}<p className="text-[11px] text-ink-400">{t("hq.allTimeLine", { amount: fmt.euro(c.platform_fee_all_time_cents) })}</p></TD>
                  <TD className={cn("text-right tabular-nums", c.overdue_cents > 0 && "text-rose-700 font-semibold")}>{c.overdue_cents ? fmt.euro(c.overdue_cents) : "—"}</TD>
                  <TD className="text-right"><Button size="sm" onClick={() => onEnter(c.id)}>{t("clubs.enter")}</Button></TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </section>
      {editing && <PctModal club={editing} defaultPct={data.default_platform_fee_pct} onClose={() => setEditing(null)} />}
    </div>
  );
}

function EarningsChart({ data }: { data: PlatformSummary }) {
  const { t, fmt } = useI18n();
  const reduced = usePrefersReducedMotion();
  const points = data.earnings.series.map((p) => ({ label: monthShort(p.month, fmt.tag), fee: p.platform_fee_cents / 100, shop: (data.shop.series.find((s) => s.month === p.month)?.cents ?? 0) / 100 }));
  const names: Record<string, string> = { fee: t("hq.series.fee"), shop: t("hq.series.shop") };
  return (
    <div className="h-64" role="img" aria-label={t("hq.earningsTrend")}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
          <CartesianGrid stroke={CHART.grid} vertical={false} />
          <XAxis dataKey="label" stroke={CHART.axis} fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke={CHART.axis} fontSize={11} tickLine={false} axisLine={false} width={56}
            tickFormatter={(v: number) => fmt.euroUnits(v, { maximumFractionDigits: 0, notation: "compact" })} />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(22,21,21,0.04)" }}
            formatter={(value, name) => [fmt.euroUnits(Number(value)), names[String(name)] ?? String(name)]} />
          <Legend formatter={(value: string) => <span className="text-xs text-ink-600">{names[value] ?? value}</span>} iconSize={10} />
          <Bar dataKey="fee" fill={CHART.fee} radius={[4, 4, 0, 0]} maxBarSize={20} isAnimationActive={!reduced} />
          <Bar dataKey="shop" fill={CHART.income} radius={[4, 4, 0, 0]} maxBarSize={20} isAnimationActive={!reduced} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function GrowthChart({ data }: { data: PlatformSummary }) {
  const { t, fmt } = useI18n();
  const reduced = usePrefersReducedMotion();
  const points = data.growth.map((g) => ({ label: monthShort(g.month, fmt.tag), athletes: g.athletes, families: g.families }));
  const names: Record<string, string> = { athletes: t("hq.series.athletes"), families: t("hq.series.families") };
  return (
    <div className="h-56" role="img" aria-label={t("hq.growth")}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={CHART.grid} vertical={false} />
          <XAxis dataKey="label" stroke={CHART.axis} fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke={CHART.axis} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} width={36} />
          <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(value, name) => [String(value), names[String(name)] ?? String(name)]} />
          <Legend formatter={(value: string) => <span className="text-xs text-ink-600">{names[value] ?? value}</span>} iconSize={10} />
          <Line dataKey="athletes" stroke={CHART.income} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={!reduced} />
          <Line dataKey="families" stroke={CHART.costs} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={!reduced} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** La percentuale di un club: solo il superadmin, vale dal mese in corso. */
function PctModal({ club, defaultPct, onClose }: { club: PlatformClub; defaultPct: string; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const [pct, setPct] = useState(String(Number(club.platform_fee_pct)));
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const queryClient = useQueryClient();
  const value = Number(pct.replace(",", "."));
  const valid = Number.isFinite(value) && value >= 0 && value <= 100;
  async function save() {
    setBusy(true);
    try {
      await platformSend(`/${club.id}/platform-fee`, "PUT", { pct: value.toFixed(2) });
      await queryClient.invalidateQueries({ queryKey: ["clubs"] });
      toast({ tone: "success", title: t("hq.pctSaved") });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: t("acc.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open onClose={onClose} size="sm" title={t("hq.pctTitle", { club: club.name })} subtitle={t("hq.pctHint", { pct: pctLabel(Number(defaultPct), fmt.tag) })}
      footer={<><Button variant="ghost" onClick={onClose}>{t("acc.cancel")}</Button><Button loading={busy} disabled={!valid} onClick={save}>{t("acc.save")}</Button></>}>
      <Field label={t("hq.pctLabel")} htmlFor="pct-input" hint={valid ? t("hq.pctExample", { amount: fmt.euro(Math.round(100000 * value / 100)) }) : undefined}>
        <Input id="pct-input" inputMode="decimal" value={pct} onChange={(ev) => setPct(ev.target.value)} />
      </Field>
    </Modal>
  );
}

/** La riga a parte dei corsi JAV nelle scuole: non è una commissione ma ciò
 *  che JAV tiene dei suoi corsi (incassi meno la parte dei treinador). */
function CoursesUnitLine({ unit, year, onEnter }: {
  unit: NonNullable<PlatformSummary["courses_unit"]>; year: number; onEnter: (clubId: string) => void;
}) {
  const { t, fmt } = useI18n();
  const cells: [string, number, string][] = [
    [t("javCourses.hqMonth"), unit.kept_month_cents, t("javCourses.hqMonthHint", { amount: fmt.euro(unit.kept_month_forecast_cents) })],
    [t("javCourses.hqYear", { year }), unit.kept_year_cents, t("javCourses.hqYearHint", { income: fmt.euro(unit.year.income_cents), coach: fmt.euro(unit.year.coach_share_cents ?? 0) })],
    [t("javCourses.hqAllTime"), unit.kept_all_time_cents, t("javCourses.hqPeople", { athletes: unit.athletes_active, families: unit.families })],
  ];
  return (
    <section className="glass-card rounded-3xl p-5">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div>
          <h3 className="text-base text-ink-900">🏫 {t("javCourses.hqTitle")}</h3>
          <p className="text-xs text-ink-500 max-w-2xl">{t("javCourses.hqExplain")}</p>
        </div>
        <Button size="sm" variant="secondary" onClick={() => onEnter(unit.id)}>{t("javCourses.enter")}</Button>
      </div>
      <dl className="grid sm:grid-cols-3 gap-3">
        {cells.map(([label, cents, hint]) => (
          <div key={label} className="rounded-2xl bg-ink-50 p-3">
            <dt className="text-[11px] uppercase tracking-wider text-ink-500">{label}</dt>
            <dd className="font-display text-xl text-ink-900 mt-1 tabular-nums">{fmt.euro(cents)}</dd>
            <dd className="text-[11px] text-ink-500 mt-1">{hint}</dd>
          </div>
        ))}
      </dl>
      {unit.overdue_cents > 0 && <p className="text-xs text-red-700 mt-3">{t("javCourses.hqOverdue", { amount: fmt.euro(unit.overdue_cents) })}</p>}
    </section>
  );
}
