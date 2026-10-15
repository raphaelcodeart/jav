"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { CHART } from "@/lib/club-accounting";
import { PAYMENT_METHOD_ICONS, clubGet, type Fee, type MonthState, type SeasonMonth, type SeasonMonths } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";
import { usePrefersReducedMotion } from "@/lib/motion";

/** Chi guarda il calendario: il titolare (paga), l'atleta nella sua area
 *  (legge), la segreteria (segna pagato). Decide da dove si leggono i dati
 *  e che cosa si può fare su un mese. */
export type MonthsMode = "family" | "area" | "admin";

const SOURCE: Record<MonthsMode, (id: string) => string> = {
  family: (id) => `/athletes/${id}/months`,
  area: (id) => `/athlete-area/${id}/months`,
  admin: (id) => `/admin/athletes/${id}/months`,
};

const RECEIPT: Partial<Record<MonthsMode, (proofId: string) => string>> = {
  family: (id) => `/payment-proofs/${id}/url`,
  admin: (id) => `/admin/payment-proofs/${id}/url`,
};

// I colori seguono lo stato, uguali in ogni vista: verde pagato, ambra da
// pagare, rosso scaduto, grigio previsto.
const STATE_COLORS = { paid: "#1baf7a", due: "#eda100", overdue: "#d63a2f", upcoming: "#bcbaba" };

const CELL: Record<MonthState, { box: string; icon: string; tone: Tone }> = {
  PAID: { box: "bg-emerald-50 ring-emerald-200 text-emerald-900", icon: "✓", tone: "success" },
  OVERDUE: { box: "bg-rose-50 ring-rose-300 text-rose-800", icon: "!", tone: "danger" },
  DUE: { box: "bg-amber-50 ring-amber-200 text-amber-900", icon: "⏳", tone: "warning" },
  UPCOMING: { box: "bg-white ring-ink-200 ring-dashed text-ink-600", icon: "·", tone: "neutral" },
  WAIVED: { box: "bg-ink-50 ring-ink-200 text-ink-600", icon: "—", tone: "neutral" },
  NOT_BILLED: { box: "bg-ink-50/60 ring-ink-100 text-ink-400", icon: "", tone: "neutral" },
  NOT_ENROLLED: { box: "bg-ink-50/60 ring-ink-100 text-ink-400", icon: "", tone: "neutral" },
  NONE: { box: "bg-ink-50/60 ring-ink-100 text-ink-400", icon: "", tone: "neutral" },
};

/** Le dodici mensilità della stagione di un atleta, da settembre ad agosto,
 *  con due grafici sopra: quanto è pagato / da pagare / scaduto, e le
 *  presenze mese per mese. Un mese si apre con un tocco. */
export function SeasonMonthsPanel({ athleteId, mode, onPay, onMarkPaid }: {
  athleteId: string;
  mode: MonthsMode;
  /** Solo il titolare: paga la quota di quel mese. */
  onPay?: (fee: Fee) => void;
  /** Solo la segreteria: la segna pagata (contanti, carta, bonifico). */
  onMarkPaid?: (fee: Fee) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState<SeasonMonth | null>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: ["club", "months", mode, athleteId],
    queryFn: () => clubGet<SeasonMonths>(SOURCE[mode](athleteId)),
  });

  if (isLoading) return <Skeleton className="h-72" />;
  if (error || !data) return <p className="text-sm text-rose-600">{t("months.loadFailed")}</p>;

  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-base text-ink-900">{t("months.title", { season: data.season_label })}</h3>
        <p className="text-sm text-ink-500">{mode === "area" ? t("months.hintReadOnly") : t("months.hint")}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <PaidDonut data={data} />
        <AttendanceBars data={data} />
      </div>
      <MonthGrid months={data.months} onOpen={setOpen} />
      {open && (
        <MonthDetail
          month={open}
          mode={mode}
          onClose={() => setOpen(null)}
          onPay={onPay && open.fee ? () => { setOpen(null); onPay(open.fee!); } : undefined}
          onMarkPaid={onMarkPaid && open.fee ? () => { setOpen(null); onMarkPaid(open.fee!); } : undefined}
        />
      )}
    </section>
  );
}

function monthName(m: SeasonMonth, tag: string, style: "short" | "long" = "short") {
  return new Date(m.year, m.month - 1, 1).toLocaleDateString(tag, style === "short" ? { month: "short" } : { month: "long", year: "numeric" });
}

/** Il gruppo cambia (di solito a gennaio, con l'età federale): il primo
 *  mese del gruppo nuovo porta un'etichetta. */
function groupChanges(months: SeasonMonth[]): boolean[] {
  const billed = months.map((m) => !["NOT_BILLED", "NOT_ENROLLED", "NONE"].includes(m.state) && m.group_name !== null);
  return months.map((m, i) => {
    if (!billed[i]) return false;
    const before = months.slice(0, i).filter((_, j) => billed[j]).at(-1);
    return before !== undefined && before.group_name !== m.group_name;
  });
}

