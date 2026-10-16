"use client";

import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import {
  INSURANCE_PER_ATHLETE, MEDICAL_COST, REPAIR_COST, UPKEEP, bookMedical, clubRent, collectFees,
  ledgerTotals, repairEquipment, setFee, setIntensity, type Intensity, type MonthLedger,
} from "./engine";
import { money, monthName } from "./i18n";
import { Bar, BeltBadge, COLOR_GRAD, Card, SectionTitle, type PanelProps } from "./ui";

// Le schede del club: gestione (quota, intensità, sponsor, attrezzatura),
// atleti (umore, infortuni, visita medica, quota) e soldi (entrate e uscite).

export function ClubPanel(props: PanelProps) {
  const { state, t, locale, apply } = props;
  const toast = useToast();
  const club = state.club;
  if (!club) return null;
  const unpaid = club.athletes.filter((a) => !a.feePaid).length;
  const monthlyOut = clubRent(club.city) + INSURANCE_PER_ATHLETE * club.athletes.length + UPKEEP;

  return (
    <div className="space-y-4">
      <div className={cn("relative overflow-hidden rounded-[2rem] bg-gradient-to-br p-5 text-white shadow-lift", COLOR_GRAD[club.color])}>
        <div className="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-white/20 blur-3xl" aria-hidden="true" />
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-white/80">📍 {club.city} · {t("athletesCount", { n: club.athletes.length })}</p>
        <h2 className="mt-1 font-display text-2xl">{club.name}</h2>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-2xl bg-black/20 p-3">
            <p className="text-[11px] font-bold uppercase text-white/70">{t("clubBalance")}</p>
            <p className={cn("font-display text-2xl tabular-nums", club.balance < 0 && "text-accent-300")}>{money(club.balance, locale)}</p>
          </div>
          <div className="rounded-2xl bg-black/20 p-3">
            <p className="text-[11px] font-bold uppercase text-white/70">{t("clubRep")}</p>
            <p className="font-display text-2xl tabular-nums">🌟 {club.reputation}</p>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <SectionTitle icon="💶">{t("clubFee")}</SectionTitle>
          <div className="flex items-center justify-center gap-4">
            <Button variant="secondary" size="lg" aria-label="-5" onClick={() => apply({ state: setFee(state, club.fee - 5) })}>−</Button>
            <motion.span key={club.fee} initial={{ scale: 0.8 }} animate={{ scale: 1 }} className="min-w-24 text-center font-display text-3xl text-ink-900 tabular-nums">{money(club.fee, locale)}</motion.span>
            <Button variant="secondary" size="lg" aria-label="+5" onClick={() => apply({ state: setFee(state, club.fee + 5) })}>+</Button>
          </div>
          <p className="mt-3 text-xs text-ink-500">{t("clubFeeHint")}</p>
          <p className="mt-2 text-xs font-semibold text-ink-700">
            {t("in")}: ~{money(club.fee * club.athletes.length, locale)} · {t("out")}: ~{money(monthlyOut, locale)}
          </p>
          <Button className="mt-3 w-full" variant={unpaid > 0 ? "primary" : "secondary"} disabled={unpaid === 0 || club.lastCollectWeek === state.week}
            onClick={() => {
              const r = collectFees(state);
              apply(r);
              if (!r.error) toast({ tone: r.collected > 0 ? "success" : "info", title: t("collected", { n: r.collected }) });
            }}>
            📨 {t("collect")} {unpaid > 0 && `(${unpaid})`}
          </Button>
        </Card>

        <Card>
          <SectionTitle icon="🔥">{t("intensity")}</SectionTitle>
          <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label={t("intensity")}>
            {(["LOW", "MEDIUM", "HIGH"] as Intensity[]).map((v) => (
              <button key={v} type="button" role="radio" aria-checked={club.intensity === v} onClick={() => apply({ state: setIntensity(state, v) })}
                className={cn("h-12 cursor-pointer rounded-xl text-sm font-bold ring-2 transition",
                  club.intensity === v ? "bg-ink-900 text-white ring-ink-900" : "bg-ink-50 text-ink-700 ring-transparent hover:ring-ink-200")}>
                {t(`int_${v}`)}
              </button>
            ))}
          </div>
          <p className="mt-3 text-sm text-ink-600">{t(`intd_${club.intensity}`)}</p>
        </Card>

        <Card>
          <SectionTitle icon="🤝">{t("sponsor")}</SectionTitle>
          <p className="text-sm text-ink-700">
            {club.sponsor ? t("sponsorInfo", { name: club.sponsor.name, n: money(club.sponsor.perMonth, locale), m: club.sponsor.monthsLeft }) : t("noSponsor")}
          </p>
        </Card>

        <Card className={cn(club.equipmentBroken && "ring-2 ring-rose-300")}>
          <SectionTitle icon="🧱">{t("equipment")}</SectionTitle>
          {club.equipmentBroken ? (
            <>
              <p className="text-sm font-semibold text-rose-700">{t("equipmentBroken")}</p>
              <Button className="mt-3" variant="danger" onClick={() => apply(repairEquipment(state))}>🔧 {t("repair", { n: money(REPAIR_COST, locale) })}</Button>
            </>
          ) : (
            <p className="text-sm font-semibold text-emerald-700">{t("equipmentOk")}</p>
          )}
        </Card>
      </div>
    </div>
  );
}

