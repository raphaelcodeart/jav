"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { scoreAt, type Belt, type Competition, type Fight, type FightEvent } from "./engine";
import type { CareerT } from "./i18n";
import { BELT_HEX, Judoka, Tatami, type Pose } from "./ui";

// La scena del combattimento: due judoka sul tatami, il tabellone e gli
// eventi che scorrono uno alla volta (presa, attacco, waza-ari, ippon...).

function poses(e: FightEvent | undefined, finished: boolean, fight: Fight): { A: Pose; B: Pose } {
  if (finished) {
    const ippon = fight.events.some((x) => x.t === "IPPON");
    return fight.won ? { A: "win", B: ippon ? "thrown" : "idle" } : { A: ippon ? "thrown" : "idle", B: "win" };
  }
  if (!e) return { A: "idle", B: "idle" };
  const other = e.by === "A" ? "B" : "A";
  const out: { A: Pose; B: Pose } = { A: "grip", B: "grip" };
  switch (e.t) {
    case "GRIP": return out;
    case "ATTACK": out[e.by] = "attack"; out[other] = "block"; return out;
    case "BLOCK": out[e.by] = "block"; out[other] = "grip"; return out;
    case "SHIDO": return { A: "idle", B: "idle" };
    case "YUKO":
    case "WAZA_ARI":
    case "IPPON": out[e.by] = "attack"; out[other] = "thrown"; return out;
  }
}

function roundLabel(f: Fight, t: CareerT): string {
  const left = f.rounds - f.round;
  if (left === 0) return t("round_final");
  if (left === 1) return t("round_semi");
  if (left === 2) return t("round_quarter");
  return t("fightRound", { n: f.round });
}

function ScoreRow({ name, belt, s, tone, highlight }: { name: string; belt: Belt; s: { waza: number; ippon: number; shido: number; yuko?: number }; tone: string; highlight: boolean }) {
  return (
    <div className={cn("flex items-center gap-2 px-3 py-2", tone)}>
      <span className="h-3 w-3 shrink-0 rounded-full ring-1 ring-white/50" style={{ background: BELT_HEX[belt] }} />
      <span className="min-w-0 flex-1 truncate text-sm font-bold">{name}</span>
      <span className={cn("w-8 text-center font-display text-xl tabular-nums", s.ippon ? "text-accent-300" : "")} aria-label="ippon">{s.ippon}</span>
      <span className="w-8 text-center font-display text-xl tabular-nums" aria-label="waza-ari">{s.waza}</span>
      <span className="w-8 text-center font-display text-xl tabular-nums" aria-label="yuko">{s.yuko ?? 0}</span>
      <span className="flex w-10 justify-center gap-0.5" aria-label={`shido ${s.shido}`}>
        {Array.from({ length: 3 }, (_, i) => (
          <span key={i} className={cn("h-4 w-2 rounded-sm", i < s.shido ? "bg-accent-400" : "bg-white/15")} />
        ))}
      </span>
      {highlight && <span aria-hidden="true">🏆</span>}
    </div>
  );
}

