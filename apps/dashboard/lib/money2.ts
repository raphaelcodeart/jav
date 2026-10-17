// Pagamento parziale, mese esente e relatórios della segreteria. I tipi
// rispecchiano apps/api/app/domains/club/money_reports.py e money_router.py:
// ogni importo arriva calcolato dal server; il browser sceglie solo il
// relatório, il periodo e il formato.

import type { useI18n } from "@/lib/i18n/provider";

type T = ReturnType<typeof useI18n>["t"];

export const REPORTS = ["matrix", "collections", "debts", "adjustments", "cash", "pnl"] as const;
export type ReportKey = (typeof REPORTS)[number];

export const REPORT_ICONS: Record<ReportKey, string> = {
  matrix: "🗓️", collections: "💶", debts: "⏳", adjustments: "🎗️", cash: "👛", pnl: "📊",
};

/** Lo stato di una casella della matrice (e del quadro del mese). */
export type CellState =
  | "PAID" | "PARTIAL" | "DUE" | "OVERDUE" | "WAIVED" | "MONTH_EXEMPT" | "EXEMPT" | "NOT_ENROLLED" | "UPCOMING" | "NONE";

export interface MatrixCell {
  period: string;
  state: CellState;
  paid_cents: number;
  due_cents: number;
  waived_cents: number;
  paid_on: string | null;
  method: string | null;
  receiver: string | null;
  reason: string | null;
  overdue: boolean;
  fee_id: string | null;
}

export interface MatrixRow {
  athlete_id: string;
  name: string;
  first_name: string;
  last_name: string;
  member_number: string | null;
  group: string | null;
  status: string;
  cells: MatrixCell[];
  paid_cents: number;
  due_cents: number;
  overdue_cents: number;
  waived_cents: number;
  months_paid: number;
}

export interface MatrixColumn {
  period: string;
  paid_cents: number;
  due_cents: number;
  overdue_cents: number;
  waived_cents: number;
  paid: number;
  partial: number;
  due: number;
  exempt: number;
}

export interface ReportPeriod {
  kind: "season" | "year";
  key: string;
  label: string;
  start: string;
  end: string;
  as_of?: string;
}

export interface MatrixReport {
  report: "matrix";
  period: ReportPeriod;
  months: string[];
  rows: MatrixRow[];
  columns: MatrixColumn[];
  totals: { athletes: number; paid_cents: number; due_cents: number; overdue_cents: number; waived_cents: number };
}

export type ColumnType = "text" | "money" | "date" | "int" | "pct" | "code" | "month" | "fee";

export interface TableColumn {
  key: string;
  type: ColumnType;
  /** Una colonna per mese ("2026-10") o per metodo di pagamento. */
  month?: string;
  method?: string;
}

export type TableValue = string | number | null;

export interface TableReport {
  report: Exclude<ReportKey, "matrix">;
  period: ReportPeriod;
  columns: TableColumn[];
  rows: Record<string, TableValue>[];
  totals: Record<string, TableValue> | null;
  by_type?: Record<string, { count: number; cents: number }>;
}

/** I colori delle caselle, gli stessi del quadro del mese (month-board.tsx). */
export const CELL_STYLE: Record<CellState, { box: string; dot: string; icon: string }> = {
  PAID: { box: "bg-emerald-50 text-emerald-900 ring-emerald-200", dot: "bg-emerald-500", icon: "✓" },
  PARTIAL: { box: "bg-amber-50 text-amber-900 ring-amber-300", dot: "bg-amber-400", icon: "½" },
  DUE: { box: "bg-orange-50 text-orange-900 ring-orange-200", dot: "bg-orange-300", icon: "⏳" },
  OVERDUE: { box: "bg-rose-50 text-rose-800 ring-rose-300", dot: "bg-rose-500", icon: "!" },
  WAIVED: { box: "bg-ink-100 text-ink-600 ring-ink-200", dot: "bg-ink-400", icon: "🤝" },
  MONTH_EXEMPT: { box: "bg-sky-50 text-sky-800 ring-sky-200", dot: "bg-sky-400", icon: "🎗️" },
  EXEMPT: { box: "bg-sky-50 text-sky-800 ring-sky-200", dot: "bg-sky-300", icon: "🎗️" },
  NOT_ENROLLED: { box: "bg-white text-ink-300 ring-ink-100", dot: "bg-ink-100", icon: "" },
  UPCOMING: { box: "bg-white text-ink-400 ring-ink-100 ring-dashed", dot: "bg-ink-200", icon: "·" },
  NONE: { box: "bg-ink-50/60 text-ink-400 ring-ink-100", dot: "bg-ink-200", icon: "" },
};

/** Il nome di uno stato: i nuovi (PARTIAL, MONTH_EXEMPT, …) con le chiavi
 *  money2, gli altri con quelle che hanno già il quadro del mese (`month`)
 *  o il calendario della stagione (`months`). */
export function stateLabel(state: string, t: T, base: "month" | "months" = "month"): string {
  const other = base === "month" ? "months" : "month";
  return t.dyn(`money2.state.${state}`, t.dyn(`${base}.state.${state}`, t.dyn(`${other}.state.${state}`, state)));
}

/** URL di un relatório, per lo schermo o da scaricare. */
export function reportUrl(report: ReportKey, period: { season?: number; year?: number }, format: "json" | "csv" | "xlsx" = "json", lang?: string) {
  const q = new URLSearchParams({ format });
  if (period.year) q.set("year", String(period.year));
  else if (period.season) q.set("season", String(period.season));
  if (lang) q.set("lang", lang);
  return `/admin/reports/${report}?${q.toString()}`;
}

/** La stagione in corso (settembre → agosto): l'anno in cui comincia. */
export function currentSeason(): number {
  const d = new Date();
  return d.getMonth() >= 8 ? d.getFullYear() : d.getFullYear() - 1;
}
