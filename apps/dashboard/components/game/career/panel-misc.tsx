"use client";

import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { MEDICAL_COST, bookMedical, gameDate, type GameAlert, type Medal, type MedalKind } from "./engine";
import { money, monthName } from "./i18n";
import { Card, MEDAL_EMOJI, SectionTitle, type PanelProps } from "./ui";

// Avvisi (in evidenza, con il rimedio a portata di dito) e bacheca dei trofei.

export type TabId = "week" | "progress" | "calendar" | "club" | "athletes" | "money" | "alerts" | "trophies" | "diary";

const SEV: Record<GameAlert["severity"], string> = {
  high: "bg-rose-50 ring-rose-300 text-rose-900",
  medium: "bg-amber-50 ring-amber-300 text-amber-900",
  low: "bg-sky-50 ring-sky-200 text-sky-900",
};
const SEV_ICON: Record<GameAlert["severity"], string> = { high: "🚨", medium: "⚠️", low: "ℹ️" };

export function AlertsPanel({ state, t, locale, apply, alerts, onGoTab, onGoAcademy }: PanelProps & {
  alerts: GameAlert[]; onGoTab: (t: TabId) => void; onGoAcademy: () => void;
}) {
  return (
    <div className="space-y-3">
      <SectionTitle icon="🔔">{t("alertsTitle")} ({alerts.length})</SectionTitle>
      {alerts.length === 0 && (
        <Card><p className="text-center text-lg font-bold text-emerald-700">{t("alertsEmpty")}</p></Card>
      )}
      {alerts.map((a, i) => {
        const vars = { ...a.vars };
        if (typeof vars.belt === "string") vars.belt = t(`belt_${vars.belt}` as Parameters<typeof t>[0]);
        if (typeof vars.level === "string") vars.level = t(`level_${vars.level}` as Parameters<typeof t>[0]);
        if (a.kind === "NEGATIVE_BALANCE") vars.n = money(Number(vars.n), locale);
        return (
          <motion.div key={a.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }}
            className={cn("flex flex-wrap items-center gap-3 rounded-2xl p-3 ring-2", SEV[a.severity])}>
            <span className="text-2xl" aria-hidden="true">{SEV_ICON[a.severity]}</span>
            <p className="min-w-0 flex-1 text-sm font-semibold">{t(`al_${a.kind}`, vars)}</p>
            {(a.kind === "MEDICAL_EXPIRED" || a.kind === "MEDICAL_SOON") && a.athleteId !== undefined && (
              <Button size="sm" onClick={() => apply(bookMedical(state, a.athleteId!))}>🩺 {money(MEDICAL_COST, locale)}</Button>
            )}
            {a.kind === "UNPAID" && <Button size="sm" variant="secondary" onClick={() => onGoTab("club")}>📨</Button>}
            {(a.kind === "LOW_MOOD" || a.kind === "INJURY") && <Button size="sm" variant="secondary" onClick={() => onGoTab("athletes")}>👥</Button>}
            {a.kind === "REG_CLOSING" && <Button size="sm" variant="secondary" onClick={() => onGoTab("calendar")}>📅</Button>}
            {(a.kind === "NEGATIVE_BALANCE" || a.kind === "EQUIPMENT_BROKEN") && <Button size="sm" variant="secondary" onClick={() => onGoTab(a.kind === "NEGATIVE_BALANCE" ? "money" : "club")}>👉</Button>}
            {a.kind === "EXAM_NEEDED" && <Button size="sm" onClick={onGoAcademy}>🎓 {t("goAcademy")}</Button>}
          </motion.div>
        );
      })}
    </div>
  );
}

const ORDER: MedalKind[] = ["GOLD", "SILVER", "BRONZE"];

function Shelf({ medals, t, locale }: { medals: Medal[]; t: PanelProps["t"]; locale: string }) {
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
      {medals.map((m, i) => {
        const d = gameDate(m.week);
        return (
          <motion.div key={m.id} initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: Math.min(i, 12) * 0.03, type: "spring" }}
            className="flex flex-col items-center rounded-2xl bg-gradient-to-b from-white to-ink-50 p-2 text-center shadow-soft ring-1 ring-ink-100">
            <motion.span className="text-4xl drop-shadow" whileHover={{ rotate: [0, -10, 10, 0] }} aria-label={t(`medal_${m.kind}`)}>{MEDAL_EMOJI[m.kind]}</motion.span>
            <span className="mt-1 line-clamp-1 text-[11px] font-bold text-ink-800">{m.owner.split(" ")[0]}</span>
            <span className="text-[10px] text-ink-500">{t(`level_${m.level}`)} · {m.city}</span>
            <span className="text-[10px] capitalize text-ink-400">{monthName(d.month, locale).slice(0, 3)} {t("year", { y: d.year })}</span>
          </motion.div>
        );
      })}
    </div>
  );
}

export function TrophiesPanel({ state, t, locale }: PanelProps) {
  const sorted = [...state.medals].sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind) || b.week - a.week);
  const mine = sorted.filter((m) => !m.byClub);
  const club = sorted.filter((m) => m.byClub);
  const count = (k: MedalKind) => state.medals.filter((m) => m.kind === k).length;
  return (
    <div className="space-y-4">
      <div className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-[#3b2410] via-[#5a3a1a] to-[#2a1708] p-5 text-white shadow-lift">
        <div className="pointer-events-none absolute left-1/2 top-0 h-40 w-72 -translate-x-1/2 rounded-full bg-accent-300/30 blur-3xl" aria-hidden="true" />
        <h3 className="relative font-display text-xl">🏆 {t("trophiesTitle")}</h3>
        <div className="relative mt-4 grid grid-cols-3 gap-3">
          {ORDER.map((k) => (
            <div key={k} className="rounded-2xl bg-white/10 p-3 text-center ring-1 ring-white/15">
              <p className="text-3xl" aria-hidden="true">{MEDAL_EMOJI[k]}</p>
              <p className="font-display text-2xl tabular-nums">{count(k)}</p>
              <p className="text-[11px] text-white/70">{t(`medal_${k}`)}</p>
            </div>
          ))}
        </div>
      </div>
      {state.medals.length === 0 && <Card><p className="text-center text-ink-500">{t("trophiesEmpty")}</p></Card>}
      {mine.length > 0 && <Card><SectionTitle icon="🥋">{t("mine")}</SectionTitle><Shelf medals={mine} t={t} locale={locale} /></Card>}
      {club.length > 0 && <Card><SectionTitle icon="🏯">{t("clubMedals")}</SectionTitle><Shelf medals={club} t={t} locale={locale} /></Card>}
    </div>
  );
}
