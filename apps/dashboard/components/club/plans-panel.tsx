"use client";

import { AnimatePresence, motion } from "motion/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { CourseModal } from "@/components/club/course-modal";
import { clubGet, clubSend, type Course, type Plan } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// «Piani e prezzi» della segreteria: i gruppi del club (fascia d'età,
// mensilità, iscrizione annuale, giorno di scadenza, mesi fatturati), ognuno
// con il suo colore (`club_plans.color`, migrazione 0031). Senza colore
// scelto, il gruppo prende quello della tavolozza secondo la sua posizione.
// `allows_high_competition`: solo negli atleti di questi gruppi la segreteria
// e il treinador possono segnare l'alta competizione (club/loja.py).

const A = (path: string) => `/admin${path}`;
export const PLAN_PALETTE = ["#E2552D", "#2563EB", "#16A34A", "#9333EA", "#EA9A0C", "#0891B2", "#DB2777", "#475569"];
/** Da settembre ad agosto, come la stagione. */
const SEASON_MONTHS = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8];

export function planColor(plan: Pick<Plan, "color">, index: number): string {
  return plan.color ?? PLAN_PALETTE[index % PLAN_PALETTE.length]!;
}

/** Il testo sopra un colore: bianco sui colori scuri, quasi nero sui chiari. */
function inkOn(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return (r * 299 + g * 587 + b * 114) / 1000 > 160 ? "#111827" : "#ffffff";
}