export function FightScene({ fights, comp, heroName, heroBelt, t, onDone }: {
  fights: Fight[]; comp: Competition; heroName: string; heroBelt: Belt; t: CareerT; onDone: () => void;
}) {
  const [idx, setIdx] = useState(0);
  const [step, setStep] = useState(0);
  const fight = fights[idx];
  const len = fight?.events.length ?? 0;

  useEffect(() => {
    if (step >= len) return;
    const id = setTimeout(() => setStep((s) => s + 1), step === 0 ? 900 : 1150);
    return () => clearTimeout(id);
  }, [step, len, idx]);

  if (!fight || typeof document === "undefined") return null;
  const finished = step >= len;
  const ev = step > 0 ? fight.events[step - 1] : undefined;
  const p = poses(ev, finished, fight);
  const sc = scoreAt(fight.events, step);
  const last = idx >= fights.length - 1;

  const caption = finished
    ? fight.won ? t("fightWon") : t("fightLost")
    : ev ? t(`fight_${ev.t}`, { tech: ev.technique ?? "" }) : t("hajime");

  return createPortal(
    <div className="fixed inset-0 z-[120] flex flex-col bg-gradient-to-b from-ink-950 via-[#1b1030] to-ink-900 text-white" role="dialog" aria-modal="true" aria-label={roundLabel(fight, t)}>
      <div className="pointer-events-none absolute -top-20 left-1/2 h-72 w-72 -translate-x-1/2 rounded-full bg-accent-400/20 blur-3xl" aria-hidden="true" />
      <div className="relative mx-auto flex w-full max-w-xl flex-1 flex-col px-4 pt-4 pb-6">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-accent-300">{t("compName", { level: t(`level_${comp.level}`), city: comp.city })}</p>
            <p className="font-display text-2xl">{roundLabel(fight, t)}</p>
          </div>
          <div className="flex gap-1" aria-hidden="true">
            {fights.map((f, i) => (
              <span key={i} className={cn("h-2.5 w-6 rounded-full", i < idx ? (f.won ? "bg-emerald-400" : "bg-rose-500") : i === idx ? "bg-white" : "bg-white/20")} />
            ))}
          </div>
        </div>

        {/* tabellone */}
        <div className="mt-4 overflow-hidden rounded-2xl bg-black/60 ring-1 ring-white/10 shadow-lift">
          <div className="flex justify-end gap-2 bg-white/5 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-white/60">
            <span className="w-8 text-center">I</span><span className="w-8 text-center">W</span><span className="w-8 text-center">Y</span><span className="w-10 text-center">S</span>
            <span className="w-4" />
          </div>
          <ScoreRow name={`${heroName} (${t("you")})`} belt={heroBelt} s={sc.A} tone="bg-white/10" highlight={finished && fight.won} />
          <ScoreRow name={`${fight.opponent.name} · ${fight.opponent.city}`} belt={fight.opponent.belt} s={sc.B} tone="bg-blue-700/60" highlight={finished && !fight.won} />
        </div>

        {/* tatami */}
        <Tatami className="mt-4 h-64 sm:h-72" tone="blue">
          <div className="absolute inset-x-0 bottom-6 flex items-end justify-center gap-2">
            <Judoka belt={heroBelt} pose={p.A} />
            <Judoka belt={fight.opponent.belt} gi="#1d4ed8" pose={p.B} flip skin="#c68642" />
          </div>
          <AnimatePresence mode="wait">
            <motion.div
              key={`${idx}-${step}`}
              initial={{ opacity: 0, y: 10, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: ev?.t === "IPPON" ? 1.15 : 1 }}
              exit={{ opacity: 0, y: -8 }}
              className={cn(
                "absolute left-1/2 top-2 -translate-x-1/2 whitespace-nowrap rounded-full px-4 py-1.5 text-sm font-black shadow-lift",
                ev?.t === "IPPON" ? "bg-accent-400 text-ink-900 text-lg" : ev?.t === "WAZA_ARI" ? "bg-white text-ink-900" : ev?.t === "SHIDO" ? "bg-amber-500 text-ink-900" : "bg-black/70 text-white ring-1 ring-white/20",
              )}
              role="status"
            >
              {caption}
            </motion.div>
          </AnimatePresence>
        </Tatami>

        <div className="mt-auto flex gap-2 pt-6">
          {!finished ? (
            <Button variant="ghost" className="flex-1 text-white hover:bg-white/10 hover:text-white" onClick={() => setStep(len)}>{t("skip")} ⏭</Button>
          ) : last ? (
            <Button variant="accent" size="lg" className="flex-1" onClick={onDone}>{t("finish")}</Button>
          ) : (
            <Button variant="primary" size="lg" className="flex-1" onClick={() => { setIdx(idx + 1); setStep(0); }}>{t("nextFight")} 🥋</Button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