function MonthGrid({ months, onOpen }: { months: SeasonMonth[]; onOpen: (m: SeasonMonth) => void }) {
  const { t, fmt } = useI18n();
  const reduced = usePrefersReducedMotion();
  const changed = groupChanges(months);
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
      {months.map((m, i) => {
        const style = CELL[m.state];
        const amount = m.fee?.amount_cents ?? m.expected_cents;
        return (
          <motion.button
            key={m.period}
            type="button"
            onClick={() => onOpen(m)}
            initial={reduced ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: reduced ? 0 : i * 0.025 }}
            className={cn(
              "relative flex min-h-[92px] flex-col items-start justify-between rounded-2xl p-3 text-left ring-1 transition cursor-pointer hover:-translate-y-0.5 hover:shadow-sm",
              style.box,
              m.current && "ring-2 ring-brand-500",
            )}
            aria-label={`${monthName(m, fmt.tag, "long")}: ${t.dyn(`months.state.${m.state}`, m.state)}${amount != null ? `, ${fmt.euro(amount)}` : ""}`}
          >
            <span className="flex w-full items-start justify-between gap-1">
              <span>
                <span className="block text-xs font-bold uppercase tracking-wide">{monthName(m, fmt.tag)}</span>
                <span className="block text-[10px] opacity-70">{m.year}</span>
              </span>
              {style.icon && <span aria-hidden="true" className="text-sm font-bold">{style.icon}</span>}
            </span>
            <span className="block w-full">
              {amount != null && <span className="block font-display text-base tabular-nums">{fmt.euro(amount)}</span>}
              <span className="block text-[10px] font-semibold">{t.dyn(`months.state.${m.state}`, m.state)}</span>
            </span>
            {changed[i] && (
              <span className="absolute -top-2 right-2 rounded-full bg-accent-400 px-2 py-0.5 text-[9px] font-bold uppercase text-ink-900 shadow">
                {t("months.newGroup")}
              </span>
            )}
          </motion.button>
        );
      })}
    </div>
  );
}

/** Quanto della stagione è pagato: una ciambella per importi, con i numeri
 *  anche in chiaro sotto. */
function PaidDonut({ data }: { data: SeasonMonths }) {
  const { t, fmt } = useI18n();
  const reduced = usePrefersReducedMotion();
  const s = data.summary;
  const slices = [
    { key: "paid", label: t("months.paid"), cents: s.paid_cents, color: STATE_COLORS.paid },
    { key: "due", label: t("months.due"), cents: s.due_cents - s.overdue_cents, color: STATE_COLORS.due },
    { key: "overdue", label: t("months.overdue"), cents: s.overdue_cents, color: STATE_COLORS.overdue },
    { key: "upcoming", label: t("months.upcoming"), cents: s.upcoming_cents, color: STATE_COLORS.upcoming },
  ];
  const total = slices.reduce((sum, x) => sum + x.cents, 0);
  const billed = s.months_paid + s.months_due + s.months_overdue + s.months_upcoming;
  return (
    <div className="rounded-3xl bg-white p-4 ring-1 ring-ink-100">
      <div className="flex items-center gap-4">
        <div className="relative h-32 w-32 shrink-0" role="img" aria-label={t("months.chartAria")}>
          {total > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={slices.filter((x) => x.cents > 0)} dataKey="cents" nameKey="label" innerRadius="68%" outerRadius="100%"
                  paddingAngle={2} stroke="none" isAnimationActive={!reduced}>
                  {slices.filter((x) => x.cents > 0).map((x) => <Cell key={x.key} fill={x.color} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full w-full rounded-full ring-[14px] ring-inset ring-ink-100" />
          )}
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="font-display text-2xl text-ink-900">{s.months_paid}/{billed}</span>
          </div>
        </div>
        <ul className="min-w-0 flex-1 space-y-1.5">
          {slices.map((x) => (
            <li key={x.key} className="flex items-center justify-between gap-2 text-sm">
              <span className="flex items-center gap-2 text-ink-600">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: x.color }} />
                {x.label}
              </span>
              <span className={cn("tabular-nums font-semibold", x.key === "overdue" && x.cents > 0 ? "text-rose-600" : "text-ink-900")}>
                {fmt.euro(x.cents)}
              </span>
            </li>
          ))}
        </ul>
      </div>
      <p className="mt-3 text-xs text-ink-500">{t("months.paidOf", { paid: s.months_paid, total: billed })}</p>
    </div>
  );
}

