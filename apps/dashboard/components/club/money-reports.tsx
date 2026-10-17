"use client";

import { motion } from "motion/react";
import { type ReactNode, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input, Select } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { friendlyApiError } from "@/lib/api-error";
import { cn } from "@/lib/cn";
import { clubGet } from "@/lib/club";
import { monthShort } from "@/lib/club-accounting";
import { feeLabel } from "@/lib/fee-label";
import { useI18n } from "@/lib/i18n/provider";
import {
  CELL_STYLE, REPORTS, REPORT_ICONS, currentSeason, reportUrl, stateLabel,
  type CellState, type MatrixCell, type MatrixReport, type MatrixRow, type ReportKey, type TableColumn,
  type TableReport, type TableValue,
} from "@/lib/money2";

// I relatórios della segreteria (apps/api/app/domains/club/money_reports.py):
// la matrice atleti × mesi e cinque tabelle (incassi per metodo, debiti per
// famiglia, esenzioni e condoni, contanti per persona, entrate e uscite).
// Tutto calcolato dal server, anche i file CSV e XLSX: qui si sceglie il
// relatório e il periodo, si guarda e si scarica.

type PeriodChoice = { mode: "season" | "year"; season: number; year: number };

function periodParams(p: PeriodChoice) {
  return p.mode === "season" ? { season: p.season } : { year: p.year };
}

