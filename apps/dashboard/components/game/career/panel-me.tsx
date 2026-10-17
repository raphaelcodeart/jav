"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import {
  ACTION_ENERGY, CLUB_START_BALANCE, COACH_COURSE_COST, COACH_MIN_AGE, heroAge, COACH_COURSE_SESSIONS, MAX_ACTIONS,
  REF_COURSE_COST, REF_COURSE_SESSIONS, TECHNIQUES, actionAvailable, beltRank, enrollCoachCourse,
  enrollRefereeCourse, gameDate, promotionStatus, type ActionId, type City, type HeroColor,
} from "./engine";
import { DojoScene } from "./dojo-scene";
import { money, monthName } from "./i18n";
import type { TabId } from "./panel-misc";
import { CityPicker, ColorPicker } from "./new-career";
import { Bar, BeltBadge, Card, SectionTitle, logText, type PanelProps, type Pose } from "./ui";

// Il piano della settimana (il dojo, la prossima gara, le azioni, il grande
// bottone «Avanza») e la scheda «Progressi» (statistiche, prossima cintura,
// corsi di arbitro e allenatore, apertura del club), più il diario.

export const ACTION_ICON: Record<ActionId, string> = {
  TRAIN_TECH: "🥋", TRAIN_PHYS: "🏋️", REST: "😴", STUDY: "📚", COMPETE: "🏆",
  REFEREE: "🧑‍⚖️", REF_COURSE: "🎓", COACH_COURSE: "📋", TEACH: "👨‍🏫",
};

export interface TeachPlan { technique: string; ids: number[] | null }

