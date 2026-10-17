"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useEffect, useRef, useState, type JSX } from "react";
import { Button, Spinner } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { Modal } from "@/components/ui/modal";
import {
  LEVEL_ROUNDS, advanceWeek, compThisWeek, computeAlerts, newCareer, openClub, parseCareer, promote, promotionStatus,
  resolveEvent, sanitizeActions, type ActionId, type CareerState, type City, type Competition, type Fight,
  type HeroColor, type Result, type WeekPlan, type WeekReport,
} from "./engine";
import { FightScene } from "./fight-scene";
import { Hud, type SaveStatus } from "./hud";
import { useCareerT, type CareerKey } from "./i18n";
import { EventModal, ReportModal, RestartModal } from "./modals";
import { NewCareer } from "./new-career";
import { CalendarPanel } from "./panel-calendar";
import { AthletesPanel, ClubPanel, MoneyPanel } from "./panel-club";
import { ACTION_ICON, DiaryPanel, ProgressPanel, WeekPlanner, type TeachPlan } from "./panel-me";
import { AlertsPanel, TrophiesPanel, type TabId } from "./panel-misc";
import { CareerTournament } from "./tournament";
import { Burst, type PanelProps, type Pose } from "./ui";

// "Judo Career": carica il salvataggio, fa girare le settimane con il motore
// puro e salva sul server dopo ogni passo (mai più di 1500 XP per salvataggio).
// Il banner con i contatori resta in alto; sotto, su uno schermo largo, il
// piano della settimana a sinistra e le schede a destra, sul telefono tutto
// a schede. Le gare si combattono simulate (il motore, come prima) o passo a
// passo (il server: tournament.tsx).

const API = "/api/proxy/game/career";
const MAX_XP_PER_SAVE = 1500;

interface CareerResponse {
  state: unknown;
  week: number;
  belt: string;
  career_xp: number;
  updated_at: string | null;
  exams_passed: string[];
}

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; state: CareerState | null; exams: string[] };

async function errorDetail(res: Response): Promise<string> {
  try {
    const j = (await res.json()) as { detail?: unknown };
    if (typeof j.detail === "string") return j.detail;
    if (j.detail) return JSON.stringify(j.detail);
  } catch {
    // corpo non JSON: basta lo stato HTTP
  }
  return `HTTP ${res.status}`;
}

async function fetchCareer(): Promise<CareerResponse> {
  const res = await fetch(API, { cache: "no-store" });
  if (!res.ok) throw new Error(await errorDetail(res));
  return (await res.json()) as CareerResponse;
}

const TAB_ICON: Record<TabId, string> = {
  week: "🗓️", progress: "🥋", calendar: "📅", club: "🏯", athletes: "👥", money: "💶", alerts: "🔔", trophies: "🏆", diary: "📓",
};

