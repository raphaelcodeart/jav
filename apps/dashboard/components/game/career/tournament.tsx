"use client";

import { MotionConfig, motion } from "motion/react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Button, Spinner } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { FightArena } from "@/components/game/fight/fight-arena";
import { gameApi, postJson, type FightView } from "@/components/game/fight/types";
import { useGameText } from "@/components/game/i18n";
import { CITIES, LEVEL_ROUNDS, type City, type Competition, type Fight, type FightEvent } from "./engine";
import type { CareerT } from "./i18n";
import { BELT_HEX, MEDAL_EMOJI } from "./ui";

// La gara della settimana combattuta passo a passo: un turno alla volta,
// ognuno deciso dal server (fights.py::start_career_fight). Un turno perso
// chiude la gara; un turno già combattuto non si rifà (si riprende quello
// in corso). Alla fine i turni diventano i Fight del motore della
// carriera, che conta vittorie, medaglia, XP e premi come sempre.

function roundName(round: number, rounds: number, t: CareerT): string {
  const left = rounds - round;
  if (left === 0) return t("round_final");
  if (left === 1) return t("round_semi");
  if (left === 2) return t("round_quarter");
  return t("fightRound", { n: round });
}

function toEngineFight(v: FightView, rounds: number, comp: Competition): Fight {
  const city = (CITIES as readonly string[]).includes(v.opp.club ?? "") ? (v.opp.club as City) : comp.city;
  return {
    round: v.context?.round ?? 1, rounds,
    opponent: { name: v.opp.name, city, belt: v.opp.belt },
    events: v.timeline as FightEvent[],
    won: !!v.result?.won,
  };
}