export function WeekPlanner(props: PanelProps & {
  chosen: ActionId[];
  onToggle: (a: ActionId) => void;
  teach: TeachPlan;
  setTeach: (t: TeachPlan) => void;
  pose: Pose;
  advanceLabel: string;
  advanceAccent: boolean;
  onAdvance: () => void;
  onGoTab: (tab: TabId) => void;
}) {
  const { state, t, locale, chosen, onToggle, teach, setTeach } = props;
  const h = state.hero;
  const list: ActionId[] = ["TRAIN_TECH", "TRAIN_PHYS", "REST", "STUDY"];
  (["COMPETE", "TEACH", "REFEREE", "REF_COURSE", "COACH_COURSE"] as const).forEach((a) => {
    if (actionAvailable(state, a)) list.unshift(a);
  });
  const spent = chosen.reduce((s, a) => s + Math.max(0, ACTION_ENERGY[a]), 0);
  const left = h.energia - spent;
  const d = gameDate(state.week);
  const next = state.calendar.find((c) => c.week >= state.week && (state.heroRegs.includes(c.id) || c.week - state.week <= 4));

  return (
    <Card className="space-y-3 p-3 sm:p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-display text-lg text-ink-900">
          🗓️ {t("plannerTitle")} <span className="text-sm font-semibold capitalize text-ink-500">· {monthName(d.month, locale)}, {t("week", { w: d.weekOfMonth })}</span>
        </h3>
        <span className="shrink-0 rounded-full bg-ink-900 px-2.5 py-1 text-xs font-bold text-white">{t("actionsChosen", { n: chosen.length, max: MAX_ACTIONS })}</span>
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
        <div className="space-y-2">
          <DojoScene state={state} pose={props.pose} t={t} compact />
          {next && (
            <button type="button" onClick={() => props.onGoTab("calendar")}
              className={cn("flex w-full cursor-pointer items-center gap-2 rounded-2xl px-3 py-2 text-left text-xs font-semibold ring-1 transition hover:ring-brand-300",
                next.week === state.week ? "bg-accent-100 text-ink-900 ring-accent-300" : "bg-ink-50 text-ink-700 ring-ink-100")}>
              <span className="text-lg" aria-hidden="true">🏆</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-bold">{t("nextComp", { name: t("compName", { level: t(`level_${next.level}`), city: next.city }) })}</span>
                <span className="text-ink-500">{next.week === state.week ? t("compThisWeek") : t("nextCompWhen", { n: next.week - state.week })}
                  {state.heroRegs.includes(next.id) ? ` · ${t("registered")}` : ""}</span>
              </span>
              <span aria-hidden="true">›</span>
            </button>
          )}
        </div>

        <div>
          {/* azioni */}
          <p className="mb-2 text-xs font-semibold text-ink-500">{t("chooseActions")}</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {list.map((a) => {
              const on = chosen.includes(a);
              const cost = ACTION_ENERGY[a];
              const ok = actionAvailable(state, a);
              const tooTired = !on && cost > 0 && cost > left;
              const full = !on && chosen.length >= MAX_ACTIONS;
              const locked = a === "COMPETE" && on;
              return (
                <motion.button
                  key={a}
                  type="button"
                  whileTap={{ scale: 0.95 }}
                  disabled={!ok || tooTired || full || locked}
                  onClick={() => onToggle(a)}
                  aria-pressed={on}
                  className={cn(
                    "relative flex min-h-[4.75rem] cursor-pointer flex-col items-start gap-0.5 rounded-2xl p-2.5 text-left ring-2 transition disabled:cursor-not-allowed",
                    on ? "bg-gradient-to-br from-brand-500 to-brand-700 text-white ring-brand-300 shadow-brand" : "bg-ink-50 text-ink-900 ring-transparent hover:ring-brand-200",
                    (!ok || tooTired || full) && !on && "opacity-45",
                  )}
                >
                  <span className="text-xl" aria-hidden="true">{ACTION_ICON[a]}</span>
                  <span className="text-sm font-bold leading-tight">{t(`act_${a}`)}</span>
                  <span className={cn("text-[11px]", on ? "text-white/80" : "text-ink-500")}>{tooTired ? t("noEnergy") : t(`actd_${a}`)}</span>
                  <span className={cn("absolute right-2 top-2 rounded-full px-1.5 py-0.5 text-[10px] font-black", cost < 0 ? "bg-emerald-100 text-emerald-800" : on ? "bg-white/20" : "bg-white text-ink-700")}>
                    {cost < 0 ? t("energyGain", { n: -cost }) : t("energyCost", { n: `-${cost}` })}
                  </span>
                  {on && <span className="absolute bottom-2 right-2 text-lg" aria-hidden="true">✓</span>}
                </motion.button>
              );
            })}
          </div>

          {chosen.includes("TEACH") && state.club && (
            <div className="mt-4 rounded-2xl bg-accent-50 p-3 ring-1 ring-accent-200">
              <p className="text-sm font-bold text-ink-900">{t("teachWhat")}</p>
              <p className="text-xs text-ink-600">{t("teachHint")}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {TECHNIQUES.map((tech) => (
                  <button key={tech} type="button" onClick={() => setTeach({ ...teach, technique: tech })} aria-pressed={teach.technique === tech}
                    className={cn("h-9 cursor-pointer rounded-full px-3 text-xs font-bold ring-1 transition", teach.technique === tech ? "bg-ink-900 text-white ring-ink-900" : "bg-white text-ink-700 ring-ink-200")}>
                    {tech}
                  </button>
                ))}
              </div>
              <p className="mt-3 text-sm font-bold text-ink-900">{t("teachWho")}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <button type="button" onClick={() => setTeach({ ...teach, ids: null })} aria-pressed={teach.ids === null}
                  className={cn("h-9 cursor-pointer rounded-full px-3 text-xs font-bold ring-1", teach.ids === null ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-ink-700 ring-ink-200")}>
                  {t("teachAll")}
                </button>
                {state.club.athletes.map((a) => {
                  const on = teach.ids === null || teach.ids.includes(a.id);
                  return (
                    <button key={a.id} type="button" disabled={a.lesao > 0}
                      onClick={() => {
                        const cur = teach.ids ?? state.club!.athletes.map((x) => x.id);
                        setTeach({ ...teach, ids: on ? cur.filter((x) => x !== a.id) : [...cur, a.id] });
                      }}
                      aria-pressed={on}
                      className={cn("h-9 cursor-pointer rounded-full px-3 text-xs font-bold ring-1 disabled:opacity-40", on ? "bg-brand-100 text-brand-800 ring-brand-300" : "bg-white text-ink-500 ring-ink-200")}>
                      {a.name.split(" ")[0]}{a.techniques.includes(teach.technique) ? " ✓" : ""}{a.lesao > 0 ? " 🤕" : ""}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      <Button size="xl" className="hidden w-full lg:flex" variant={props.advanceAccent ? "accent" : "primary"} onClick={props.onAdvance}>
        {props.advanceLabel}
      </Button>
    </Card>
  );
}

export function ProgressPanel(props: PanelProps & {
  onPromote: () => void;
  onGoAcademy: () => void;
  onOpenClub: (v: { name: string; color: HeroColor; city: City }) => void;
  onRestart: () => void;
}) {
  const { state, t, locale, examsPassed, apply } = props;
  const h = state.hero;
  const ps = promotionStatus(state, examsPassed);
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-1 2xl:grid-cols-2">
        <Card>
          <SectionTitle icon="📊">{h.name}</SectionTitle>
          <div className="space-y-3 text-ink-800">
            <Bar label={t("stat_tecnica")} right={h.tecnica} value={h.tecnica} tone="bg-gradient-to-r from-brand-400 to-brand-600" />
            <Bar label={t("stat_fisico")} right={h.fisico} value={h.fisico} tone="bg-gradient-to-r from-emerald-400 to-green-600" />
            <Bar label={t("stat_mental")} right={h.mental} value={h.mental} tone="bg-gradient-to-r from-sky-400 to-indigo-600" />
          </div>
          {h.injury > 0 && <p className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-700">🤕 {t("al_HERO_INJURED", { n: h.injury })}</p>}
          <p className="mt-3 text-xs text-ink-500">{t("statsHint")}</p>
        </Card>

        {/* prossima cintura */}
        <Card className="relative overflow-hidden">
          <SectionTitle icon="🎌">{t("beltCard")}</SectionTitle>
          {!ps.next || !ps.req ? (
            <p className="text-lg font-bold text-ink-900">{t("beltMax")}</p>
          ) : (
            <>
              <div className="mb-3 flex items-center gap-2">
                <BeltBadge belt={h.belt} t={t} small /> <span aria-hidden="true">→</span> <BeltBadge belt={ps.next} t={t} />
              </div>
              <ul className="space-y-1.5 text-sm">
                {([
                  ["req_weeks", h.weeksAtBelt, ps.req.weeks],
                  ["req_tec", h.tecnica, ps.req.tec],
                  ["req_fis", h.fisico, ps.req.fis],
                  ["req_study", h.study, ps.req.study],
                  ...(ps.req.age > 0 ? [["req_age", heroAge(state), ps.req.age] as const] : []),
                ] as const).map(([k, a, b]) => (
                  <li key={k} className={cn("flex items-center gap-2", a >= b ? "text-emerald-700" : "text-ink-600")}>
                    <span aria-hidden="true">{a >= b ? "✅" : "⬜"}</span>{t(k, { a: Math.min(a, b), b })}
                  </li>
                ))}
                <li className={cn("flex items-center gap-2 font-semibold", ps.examOk ? "text-emerald-700" : "text-amber-700")}>
                  <span aria-hidden="true">{ps.examOk ? "✅" : "📝"}</span>{t("req_exam")}: {ps.examOk ? t("examOk") : t("examMissing")}
                </li>
              </ul>
              <div className="mt-4 flex flex-col gap-2">
                {ps.ready ? (
                  <Button variant="accent" size="lg" onClick={props.onPromote}>{t("promote")} 🎉</Button>
                ) : null}
                {!ps.examOk && (
                  <Button variant={ps.statsOk ? "primary" : "secondary"} onClick={props.onGoAcademy}>🎓 {t("goAcademy")}</Button>
                )}
              </div>
            </>
          )}
        </Card>
      </div>
      {/* percorsi: arbitro e allenatore */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-1 2xl:grid-cols-2">
        <Card>
          <SectionTitle icon="🧑‍⚖️">{t("refTitle")}</SectionTitle>
          <p className="text-sm text-ink-600">{t("refText", { cost: money(REF_COURSE_COST, locale) })}</p>
          <div className="mt-3">
            {state.referee.status === "DONE" ? (
              <p className="font-bold text-emerald-700">{t("refDone")}</p>
            ) : state.referee.status === "ENROLLED" ? (
              <Bar label={t("refProgress", { n: state.referee.sessions, total: REF_COURSE_SESSIONS })} value={state.referee.sessions} max={REF_COURSE_SESSIONS} tone="bg-sky-500" />
            ) : beltRank(h.belt) < beltRank("BROWN") ? (
              <p className="text-sm font-semibold text-ink-400">🔒 {t("refLocked")}</p>
            ) : (
              <Button variant="secondary" onClick={() => apply(enrollRefereeCourse(state))}>{t("refEnroll")}</Button>
            )}
          </div>
        </Card>
        <Card>
          <SectionTitle icon="📋">{t("coachTitle")}</SectionTitle>
          <p className="text-sm text-ink-600">{t("coachText", { cost: money(COACH_COURSE_COST, locale) })}</p>
          <div className="mt-3">
            {state.coachCourse.status === "DONE" ? (
              <p className="font-bold text-emerald-700">{t("coachDone")}</p>
            ) : state.coachCourse.status === "ENROLLED" ? (
              <Bar label={t("coachProgress", { n: state.coachCourse.sessions, total: COACH_COURSE_SESSIONS })} value={state.coachCourse.sessions} max={COACH_COURSE_SESSIONS} tone="bg-violet-500" />
            ) : h.belt !== "BLACK" || heroAge(state) < COACH_MIN_AGE ? (
              <p className="text-sm font-semibold text-ink-400">🔒 {t("coachLocked")}</p>
            ) : (
              <Button variant="secondary" onClick={() => apply(enrollCoachCourse(state))}>{t("coachEnroll")}</Button>
            )}
          </div>
        </Card>
      </div>

      {state.phase === "COACH" && !state.club && <OpenClubCard {...props} />}

      <div className="flex justify-center pt-2">
        <Button variant="ghost" size="sm" onClick={props.onRestart}>↺ {t("restart")}</Button>
      </div>
    </div>
  );
}

function OpenClubCard({ state, t, locale, onOpenClub }: PanelProps & { onOpenClub: (v: { name: string; color: HeroColor; city: City }) => void }) {
  const [name, setName] = useState(`Judo Clube ${state.hero.name.split(" ")[0] ?? ""}`.trim());
  const [color, setColor] = useState<HeroColor>(state.hero.color);
  const [city, setCity] = useState<City>(state.hero.city);
  return (
    <Card className="bg-gradient-to-br from-accent-50 to-white ring-accent-200">
      <SectionTitle icon="🏯">{t("openClubTitle")}</SectionTitle>
      <p className="text-sm text-ink-600">{t("openClubText", { money: money(CLUB_START_BALANCE, locale) })}</p>
      <form className="mt-4 space-y-4" onSubmit={(e) => { e.preventDefault(); onOpenClub({ name, color, city }); }}>
        <label className="block">
          <span className="mb-2 block text-sm font-bold text-ink-800">{t("clubName")}</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={32} required
            className="h-12 w-full rounded-xl border border-ink-200 bg-white px-4 font-semibold outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-200" />
        </label>
        <ColorPicker value={color} onChange={setColor} label={t("newColor")} />
        <CityPicker value={city} onChange={setCity} label={t("clubCity")} />
        <Button type="submit" variant="accent" size="lg" className="w-full" disabled={!name.trim()}>{t("openClub")} 🏯</Button>
      </form>
    </Card>
  );
}

export function DiaryPanel({ state, t }: PanelProps) {
  return (
    <Card>
      <SectionTitle icon="📓">{t("recentLog")}</SectionTitle>
      {state.log.length === 0 ? <p className="text-sm text-ink-500">—</p> : (
        <ul className="space-y-1.5 text-sm text-ink-700">
          {state.log.slice(0, 40).map((l, i) => (
            <li key={i} className="flex gap-2">
              <span className="shrink-0 rounded-md bg-ink-100 px-1.5 text-[11px] font-bold leading-5 text-ink-500">{l.week}</span>
              <span>{logText(t, l)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
