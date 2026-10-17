// La contabilità del club, della piattaforma e della famiglia. I tipi
// rispecchiano apps/api/app/domains/club/accounting_schemas.py: ogni importo
// arriva calcolato dal server, qui si sceglie solo il periodo.

import { friendlyApiError } from "@/lib/api-error";
import type { Fee } from "@/lib/club";

export const FEE_KINDS = ["MONTHLY", "ENROLLMENT", "COMPETITION", "MEMBERSHIP", "EQUIPMENT", "FINE"] as const;
export const EXPENSE_CATEGORIES = [
  "RENT", "STAFF", "FEDERATION", "INSURANCE", "EQUIPMENT", "TRANSPORT", "EVENTS", "UTILITIES", "MARKETING", "ADMIN",
  "COLLABORATORS", "CLEANING", "EXTERNAL_COACH", "OTHER",
] as const;
export const PAYMENT_METHODS = ["BANK_TRANSFER", "MBWAY", "CASH", "CARD", "DIRECT_DEBIT", "CHEQUE", "OTHER"] as const;
export const AGING_KEYS = ["NOT_DUE", "D0_30", "D31_60", "D61_90", "D90_PLUS"] as const;

/** I colori dei grafici, sempre gli stessi per la stessa cosa: entrate,
 *  costi e commissione sono i primi tre posti della palette categoriale
 *  validata (skill dataviz), il risultato è inchiostro. I tipi di quota
 *  usano i primi quattro, nello stesso ordine ovunque. */
export const CHART = {
  income: "#2a78d6",
  costs: "#eb6834",
  fee: "#1baf7a",
  result: "#161515",
  grid: "#ededed",
  axis: "#6b696a",
  kinds: {
    MONTHLY: "#2a78d6", ENROLLMENT: "#eb6834", COMPETITION: "#1baf7a", MEMBERSHIP: "#eda100", EQUIPMENT: "#8b5cf6",
    FINE: "#64748b",
  } as Record<string, string>,
  /** Anzianità dei debiti: grigio per ciò che non è ancora scaduto, poi
   *  una sola tinta che scurisce con il ritardo (sequenziale). */
  aging: { NOT_DUE: "#bcbaba", D0_30: "#ffc5b6", D31_60: "#f6694e", D61_90: "#c8311a", D90_PLUS: "#6d2219" } as Record<string, string>,
};

export interface Figures {
  income_cents: number;
  income_by_kind: Record<string, number>;
  credit_cents: number;
  issued_cents: number;
  issued_paid_cents: number;
  collection_rate: number | null;
  discounts_cents: number;
  absence_cents: number;
  waived_cents: number;
  missed_cents: number;
  /** Mensilità esenti («Isenta este mês»): fuori dall'emesso e dai mancati incassi. */
  exempt_cents?: number;
  expenses_cents: number;
  expenses_by_category: Record<string, number>;
  staff_cents: number;
  staff_minutes: number;
  /** Corsi JAV: la parte dei treinador e ciò che resta a JAV. */
  coach_share_cents?: number;
  kept_cents?: number;
  costs_cents: number;
  platform_fee_cents: number;
  result_cents: number;
}

export interface SeriesPoint {
  month: string;
  income_cents: number;
  costs_cents: number;
  platform_fee_cents: number;
  result_cents: number;
}

export interface AgingBucket {
  cents: number;
  count: number;
}

export interface Debtor {
  user_id: string;
  name: string;
  due_cents: number;
  overdue_cents: number;
  fees: number;
  oldest_due_date: string;
  days_overdue: number;
}

export interface Debts {
  total_cents: number;
  overdue_cents: number;
  families: number;
  aging: Record<string, AgingBucket>;
  top: Debtor[];
}

export interface ClubSummary {
  period: string;
  kind: "month" | "year";
  start: string;
  end: string;
  platform_fee_pct: string;
  totals: Figures;
  compared_months: string[];
  current: Figures;
  previous: Figures;
  series: SeriesPoint[];
  ytd: Figures | null;
  ytd_previous: Figures | null;
  forecast: { expected_cents: number; income_cents: number; platform_fee_cents: number; result_cents: number } | null;
  debts: Debts;
}

export interface LedgerRow {
  id: string;
  date: string;
  type: "INCOME" | "EXPENSE" | "STAFF" | "PLATFORM_FEE";
  category: string;
  description: string;
  counterparty: string;
  family: string;
  amount_cents: number;
  method: string;
  has_receipt: boolean;
  expense_id: string | null;
  recurring: boolean;
  computed: boolean;
}

export interface Ledger {
  rows: LedgerRow[];
  truncated: boolean;
  in_cents: number;
  out_cents: number;
}