export function CareerTournament({ comp, t, onDone, onSimulate, onCancel }: {
  comp: Competition; t: CareerT; onDone: (fights: Fight[]) => void; onSimulate: () => void; onCancel: () => void;
}) {
  const { lang } = useGameText();
  const rounds = LEVEL_ROUNDS[comp.level];
  const [loaded, setLoaded] = useState<FightView[] | null>(null);
  const [current, setCurrent] = useState<FightView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    gameApi<{ rounds: FightView[] }>(`/api/proxy/game/career/fights/${encodeURIComponent(comp.id)}`)
      .then((r) => { if (alive) setLoaded(r.rounds); })
      .catch((e: unknown) => { if (alive) { setLoaded([]); setError(e instanceof Error ? e.message : String(e)); } });
    return () => { alive = false; };
  }, [comp.id]);

  const all = loaded ?? [];
  const done = all.filter((f) => f.status === "FINISHED").sort((a, b) => (a.context?.round ?? 0) - (b.context?.round ?? 0));
  const active = all.find((f) => f.status === "ACTIVE") ?? null;
  const lost = done.some((f) => !f.result?.won);
  const over = lost || done.length >= rounds;
  const wins = done.filter((f) => f.result?.won).length;
  const nextRound = done.length + 1;
  const medal = wins >= rounds ? "GOLD" : wins === rounds - 1 ? "SILVER" : wins === rounds - 2 ? "BRONZE" : null;
  const compName = t("compName", { level: t(`level_${comp.level}`), city: comp.city });

  async function fight() {
    if (active) { setCurrent(active); return; }
    setBusy(true);
    setError(null);
    try {
      const v = await gameApi<FightView>(`/api/proxy/game/career/fights?lang=${lang}`, postJson({ comp_id: comp.id, round: nextRound }));
      setCurrent(v);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function closed(v: FightView) {
    setCurrent(null);
    setLoaded([...all.filter((f) => f.id !== v.id), v]);
  }

  if (typeof document === "undefined") return null;
  return createPortal(
    <MotionConfig reducedMotion="user">
      <div className="fixed inset-0 z-[115] flex items-center justify-center overflow-y-auto bg-gradient-to-b from-ink-950 via-[#1b1030] to-ink-900 p-3 text-white" role="dialog" aria-modal="true" aria-label={compName}>
        <div className="pointer-events-none absolute -top-20 left-1/2 h-72 w-72 -translate-x-1/2 rounded-full bg-accent-400/20 blur-3xl" aria-hidden="true" />
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="relative w-full max-w-lg rounded-[2rem] bg-white/10 p-5 shadow-lift ring-1 ring-white/15 backdrop-blur">
          {loaded !== null && all.length === 0 && (
            // prima del primo incontro si può ancora tornare indietro (e scegliere il simulato)
            <button type="button" onClick={onCancel} aria-label={t("cancel")}
              className="absolute right-4 top-4 flex h-9 w-9 cursor-pointer items-center justify-center rounded-full bg-white/10 text-white/80 hover:bg-white/20">✕</button>
          )}
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-accent-300">{t("modeTitle")}</p>
          <h2 className="font-display text-2xl">{compName}</h2>

          {/* il tabellone dei turni */}
          <ol className="mt-4 space-y-2">
            {Array.from({ length: rounds }, (_, i) => {
              const r = i + 1;
              const f = done.find((x) => x.context?.round === r) ?? (active?.context?.round === r ? active : undefined);
              const state = f?.status === "FINISHED" ? (f.result?.won ? "won" : "lost") : f ? "live" : r === nextRound && !over ? "next" : "todo";
              return (
                <li key={r} className={cn("flex items-center gap-3 rounded-2xl px-3 py-2 ring-1",
                  state === "won" ? "bg-emerald-500/20 ring-emerald-300/40" : state === "lost" ? "bg-rose-500/20 ring-rose-300/40" : state === "live" || state === "next" ? "bg-white/15 ring-accent-300/60" : "bg-white/5 ring-white/10 opacity-60")}>
                  <span className="w-6 text-center font-display text-lg">{state === "won" ? "✅" : state === "lost" ? "❌" : state === "live" ? "⏳" : r}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-bold">{roundName(r, rounds, t)}</span>
                    {f && (
                      <span className="flex items-center gap-1.5 truncate text-[11px] text-white/75">
                        <span className="h-2 w-4 rounded-full" style={{ background: BELT_HEX[f.opp.belt] }} aria-hidden="true" />
                        {t("tourVs", { name: f.opp.name })}{f.opp.club ? ` · ${f.opp.club}` : ""}
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
          </ol>

          <div className="mt-5">
            {loaded === null ? (
              <div className="flex justify-center py-3"><Spinner className="h-7 w-7 text-accent-300" /></div>
            ) : over ? (
              <div className="text-center">
                <p className="font-display text-2xl">{medal ? `${MEDAL_EMOJI[medal]} ${medal === "GOLD" ? t("tourChampion") : t("medalWon", { medal: t(`medal_${medal}`) })}` : t("tourOut", { n: wins })}</p>
                <Button size="xl" variant="accent" className="mt-4 w-full" onClick={() => onDone(done.map((f) => toEngineFight(f, rounds, comp)))}>
                  {t("tourDone")} ➜
                </Button>
              </div>
            ) : (
              <>
                <p className="mb-2 text-center text-sm text-white/80">{t("tourRound", { n: active?.context?.round ?? nextRound, total: rounds })}</p>
                <Button size="xl" variant="accent" className="w-full" loading={busy} onClick={() => void fight()}>
                  🥋 {active ? t("tourResume") : t("tourFight")}
                </Button>
              </>
            )}
            {error && (
              <div className="mt-3 rounded-2xl bg-rose-500/20 p-3 text-sm ring-1 ring-rose-300/40">
                <p className="font-bold">{t("tourError")}</p>
                <p className="text-xs text-white/80">{error}</p>
                {all.length === 0 && (
                  <Button size="md" variant="secondary" className="mt-2 w-full" onClick={onSimulate}>🎬 {t("tourSimInstead")}</Button>
                )}
              </div>
            )}
          </div>
        </motion.div>
      </div>
      {current && (
        <FightArena
          initial={current}
          heading={roundName(current.context?.round ?? nextRound, rounds, t)}
          sub={compName}
          finishLabel={t("ok")}
          onClose={closed}
        />
      )}
    </MotionConfig>,
    document.body,
  );
}
