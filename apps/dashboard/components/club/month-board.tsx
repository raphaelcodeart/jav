"use client";

import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { AthleteMarks } from "@/components/club/person-marks";
import { ProofPicker } from "@/components/ui/proof-picker";
import { ReceiptViewer } from "@/components/club/proofs-panel";
import { ExemptMonthModal, PartialPayModal, useMoneyUndo } from "@/components/club/money-actions";
import { feeLabel } from "@/lib/fee-label";
import { clubGet, clubSend, type Fee, type MonthBoard, type MonthBoardState, type MonthRow } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import { stateLabel } from "@/lib/money2";

// Il quadro del mese (apps/api/app/domains/club/month_board.py): la prima
// cosa che la segreteria deve vedere. Il mese corrente in grande, quanto si
// doveva incassare e quanto manca, e un riquadro per atleta con la sua
// mensilità: pagata o no, e «Segna pagato» con un tocco. Accanto, ciò che la
// stessa persona deve ancora (mesi arretrati, gare, judogi): si paga tutto
// insieme. Lo Shop resta a parte, con il suo numero.

type Filter = "todo" | "paid" | "all" | "other";

export const MONTH_STATE_STYLE: Record<MonthBoardState, { tone: string; ring: string; icon: string }> = {
  PAID: { tone: "bg-emerald-50 text-emerald-800", ring: "ring-emerald-200", icon: "✅" },
  DUE: { tone: "bg-amber-50 text-amber-800", ring: "ring-amber-200", icon: "⏳" },
  OVERDUE: { tone: "bg-rose-50 text-rose-700", ring: "ring-rose-300", icon: "⚠️" },
  PARTIAL: { tone: "bg-amber-50 text-amber-900", ring: "ring-amber-300", icon: "½" },
  WAIVED: { tone: "bg-ink-50 text-ink-600", ring: "ring-ink-100", icon: "🤝" },
  MONTH_EXEMPT: { tone: "bg-sky-50 text-sky-800", ring: "ring-sky-200", icon: "🎗️" },
  EXEMPT: { tone: "bg-sky-50 text-sky-800", ring: "ring-sky-200", icon: "🎗️" },
  NONE: { tone: "bg-ink-50 text-ink-500", ring: "ring-ink-100", icon: "—" },
};

const KIND_ICONS: Record<string, string> = {
  MONTHLY: "📅", ENROLLMENT: "📝", COMPETITION: "🏆", MEMBERSHIP: "🪪", FINE: "⚖️", EQUIPMENT: "🥋",
};

export function monthLabel(period: string, fmt: { date: (d: Date, o: Intl.DateTimeFormatOptions) => string }) {
  const [y, m] = period.split("-").map(Number);
  return fmt.date(new Date(y!, m! - 1, 15), { month: "long", year: "numeric" });
}