export interface Expense {
  id: string;
  spent_on: string;
  category: string;
  amount_cents: number;
  description: string;
  supplier: string | null;
  payment_method: string;
  has_receipt: boolean;
  receipt_filename: string | null;
  recurring_id: string | null;
  period: string | null;
  created_at: string;
}

export interface RecurringExpense {
  id: string;
  category: string;
  amount_cents: number;
  description: string;
  supplier: string | null;
  payment_method: string;
  day_of_month: number;
  starts_on: string;
  ends_on: string | null;
  active: boolean;
}

export interface StaffCost {
  user_id: string;
  name: string;
  minutes: number;
  hourly_rate_cents: number | null;
  rate_valid_from: string | null;
  cost_cents: number;
}

export interface PlatformClub {
  id: string;
  name: string;
  slug: string;
  status: string;
  kind?: string;
  platform_fee_pct: string;
  athletes_active: number;
  families: number;
  month: Figures;
  year: Figures;
  platform_fee_all_time_cents: number;
  debt_cents: number;
  overdue_cents: number;
  aging: Record<string, AgingBucket>;
}

export interface PlatformSummary {
  year: number;
  month: string;
  year_months: string[];
  clubs: PlatformClub[];
  /** L'unità dei corsi JAV, fuori dai club: ciò che JAV tiene dei suoi incassi. */
  courses_unit: (PlatformClub & {
    kept_month_cents: number; kept_month_forecast_cents: number; kept_year_cents: number; kept_all_time_cents: number;
  }) | null;
  totals: {
    clubs_active: number;
    athletes_active: number;
    families: number;
    month: Figures;
    year: Figures;
    debt_cents: number;
    overdue_cents: number;
    aging: Record<string, AgingBucket>;
  };
  earnings: {
    month_cents: number;
    month_forecast_cents: number;
    year_cents: number;
    all_time_cents: number;
    courses_month_cents: number;
    courses_month_forecast_cents: number;
    courses_year_cents: number;
    courses_all_time_cents: number;
    series: (SeriesPoint & { by_club: Record<string, number>; courses_kept_cents?: number })[];
  };
  growth: { month: string; clubs: number; athletes: number; families: number }[];
  shop: { month_cents: number; year_cents: number; all_time_cents: number; orders_year: number; series: { month: string; cents: number }[] };
  default_platform_fee_pct: string;
}

export interface PersonalNumbers {
  paid_year_cents: number;
  paid_all_time_cents: number;
  paid_by_kind: Record<string, number>;
  due_cents: number;
  overdue_cents: number;
  upcoming_cents: number;
  savings_year_cents: number;
}

export interface PersonalAccount {
  year: number;
  has_children: boolean;
  is_athlete: boolean;
  totals: PersonalNumbers;
  people: (PersonalNumbers & { athlete_id: string | null; name: string; is_self: boolean; status: string; shop_year_cents: number })[];
  shop: { year_cents: number; all_time_cents: number; orders_year: number; credit_used_year_cents: number };
  wallet: {
    balance_cents: number;
    referral_credits_cents: number;
    investments_cents: number;
    credit_spent_on_fees_cents: number;
    credit_spent_on_shop_cents: number;
  };
  series: { month: string; fees_cents: number; shop_cents: number }[];
  next_payments: Fee[];
  discounts: (Fee & { saved_cents: number; absence_adjustment?: string | null })[];
}

/** Le API della piattaforma (`/clubs/...`) non passano da `/club`. */
export async function platformGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api/proxy/clubs${path}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

export async function platformSend<T>(path: string, method: "PUT" | "PATCH", body: unknown): Promise<T> {
  const res = await fetch(`/api/proxy/clubs${path}`, {
    method, body: JSON.stringify(body), headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** "2026-10" -> "ott 26" nella lingua di chi legge. */
export function monthShort(month: string, tag: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(y!, (m ?? 1) - 1, 1).toLocaleDateString(tag, { month: "short", year: "2-digit" });
}

export function monthLong(month: string, tag: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(y!, (m ?? 1) - 1, 1).toLocaleDateString(tag, { month: "long", year: "numeric" });
}

/** La variazione percentuale tra due importi, o null se prima non c'era niente. */
export function delta(now: number, before: number): number | null {
  if (!before) return null;
  return Math.round(((now - before) / Math.abs(before)) * 100);
}

export function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** "10 %" / "7,5 %" nella lingua di chi legge. */
export function pctLabel(n: number, tag: string): string {
  return `${n.toLocaleString(tag, { maximumFractionDigits: 2 })}%`;
}

/** Da euro scritti a mano ("12,50") a centesimi; NaN se non è un numero. */
export function toCents(value: string): number {
  const n = Number(value.replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(n) ? Math.round(n * 100) : NaN;
}
