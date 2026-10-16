"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import {
  ageGroup, athleteCanRegister, gameDate, heroAge, heroCanRegister, registerAthlete, registerHero,
  registrationOpen, type CompLevel, type Competition,
} from "./engine";
import { money, monthName } from "./i18n";
import { BeltBadge, Card, SectionTitle, type PanelProps } from "./ui";

// Scheda "Calendário & Provas": le gare dell'anno, l'iscrizione propria e
// quella degli atleti del club (con i motivi quando non si può).

const LEVEL_STYLE: Record<CompLevel, string> = {
  REGIONAL: "from-emerald-400 to-teal-600",
  NACIONAL: "from-sky-400 to-indigo-600",
  INTERNACIONAL: "from-fuchsia-500 to-brand-600",
};
const LEVEL_ICON: Record<CompLevel, string> = { REGIONAL: "🏅", NACIONAL: "🇵🇹", INTERNACIONAL: "🌍" };

export function CalendarPanel(props: PanelProps) {
  const { state, t } = props;
  const upcoming = state.calendar.filter((c) => c.week >= state.week);
  return (
    <div className="space-y-3">
      <SectionTitle icon="📅">{t("calTitle")}</SectionTitle>
      <p className="-mt-2 text-sm text-ink-500">{t("ageGroup", { g: t(`ag_${ageGroup(heroAge(state))}`) })}</p>
      {upcoming.length === 0 && <Card><p className="text-ink-500">{t("calEmpty")}</p></Card>}
      {upcoming.map((c) => <CompCard key={c.id} comp={c} {...props} />)}
    </div>
  );
}

function CompCard({ comp: c, state, t, locale, apply }: PanelProps & { comp: Competition }) {
  const [open, setOpen] = useState(false);
  const d = gameDate(c.week);
  const isNow = c.week === state.week;
  const heroReg = state.heroRegs.includes(c.id);
  const heroErr = heroCanRegister(state, c);
  const club = state.club;
  const regs = club?.registrations[c.id] ?? [];
  const regOpen = registrationOpen(state, c);

  return (
    <Card className={cn("overflow-hidden p-0 sm:p-0", isNow && "ring-2 ring-accent-400")}>
      <div className={cn("flex items-center gap-3 bg-gradient-to-r p-4 text-white", LEVEL_STYLE[c.level])}>
        <span className="text-3xl" aria-hidden="true">{LEVEL_ICON[c.level]}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-base leading-tight">{t("compName", { level: t(`level_${c.level}`), city: c.city })}</p>
          <p className="text-xs font-semibold text-white/85">
            <span className="capitalize">{monthName(d.month, locale)}</span> · {t("compWeek", { w: d.weekOfMonth })}
            {isNow && <span className="ml-2 rounded-full bg-accent-400 px-2 py-0.5 text-ink-900">{t("compThisWeek")}</span>}
          </p>
        </div>
        <span className="rounded-full bg-white/20 px-2 py-1 text-xs font-bold">{c.week - state.week === 0 ? "⏰" : `+${c.week - state.week}`}</span>
      </div>
      <div className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2 text-xs text-ink-600">
          <span className="rounded-full bg-ink-100 px-2 py-1 font-semibold">{t("compFee", { fee: money(c.fee, locale) })}</span>
          <span className="flex items-center gap-1">{t("compMinBelt", { belt: "" })}<BeltBadge belt={c.minBelt} t={t} small /></span>
          <span className={cn("rounded-full px-2 py-1 font-semibold", regOpen ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700")}>
            {regOpen ? t("compDeadline", { w: `${gameDate(c.week - 1).weekOfMonth} (${monthName(gameDate(c.week - 1).month, locale)})` }) : t("compClosed")}
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {heroReg ? (
            <span className="inline-flex h-10 items-center rounded-xl bg-emerald-100 px-4 text-sm font-bold text-emerald-800">{t("registered")}</span>
          ) : (
            <Button size="md" disabled={!!heroErr} onClick={() => apply(registerHero(state, c.id))}>
              {heroErr && heroErr !== "already" ? t(`err_${heroErr}`) : t("register")}
            </Button>
          )}
          {club && (
            <Button size="md" variant="secondary" onClick={() => setOpen(!open)} aria-expanded={open}>
              👥 {t("registerAthletes")} {regs.length > 0 && `(${regs.length})`}
            </Button>
          )}
        </div>
        {club && open && (
          <ul className="divide-y divide-ink-100 rounded-2xl bg-ink-50 ring-1 ring-ink-100">
            {club.athletes.length === 0 && <li className="p-3 text-sm text-ink-500">{t("athletesEmpty")}</li>}
            {club.athletes.map((a) => {
              const err = athleteCanRegister(state, c, a);
              const on = regs.includes(a.id);
              return (
                <li key={a.id} className="flex items-center gap-2 p-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-bold text-ink-900">{a.name}</p>
                    <p className="text-[11px] text-ink-500">{t("ageShort", { n: a.age })} · {t(`belt_${a.belt}`)}</p>
                  </div>
                  {on ? (
                    <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-800">{t("registered")}</span>
                  ) : (
                    <Button size="sm" variant={err ? "ghost" : "primary"} disabled={!!err} onClick={() => apply(registerAthlete(state, c.id, a.id))}>
                      {err ? t(`err_${err}`) : `+ ${money(c.fee, locale)}`}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Card>
  );
}