function shift(period: string, delta: number): string {
  const [y, m] = period.split("-").map(Number);
  const d = new Date(y!, m! - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** Il mese, la barra dell'incasso e i numeri: in cima alla panoramica e alle quote. */
function MonthHeader({ board, period, setPeriod, compact }: { board: MonthBoard; period: string; setPeriod?: (p: string) => void; compact?: boolean }) {
  const { t, fmt } = useI18n();
  const tt = board.totals;
  const pct = tt.expected_cents > 0 ? Math.round((tt.collected_cents / tt.expected_cents) * 100) : 0;
  return (
    <div className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-brand-600 via-brand-700 to-ink-950 p-5 text-white shadow-lift sm:p-7">
      <div className="pointer-events-none absolute -right-10 -top-16 h-64 w-64 rounded-full bg-accent-400/30 blur-3xl" aria-hidden="true" />
      <div className="relative flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          {setPeriod && (
            <button type="button" onClick={() => setPeriod(shift(period, -1))} aria-label={t("month.prev")}
              className="flex h-11 w-11 cursor-pointer items-center justify-center rounded-full bg-white/15 text-xl ring-1 ring-white/25 hover:bg-white/25">‹</button>
          )}
          <div className="px-1">
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-accent-200">
              {board.is_current ? `● ${t("month.current")}` : t("month.title")}
            </p>
            <h2 className="font-display text-3xl capitalize leading-tight sm:text-4xl">{monthLabel(board.period, fmt)}</h2>
          </div>
          {setPeriod && (
            <button type="button" onClick={() => setPeriod(shift(period, 1))} aria-label={t("month.next")}
              className="flex h-11 w-11 cursor-pointer items-center justify-center rounded-full bg-white/15 text-xl ring-1 ring-white/25 hover:bg-white/25">›</button>
          )}
          {setPeriod && !board.is_current && (
            <button type="button" onClick={() => setPeriod(currentPeriod())} className="ml-1 h-9 cursor-pointer rounded-full bg-accent-400 px-4 text-sm font-semibold text-ink-900 hover:bg-accent-300">
              {t("month.today")}
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Kpi value={String(tt.to_pay)} label={t("month.kpiToPay")} tone={tt.to_pay > 0 ? "warn" : "ok"} />
          <Kpi value={String(tt.paid)} label={t("month.kpiPaid")} tone="ok" />
          <Kpi value={fmt.euro(tt.missing_cents)} label={t("month.kpiMissing")} tone={tt.missing_cents > 0 ? "warn" : "ok"} />
        </div>
      </div>
      <div className="relative mt-5">
        <div className="flex items-baseline justify-between text-sm">
          <span>{t("month.collected", { done: fmt.euro(tt.collected_cents), total: fmt.euro(tt.expected_cents) })}</span>
          <span className="font-display text-2xl">{pct}%</span>
        </div>
        <div className="mt-2 h-4 overflow-hidden rounded-full bg-white/15 ring-1 ring-white/20">
          <motion.div className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-accent-300"
            initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.9, ease: "easeOut" }} />
        </div>
        {!compact && (tt.arrears_cents > 0 || tt.other_due_cents > 0) && (
          <p className="mt-3 text-sm text-white/80">
            {tt.arrears_cents > 0 && <span className="mr-4">⏮ {t("month.arrearsTotal", { amount: fmt.euro(tt.arrears_cents) })}</span>}
            {tt.other_due_cents > 0 && <span>🏆🥋 {t("month.otherTotal", { amount: fmt.euro(tt.other_due_cents) })}</span>}
          </p>
        )}
      </div>
    </div>
  );
}

function Kpi({ value, label, tone }: { value: string; label: string; tone: "ok" | "warn" }) {
  return (
    <div className={cn("min-w-[6.5rem] rounded-2xl px-4 py-2 text-center ring-1", tone === "warn" ? "bg-accent-400/90 text-ink-900 ring-accent-200" : "bg-white/15 ring-white/25")}>
      <p className="font-display text-2xl leading-none">{value}</p>
      <p className="mt-1 text-[10px] font-bold uppercase tracking-wider opacity-80">{label}</p>
    </div>
  );
}

function initials(r: MonthRow) {
  return `${r.first_name[0] ?? ""}${r.last_name[0] ?? ""}`.toUpperCase();
}

/** Che cosa si può fare su una mensilità oltre a «Segna pagato»: pagarla in
 *  parte, esentare il mese, annullare l'una o l'altra (money-actions.tsx). */
type BoxActions = {
  partial: (fee: Fee, title: string) => void;
  exempt: (row: MonthRow) => void;
  undo: (kind: "exempt" | "partial", feeId: string) => void;
};

const OPEN_STATES = ["DUE", "OVERDUE", "PARTIAL"];

