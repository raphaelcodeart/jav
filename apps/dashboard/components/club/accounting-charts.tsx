"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { cn } from "@/lib/cn";
import { AGING_KEYS, CHART, FEE_KINDS, monthShort, type AgingBucket, type SeriesPoint } from "@/lib/club-accounting";
import { useI18n } from "@/lib/i18n/provider";
import { usePrefersReducedMotion } from "@/lib/motion";

// I pezzi dei cruscotti contabili: grafici e righe di conto che si
// spiegano da sé. Ogni numero porta una riga in parole che dice come è
// calcolato; i colori seguono la cosa (entrate, costi, commissione), mai la
// posizione; ogni grafico ha i valori anche in chiaro (etichette o tabella).

const TOOLTIP_STYLE = {
  background: "#ffffff", border: "1px solid #d9d8d8", borderRadius: 12, fontSize: 12, boxShadow: "0 8px 24px rgba(0,0,0,.08)",
};

/** Entrate contro uscite, mese per mese, con il risultato come linea: una
 *  sola scala (tutto in euro), le uscite impilate (costi + commissione). */
export function IncomeCostChart({ series, height = 260, showFee = true }: { series: SeriesPoint[]; height?: number; showFee?: boolean }) {
  const { t, fmt } = useI18n();
  const reduced = usePrefersReducedMotion();
  const data = series.map((p) => ({
    label: monthShort(p.month, fmt.tag),
    income: p.income_cents / 100,
    costs: p.costs_cents / 100,
    fee: p.platform_fee_cents / 100,
    result: p.result_cents / 100,
  }));
  const names: Record<string, string> = {
    income: t("acc.chart.income"), costs: t("acc.chart.costs"), fee: t("acc.chart.fee"), result: t("acc.chart.result"),
  };
  return (
    <div style={{ height }} role="img" aria-label={t("acc.chart.incomeCostAria")}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
          <CartesianGrid stroke={CHART.grid} vertical={false} />
          <XAxis dataKey="label" stroke={CHART.axis} fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke={CHART.axis} fontSize={11} tickLine={false} axisLine={false} width={56}
            tickFormatter={(v: number) => fmt.euroUnits(v, { maximumFractionDigits: 0, notation: "compact" })} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: "rgba(22,21,21,0.04)" }}
            formatter={(value, name) => [fmt.euroUnits(Number(value)), names[String(name)] ?? String(name)]}
          />
          <Legend formatter={(value: string) => <span className="text-xs text-ink-600">{names[value] ?? value}</span>} iconSize={10} />
          <Bar dataKey="income" fill={CHART.income} radius={[4, 4, 0, 0]} maxBarSize={22} isAnimationActive={!reduced} />
          <Bar dataKey="costs" stackId="out" fill={CHART.costs} maxBarSize={22} isAnimationActive={!reduced}
            radius={showFee ? [0, 0, 0, 0] : [4, 4, 0, 0]} stroke="#ffffff" strokeWidth={1} />
          {showFee && (
            <Bar dataKey="fee" stackId="out" fill={CHART.fee} radius={[4, 4, 0, 0]} maxBarSize={22} isAnimationActive={!reduced}
              stroke="#ffffff" strokeWidth={1} />
          )}
          <Line dataKey="result" type="monotone" stroke={CHART.result} strokeWidth={2} dot={{ r: 3, strokeWidth: 2, fill: "#ffffff" }}
            isAnimationActive={!reduced} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Una barra sola divisa per tipo (mensilità, iscrizioni, gare, quote
 *  socio), con la legenda che porta anche gli importi. */