export function JudoCareer({ playerName, examsPassed, onGoAcademy, onXpChange }: {
  playerName: string; examsPassed: string[]; onGoAcademy: () => void; onXpChange?: () => void;
}): JSX.Element {
  const { t, locale } = useCareerT();
  const toast = useToast();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [game, setGame] = useState<CareerState | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [level, setLevel] = useState<number | null>(null);
  const [tab, setTab] = useState<TabId>("week");
  // la gara di questa settimana: si sceglie come combatterla, poi (passo a passo) il torneo
  const [compMode, setCompMode] = useState<{ comp: Competition; step: boolean } | null>(null);
  const [selected, setSelected] = useState<ActionId[]>([]);
  const [teach, setTeach] = useState<TeachPlan>({ technique: "O-soto-gari", ids: null });
  const [pose, setPose] = useState<Pose>("idle");
  const [fight, setFight] = useState<{ fights: Fight[]; comp: Competition } | null>(null);
  const [report, setReport] = useState<WeekReport | null>(null);
  const [burst, setBurst] = useState(0);
  const [eventHidden, setEventHidden] = useState(false);
  const [restartOpen, setRestartOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const serverXp = useRef<number | null>(null);
  const chain = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    let alive = true;
    fetchCareer()
      .then((r) => {
        if (!alive) return;
        serverXp.current = r.career_xp;
        setLoad({ status: "ready", state: parseCareer(r.state), exams: r.exams_passed ?? [] });
      })
      .catch((e: unknown) => {
        if (alive) setLoad({ status: "error", message: e instanceof Error ? e.message : String(e) });
      });
    return () => { alive = false; };
  }, [reloadKey]);

  const career = game ?? (load.status === "ready" ? load.state : null);
  const exams = Array.from(new Set([...examsPassed, ...(load.status === "ready" ? load.exams : [])]));

  function fireBurst() {
    setBurst((b) => b + 1);
    setTimeout(() => setBurst(0), 1800);
  }

  /** Salva in coda: un salvataggio alla volta, XP limitato al massimo consentito. */
  function persist(next: CareerState) {
    setSaveStatus("saving");
    chain.current = chain.current.then(async () => {
      const base = serverXp.current ?? next.careerXp;
      const xp = Math.min(next.careerXp, base + MAX_XP_PER_SAVE);
      try {
        const res = await fetch(API, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ state: next, career_xp: xp, week: next.week, belt: next.hero.belt }),
        });
        if (!res.ok) throw new Error(await errorDetail(res));
        const body = (await res.json()) as { career_xp?: number; level?: number };
        serverXp.current = typeof body.career_xp === "number" ? body.career_xp : xp;
        if (typeof body.level === "number") setLevel(body.level);
        setSaveStatus("saved");
        onXpChange?.();
      } catch (e) {
        setSaveStatus("error");
        toast({ tone: "error", title: t("saveError"), text: e instanceof Error ? e.message : undefined });
      }
    });
  }

  function commit(next: CareerState) {
    setGame(next);
    persist(next);
  }

  function apply(r: Result) {
    if (r.error) {
      toast({ tone: "error", title: t(`err_${r.error}`) });
      return;
    }
    if (r.state !== career) commit(r.state);
  }

  /* ---------------- schermate di attesa e nuova carriera ---------------- */

  if (load.status === "loading") {
    return (
      <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-ink-500">
        <Spinner className="h-8 w-8 text-brand-500" />
        <p className="font-semibold">{t("loading")}</p>
      </div>
    );
  }
  if (load.status === "error") {
    return (
      <div className="mx-auto max-w-md rounded-3xl bg-white p-6 text-center shadow-soft ring-1 ring-rose-100">
        <p className="text-4xl" aria-hidden="true">😵</p>
        <p className="mt-2 font-bold text-ink-900">{t("loadError")}</p>
        <p className="mt-1 text-xs text-ink-500">{load.message}</p>
        <Button className="mt-4" onClick={() => { setLoad({ status: "loading" }); setReloadKey((k) => k + 1); }}>{t("retry")}</Button>
      </div>
    );
  }
  if (!career) {
    return (
      <MotionConfig reducedMotion="user">
        <NewCareer
          defaultName={playerName}
          t={t}
          busy={busy}
          onStart={(v) => {
            const s = newCareer({ ...v, seed: Math.floor(Math.random() * 2 ** 31) }, serverXp.current ?? 0);
            setTab("week");
            commit(s);
          }}
        />
      </MotionConfig>
    );
  }

  /* ---------------- partita in corso ---------------- */

  const state = career;
  const alerts = computeAlerts(state, exams);
  const chosen = sanitizeActions(state, selected);
  const hasClub = !!state.club;
  const tabs: TabId[] = hasClub
    ? ["week", "progress", "calendar", "club", "athletes", "money", "alerts", "trophies", "diary"]
    : ["week", "progress", "calendar", "money", "alerts", "trophies", "diary"];
  const activeTab: TabId = tabs.includes(tab) ? tab : "week";
  // su uno schermo largo il piano della settimana è sempre a sinistra: a destra le altre schede
  const sideTab: TabId = activeTab === "week" ? "progress" : activeTab;
  const panel: PanelProps = { state, t, locale, examsPassed: exams, apply };
  const event = state.pendingEvent;

  function toggle(a: ActionId) {
    setSelected(chosen.includes(a) ? chosen.filter((x) => x !== a) : [...chosen, a]);
  }

  function advance() {
    if (state.pendingEvent) { setEventHidden(false); return; }
    const comp = chosen.includes("COMPETE") ? compThisWeek(state) : null;
    if (comp) {
      // turni già combattuti passo a passo (per esempio prima di ricaricare la pagina): si riprende quel torneo
      void (async () => {
        await chain.current;
        const r = await fetch(`/api/proxy/game/career/fights/${encodeURIComponent(comp.id)}`, { cache: "no-store" })
          .then((x) => (x.ok ? (x.json() as Promise<{ rounds: unknown[] }>) : null)).catch(() => null);
        setCompMode({ comp, step: !!r && r.rounds.length > 0 });
      })();
      return;
    }
    runWeek();
  }

  function runWeek(compFights?: Fight[]) {
    setCompMode(null);
    const plan: WeekPlan = { actions: chosen, compFights };
    if (chosen.includes("TEACH") && state.club) {
      plan.teach = { technique: teach.technique, athleteIds: teach.ids ?? state.club.athletes.map((a) => a.id) };
    }
    const { state: next, report: rep } = advanceWeek(state, plan);
    setPose(chosen.includes("COMPETE") ? "win" : chosen.includes("TRAIN_TECH") || chosen.includes("TEACH") ? "attack" : chosen.includes("TRAIN_PHYS") ? "grip" : "idle");
    setSelected([]);
    setEventHidden(false);
    // passo a passo i combattimenti li hai già vissuti: niente film, subito il riepilogo
    if (rep.fights.length > 0 && rep.comp && !compFights) setFight({ fights: rep.fights, comp: rep.comp });
    else if (rep.medal || rep.clubResults.some((r) => r.medal)) fireBurst();
    setReport(rep);
    commit(next);
    window.scrollTo?.({ top: 0, behavior: "smooth" });
  }

  function doPromote() {
    const st = promotionStatus(state, exams);
    const next = promote(state, exams);
    if (next === state || !st.next) return;
    commit(next);
    fireBurst();
    toast({ tone: "success", title: t("promotedTitle", { belt: t(`belt_${st.next}`) }) });
  }

  function doOpenClub(v: { name: string; color: HeroColor; city: City }) {
    const r = openClub(state, v);
    apply(r);
    if (!r.error) { fireBurst(); setTab("club"); }
  }

  async function doRestart() {
    setBusy(true);
    try {
      const res = await fetch(API, { method: "DELETE" });
      if (!res.ok && res.status !== 204) throw new Error(await errorDetail(res));
      const fresh = await fetchCareer().catch(() => null);
      if (fresh) serverXp.current = fresh.career_xp;
      setGame(null);
      setReport(null);
      setFight(null);
      setSelected([]);
      setSaveStatus("idle");
      setLoad({ status: "ready", state: null, exams: fresh?.exams_passed ?? (load.status === "ready" ? load.exams : []) });
      setRestartOpen(false);
    } catch (e) {
      toast({ tone: "error", title: t("err_notAllowed"), text: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
    }
  }

  const advanceLabel = event ? `⚡ ${t("advanceBlocked")}` : `${t("advance")} ▶`;
  const plannerProps = {
    ...panel, chosen, onToggle: toggle, teach, setTeach, pose,
    advanceLabel, advanceAccent: !!event, onAdvance: advance, onGoTab: setTab,
  };
  const progressProps = {
    ...panel, onPromote: doPromote, onGoAcademy, onOpenClub: doOpenClub, onRestart: () => setRestartOpen(true),
  };

  return (
    <MotionConfig reducedMotion="user">
      <div className="mx-auto max-w-7xl space-y-3">
        <Hud state={state} t={t} locale={locale} alerts={alerts.length} level={level} saveStatus={saveStatus} onBell={() => setTab("alerts")} />

        {/* schede (sul largo «Settimana» è sempre a sinistra e la sua scheda non serve) */}
        <nav className="-mx-3 overflow-x-auto px-3 [scrollbar-width:none]" aria-label="Judo Career">
          <div className="flex w-max gap-1.5" role="tablist">
            {tabs.map((id) => {
              const on = (id === "week" ? activeTab === "week" : sideTab === id && (activeTab !== "week" || id === "progress"));
              const badge = id === "alerts" ? alerts.length : 0;
              return (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  onClick={() => setTab(id)}
                  className={cn(
                    "relative flex h-10 cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 text-sm font-bold transition",
                    id === "week" && "lg:hidden",
                    on ? "text-white" : "bg-white text-ink-700 ring-1 ring-ink-200 hover:ring-brand-300",
                    // sul telefono «Progressi» è acceso solo quando lo scegli
                    id === "progress" && activeTab === "week" && "max-lg:bg-white max-lg:text-ink-700 max-lg:ring-1 max-lg:ring-ink-200",
                  )}
                >
                  {on && (
                    <motion.span layoutId="career-tab" className={cn("absolute inset-0 rounded-full bg-gradient-to-r from-brand-500 to-brand-700 shadow-brand", id === "progress" && activeTab === "week" && "max-lg:hidden")}
                      transition={{ type: "spring", stiffness: 400, damping: 32 }} />
                  )}
                  <span className="relative" aria-hidden="true">{TAB_ICON[id]}</span>
                  <span className="relative">{t(`tab_${id}` as CareerKey)}</span>
                  {badge > 0 && <span className="relative rounded-full bg-accent-400 px-1.5 text-[11px] font-black text-ink-900">{badge}</span>}
                </button>
              );
            })}
          </div>
        </nav>

        <div className="grid gap-4 lg:grid-cols-12 lg:items-start">
          <div className={cn("lg:col-span-7", activeTab !== "week" && "hidden lg:block")}>
            <WeekPlanner {...plannerProps} />
          </div>
          <div className={cn("lg:col-span-5", activeTab === "week" && "hidden lg:block")}>
            <AnimatePresence mode="wait">
              <motion.div key={sideTab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }} role="tabpanel">
                {sideTab === "progress" && <ProgressPanel {...progressProps} />}
                {sideTab === "calendar" && <CalendarPanel {...panel} />}
                {sideTab === "club" && <ClubPanel {...panel} />}
                {sideTab === "athletes" && <AthletesPanel {...panel} />}
                {sideTab === "money" && <MoneyPanel {...panel} />}
                {sideTab === "alerts" && <AlertsPanel {...panel} alerts={alerts} onGoTab={setTab} onGoAcademy={onGoAcademy} />}
                {sideTab === "trophies" && <TrophiesPanel {...panel} />}
                {sideTab === "diary" && <DiaryPanel {...panel} />}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>

        {/* sul telefono e sul tablet: il grande pulsante della settimana resta in basso */}
        <div className="pointer-events-none sticky bottom-3 z-30 flex justify-center lg:hidden">
          <div className="pointer-events-auto flex w-full max-w-xl items-center gap-2 rounded-3xl bg-white/85 p-2 shadow-lift ring-1 ring-ink-100 backdrop-blur-xl">
            <div className="flex shrink-0 gap-1 pl-1" aria-hidden="true">
              {[0, 1].map((i) => (
                <span key={i} className={cn("flex h-10 w-10 items-center justify-center rounded-2xl text-lg", chosen[i] ? "bg-brand-100" : "bg-ink-100 text-ink-300")}>
                  {chosen[i] ? ACTION_ICON[chosen[i]!] : "·"}
                </span>
              ))}
            </div>
            <Button size="xl" className="flex-1" variant={event ? "accent" : "primary"} onClick={advance}>{advanceLabel}</Button>
          </div>
        </div>
      </div>

      {fight && (
        <FightScene
          fights={fight.fights}
          comp={fight.comp}
          heroName={state.hero.name}
          heroBelt={state.hero.belt}
          t={t}
          onDone={() => {
            setFight(null);
            if (report?.medal || report?.clubResults.some((r) => r.medal)) fireBurst();
          }}
        />
      )}
      {report && !fight && <ReportModal report={report} t={t} locale={locale} onClose={() => setReport(null)} />}
      {event && (
        <EventModal
          event={event}
          open={!report && !fight && !eventHidden}
          t={t}
          locale={locale}
          onClose={() => setEventHidden(true)}
          onResolve={(accept) => commit(resolveEvent(state, accept))}
        />
      )}
      {compMode && !compMode.step && (
        <Modal open onClose={() => setCompMode(null)} title={`🏆 ${t("modeTitle")}`} size="md"
          subtitle={t("modeText", { name: t("compName", { level: t(`level_${compMode.comp.level}`), city: compMode.comp.city }), n: LEVEL_ROUNDS[compMode.comp.level] })}>
          <div className="grid gap-3 sm:grid-cols-2">
            <button type="button" onClick={() => runWeek()}
              className="flex cursor-pointer flex-col gap-1 rounded-2xl bg-gradient-to-br from-sky-500 to-indigo-700 p-4 text-left text-white shadow-soft transition hover:-translate-y-0.5 hover:shadow-lift">
              <span className="font-display text-lg">{t("modeSim")}</span>
              <span className="text-sm text-white/85">{t("modeSimText")}</span>
            </button>
            <button type="button" onClick={() => setCompMode({ ...compMode, step: true })}
              className="flex cursor-pointer flex-col gap-1 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 p-4 text-left text-white shadow-soft transition hover:-translate-y-0.5 hover:shadow-lift">
              <span className="font-display text-lg">{t("modeStep")}</span>
              <span className="text-sm text-white/85">{t("modeStepText")}</span>
            </button>
          </div>
        </Modal>
      )}
      {compMode?.step && (
        <CareerTournament comp={compMode.comp} t={t} onDone={(fights) => runWeek(fights)} onSimulate={() => runWeek()} onCancel={() => setCompMode(null)} />
      )}
      <RestartModal open={restartOpen} busy={busy} t={t} onCancel={() => setRestartOpen(false)} onConfirm={doRestart} />
      <AnimatePresence>{burst > 0 && <motion.div key={burst} exit={{ opacity: 0 }}><Burst big /></motion.div>}</AnimatePresence>
    </MotionConfig>
  );
}