/** Il riquadro di un atleta: chi, gruppo, quanto, stato, e il bottone. */
function PersonBox({ row, onPay, onProof, index, actions }: {
  row: MonthRow; onPay: (fees: Fee[], title: string) => void; onProof: (fee: Fee) => void; index: number; actions: BoxActions;
}) {
  const { t, fmt } = useI18n();
  // La prova mandata dalla famiglia (anche rifiutata): si apre da qui.
  const withProof = [...(row.fee ? [row.fee] : []), ...row.arrears, ...row.other_due].find((f) => f.proof_id);
  const style = MONTH_STATE_STYLE[row.state];
  const extra = [...row.arrears, ...row.other_due];
  const toPay = [...(row.fee && OPEN_STATES.includes(row.state) ? [row.fee] : []), ...extra];
  const name = `${row.first_name} ${row.last_name}`;
  const parts = row.parts ?? [];
  // «Annulla parziale» si fa sulla parte pagata da cui nasce il resto aperto.
  const splitParent = row.state === "PARTIAL" ? row.fee?.split_from_fee_id ?? null : null;
  const reason = parts.find((p) => p.split_reason)?.split_reason;
  return (
    <motion.li layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.96 }}
      transition={{ delay: Math.min(index, 16) * 0.02 }}
      className={cn("flex flex-col rounded-3xl bg-white p-4 shadow-soft ring-2", style.ring)}>
      <div className="flex items-center gap-3">
        {row.photo_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- foto dell'atleta
          <img src={row.photo_url} alt="" className="h-12 w-12 shrink-0 rounded-2xl object-cover" />
        ) : (
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-ink-700 to-ink-900 font-display text-white">{initials(row)}</span>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-ink-900">{name} <AthleteMarks id={row.athlete_id} /></p>
          <p className="truncate text-xs text-ink-500">{row.group ?? t("month.noGroup")}</p>
        </div>
      </div>
      <div className={cn("mt-3 flex items-center justify-between gap-2 rounded-2xl px-3 py-2", style.tone)}>
        <span className="text-sm font-semibold">{style.icon} {stateLabel(row.state, t)}</span>
        <span className="font-display text-xl">{row.state === "PARTIAL" ? fmt.euro(row.due_cents ?? 0) : row.fee ? fmt.euro(row.fee.amount_cents) : "—"}</span>
      </div>
      {row.state === "PARTIAL" && (
        <div className="mt-1.5 space-y-1">
          <div className="h-1.5 overflow-hidden rounded-full bg-amber-100" aria-hidden="true">
            <div className="h-full rounded-full bg-emerald-400"
              style={{ width: `${Math.round(((row.paid_cents ?? 0) * 100) / Math.max((row.paid_cents ?? 0) + (row.due_cents ?? 0), 1))}%` }} />
          </div>
          <p className="text-[11px] text-amber-900">
            {t("money2.board.partialLine", { paid: fmt.euro(row.paid_cents ?? 0), total: fmt.euro((row.paid_cents ?? 0) + (row.due_cents ?? 0)) })}
            {row.fee?.overdue ? ` · ${t("month.state.OVERDUE")}` : ""}
          </p>
          {reason && <p className="truncate text-[11px] italic text-ink-500" title={reason}>“{reason}”</p>}
        </div>
      )}
      {row.state === "MONTH_EXEMPT" && row.fee?.waive_reason && (
        <p className="mt-1 truncate text-[11px] italic text-sky-800" title={row.fee.waive_reason}>“{row.fee.waive_reason}”</p>
      )}
      {row.state === "PAID" && row.fee?.paid_at && (
        <p className="mt-1 text-[11px] text-emerald-700">
          {fmt.shortDate(row.fee.paid_at)}{row.fee.payment_method ? ` · ${t(`month.method.${row.fee.payment_method}`)}` : ""}{row.fee.cash_received_by_name ? ` · ${row.fee.cash_received_by_name}` : ""}
        </p>
      )}
      {row.state === "OVERDUE" && row.fee && <p className="mt-1 text-[11px] text-rose-600">{t("month.dueSince", { date: fmt.shortDate(row.fee.due_date) })}</p>}
      {extra.length > 0 && (
        <ul className="mt-2 space-y-1">
          {extra.slice(0, 3).map((f) => (
            <li key={f.id} className="flex items-center justify-between gap-2 rounded-xl bg-ink-50 px-2.5 py-1 text-xs text-ink-700">
              <span className="truncate">{KIND_ICONS[f.kind] ?? "•"} {feeLabel(f, t, fmt)}</span>
              <span className="shrink-0 font-semibold">{fmt.euro(f.amount_cents)}</span>
            </li>
          ))}
          {extra.length > 3 && <li className="text-[11px] text-ink-500">+ {extra.length - 3}</li>}
        </ul>
      )}
      <div className="mt-auto space-y-2 pt-3">
        {withProof && (
          <button type="button" onClick={() => onProof(withProof)}
            className={cn("flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold ring-1 transition",
              withProof.proof_status === "REJECTED" ? "bg-rose-50 text-rose-800 ring-rose-200 hover:bg-rose-100" : "bg-sky-50 text-sky-800 ring-sky-200 hover:bg-sky-100")}>
            🧾 {withProof.proof_status === "REJECTED" ? t("fees.viewRejectedProof") : t("fees.viewProof")}
          </button>
        )}
        {toPay.length > 0 ? (
          <Button className="w-full" onClick={() => onPay(toPay, name)}>
            ✓ {toPay.length === 1 ? t("month.markPaid") : t("month.markAllPaid", { amount: fmt.euro(toPay.reduce((s, f) => s + f.amount_cents, 0)) })}
          </Button>
        ) : row.state === "PAID" ? (
          <p className="text-center text-xs font-semibold text-emerald-700">✓ {t("month.allDone")}</p>
        ) : null}
        {/* La mensilità del mese: pagarla in parte, o esentare il mese. */}
        {(row.fee && OPEN_STATES.includes(row.state)) || row.state === "NONE" ? (
          <div className="grid grid-cols-2 gap-2">
            {row.fee && OPEN_STATES.includes(row.state) ? (
              <button type="button" onClick={() => actions.partial(row.fee!, name)}
                className="cursor-pointer rounded-xl bg-amber-50 px-2 py-2 text-xs font-semibold text-amber-900 ring-1 ring-amber-200 transition hover:bg-amber-100">
                ½ {t("money2.board.partial")}
              </button>
            ) : <span />}
            {row.state !== "PARTIAL" ? (
              <button type="button" onClick={() => actions.exempt(row)}
                className="cursor-pointer rounded-xl bg-sky-50 px-2 py-2 text-xs font-semibold text-sky-800 ring-1 ring-sky-200 transition hover:bg-sky-100">
                🎗️ {t("money2.board.exempt")}
              </button>
            ) : splitParent ? (
              <button type="button" onClick={() => actions.undo("partial", splitParent)}
                className="cursor-pointer rounded-xl px-2 py-2 text-xs font-semibold text-ink-500 ring-1 ring-ink-200 transition hover:bg-ink-50">
                ↶ {t("money2.board.undoPartial")}
              </button>
            ) : <span />}
          </div>
        ) : null}
        {row.state === "MONTH_EXEMPT" && row.fee && (
          <button type="button" onClick={() => actions.undo("exempt", row.fee!.id)}
            className="w-full cursor-pointer rounded-xl px-2 py-2 text-xs font-semibold text-sky-800 ring-1 ring-sky-200 transition hover:bg-sky-50">
            ↶ {t("money2.board.undoExempt")}
          </button>
        )}
      </div>
    </motion.li>
  );
}