export function MoneyReports() {
  const { t, fmt, locale } = useI18n();
  const toast = useToast();
  const [report, setReport] = useState<ReportKey>("matrix");
  const [period, setPeriod] = useState<PeriodChoice>(() => ({ mode: "season", season: currentSeason(), year: new Date().getFullYear() }));
  const [downloading, setDownloading] = useState<"csv" | "xlsx" | null>(null);
  const params = periodParams(period);
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["club", "accounting", "reports", report, params],
    queryFn: () => clubGet<MatrixReport | TableReport>(reportUrl(report, params)),
    placeholderData: (prev) => (prev && prev.report === report ? prev : undefined),
  });

  async function download(format: "csv" | "xlsx") {
    setDownloading(format);
    try {
      const res = await fetch(`/api/proxy/club${reportUrl(report, params, format, locale)}`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `relatorio-${report}-${data?.period.key ?? "periodo"}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast({ tone: "error", title: t("money2.reports.downloadFailed"), text: (e as Error).message });
    } finally {
      setDownloading(null);
    }
  }

  const thisSeason = currentSeason();
  const thisYear = new Date().getFullYear();
  return (
    <div className="space-y-5">
      <div className="glass-card space-y-4 rounded-3xl p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-base text-ink-900">📑 {t("money2.reports.title")}</h3>
            <p className="text-xs text-ink-500">{t("money2.reports.subtitle")}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Tabs value={period.mode} onChange={(k) => setPeriod((p) => ({ ...p, mode: k as "season" | "year" }))}
              items={[{ key: "season", label: t("money2.reports.season") }, { key: "year", label: t("money2.reports.year") }]} />
            {period.mode === "season" ? (
              <Select value={period.season} onChange={(e) => setPeriod((p) => ({ ...p, season: Number(e.target.value) }))}
                className="w-32" aria-label={t("money2.reports.season")}>
                {Array.from({ length: 5 }, (_, i) => thisSeason - i).map((s) => <option key={s} value={s}>{s}/{String(s + 1).slice(2)}</option>)}
              </Select>
            ) : (
              <Select value={period.year} onChange={(e) => setPeriod((p) => ({ ...p, year: Number(e.target.value) }))}
                className="w-28" aria-label={t("money2.reports.year")}>
                {Array.from({ length: 6 }, (_, i) => thisYear - i).map((y) => <option key={y} value={y}>{y}</option>)}
              </Select>
            )}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6" role="radiogroup" aria-label={t("money2.reports.title")}>
          {REPORTS.map((key) => (
            <button key={key} type="button" role="radio" aria-checked={report === key} onClick={() => setReport(key)}
              className={cn("relative cursor-pointer rounded-2xl p-3 text-left ring-1 transition",
                report === key ? "bg-ink-900 text-white ring-ink-900 shadow-lift" : "bg-white text-ink-800 ring-ink-200 hover:ring-ink-300")}>
              <span className="block text-xl" aria-hidden="true">{REPORT_ICONS[key]}</span>
              <span className="mt-1 block text-sm font-semibold leading-tight">{t.dyn(`money2.report.${key}.title`, key)}</span>
              <span className={cn("mt-0.5 block text-[11px] leading-snug", report === key ? "text-white/70" : "text-ink-500")}>
                {t.dyn(`money2.report.${key}.hint`, "")}
              </span>
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ink-100 pt-3">
          <p className="text-xs text-ink-500">
            {data ? (report === "debts" ? t("money2.reports.asOfToday") : t("money2.reports.periodLabel", { period: data.period.label })) : " "}
          </p>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" loading={downloading === "csv"} disabled={!data} onClick={() => download("csv")}>⬇ CSV</Button>
            <Button size="sm" loading={downloading === "xlsx"} disabled={!data} onClick={() => download("xlsx")}>⬇ Excel (XLSX)</Button>
          </div>
        </div>
      </div>

      {isLoading || !data ? (
        error ? <EmptyState title={t("money2.reports.loadFailed")} text={(error as Error).message} /> : <Skeleton className="h-96" />
      ) : (
        <motion.div key={report} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={cn("transition-opacity", isFetching && "opacity-60")}>
          {data.report === "matrix" ? <MatrixView data={data} /> : <TableView data={data} />}
        </motion.div>
      )}
      <p className="text-[11px] text-ink-400">{t("money2.reports.footnote", { today: fmt.shortDate(new Date().toISOString()) })}</p>
    </div>
  );
}

// --- La matrice -----------------------------------------------------------------------------------

const LEGEND: CellState[] = ["PAID", "PARTIAL", "DUE", "OVERDUE", "MONTH_EXEMPT", "WAIVED", "EXEMPT", "NONE"];

function MatrixView({ data }: { data: MatrixReport }) {
  const { t, fmt } = useI18n();
  const [q, setQ] = useState("");
  const [group, setGroup] = useState("");
  const [onlyDebt, setOnlyDebt] = useState(false);
  const [open, setOpen] = useState<{ row: MatrixRow; cell: MatrixCell } | null>(null);
  const groups = useMemo(() => [...new Set(data.rows.map((r) => r.group ?? ""))].sort(), [data]);
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return data.rows.filter((r) =>
      (!needle || `${r.name} ${r.member_number ?? ""}`.toLowerCase().includes(needle))
      && (!group || (r.group ?? "") === group)
      && (!onlyDebt || r.due_cents > 0));
  }, [data, q, group, onlyDebt]);
  const short = (c: number) => fmt.euro(c, { minimumFractionDigits: c % 100 ? 2 : 0, maximumFractionDigits: c % 100 ? 2 : 0 });
  const t0 = data.totals;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("money2.matrix.athletes")} value={String(t0.athletes)} />
        <Stat label={t("money2.matrix.paid")} value={fmt.euro(t0.paid_cents)} tone="good" />
        <Stat label={t("money2.matrix.due")} value={fmt.euro(t0.due_cents)} tone={t0.due_cents > 0 ? "warn" : undefined} />
        <Stat label={t("money2.matrix.overdue")} value={fmt.euro(t0.overdue_cents)} tone={t0.overdue_cents > 0 ? "bad" : undefined} />
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input placeholder={t("money2.matrix.search")} value={q} onChange={(e) => setQ(e.target.value)} className="sm:max-w-xs" />
        {groups.length > 1 && (
          <Select value={group} onChange={(e) => setGroup(e.target.value)} className="sm:w-56" aria-label={t("month.group")}>
            <option value="">{t("month.allGroups")}</option>
            {groups.map((g) => <option key={g || "none"} value={g}>{g || t("month.noGroup")}</option>)}
          </Select>
        )}
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-ink-700">
          <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={onlyDebt} onChange={(e) => setOnlyDebt(e.target.checked)} />
          {t("money2.matrix.onlyDebt")}
        </label>
      </div>
      <ul className="flex flex-wrap gap-x-3 gap-y-1.5" aria-label={t("money2.matrix.legend")}>
        {LEGEND.map((s) => (
          <li key={s} className="inline-flex items-center gap-1.5 text-[11px] text-ink-600">
            <span className={cn("h-3 w-3 rounded-sm", CELL_STYLE[s].dot)} aria-hidden="true" />{stateLabel(s, t, "months")}
          </li>
        ))}
      </ul>
      {rows.length === 0 ? <EmptyState title={t("money2.matrix.nobody")} /> : (
        <div className="glass-card overflow-hidden rounded-2xl">
          <div className="max-h-[70vh] overflow-auto">
            <table className="w-full border-separate border-spacing-0 text-xs">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider text-ink-500">
                  <th className="sticky left-0 top-0 z-20 min-w-[11rem] bg-ink-50 px-3 py-2 text-left font-semibold">{t("money2.matrix.athlete")}</th>
                  {data.months.map((m) => (
                    <th key={m} className="sticky top-0 z-10 min-w-[4.25rem] bg-ink-50 px-1 py-2 text-center font-semibold">{monthShort(m, fmt.tag)}</th>
                  ))}
                  <th className="sticky top-0 z-10 bg-ink-50 px-2 py-2 text-right font-semibold">{t("money2.matrix.paid")}</th>
                  <th className="sticky top-0 z-10 bg-ink-50 px-2 py-2 text-right font-semibold">{t("money2.matrix.due")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.athlete_id} className="group">
                    <th scope="row" className="sticky left-0 z-10 border-b border-ink-100 bg-white px-3 py-1.5 text-left font-normal group-hover:bg-brand-50">
                      <span className="block max-w-[13rem] truncate font-semibold text-ink-900">{r.name}</span>
                      <span className="block max-w-[13rem] truncate text-[10px] text-ink-500">
                        {[r.member_number ? `#${r.member_number}` : null, r.group].filter(Boolean).join(" · ") || "—"}
                      </span>
                    </th>
                    {r.cells.map((c) => {
                      const style = CELL_STYLE[c.state];
                      const amount = c.state === "PAID" ? c.paid_cents : c.state === "PARTIAL" || c.state === "DUE" || c.state === "OVERDUE" ? c.due_cents : null;
                      return (
                        <td key={c.period} className="border-b border-ink-100 p-0.5">
                          <button type="button" onClick={() => setOpen({ row: r, cell: c })}
                            title={`${monthShort(c.period, fmt.tag)} · ${stateLabel(c.state, t, "months")}${c.reason ? ` · ${c.reason}` : ""}`}
                            className={cn("flex h-10 w-full cursor-pointer flex-col items-center justify-center rounded-lg ring-1 transition hover:scale-[1.04]", style.box)}>
                            <span className="text-[11px] leading-none" aria-hidden="true">{style.icon}</span>
                            {amount !== null && <span className="mt-0.5 text-[10px] font-semibold leading-none tabular-nums">{short(amount)}</span>}
                          </button>
                        </td>
                      );
                    })}
                    <td className="border-b border-ink-100 px-2 text-right font-semibold tabular-nums text-emerald-700">{fmt.euro(r.paid_cents)}</td>
                    <td className={cn("border-b border-ink-100 px-2 text-right font-semibold tabular-nums", r.overdue_cents > 0 ? "text-rose-700" : r.due_cents > 0 ? "text-amber-700" : "text-ink-300")}>
                      {fmt.euro(r.due_cents)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="font-semibold text-ink-900">
                  <th scope="row" className="sticky bottom-0 left-0 z-20 bg-ink-50 px-3 py-2 text-left text-[11px] uppercase tracking-wider">{t("money2.matrix.total")}</th>
                  {data.columns.map((col) => (
                    <td key={col.period} className="sticky bottom-0 z-10 bg-ink-50 px-1 py-2 text-center tabular-nums">
                      <span className="block text-[10px] text-emerald-700">{short(col.paid_cents)}</span>
                      {col.due_cents > 0 && <span className="block text-[10px] text-rose-700">{short(col.due_cents)}</span>}
                    </td>
                  ))}
                  <td className="sticky bottom-0 bg-ink-50 px-2 py-2 text-right tabular-nums text-emerald-700">{fmt.euro(t0.paid_cents)}</td>
                  <td className="sticky bottom-0 bg-ink-50 px-2 py-2 text-right tabular-nums text-rose-700">{fmt.euro(t0.due_cents)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}
      {open && <CellDetail row={open.row} cell={open.cell} onClose={() => setOpen(null)} />}
    </div>
  );
}

function CellDetail({ row, cell, onClose }: { row: MatrixRow; cell: MatrixCell; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const style = CELL_STYLE[cell.state];
  const lines: [string, string][] = [];
  if (cell.paid_cents) lines.push([t("money2.matrix.paid"), fmt.euro(cell.paid_cents)]);
  if (cell.due_cents) lines.push([t("money2.matrix.due"), fmt.euro(cell.due_cents)]);
  if (cell.waived_cents) lines.push([t("money2.matrix.waived"), fmt.euro(cell.waived_cents)]);
  if (cell.paid_on) lines.push([t("months.paidOn"), fmt.shortDate(cell.paid_on)]);
  if (cell.method) lines.push([t("months.method"), t.dyn(`month.method.${cell.method}`, t.dyn(`money2.method.${cell.method}`, cell.method))]);
  if (cell.receiver) lines.push([t("months.cashTo"), cell.receiver]);
  return (
    <Modal open onClose={onClose} title={row.name} subtitle={monthShort(cell.period, fmt.tag)}
      footer={<Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>}>
      <div className="space-y-3">
        <p className={cn("rounded-2xl px-4 py-3 text-sm font-semibold ring-1", style.box)}>{style.icon} {stateLabel(cell.state, t, "months")}</p>
        {lines.length > 0 && (
          <dl className="divide-y divide-ink-100 rounded-2xl bg-white ring-1 ring-ink-100">
            {lines.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 px-4 py-2 text-sm"><dt className="text-ink-500">{k}</dt><dd className="font-medium text-ink-900">{v}</dd></div>
            ))}
          </dl>
        )}
        {cell.reason && <p className="text-sm italic text-ink-600">“{cell.reason}”</p>}
      </div>
    </Modal>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "good" | "warn" | "bad" }) {
  return (
    <div className="rounded-2xl bg-white p-3 ring-1 ring-ink-100">
      <p className="text-[10px] font-bold uppercase tracking-wider text-ink-500">{label}</p>
      <p className={cn("font-display text-xl tabular-nums", tone === "good" ? "text-emerald-700" : tone === "warn" ? "text-amber-700" : tone === "bad" ? "text-rose-700" : "text-ink-900")}>{value}</p>
    </div>
  );
}

// --- Le tabelle -----------------------------------------------------------------------------------

function TableView({ data }: { data: TableReport }) {
  const { t, fmt } = useI18n();
  const label = (c: TableColumn) => {
    if (c.month) return monthShort(c.month, fmt.tag);
    if (c.method) return t.dyn(`month.method.${c.method}`, t.dyn(`money2.method.${c.method}`, c.method));
    return t.dyn(`money2.col.${c.key}`, t.dyn(`acc.aging.${c.key}`, c.key));
  };
  const cell = (c: TableColumn, row: Record<string, TableValue>, total = false): ReactNode => {
    const v = row[c.key];
    if (v === null || v === undefined || v === "") return total ? "" : "—";
    switch (c.type) {
      case "money": return fmt.euro(Number(v));
      case "pct": return `${v}%`;
      case "date": return fmt.shortDate(String(v));
      case "month": return monthShort(String(v), fmt.tag);
      case "code": return t.dyn(`money2.adj.${v}`, stateLabel(String(v), t));
      case "fee": return feeLabel({ kind: String(row.kind ?? ""), period: String(row.period ?? ""), description: String(v) }, t, fmt);
      default: return String(v);
    }
  };
  const numeric = (c: TableColumn) => ["money", "int", "pct"].includes(c.type);
  return (
    <div className="space-y-4">
      {data.report === "adjustments" && data.by_type && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {Object.entries(data.by_type).map(([type, v]) => (
            <Stat key={type} label={`${t.dyn(`money2.adj.${type}`, type)} · ${v.count}`} value={fmt.euro(v.cents)} />
          ))}
        </div>
      )}
      {data.rows.length === 0 ? <EmptyState title={t("money2.reports.empty")} /> : (
        <Table>
          <THead>
            <TR>{data.columns.map((c) => <TH key={c.key} className={cn(numeric(c) && "text-right")}>{label(c)}</TH>)}</TR>
          </THead>
          <TBody>
            {data.rows.map((r, i) => (
              <TR key={i}>
                {data.columns.map((c, j) => (
                  <TD key={c.key} className={cn(numeric(c) && "text-right tabular-nums whitespace-nowrap", j === 0 && "font-semibold text-ink-900 whitespace-nowrap",
                    c.key === "reason" && "min-w-[12rem] text-ink-600 italic",
                    (c.key === "result" && Number(r[c.key]) < 0) && "text-rose-700",
                    (c.key === "overdue" && Number(r[c.key]) > 0) && "text-rose-700 font-semibold")}>
                    {cell(c, r)}
                  </TD>
                ))}
              </TR>
            ))}
            {data.totals && (
              <TR className="bg-ink-50/80 font-semibold">
                {data.columns.map((c, j) => (
                  <TD key={c.key} className={cn("text-ink-900", numeric(c) && "text-right tabular-nums whitespace-nowrap")}>
                    {j === 0 ? t("money2.matrix.total") : cell(c, data.totals!, true)}
                  </TD>
                ))}
              </TR>
            )}
          </TBody>
        </Table>
      )}
    </div>
  );
}