export function PlansPanel() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "plans"], queryFn: () => clubGet<Plan[]>(A("/plans")) });
  const { data: courses } = useQuery({ queryKey: ["club", "admin", "courses"], queryFn: () => clubGet<Course[]>(A("/courses")) });
  const [editing, setEditing] = useState<{ plan: Plan | null; index: number } | null>(null);
  // Le turmas senza età non vanno in nessun gruppo (la stessa regola del sito
  // e di JAVBOT, site.py::plan_slots): lo si dice, invece di nasconderle.
  const ageless = (courses ?? []).filter((c) => c.active && c.min_age == null && c.max_age == null);
  const plans = [...(data ?? [])].sort((a, b) => Number(b.active) - Number(a.active) || a.min_age - b.min_age);

  async function remove(p: Plan) {
    if (!window.confirm(t("plans.deleteConfirm", { name: p.name }))) return;
    try {
      await clubSend(A(`/plans/${p.id}`), "DELETE");
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: t("plans.deleted") });
    } catch (e) {
      toast({ tone: "error", title: t("plans.failed"), text: (e as Error).message });
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-ink-600">💡 {t("plans.intro")}</p>
        <Button className="shrink-0" onClick={() => setEditing({ plan: null, index: plans.length })} icon={<span>＋</span>}>{t("plans.new")}</Button>
      </div>

      {isLoading ? (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3"><Skeleton className="h-72" /><Skeleton className="h-72" /><Skeleton className="h-72" /></div>
      ) : plans.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">📋</span>} title={t("plans.empty")} text={t("plans.emptyText")}
          action={<Button onClick={() => setEditing({ plan: null, index: 0 })}>{t("plans.createFirst")}</Button>} />
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
          <AnimatePresence initial={false}>
            {plans.map((p, i) => (
              <PlanCard key={p.id} plan={p} color={planColor(p, i)} index={i} fmt={fmt} courses={courses ?? []}
                onEdit={() => setEditing({ plan: p, index: i })} onDelete={() => remove(p)} />
            ))}
          </AnimatePresence>
        </div>
      )}
      {ageless.length > 0 && (
        <p className="rounded-2xl bg-amber-50 p-4 text-sm text-amber-900 ring-1 ring-amber-200">
          ⚠️ {t("groups.ageless", { n: ageless.length, names: ageless.map((c) => c.name).join(", ") })}
        </p>
      )}
      {editing && <PlanModal plan={editing.plan} index={editing.index} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ages(p: Pick<Plan, "min_age" | "max_age">, t: ReturnType<typeof useI18n>["t"]) {
  return p.max_age != null ? t("plans.ageRange", { min: p.min_age, max: p.max_age }) : t("plans.agePlus", { min: p.min_age });
}

function PlanCard({ plan: p, color, index, fmt, courses, onEdit, onDelete }: {
  plan: Plan; color: string; index: number; fmt: ReturnType<typeof useI18n>["fmt"]; courses: Course[]; onEdit: () => void; onDelete: () => void;
}) {
  const { t } = useI18n();
  const ink = inkOn(color);
  const billed = new Set(p.billing_months);
  return (
    <motion.article layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
      transition={{ delay: Math.min(index, 8) * 0.04 }} whileHover={{ y: -4 }}
      className={cn("group flex flex-col overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/5 transition-shadow hover:shadow-lift", !p.active && "opacity-70")}>
      {/* La fascia del gruppo, nel suo colore */}
      <header className="relative overflow-hidden px-5 pb-5 pt-4" style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)`, color: ink }}>
        <span aria-hidden="true" className="pointer-events-none absolute -right-6 -top-8 select-none font-display text-[7rem] leading-none opacity-15">柔</span>
        <div className="relative flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] opacity-80">{ages(p, t)}</p>
            <h3 className="mt-1 font-display text-2xl leading-tight">{p.name}</h3>
          </div>
          <span className="shrink-0 rounded-full px-2.5 py-1 text-xs font-bold" style={{ background: `${ink}22`, color: ink }}>
            👥 {p.athletes_count ?? 0}
          </span>
        </div>
        {(!p.active || p.allows_high_competition) && (
          <div className="relative mt-2 flex flex-wrap gap-1.5">
            {!p.active && <span className="inline-block rounded-full bg-black/25 px-2 py-0.5 text-[11px] font-semibold text-white">{t("plans.inactive")}</span>}
            {p.allows_high_competition && <span className="inline-block rounded-full bg-white/90 px-2 py-0.5 text-[11px] font-semibold text-ink-900">🏅 {t("lojaStaff.plan.highBadge")}</span>}
          </div>
        )}
      </header>

      <div className="flex flex-1 flex-col gap-4 p-5">
        {/* I prezzi */}
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">{t("plans.monthly")}</p>
            <p className="font-display text-4xl leading-none text-ink-900">{fmt.euro(p.monthly_fee_cents)}</p>
          </div>
          <div className="text-right">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">{t("plans.enrollment")}</p>
            <p className="text-lg font-semibold text-ink-800">{p.enrollment_fee_cents > 0 ? fmt.euro(p.enrollment_fee_cents) : "—"}</p>
          </div>
        </div>

        {p.description && <p className="line-clamp-3 text-sm text-ink-600">{p.description}</p>}

        {/* Quando si paga */}
        <div className="rounded-2xl bg-ink-50 p-3">
          <p className="text-xs font-semibold text-ink-600">📅 {t("plans.dueDay", { day: p.due_day })}</p>
          <div className="mt-2 grid grid-cols-12 gap-0.5" aria-label={t("plans.billedMonths")}>
            {SEASON_MONTHS.map((m) => (
              <span key={m} title={fmt.date(new Date(2026, m - 1, 1), { month: "long" })}
                className={cn("flex h-6 items-center justify-center rounded text-[9px] font-bold uppercase", billed.has(m) ? "" : "bg-white text-ink-300 ring-1 ring-ink-100")}
                style={billed.has(m) ? { background: color, color: ink } : undefined}>
                {fmt.date(new Date(2026, m - 1, 1), { month: "narrow" })}
              </span>
            ))}
          </div>
          <p className="mt-1.5 text-[11px] text-ink-500">{t("plans.billedCount", { n: p.billing_months.length })}</p>
        </div>

        <GroupSchedule plan={p} color={color} courses={courses} />

        <div className="mt-auto flex gap-2 pt-1">
          <Button size="sm" variant="secondary" className="flex-1" onClick={onEdit}>✏️ {t("plans.edit")}</Button>
          <Button size="sm" variant="ghost" className="text-rose-600" onClick={onDelete} aria-label={t("plans.delete")}>🗑</Button>
        </div>
      </div>
    </motion.article>
  );
}

function PlanModal({ plan, index, onClose }: { plan: Plan | null; index: number; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState(plan?.name ?? "");
  const [description, setDescription] = useState(plan?.description ?? "");
  const [minAge, setMinAge] = useState(String(plan?.min_age ?? 4));
  const [maxAge, setMaxAge] = useState(plan?.max_age != null ? String(plan.max_age) : "");
  const [monthly, setMonthly] = useState(plan ? String(plan.monthly_fee_cents / 100) : "");
  const [enrollment, setEnrollment] = useState(plan ? String(plan.enrollment_fee_cents / 100) : "0");
  const [dueDay, setDueDay] = useState(String(plan?.due_day ?? 10));
  const [months, setMonths] = useState<number[]>(plan?.billing_months ?? [9, 10, 11, 12, 1, 2, 3, 4, 5, 6]);
  const [active, setActive] = useState(plan?.active ?? true);
  const [highCompetition, setHighCompetition] = useState(plan?.allows_high_competition ?? false);
  const [color, setColor] = useState(plan?.color ?? PLAN_PALETTE[index % PLAN_PALETTE.length]!);
  const [busy, setBusy] = useState(false);
  const cents = (v: string) => Math.round(Number(v.replace(",", ".")) * 100) || 0;

  async function save() {
    setBusy(true);
    const body = {
      name, description: description || null, min_age: Number(minAge), max_age: maxAge ? Number(maxAge) : null,
      monthly_fee_cents: cents(monthly), enrollment_fee_cents: cents(enrollment), due_day: Number(dueDay),
      billing_months: months, active, color, allows_high_competition: highCompetition,
    };
    try {
      await (plan ? clubSend(A(`/plans/${plan.id}`), "PATCH", body) : clubSend(A("/plans"), "POST", body));
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: plan ? t("plans.updated") : t("plans.created") });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: t("plans.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const ink = inkOn(color);
  const preview = { min_age: Number(minAge) || 0, max_age: maxAge ? Number(maxAge) : null };

  return (
    <Modal open onClose={onClose} size="lg" title={plan ? t("plans.editTitle") : t("plans.newTitle")}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button loading={busy} onClick={save} disabled={!name.trim() || !monthly || months.length === 0}>{t("plans.save")}</Button>
      </>}>
      <div className="space-y-5">
        {/* Anteprima della fascia, mentre si scrive */}
        <div className="overflow-hidden rounded-2xl px-5 py-4 shadow-soft" style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)`, color: ink }}>
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] opacity-80">{ages(preview, t)}</p>
          <p className="mt-1 font-display text-2xl leading-tight">{name || t("plans.namePlaceholder")}</p>
          <p className="mt-1 text-sm opacity-90">{monthly ? `${fmt.euro(cents(monthly))} ${t("plans.perMonth")}` : ""}</p>
        </div>

        <Field label={t("plans.name")} htmlFor="pl-name">
          <Input id="pl-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("plans.namePlaceholder")} />
        </Field>

        <div>
          <p className="mb-2 text-sm font-semibold text-ink-800">{t("plans.color")}</p>
          <div className="flex flex-wrap items-center gap-2">
            {PLAN_PALETTE.map((c) => (
              <button key={c} type="button" onClick={() => setColor(c)} aria-label={c} aria-pressed={color.toLowerCase() === c.toLowerCase()}
                className={cn("h-9 w-9 cursor-pointer rounded-full shadow-sm ring-2 ring-offset-2 transition hover:scale-110",
                  color.toLowerCase() === c.toLowerCase() ? "ring-ink-900" : "ring-transparent")}
                style={{ background: c }} />
            ))}
            <label className="relative ml-1 inline-flex h-9 cursor-pointer items-center gap-2 rounded-full bg-ink-50 px-3 text-xs font-semibold text-ink-700 ring-1 ring-ink-200 hover:bg-white">
              🎨 {t("plans.customColor")}
              <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="absolute inset-0 cursor-pointer opacity-0" aria-label={t("plans.customColor")} />
            </label>
          </div>
        </div>

        <Field label={t("plans.description")} hint={t("plans.descriptionHint")} htmlFor="pl-desc">
          <Textarea id="pl-desc" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label={t("plans.minAge")} hint={t("plans.minAgeHint")} htmlFor="pl-min"><Input id="pl-min" type="number" min={0} value={minAge} onChange={(e) => setMinAge(e.target.value)} /></Field>
          <Field label={t("plans.maxAge")} hint={t("plans.maxAgeHint")} htmlFor="pl-max"><Input id="pl-max" type="number" min={0} value={maxAge} onChange={(e) => setMaxAge(e.target.value)} /></Field>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label={t("plans.monthlyEur")} htmlFor="pl-month"><Input id="pl-month" inputMode="decimal" value={monthly} onChange={(e) => setMonthly(e.target.value)} /></Field>
          <Field label={t("plans.enrollmentEur")} hint={t("clubAdmin.planEnrollmentHint")} htmlFor="pl-enr"><Input id="pl-enr" inputMode="decimal" value={enrollment} onChange={(e) => setEnrollment(e.target.value)} /></Field>
          <Field label={t("plans.dueDayLabel")} htmlFor="pl-due"><Input id="pl-due" type="number" min={1} max={28} value={dueDay} onChange={(e) => setDueDay(e.target.value)} /></Field>
        </div>

        <div>
          <p className="mb-1 text-sm font-semibold text-ink-800">{t("plans.billedMonths")}</p>
          <p className="mb-2 text-xs text-ink-500">{t("plans.billedMonthsHint")}</p>
          <div className="grid grid-cols-6 gap-1.5 sm:grid-cols-12">
            {SEASON_MONTHS.map((m) => {
              const on = months.includes(m);
              return (
                <button key={m} type="button" aria-pressed={on}
                  onClick={() => setMonths((cur) => (on ? cur.filter((x) => x !== m) : [...cur, m]))}
                  className={cn("cursor-pointer rounded-xl py-2 text-xs font-bold capitalize ring-1 transition", on ? "shadow-sm" : "bg-white text-ink-400 ring-ink-200 hover:ring-ink-300")}
                  style={on ? { background: color, color: ink, borderColor: color } : undefined}>
                  {fmt.date(new Date(2026, m - 1, 1), { month: "short" }).replace(".", "")}
                </button>
              );
            })}
          </div>
        </div>

        <button type="button" role="switch" aria-checked={active} onClick={() => setActive((v) => !v)}
          className="flex w-full cursor-pointer items-center justify-between gap-3 rounded-2xl bg-ink-50 px-4 py-3 text-left text-sm font-semibold text-ink-800 ring-1 ring-ink-200">
          <span>{t("plans.active")}<span className="block text-xs font-normal text-ink-500">{t("plans.activeHint")}</span></span>
          <span aria-hidden="true" className={cn("relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors", active ? "bg-emerald-500" : "bg-ink-300")}>
            <motion.span layout transition={{ type: "spring", stiffness: 600, damping: 34 }}
              className={cn("absolute h-5 w-5 rounded-full bg-white shadow", active ? "right-0.5" : "left-0.5")} />
          </span>
        </button>

        <button type="button" role="switch" aria-checked={highCompetition} onClick={() => setHighCompetition((v) => !v)}
          className="flex w-full cursor-pointer items-center justify-between gap-3 rounded-2xl bg-ink-50 px-4 py-3 text-left text-sm font-semibold text-ink-800 ring-1 ring-ink-200">
          <span>{t("lojaStaff.plan.highToggle")}<span className="block text-xs font-normal text-ink-500">{t("lojaStaff.plan.highToggleHint")}</span></span>
          <span aria-hidden="true" className={cn("relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors", highCompetition ? "bg-emerald-500" : "bg-ink-300")}>
            <motion.span layout transition={{ type: "spring", stiffness: 600, damping: 34 }}
              className={cn("absolute h-5 w-5 rounded-full bg-white shadow", highCompetition ? "right-0.5" : "left-0.5")} />
          </span>
        </button>
      </div>
    </Modal>
  );
}