/** La segreteria: il mese con tutti gli atleti. `compact` (panoramica): il
 *  mese corrente, chi manca, e il link al quadro completo. */
export function MonthBoardPanel({ compact = false, onOpen }: { compact?: boolean; onOpen?: () => void }) {
  const { t, fmt } = useI18n();
  const [period, setPeriod] = useState(currentPeriod);
  const [filter, setFilter] = useState<Filter>("todo");
  const [group, setGroup] = useState("");
  const [q, setQ] = useState("");
  const [paying, setPaying] = useState<{ fees: Fee[]; title: string } | null>(null);
  const [viewingProof, setViewingProof] = useState<{ id: string; status?: string | null } | null>(null);
  const [partial, setPartial] = useState<{ fee: Fee; title: string } | null>(null);
  const [exempting, setExempting] = useState<MonthRow | null>(null);
  const undo = useMoneyUndo();
  const { data, isLoading, error } = useQuery({
    queryKey: ["club", "admin", "month", period],
    queryFn: () => clubGet<MonthBoard>(`/admin/month?period=${period}`),
  });
  const shop = useQuery({
    queryKey: ["club", "admin", "shop-orders"],
    queryFn: () => clubGet<{ id: string; status: string; amount_cents: number }[]>("/admin/shop-orders"),
    enabled: !compact,
  });
  const groups = useMemo(() => [...new Set((data?.rows ?? []).map((r) => r.group ?? ""))].sort(), [data]);
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data?.rows ?? []).filter((r) => {
      if (group && (r.group ?? "") !== group) return false;
      if (needle && !`${r.first_name} ${r.last_name} ${r.guardian_email ?? ""}`.toLowerCase().includes(needle)) return false;
      if (filter === "todo") return OPEN_STATES.includes(r.state);
      if (filter === "paid") return r.state === "PAID";
      if (filter === "other") return r.arrears.length > 0 || r.other_due.length > 0;
      return true;
    }).sort((a, b) => Number(b.state === "OVERDUE") - Number(a.state === "OVERDUE"));
  }, [data, filter, group, q]);

  if (isLoading) return <Skeleton className={compact ? "h-48" : "h-96"} />;
  if (error || !data) return <EmptyState title={t("month.loadError")} text={(error as Error)?.message} />;
  const tt = data.totals;
  const shopWaiting = (shop.data ?? []).filter((o) => o.status === "AWAITING_PAYMENT");

  if (compact) {
    const todo = data.rows.filter((r) => OPEN_STATES.includes(r.state));
    return (
      <div className="space-y-4">
        <MonthHeader board={data} period={period} compact />
        {todo.length > 0 ? (
          <div className="glass-card rounded-3xl p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-base text-ink-900">⏳ {t("month.whoMissing", { n: todo.length })}</h3>
              {onOpen && <Button size="sm" onClick={onOpen}>{t("month.openBoard")} →</Button>}
            </div>
            <ul className="flex flex-wrap gap-2">
              {todo.slice(0, 24).map((r) => (
                <li key={r.athlete_id} className={cn("inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-semibold ring-1",
                  r.state === "OVERDUE" ? "bg-rose-50 text-rose-700 ring-rose-200" : "bg-amber-50 text-amber-800 ring-amber-200")}>
                  {r.first_name} {r.last_name[0]}. · {r.fee ? fmt.euro(r.state === "PARTIAL" ? r.due_cents ?? 0 : r.fee.amount_cents) : ""}
                </li>
              ))}
              {todo.length > 24 && <li className="self-center text-sm text-ink-500">+ {todo.length - 24}</li>}
            </ul>
          </div>
        ) : (
          <div className="rounded-3xl bg-emerald-50 p-5 text-center font-semibold text-emerald-800 ring-1 ring-emerald-200">🎉 {t("month.everyonePaid")}</div>
        )}
      </div>
    );
  }

  const tabs: { key: Filter; label: string; n: number }[] = [
    { key: "todo", label: `⏳ ${t("month.filterTodo")}`, n: tt.to_pay },
    { key: "paid", label: `✅ ${t("month.filterPaid")}`, n: tt.paid },
    { key: "other", label: `🏆 ${t("month.filterOther")}`, n: data.rows.filter((r) => r.arrears.length || r.other_due.length).length },
    { key: "all", label: t("month.filterAll"), n: data.rows.length },
  ];

  return (
    <div className="space-y-5">
      <MonthHeader board={data} period={period} setPeriod={setPeriod} />

      {shopWaiting.length > 0 && (
        <p className="rounded-2xl bg-sky-50 px-4 py-3 text-sm text-sky-900 ring-1 ring-sky-200">
          🛍️ {t("month.shopWaiting", { n: shopWaiting.length, amount: (shopWaiting.reduce((s, o) => s + o.amount_cents, 0) / 100).toFixed(2) })}
        </p>
      )}

      <div className="sticky top-0 z-10 -mx-1 space-y-3 rounded-3xl bg-white/90 p-3 shadow-soft ring-1 ring-ink-900/5 backdrop-blur">
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button key={tab.key} type="button" onClick={() => setFilter(tab.key)}
              className={cn("inline-flex h-10 cursor-pointer items-center gap-2 rounded-full px-4 text-sm font-semibold transition",
                filter === tab.key ? "bg-ink-900 text-white shadow" : "bg-ink-50 text-ink-700 hover:bg-ink-100")}>
              {tab.label} <span className={cn("rounded-full px-2 text-xs", filter === tab.key ? "bg-white/20" : "bg-white")}>{tab.n}</span>
            </button>
          ))}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input placeholder={t("month.search")} value={q} onChange={(e) => setQ(e.target.value)} />
          {groups.length > 1 && (
            <Select value={group} onChange={(e) => setGroup(e.target.value)} className="sm:w-64" aria-label={t("month.group")}>
              <option value="">{t("month.allGroups")}</option>
              {groups.map((g) => <option key={g || "none"} value={g}>{g || t("month.noGroup")}</option>)}
            </Select>
          )}
        </div>
      </div>

      {rows.length === 0 ? (
        filter === "todo" && !q && !group
          ? <div className="rounded-3xl bg-emerald-50 p-8 text-center text-lg font-semibold text-emerald-800 ring-1 ring-emerald-200">🎉 {t("month.everyonePaid")}</div>
          : <EmptyState title={t("month.nobody")} />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          <AnimatePresence initial={false}>
            {rows.map((r, i) => <PersonBox key={r.athlete_id} row={r} index={i} onPay={(fees, title) => setPaying({ fees, title })}
              actions={{ partial: (fee, title) => setPartial({ fee, title }), exempt: setExempting, undo }}
              onProof={(f) => setViewingProof(f.proof_id ? { id: f.proof_id, status: f.proof_status } : null)} />)}
          </AnimatePresence>
        </ul>
      )}
      {tt.none > 0 && filter === "all" && <p className="text-xs text-ink-500">{t("month.noneNote", { n: tt.none })}</p>}
      {paying && <QuickPayModal fees={paying.fees} title={paying.title} onClose={() => setPaying(null)} />}
      {partial && <PartialPayModal fee={partial.fee} title={partial.title} onClose={() => setPartial(null)} />}
      {exempting && (
        <ExemptMonthModal athleteId={exempting.athlete_id} name={`${exempting.first_name} ${exempting.last_name}`}
          period={data.period} periodName={monthLabel(data.period, fmt)} amountCents={exempting.fee?.amount_cents ?? null}
          onClose={() => setExempting(null)} />
      )}
      <ReceiptViewer proof={viewingProof} onClose={() => setViewingProof(null)} />
    </div>
  );
}

