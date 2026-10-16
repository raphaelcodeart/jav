"use client";

import { AnimatePresence, motion } from "motion/react";
import { cn } from "@/lib/cn";
import { gameDate, heroAge, type CareerState } from "./engine";
import { money, monthName, type CareerT } from "./i18n";
import { Bar, BeltBadge, COLOR_GRAD } from "./ui";

// La barra in alto: chi sei, la tua cintura, il tempo di gioco, le risorse e gli avvisi.

export type SaveStatus = "idle" | "saving" | "saved" | "error";

export function Hud({ state, t, locale, alerts, level, saveStatus, onBell }: {
  state: CareerState; t: CareerT; locale: string; alerts: number; level: number | null;
  saveStatus: SaveStatus; onBell: () => void;
}) {
  const h = state.hero;
  const d = gameDate(state.week);
  const club = state.club;
  const cash = club ? club.balance : h.dinheiro;

  return (
    <div className={cn("relative overflow-hidden rounded-[2rem] bg-gradient-to-br p-4 text-white shadow-lift sm:p-5", COLOR_GRAD[h.color])}>
      <div className="pointer-events-none absolute -right-12 -top-16 h-56 w-56 rounded-full bg-white/20 blur-3xl" aria-hidden="true" />
      <div className="pointer-events-none absolute -bottom-20 -left-10 h-48 w-48 rounded-full bg-accent-300/30 blur-3xl" aria-hidden="true" />
      <div className="relative flex items-start gap-3">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-white/20 text-3xl shadow-inner ring-1 ring-white/30 backdrop-blur" aria-hidden="true">
          {h.avatar}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate font-display text-xl leading-tight">{h.name}</h2>
            <BeltBadge belt={h.belt} t={t} small />
          </div>
          <p className="mt-0.5 text-xs font-semibold text-white/85">
            {t("age", { n: heroAge(state) })} · <span className="capitalize">{monthName(d.month, locale)}</span> · {t("week", { w: d.weekOfMonth })} · {t("year", { y: d.year })}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] font-bold">
            <span className="rounded-full bg-black/25 px-2 py-0.5">⭐ {state.careerXp.toLocaleString()} {t("xp")}</span>
            {level !== null && <span className="rounded-full bg-accent-400 px-2 py-0.5 text-ink-900">{t("level", { n: level })}</span>}
            <AnimatePresence mode="wait">
              {saveStatus !== "idle" && (
                <motion.span
                  key={saveStatus}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className={cn("rounded-full px-2 py-0.5", saveStatus === "error" ? "bg-rose-600" : "bg-white/20")}
                  role="status"
                >
                  {saveStatus === "saving" ? t("saving") : saveStatus === "saved" ? t("saved") : `⚠ ${t("saveError")}`}
                </motion.span>
              )}
            </AnimatePresence>
          </div>
        </div>
        <button
          type="button"
          onClick={onBell}
          aria-label={`${t("alerts")}: ${alerts}`}
          className="relative flex h-12 w-12 shrink-0 cursor-pointer items-center justify-center rounded-2xl bg-white/20 text-2xl ring-1 ring-white/30 hover:bg-white/30"
        >
          <motion.span animate={alerts > 0 ? { rotate: [0, -14, 12, -8, 0] } : { rotate: 0 }} transition={{ duration: 0.8, repeat: alerts > 0 ? Infinity : 0, repeatDelay: 3 }} aria-hidden="true">
            🔔
          </motion.span>
          {alerts > 0 && (
            <span className="absolute -right-1.5 -top-1.5 flex h-6 min-w-6 items-center justify-center rounded-full bg-accent-400 px-1.5 text-xs font-black text-ink-900 ring-2 ring-white">
              {alerts > 99 ? "99+" : alerts}
            </span>
          )}
        </button>
      </div>
      <div className="relative mt-4 grid grid-cols-3 gap-3">
        <Bar label={`⚡ ${t("energy")}`} right={h.energia} value={h.energia} tone="bg-gradient-to-r from-lime-300 to-emerald-400" />
        <Bar label={`💶 ${club ? t("clubBalance") : t("money")}`} right={money(cash, locale)} value={Math.max(0, cash)} max={club ? 3000 : 300} tone={cash < 0 ? "bg-rose-400" : "bg-gradient-to-r from-accent-200 to-accent-400"} />
        <Bar label={`🌟 ${t("reputation")}`} right={club ? club.reputation : h.reputacao} value={club ? club.reputation : h.reputacao} tone="bg-gradient-to-r from-sky-300 to-fuchsia-300" />
      </div>
    </div>
  );
}