export function KindBreakdown({ byKind }: { byKind: Record<string, number> }) {
  const { t, fmt } = useI18n();
  const total = FEE_KINDS.reduce((s, k) => s + (byKind[k] ?? 0), 0);
  if (!total) return <p className="text-sm text-ink-500 py-4">{t("acc.noIncome")}</p>;
  return (
    <div className="space-y-3">
      <div className="flex h-4 w-full overflow-hidden rounded-full bg-ink-100 gap-[2px]" role="img" aria-label={t("acc.byKindAria")}>
        {FEE_KINDS.filter((k) => byKind[k]).map((k) => (
          <motion.div key={k} initial={{ width: 0 }} animate={{ width: `${((byKind[k] ?? 0) / total) * 100}%` }}
            title={`${t.dyn(`acc.kind.${k}`, k)}: ${fmt.euro(byKind[k] ?? 0)}`}
            style={{ background: CHART.kinds[k] }} className="h-full first:rounded-l-full last:rounded-r-full" />
        ))}
      </div>
      <ul className="grid grid-cols-2 gap-x-4 gap-y-2">
        {FEE_KINDS.map((k) => (
          <li key={k} className="flex items-center gap-2 text-sm">
            <span className="h-2.5 w-2.5 rounded-sm shrink-0" style={{ background: CHART.kinds[k] }} aria-hidden="true" />
            <span className="text-ink-600 truncate">{t.dyn(`acc.kind.${k}`, k)}</span>
            <span className="ml-auto font-semibold text-ink-900 tabular-nums">{fmt.euro(byKind[k] ?? 0)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** I debiti per anzianità: una barra per fascia, lunga quanto l'importo. */
export function AgingBars({ aging }: { aging: Record<string, AgingBucket> }) {
  const { t, fmt } = useI18n();
  const max = Math.max(1, ...AGING_KEYS.map((k) => aging[k]?.cents ?? 0));
  return (
    <ul className="space-y-2.5" aria-label={t("acc.agingAria")}>
      {AGING_KEYS.map((k) => {
        const b = aging[k] ?? { cents: 0, count: 0 };
        return (
          <li key={k} className="grid grid-cols-[7.5rem_1fr_auto] items-center gap-3 text-sm">
            <span className="text-ink-600">{t.dyn(`acc.aging.${k}`, k)}</span>
            <span className="h-3 rounded-full bg-ink-100 overflow-hidden">
              <motion.span initial={{ width: 0 }} animate={{ width: `${(b.cents / max) * 100}%` }}
                className="block h-full rounded-full" style={{ background: CHART.aging[k] }} />
            </span>
            <span className="text-right tabular-nums">
              <span className="font-semibold text-ink-900">{fmt.euro(b.cents)}</span>
              <span className="text-xs text-ink-400 ml-1.5">{t("acc.feesCount", { n: b.count })}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** Barre orizzontali di una sola tinta, dalla voce più grande: per le
 *  categorie di spesa, dove conta quanto e non il colore. */
export function RankBars({ rows, color = CHART.costs, empty }: { rows: { key: string; label: string; cents: number; hint?: string }[]; color?: string; empty: string }) {
  const { fmt } = useI18n();
  const shown = rows.filter((r) => r.cents > 0).sort((a, b) => b.cents - a.cents);
  if (!shown.length) return <p className="text-sm text-ink-500 py-4">{empty}</p>;
  const max = shown[0]!.cents;
  return (
    <ul className="space-y-2.5">
      {shown.map((r) => (
        <li key={r.key} className="text-sm">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-ink-700 truncate">{r.label}{r.hint && <span className="text-xs text-ink-400 ml-1.5">{r.hint}</span>}</span>
            <span className="font-semibold text-ink-900 tabular-nums">{fmt.euro(r.cents)}</span>
          </div>
          <span className="mt-1 block h-2 rounded-full bg-ink-100 overflow-hidden">
            <motion.span initial={{ width: 0 }} animate={{ width: `${(r.cents / max) * 100}%` }} className="block h-full rounded-full" style={{ background: color }} />
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Più o meno rispetto a prima, in percentuale; verde se è un bene. */
export function DeltaBadge({ value, goodWhenUp = true, label }: { value: number | null; goodWhenUp?: boolean; label?: string }) {
  if (value === null) return null;
  const good = value === 0 ? null : (value > 0) === goodWhenUp;
  return (
    <span className={cn(
      "inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[11px] font-bold tabular-nums ring-1 ring-inset",
      good === null ? "bg-ink-50 text-ink-600 ring-ink-200" : good ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-rose-50 text-rose-700 ring-rose-200",
    )} title={label}>
      <span aria-hidden="true">{value > 0 ? "▲" : value < 0 ? "▼" : "="}</span>
      {value > 0 ? "+" : ""}{value}%
      {label && <span className="sr-only"> {label}</span>}
    </span>
  );
}

/** Una cifra grande con la sua spiegazione in una riga: il mattone delle
 *  testate dei cruscotti. */
export function Kpi({ label, value, explain, tone = "ink", extra, onClick }: {
  label: ReactNode; value: ReactNode; explain: ReactNode; tone?: "ink" | "income" | "costs" | "fee" | "good" | "bad"; extra?: ReactNode; onClick?: () => void;
}) {
  const bar = { ink: "bg-ink-300", income: "", costs: "", fee: "", good: "bg-emerald-500", bad: "bg-rose-500" }[tone];
  const color = tone === "income" ? CHART.income : tone === "costs" ? CHART.costs : tone === "fee" ? CHART.fee : undefined;
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick} className={cn("glass-card relative overflow-hidden rounded-2xl p-5 text-left w-full", onClick && "cursor-pointer hover:-translate-y-0.5 transition-transform")}>
      <span className={cn("absolute left-0 top-4 bottom-4 w-1 rounded-r-full", bar)} style={color ? { background: color } : undefined} aria-hidden="true" />
      <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">{label}</p>
      <div className="mt-2 flex items-baseline gap-2 flex-wrap">
        <p className="font-display text-2xl sm:text-3xl text-ink-900 tabular-nums">{value}</p>
        {extra}
      </div>
      <p className="text-xs text-ink-500 mt-1.5 leading-relaxed">{explain}</p>
    </Tag>
  );
}

/** Una riga del conto economico: voce, spiegazione, importo. */
export function StatementLine({ label, explain, cents, strong = false, sign = 1, indent = false }: {
  label: ReactNode; explain?: ReactNode; cents: number; strong?: boolean; sign?: 1 | -1; indent?: boolean;
}) {
  const { fmt } = useI18n();
  const shown = cents * sign;
  return (
    <div className={cn("flex items-start justify-between gap-4 py-2.5", strong && "border-t border-ink-200 pt-3 mt-1", indent && "pl-4")}>
      <div className="min-w-0">
        <p className={cn("text-sm", strong ? "font-bold text-ink-900" : indent ? "text-ink-600" : "font-semibold text-ink-800")}>{label}</p>
        {explain && <p className="text-xs text-ink-500 mt-0.5">{explain}</p>}
      </div>
      <p className={cn("tabular-nums shrink-0", strong ? "font-display text-lg" : "font-semibold text-sm", shown < 0 ? "text-rose-700" : "text-ink-900")}>
        {shown < 0 ? "−" : ""}{fmt.euro(Math.abs(shown))}
      </p>
    </div>
  );
}

/** Una tabella dei dati dei grafici: chi non vede i colori (o il grafico)
 *  ha gli stessi numeri in chiaro. */
export function SeriesTable({ series }: { series: SeriesPoint[] }) {
  const { t, fmt } = useI18n();
  return (
    <details className="mt-3 group">
      <summary className="text-xs font-semibold text-ink-500 cursor-pointer hover:text-ink-800">{t("acc.showTable")}</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-xs tabular-nums">
          <thead><tr className="text-ink-500 text-left"><th className="py-1 pr-3">{t("acc.colMonth")}</th><th className="py-1 pr-3 text-right">{t("acc.chart.income")}</th><th className="py-1 pr-3 text-right">{t("acc.chart.costs")}</th><th className="py-1 pr-3 text-right">{t("acc.chart.fee")}</th><th className="py-1 text-right">{t("acc.chart.result")}</th></tr></thead>
          <tbody>
            {series.map((p) => (
              <tr key={p.month} className="border-t border-ink-100">
                <td className="py-1 pr-3 text-ink-700">{monthShort(p.month, fmt.tag)}</td>
                <td className="py-1 pr-3 text-right">{fmt.euro(p.income_cents)}</td>
                <td className="py-1 pr-3 text-right">{fmt.euro(p.costs_cents)}</td>
                <td className="py-1 pr-3 text-right">{fmt.euro(p.platform_fee_cents)}</td>
                <td className={cn("py-1 text-right font-semibold", p.result_cents < 0 && "text-rose-700")}>{fmt.euro(p.result_cents)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