type Method = "CASH" | "MBWAY" | "BANK_TRANSFER" | "CARD";
const METHODS: { key: Method; icon: string }[] = [
  { key: "CASH", icon: "💶" }, { key: "MBWAY", icon: "📱" }, { key: "BANK_TRANSFER", icon: "🏦" }, { key: "CARD", icon: "💳" },
];

/** «Segna pagato»: una o più quote della stessa persona insieme, con il
 *  modo (e per i contanti a chi). Le stesse regole di /fees/{id}/mark-paid. */
function QuickPayModal({ fees, title, onClose }: { fees: Fee[]; title: string; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(() => new Set(fees.map((f) => f.id)));
  const [method, setMethod] = useState<Method>("CASH");
  const [receiver, setReceiver] = useState("");
  const [otherName, setOtherName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: receivers } = useQuery({
    queryKey: ["club", "admin", "cash-receivers"],
    queryFn: () => clubGet<{ user_id: string; name: string }[]>("/admin/cash-receivers"),
  });
  const chosen = fees.filter((f) => selected.has(f.id));
  const ready = chosen.length > 0 && (method !== "CASH" || (receiver === "other" ? otherName.trim().length >= 2 : receiver !== ""));

  // Una ricevuta sola per le quote scelte, con la foto o il PDF se c'è
  // (POST /club/admin/fees/pay, club_service.staff_record_payment).
  async function save() {
    setBusy(true);
    try {
      const form = new FormData();
      for (const f of chosen) form.append("fee_ids", f.id);
      form.append("method", method);
      if (method === "CASH") {
        if (receiver === "other") form.append("cash_received_by_name", otherName.trim());
        else form.append("cash_received_by_user_id", receiver);
      }
      if (file) form.append("file", file);
      await clubSend("/admin/fees/pay", "POST", form);
      toast({ tone: "success", title: t("month.paidDone", { n: chosen.length }), text: file ? t("proof.saved") : undefined });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: t("month.payFailed", { n: 0 }), text: (e as Error).message });
    } finally {
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={t("month.markPaid")} subtitle={title}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
        <Button loading={busy} disabled={!ready} onClick={save}>✓ {t("month.confirmPaid", { amount: fmt.euro(chosen.reduce((s, f) => s + f.amount_cents, 0)) })}</Button>
      </>}>
      <div className="space-y-4">
        <ul className="space-y-2">
          {fees.map((f) => (
            <li key={f.id}>
              <label className="flex cursor-pointer items-center gap-3 rounded-2xl bg-ink-50 px-4 py-3 ring-1 ring-ink-100">
                <input type="checkbox" className="h-5 w-5 accent-brand-600" checked={selected.has(f.id)}
                  onChange={(e) => setSelected((s) => { const n = new Set(s); if (e.target.checked) n.add(f.id); else n.delete(f.id); return n; })} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-ink-900">{KIND_ICONS[f.kind] ?? "•"} {feeLabel(f, t, fmt)}</span>
                  <span className="block text-xs text-ink-500">{t("club.dueOnCap", { date: fmt.shortDate(f.due_date) })}{f.overdue ? ` · ${t("month.state.OVERDUE")}` : ""}</span>
                </span>
                <span className="font-display text-ink-900">{fmt.euro(f.amount_cents)}</span>
              </label>
            </li>
          ))}
        </ul>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label={t("month.how")}>
          {METHODS.map((m) => (
            <button key={m.key} type="button" role="radio" aria-checked={method === m.key} onClick={() => setMethod(m.key)}
              className={cn("cursor-pointer rounded-2xl p-3 text-center ring-1", method === m.key ? "bg-brand-50 ring-2 ring-brand-400" : "bg-white ring-ink-200 hover:ring-ink-300")}>
              <span className="block text-2xl" aria-hidden="true">{m.icon}</span>
              <span className="block text-sm font-semibold text-ink-900">{t(`month.method.${m.key}`)}</span>
            </button>
          ))}
        </div>
        {method === "CASH" && (
          <Field label={t("month.cashTo")}>
            <Select value={receiver} onChange={(e) => setReceiver(e.target.value)}>
              <option value="">{t("month.choose")}</option>
              {(receivers ?? []).map((r) => <option key={r.user_id} value={r.user_id}>{r.name}</option>)}
              <option value="other">{t("month.someoneElse")}</option>
            </Select>
          </Field>
        )}
        {method === "CASH" && receiver === "other" && (
          <Field label={t("month.whoName")}><Input value={otherName} maxLength={120} onChange={(e) => setOtherName(e.target.value)} /></Field>
        )}
        <ProofPicker file={file} onFile={setFile} optional />
      </div>
    </Modal>
  );
}