function AttendanceBars({ data }: { data: SeasonMonths }) {
  const { t, fmt } = useI18n();
  const reduced = usePrefersReducedMotion();
  const points = data.months.map((m) => ({ label: monthName(m, fmt.tag), n: m.attendances, current: m.current }));
  return (
    <div className="rounded-3xl bg-white p-4 ring-1 ring-ink-100">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-ink-900">{t("months.attendanceTitle")}</p>
        <p className="text-xs text-ink-500">{t("months.attendanceTotal", { n: data.summary.attendances })}</p>
      </div>
      <div className="mt-2 h-32" role="img" aria-label={t("months.attendanceTitle")}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={points} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
            <XAxis dataKey="label" stroke={CHART.axis} fontSize={10} tickLine={false} axisLine={false} interval={0} />
            <Tooltip
              cursor={{ fill: "rgba(22,21,21,0.04)" }}
              contentStyle={{ background: "#ffffff", border: "1px solid #d9d8d8", borderRadius: 12, fontSize: 12 }}
              formatter={(value) => [String(value), t("months.attendances")]}
            />
            <Bar dataKey="n" radius={[6, 6, 0, 0]} maxBarSize={22} isAnimationActive={!reduced}>
              {points.map((p) => <Cell key={p.label} fill={p.current ? CHART.costs : CHART.income} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function MonthDetail({ month: m, mode, onClose, onPay, onMarkPaid }: {
  month: SeasonMonth; mode: MonthsMode; onClose: () => void; onPay?: () => void; onMarkPaid?: () => void;
}) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const fee = m.fee;
  const payable = fee && (m.state === "DUE" || m.state === "OVERDUE");
  const receipt = RECEIPT[mode];
  const method = fee?.payment_method;

  async function openReceipt(proofId: string) {
    try {
      const { url } = await clubGet<{ url: string }>(receipt!(proofId));
      window.open(url, "_blank", "noopener");
    } catch (e) {
      toast({ tone: "error", title: t("months.receiptFailed"), text: (e as Error).message });
    }
  }

  const rows: [string, React.ReactNode][] = [];
  if (m.group_name) {
    rows.push([t("months.group"), (
      <span key="g" title={t("months.federalAgeHint")}>{m.group_name} · {t("months.federalAge", { n: m.federal_age })}</span>
    )]);
  }
  if (fee) {
    rows.push([t("months.dueDate"), fmt.shortDate(fee.due_date)]);
    if (fee.discount_cents > 0 && fee.gross_amount_cents !== null) {
      rows.push([t("months.amount"), t("pay.discounted", { list: fmt.euro(fee.gross_amount_cents), note: fee.discount_note ?? "" })]);
    }
    if (fee.status === "PAID" && fee.paid_at) rows.push([t("months.paidOn"), fmt.shortDate(fee.paid_at)]);
    if (fee.status === "PAID" && method) {
      rows.push([t("months.method"), `${PAYMENT_METHOD_ICONS[method] ?? ""} ${t.dyn(`method.${method}`, method)}`]);
    }
    if (fee.cash_received_by_name) rows.push([t("months.cashTo"), fee.cash_received_by_name]);
    if (fee.payment_note) rows.push(["", <span key="n" className="italic">“{fee.payment_note}”</span>]);
    if (fee.status === "WAIVED" && fee.waive_reason) rows.push(["", t("months.waived", { reason: fee.waive_reason })]);
  }
  rows.push([t("months.attendances"), String(m.attendances)]);

  const amount = fee?.amount_cents ?? m.expected_cents;
  const style = CELL[m.state];
  const title = monthName(m, fmt.tag, "long");
  return (
    <Modal
      open
      onClose={onClose}
      title={title.charAt(0).toUpperCase() + title.slice(1)}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
          {payable && onPay && <Button onClick={onPay}>💶 {t("months.pay")}</Button>}
          {payable && onMarkPaid && <Button onClick={onMarkPaid}>✓ {t("months.markPaid")}</Button>}
        </>
      }
    >
      <div className="space-y-4">
        <div className={cn("flex items-center justify-between gap-3 rounded-2xl p-4 ring-1", style.box)}>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide opacity-80">
              {m.state === "UPCOMING" ? t("months.expected") : t("months.amount")}
            </p>
            <p className="font-display text-3xl tabular-nums">{amount != null ? fmt.euro(amount) : "—"}</p>
          </div>
          <Badge tone={style.tone} dot>{t.dyn(`months.state.${m.state}`, m.state)}</Badge>
        </div>
        {m.state === "UPCOMING" && <p className="text-xs text-ink-500">{t("months.expectedHint")}</p>}
        {m.state === "NOT_BILLED" && <p className="text-sm text-ink-600">{t("months.notBilledText")}</p>}
        {m.state === "NOT_ENROLLED" && <p className="text-sm text-ink-600">{t("months.notEnrolledText")}</p>}
        {m.state === "NONE" && <p className="text-sm text-ink-600">{t("months.noneText")}</p>}
        <dl className="divide-y divide-ink-100 rounded-2xl bg-white ring-1 ring-ink-100">
          {rows.map(([label, value], i) => (
            <div key={i} className="flex items-start justify-between gap-4 px-4 py-2.5 text-sm">
              <dt className="text-ink-500">{label}</dt>
              <dd className="text-right font-medium text-ink-900">{value}</dd>
            </div>
          ))}
        </dl>
        {m.group_name && <p className="text-xs text-ink-500">{t("months.federalAgeHint")}</p>}
        {m.proof?.has_file && receipt && (
          <Button variant="secondary" size="sm" onClick={() => openReceipt(m.proof!.id)}>🧾 {t("months.openReceipt")} ↗</Button>
        )}
        {payable && mode === "area" && <p className="text-sm text-ink-600">{t("months.payInfo")}</p>}
      </div>
    </Modal>
  );
}