/** Le turmas di un gruppo: quelle la cui fascia d'età tocca quella del
 *  gruppo (site.py::plan_slots, la stessa regola del sito e di JAVBOT). In
 *  sintesi i giorni della settimana; aprendo «Gerir», ogni turma con il
 *  treinador e gli orari, da aggiungere o togliere, e una turma nuova con le
 *  età del gruppo già scritte. La pagina «Turmas e horários» resta per vedere
 *  tutti gli orari insieme. */
function GroupSchedule({ plan, color, courses }: { plan: Plan; color: string; courses: Course[] }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Course | "new" | null>(null);
  const [draft, setDraft] = useState<Record<string, { weekday: string; from: string; to: string }>>({});
  const pMin = plan.min_age ?? 0;
  const pMax = plan.max_age ?? 999;
  const mine = courses.filter((c) => c.active && (c.min_age != null || c.max_age != null)
    && (c.min_age ?? 0) <= pMax && pMin <= (c.max_age ?? 999));
  const slots = mine.flatMap((c) => c.slots.map((s) => ({ ...s, course: c.name })))
    .sort((a, b) => a.weekday - b.weekday || a.starts_at.localeCompare(b.starts_at));
  const ink = inkOn(color);

  async function act(fn: () => Promise<unknown>, ok: string) {
    try {
      await fn();
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: ok });
    } catch (e) {
      toast({ tone: "error", title: t("common.failed"), text: (e as Error).message });
    }
  }

  return (
    <div className="rounded-2xl ring-1 ring-ink-900/5">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="flex w-full cursor-pointer items-center justify-between gap-2 rounded-2xl px-3 py-2.5 text-left hover:bg-ink-50">
        <span className="text-xs font-semibold text-ink-700">🗓️ {t("groups.title")} · {t("groups.perWeek", { n: slots.length })}</span>
        <span className="text-xs font-bold text-brand-700">{open ? t("groups.close") : t("groups.manage")} {open ? "▲" : "▼"}</span>
      </button>
      {/* In sintesi: i turni della settimana */}
      {!open && slots.length > 0 && (
        <div className="flex flex-wrap gap-1 px-3 pb-3">
          {slots.map((s) => (
            <span key={s.id} className="rounded-lg px-2 py-0.5 text-[11px] font-semibold" style={{ background: `${color}1a`, color: "#1f2328" }}>
              {t.dyn(`site.weekdayShort.${s.weekday}`, String(s.weekday))} {s.starts_at.slice(0, 5)}
            </span>
          ))}
        </div>
      )}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="space-y-3 px-3 pb-3">
              {mine.length === 0 && <p className="rounded-xl bg-ink-50 p-3 text-xs text-ink-500">{t("groups.empty")}</p>}
              {mine.map((c) => {
                const d = draft[c.id] ?? { weekday: "0", from: "18:00", to: "19:00" };
                return (
                  <div key={c.id} className="rounded-xl bg-ink-50/70 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-ink-900">{c.name}</p>
                        <p className="text-[11px] text-ink-500">
                          🧑‍🏫 {c.instructor_name ?? t("groups.noCoach")} · {t("groups.ages", { min: c.min_age ?? 0, max: c.max_age ?? "+" })} · 👥 {c.athletes_count}
                        </p>
                      </div>
                      <button type="button" onClick={() => setEditing(c)} className="shrink-0 cursor-pointer rounded-lg px-2 py-1 text-xs font-semibold text-brand-700 hover:bg-white">✏️</button>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {c.slots.map((s) => (
                        <span key={s.id} className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold" style={{ background: color, color: ink }}>
                          {t.dyn(`site.weekdayShort.${s.weekday}`, String(s.weekday))} {s.starts_at.slice(0, 5)}–{s.ends_at.slice(0, 5)}
                          <button type="button" aria-label={t("ca.slot.remove")} className="cursor-pointer opacity-70 hover:opacity-100"
                            onClick={() => window.confirm(t("groups.removeSlot")) && act(() => clubSend(A(`/slots/${s.id}`), "DELETE"), t("ca.slot.removed"))}>✕</button>
                        </span>
                      ))}
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <select value={d.weekday} onChange={(e) => setDraft((x) => ({ ...x, [c.id]: { ...d, weekday: e.target.value } }))} aria-label={t("ca.slot.day")}
                        className="h-8 rounded-lg bg-white px-2 text-xs ring-1 ring-ink-200">
                        {[0, 1, 2, 3, 4, 5, 6].map((i) => <option key={i} value={i}>{t.dyn(`site.weekday.${i}`, String(i))}</option>)}
                      </select>
                      <input type="time" value={d.from} onChange={(e) => setDraft((x) => ({ ...x, [c.id]: { ...d, from: e.target.value } }))} aria-label={t("ca.slot.from")} className="h-8 rounded-lg bg-white px-2 text-xs ring-1 ring-ink-200" />
                      <input type="time" value={d.to} onChange={(e) => setDraft((x) => ({ ...x, [c.id]: { ...d, to: e.target.value } }))} aria-label={t("ca.slot.to")} className="h-8 rounded-lg bg-white px-2 text-xs ring-1 ring-ink-200" />
                      <button type="button" className="h-8 cursor-pointer rounded-lg bg-ink-900 px-3 text-xs font-semibold text-white hover:bg-ink-800"
                        onClick={() => act(() => clubSend(A(`/courses/${c.id}/slots`), "POST", { weekday: Number(d.weekday), starts_at: d.from, ends_at: d.to, room: null }), t("ca.slot.added"))}>
                        ＋ {t("groups.addSlot")}
                      </button>
                    </div>
                  </div>
                );
              })}
              <button type="button" onClick={() => setEditing("new")}
                className="w-full cursor-pointer rounded-xl border-2 border-dashed border-ink-200 py-2 text-xs font-semibold text-ink-600 hover:border-brand-300 hover:text-brand-700">
                ＋ {t("groups.newCourse")}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {editing && (
        <CourseModal course={editing === "new" ? null : editing}
          defaults={{ name: plan.name, min_age: plan.min_age, max_age: plan.max_age }} onClose={() => setEditing(null)} />
      )}
    </div>
  );
}