function moodEmoji(h: number) {
  return h > 70 ? "😄" : h > 45 ? "🙂" : h > 25 ? "😕" : "😢";
}

export function AthletesPanel({ state, t, locale, apply }: PanelProps) {
  const club = state.club;
  if (!club) return null;
  return (
    <div className="space-y-3">
      <SectionTitle icon="👥">{t("athletesTitle")} ({club.athletes.length})</SectionTitle>
      {club.athletes.length === 0 && <Card><p className="text-ink-500">{t("athletesEmpty")}</p></Card>}
      <div className="grid gap-3 md:grid-cols-2">
        {club.athletes.map((a) => {
          const expired = a.medicalUntil < state.week;
          return (
            <motion.div key={a.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <Card className={cn((expired || a.humor < 30 || !a.feePaid) && "ring-2 ring-amber-200")}>
                <div className="flex items-start gap-3">
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-ink-50 text-2xl" aria-label={`${t("mood")} ${a.humor}`}>{moodEmoji(a.humor)}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-bold text-ink-900">{a.name}</p>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-500">
                      <span>{t("ageShort", { n: a.age })}</span>
                      <BeltBadge belt={a.belt} t={t} small />
                      {a.medals > 0 && <span>🏅×{a.medals}</span>}
                      {a.discount && <span>⭐</span>}
                    </div>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-ink-700">
                  <Bar label={t("stat_tecnica")} right={a.tecnica} value={a.tecnica} tone="bg-brand-500" />
                  <Bar label={t("stat_fisico")} right={a.fisico} value={a.fisico} tone="bg-emerald-500" />
                  <Bar label={t("mood")} right={a.humor} value={a.humor} tone={a.humor < 30 ? "bg-rose-500" : "bg-sky-500"} />
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] font-bold">
                  {a.lesao > 0 && <span className="rounded-full bg-rose-100 px-2 py-1 text-rose-700">🤕 {t("injury", { n: a.lesao })}</span>}
                  <span className={cn("rounded-full px-2 py-1", expired ? "bg-rose-100 text-rose-700" : "bg-emerald-50 text-emerald-700")}>
                    🩺 {expired ? t("medicalExpired") : t("medicalOk", { w: a.medicalUntil })}
                  </span>
                  <span className={cn("rounded-full px-2 py-1", a.feePaid ? "bg-emerald-50 text-emerald-700" : "bg-amber-100 text-amber-800")}>
                    💶 {a.feePaid ? t("feePaid") : t("feeUnpaid")}
                  </span>
                </div>
                {a.techniques.length > 0 && (
                  <p className="mt-2 text-[11px] text-ink-500"><span className="font-bold">{t("techniques")}:</span> {a.techniques.join(", ")}</p>
                )}
                {a.medicalUntil < state.week + 8 && (
                  <Button size="sm" variant={expired ? "primary" : "secondary"} className="mt-3" onClick={() => apply(bookMedical(state, a.id))}>
                    🩺 {t("bookMedical", { n: money(MEDICAL_COST, locale) })}
                  </Button>
                )}
              </Card>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

const ROWS_IN = ["fees", "sponsor"] as const;
const ROWS_OUT = ["rent", "insurance", "medical", "competitions", "equipment"] as const;

export function LedgerTable({ l, t, locale }: { l: MonthLedger; t: PanelProps["t"]; locale: string }) {
  const tot = ledgerTotals(l);
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="rounded-2xl bg-emerald-50 p-3 ring-1 ring-emerald-100">
        <p className="mb-2 text-sm font-black text-emerald-800">⬇️ {t("in")}</p>
        {ROWS_IN.map((k) => (
          <p key={k} className="flex justify-between text-sm text-emerald-900"><span>{t(`l_${k}`)}</span><span className="tabular-nums">+{money(l[k], locale)}</span></p>
        ))}
        <p className="mt-2 flex justify-between border-t border-emerald-200 pt-2 font-bold text-emerald-900"><span>Σ</span><span className="tabular-nums">+{money(tot.income, locale)}</span></p>
      </div>
      <div className="rounded-2xl bg-rose-50 p-3 ring-1 ring-rose-100">
        <p className="mb-2 text-sm font-black text-rose-800">⬆️ {t("out")}</p>
        {ROWS_OUT.map((k) => (
          <p key={k} className="flex justify-between text-sm text-rose-900"><span>{t(`l_${k}`)}</span><span className="tabular-nums">−{money(l[k], locale)}</span></p>
        ))}
        <p className="mt-2 flex justify-between border-t border-rose-200 pt-2 font-bold text-rose-900"><span>Σ</span><span className="tabular-nums">−{money(tot.expenses, locale)}</span></p>
      </div>
      <p className={cn("rounded-2xl px-4 py-3 text-center font-display text-xl sm:col-span-2", tot.net >= 0 ? "bg-emerald-600 text-white" : "bg-rose-600 text-white")}>
        {t("net")}: {tot.net >= 0 ? "+" : ""}{money(tot.net, locale)}
      </p>
    </div>
  );
}

export function MoneyPanel({ state, t, locale }: PanelProps) {
  const club = state.club;
  const hist = club?.ledger ?? [];
  const max = Math.max(1, ...hist.map((l) => Math.max(ledgerTotals(l).income, ledgerTotals(l).expenses)));
  return (
    <div className="space-y-4">
      <Card>
        <SectionTitle icon="🐷">{t("pocket")}</SectionTitle>
        <p className="font-display text-3xl text-ink-900 tabular-nums">{money(state.hero.dinheiro, locale)}</p>
        <p className="mt-1 text-sm text-ink-500">{t("pocketHint")}</p>
      </Card>
      {club && (
        <>
          <Card>
            <SectionTitle icon="🧾">{t("monthNow")}</SectionTitle>
            <LedgerTable l={club.current} t={t} locale={locale} />
            <p className="mt-3 rounded-2xl bg-accent-50 p-3 text-sm font-semibold text-ink-800 ring-1 ring-accent-200">💡 {t("moneyLesson")}</p>
          </Card>
          <Card>
            <SectionTitle icon="📈">{t("history")}</SectionTitle>
            {hist.length === 0 ? (
              <p className="text-sm text-ink-500">{t("noHistory")}</p>
            ) : (
              <div className="flex h-44 items-end gap-2 overflow-x-auto pb-1">
                {hist.map((l) => {
                  const tot = ledgerTotals(l);
                  return (
                    <div key={l.month} className="flex min-w-10 flex-1 flex-col items-center gap-1">
                      <div className="flex h-32 w-full items-end justify-center gap-0.5">
                        <motion.div className="w-1/2 rounded-t-md bg-emerald-500" initial={{ height: 0 }} animate={{ height: `${(tot.income / max) * 100}%` }} title={`${t("in")} ${money(tot.income, locale)}`} />
                        <motion.div className="w-1/2 rounded-t-md bg-rose-500" initial={{ height: 0 }} animate={{ height: `${(tot.expenses / max) * 100}%` }} title={`${t("out")} ${money(tot.expenses, locale)}`} />
                      </div>
                      <span className={cn("text-[10px] font-bold tabular-nums", tot.net >= 0 ? "text-emerald-700" : "text-rose-700")}>{tot.net >= 0 ? "+" : ""}{tot.net}</span>
                      <span className="text-[10px] capitalize text-ink-500">{monthName(l.month % 12, locale).slice(0, 3)}</span>
                    </div>
                  );
                })}
              </div>
            )}
            <div className="mt-2 flex gap-4 text-xs text-ink-600">
              <span className="flex items-center gap-1"><span className="h-3 w-3 rounded bg-emerald-500" />{t("in")}</span>
              <span className="flex items-center gap-1"><span className="h-3 w-3 rounded bg-rose-500" />{t("out")}</span>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