/** La famiglia: «Questo mese», la mensilità di ogni figlio in grande, e ciò
 *  che resta. Il bottone apre il pagamento con quelle quote già scelte. */
export function FamilyMonthCard({ board, onPay }: { board: MonthBoard; onPay: (feeIds: string[]) => void }) {
  const { t, fmt } = useI18n();
  if (board.rows.length === 0) return null;
  const due = board.rows.flatMap((r) => [
    ...(r.fee && OPEN_STATES.includes(r.state) ? [r.fee] : []), ...r.arrears, ...r.other_due,
  ]);
  const total = due.reduce((s, f) => s + f.amount_cents, 0);
  return (
    <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      className="overflow-hidden rounded-[2rem] bg-white shadow-lift ring-1 ring-ink-900/5">
      <div className="flex flex-wrap items-center justify-between gap-4 bg-gradient-to-r from-brand-600 to-brand-800 px-6 py-5 text-white">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-accent-200">● {t("month.current")}</p>
          <h2 className="font-display text-3xl capitalize">{monthLabel(board.period, fmt)}</h2>
        </div>
        {total > 0 ? (
          <div className="text-right">
            <p className="text-xs font-semibold uppercase tracking-wider text-white/80">{t("month.familyToPay")}</p>
            <p className="font-display text-4xl leading-none">{fmt.euro(total)}</p>
          </div>
        ) : (
          <p className="rounded-full bg-emerald-400 px-4 py-2 font-semibold text-ink-900">🎉 {t("month.familyAllPaid")}</p>
        )}
      </div>
      <ul className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3">
        {board.rows.map((r) => {
          const style = MONTH_STATE_STYLE[r.state];
          return (
            <li key={r.athlete_id} className={cn("rounded-2xl p-4 ring-2", style.ring)}>
              <div className="flex items-center justify-between gap-2">
                <p className="truncate font-semibold text-ink-900">{r.first_name}</p>
                <span className="text-xs text-ink-500">{r.group ?? ""}</span>
              </div>
              <div className={cn("mt-2 flex items-center justify-between rounded-xl px-3 py-2", style.tone)}>
                <span className="text-sm font-semibold">{style.icon} {stateLabel(r.state, t)}</span>
                <span className="font-display text-xl">{r.state === "PARTIAL" ? fmt.euro(r.due_cents ?? 0) : r.fee ? fmt.euro(r.fee.amount_cents) : "—"}</span>
              </div>
              {r.state === "PARTIAL" && (
                <p className="mt-1 text-[11px] text-amber-900">
                  {t("money2.board.partialLine", { paid: fmt.euro(r.paid_cents ?? 0), total: fmt.euro((r.paid_cents ?? 0) + (r.due_cents ?? 0)) })}
                </p>
              )}
              {[...r.arrears, ...r.other_due].map((f) => (
                <p key={f.id} className="mt-1.5 flex justify-between gap-2 text-xs text-ink-600">
                  <span className="truncate">{KIND_ICONS[f.kind] ?? "•"} {feeLabel(f, t, fmt)}</span><span className="shrink-0 font-semibold">{fmt.euro(f.amount_cents)}</span>
                </p>
              ))}
            </li>
          );
        })}
      </ul>
      {total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-ink-100 px-5 py-4">
          <p className="text-sm text-ink-600">{t("month.familyHint")}</p>
          <Button size="lg" onClick={() => onPay(due.map((f) => f.id))}>📸 {t("month.familyPay", { amount: fmt.euro(total) })}</Button>
        </div>
      )}
    </motion.section>
  );
}

