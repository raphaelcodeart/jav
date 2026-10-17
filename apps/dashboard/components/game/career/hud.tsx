"use client";

import { AnimatePresence, motion } from "motion/react";
import { cn } from "@/lib/cn";
import { gameDate, heroAge, type CareerState } from "./engine";
import { money, monthName, type CareerT } from "./i18n";
import { BeltBadge, COLOR_GRAD } from "./ui";

// Il banner in alto, sempre visibile (sticky sotto la barra della pagina,
// o in cima a schermo intero): chi sei, la cintura, il tempo di gioco e i
// contatori che decidono la carriera e i combattimenti — tecnica, forza,
// testa, energia, salute, soldi, fama — più XP, salvataggio e avvisi.

export type SaveStatus = "idle" | "saving" | "saved" | "error";

/** La salute del personaggio: 100 se sta bene, meno per ogni settimana di infortunio. */
export const heroHealth = (injury: number) => Math.max(0, 100 - 25 * injury);

function Chip({ icon, label, value, pct, tone, warn }: {
  icon: string; label: string; value: string | number; pct?: number; tone: string; warn?: boolean;
}) {
  return (
    <div className={cn("flex min-w-[5.5rem] shrink-0 flex-col justify-center rounded-xl px-2 py-1 ring-1 sm:min-w-0", warn ? "bg-rose-600/80 ring-rose-200/60" : "bg-black/20 ring-white/15")} title={label}>
      <div className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-white/75">
        <span aria-hidden="true">{icon}</span><span className="truncate">{label}</span>
      </div>
      <div className="truncate font-display text-base leading-tight tabular-nums">{value}</div>
      {pct !== undefined && (
        <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-white/20" aria-hidden="true">
          <motion.div className={cn("h-full rounded-full", tone)} initial={false} animate={{ width: `${Math.max(0, Math.min(100, pct))}%` }} transition={{ type: "spring", stiffness: 120, damping: 20 }} />
        </div>
      )}
    </div>
  );
}

export function Hud({ state, t, locale, alerts, level, saveStatus, onBell }: {
  state: CareerState; t: CareerT; locale: string; alerts: number; level: number | null;
  saveStatus: SaveStatus; onBell: () => void;
}) {
  const h = state.hero;
  const d = gameDate(state.week);
  const club = state.club;
  const cash = club ? club.balance : h.dinheiro;
  const fame = club ? club.reputation : h.reputacao;
  const health = heroHealth(h.injury);

  return (
    <div className={cn("sticky top-[var(--game-top,0px)] z-20 overflow-hidden rounded-2xl bg-gradient-to-br px-3 py-2 text-white shadow-lift ring-1 ring-black/10", COLOR_GRAD[h.color])}>
      <div className="pointer-events-none absolute -right-10 -top-12 h-40 w-40 rounded-full bg-white/20 blur-3xl" aria-hidden="true" />
      <div className="relative flex items-center gap-2.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/20 text-2xl ring-1 ring-white/30" aria-hidden="true">{h.avatar}</div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate font-display text-base leading-tight sm:text-lg">{h.name}</h2>
            <BeltBadge belt={h.belt} t={t} small />
          </div>
          <p className="truncate text-[11px] font-semibold text-white/85">
            <span className="capitalize">{monthName(d.month, locale)}</span> · {t("week", { w: d.weekOfMonth })} · {t("year", { y: d.year })} · {t("age", { n: heroAge(state) })}
          </p>
        </div>
        <div className="hidden items-center gap-1.5 text-[11px] font-bold sm:flex">
          <span className="rounded-full bg-black/25 px-2 py-0.5">⭐ {state.careerXp} {t("xp")}</span>
          {level !== null && <span className="rounded-full bg-accent-400 px-2 py-0.5 text-ink-900">{t("level", { n: level })}</span>}
        </div>
        <AnimatePresence mode="wait">
          {saveStatus !== "idle" && (
            <motion.span key={saveStatus} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className={cn("hidden rounded-full px-2 py-0.5 text-[11px] font-bold md:inline", saveStatus === "error" ? "bg-rose-600" : "bg-white/20")} role="status">
              {saveStatus === "saving" ? t("saving") : saveStatus === "saved" ? t("saved") : `⚠ ${t("saveError")}`}
            </motion.span>
          )}
        </AnimatePresence>
        {saveStatus === "error" && <span className="text-sm md:hidden" role="status" aria-label={t("saveError")}>⚠️</span>}
        <button type="button" onClick={onBell} aria-label={`${t("alerts")}: ${alerts}`}
          className="relative flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-xl bg-white/20 text-xl ring-1 ring-white/30 hover:bg-white/30">
          <motion.span animate={alerts > 0 ? { rotate: [0, -14, 12, -8, 0] } : { rotate: 0 }} transition={{ duration: 0.8, repeat: alerts > 0 ? Infinity : 0, repeatDelay: 3 }} aria-hidden="true">🔔</motion.span>
          {alerts > 0 && (
            <span className="absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-accent-400 px-1 text-[10px] font-black text-ink-900 ring-2 ring-white">
              {alerts > 99 ? "99+" : alerts}
            </span>
          )}
        </button>
      </div>
      {/* i contatori: una riga che scorre sul telefono, una griglia dal tablet in su */}
      <div className="relative -mx-3 mt-2 flex gap-1.5 overflow-x-auto px-3 pb-0.5 [scrollbar-width:none] sm:mx-0 sm:grid sm:grid-cols-7 sm:overflow-visible sm:px-0">
        <Chip icon="🥋" label={t("stat_tecnica")} value={h.tecnica} pct={h.tecnica} tone="bg-white" />
        <Chip icon="💪" label={t("stat_fisico")} value={h.fisico} pct={h.fisico} tone="bg-white" />
        <Chip icon="🧠" label={t("stat_mental")} value={h.mental} pct={h.mental} tone="bg-white" />
        <Chip icon="⚡" label={t("energy")} value={h.energia} pct={h.energia} tone="bg-lime-300" warn={h.energia < 25} />
        <Chip icon={h.injury > 0 ? "🤕" : "❤️"} label={t("health")} value={h.injury > 0 ? t("injuryWeeks", { n: h.injury }) : health} pct={health} tone="bg-rose-300" warn={h.injury > 0} />
        <Chip icon="💶" label={club ? t("clubBalance") : t("money")} value={money(cash, locale)} tone="bg-accent-300" warn={cash < 0} />
        <Chip icon="🌟" label={t("reputation")} value={fame} pct={fame} tone="bg-fuchsia-300" />
      </div>
    </div>
  );
}
