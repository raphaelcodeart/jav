"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { BELT_HEX, Judoka, Tatami, type Pose } from "@/components/game/career/ui";
import { clockText, useFightT, type FightT } from "./i18n";
import { gameApi, postJson, scoreAfter, type Exchange, type FightScore, type FightSide, type FightView, type Prompt } from "./types";

// L'arena del combattimento deciso dal server (fights.py). Passo a passo:
// il server mostra la situazione («Ele ataca com O-goshi!»), si sceglie una
// risposta, il server decide l'esito con le statistiche e il caso, e qui si
// mostra il perché. Simulato (o già finito): si rivede lo stesso incontro
// scambio per scambio. Il tabellone segue le regole IJF: yuko, waza-ari,
// ippon, shido, 4 minuti e golden score.

const ROW_TONE = { me: "bg-white/10", opp: "bg-blue-700/60" } as const;

function poses(ex: Exchange | undefined): { me: Pose; opp: Pose } {
  if (!ex) return { me: "grip", opp: "grip" };
  if (ex.points && ex.points !== "SHIDO" && ex.by) {
    const other = ex.by === "me" ? "opp" : "me";
    return { [ex.by]: "attack", [other]: "thrown" } as { me: Pose; opp: Pose };
  }
  if (ex.points === "SHIDO") return { me: "idle", opp: "idle" };
  return ex.kind === "DEF" ? { me: "block", opp: "attack" } : ex.kind === "ATT" ? { me: "attack", opp: "block" } : { me: "grip", opp: "grip" };
}

export function FightArena({ initial, heading, sub, finishLabel, onClose }: {
  initial: FightView; heading: string; sub?: string; finishLabel?: string; onClose: (v: FightView) => void;
}) {
  const t = useFightT();
  const toast = useToast();
  const [view, setView] = useState<FightView>(initial);
  // Già finito quando arriva (simulato): lo si rivede scambio per scambio.
  const replay = initial.status === "FINISHED";
  const [shown, setShown] = useState(replay ? 0 : initial.history.length);
  const [phase, setPhase] = useState<"ask" | "result" | "end">(replay ? "result" : "ask");
  const [busy, setBusy] = useState(false);
  const [confirmQuit, setConfirmQuit] = useState(false);
  const total = view.history.length;

  useEffect(() => {
    if (!replay || phase === "end") return;
    const id = shown < total
      ? setTimeout(() => setShown((s) => s + 1), shown === 0 ? 900 : 2600)
      : setTimeout(() => setPhase("end"), 1600);
    return () => clearTimeout(id);
  }, [replay, phase, shown, total]);

  async function choose(option: string | null) {
    const prompt = view.prompt;
    if (!prompt || busy) return;
    setBusy(true);
    try {
      const next = await gameApi<FightView>(`/api/proxy/game/fights/${view.id}/act`, postJson({ seq: prompt.seq, option }));
      setView(next);
      setShown(next.history.length);
      setPhase("result");
    } catch (e) {
      toast({ tone: "error", title: t("error"), text: e instanceof Error ? e.message : undefined });
      // si riallinea con il server (per esempio una risposta già arrivata)
      const fresh = await gameApi<FightView>(`/api/proxy/game/fights/${view.id}`).catch(() => null);
      if (fresh) {
        setView(fresh);
        setShown(fresh.history.length);
        setPhase(fresh.status === "FINISHED" ? "end" : "ask");
      }
    } finally {
      setBusy(false);
    }
  }

  async function quit() {
    if (view.status !== "ACTIVE") { onClose(view); return; }
    setBusy(true);
    try {
      const next = await gameApi<FightView>(`/api/proxy/game/fights/${view.id}/forfeit`, postJson());
      setView(next);
      setPhase("end");
    } catch (e) {
      toast({ tone: "error", title: t("error"), text: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
      setConfirmQuit(false);
    }
  }

  if (typeof document === "undefined") return null;

  const current: Exchange | undefined = phase === "ask" ? undefined : replay ? view.history[shown - 1] : (view.last ?? view.history[total - 1]);
  const score = replay && phase !== "end" ? scoreAfter(view.history, shown) : view.score;
  const clock = replay && phase !== "end" ? (view.history[shown - 1]?.clock ?? 0) : view.clock;
  const golden = replay && phase !== "end" ? clock > view.regulation : view.golden;
  const frac = replay && phase !== "end" && total > 0 ? shown / total : 1;
  const stamina = {
    me: Math.round(view.me.sta + (view.stamina.me - view.me.sta) * frac),
    opp: Math.round(view.opp.sta + (view.stamina.opp - view.opp.sta) * frac),
  };
  const p = poses(current);
  const finished = view.status === "FINISHED";

  return createPortal(
    <MotionConfig reducedMotion="user">
      <div className="fixed inset-0 z-[120] overflow-y-auto overscroll-contain bg-gradient-to-b from-ink-950 via-[#14122b] to-ink-900 text-white" role="dialog" aria-modal="true" aria-label={heading}>
        <div className="pointer-events-none absolute -top-24 left-1/2 h-72 w-72 -translate-x-1/2 rounded-full bg-accent-400/15 blur-3xl" aria-hidden="true" />
        <div className="relative mx-auto flex min-h-full w-full max-w-5xl flex-col px-3 pb-6 sm:px-5" style={{ paddingTop: "max(0.75rem, env(safe-area-inset-top))" }}>
          {/* intestazione */}
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              {sub && <p className="truncate text-[11px] font-bold uppercase tracking-[0.2em] text-accent-300">{sub}</p>}
              <p className="truncate font-display text-xl sm:text-2xl">{heading}</p>
            </div>
            {phase !== "end" && !finished ? (
              confirmQuit ? (
                <div className="flex shrink-0 items-center gap-2 rounded-2xl bg-rose-950/70 p-2 ring-1 ring-rose-400/40">
                  <span className="hidden max-w-48 text-xs text-rose-100 sm:block">{t("abandonConfirm")}</span>
                  <Button size="sm" variant="danger" loading={busy} onClick={quit}>{t("abandon")}</Button>
                  <Button size="sm" variant="ghost" className="text-white hover:bg-white/10 hover:text-white" onClick={() => setConfirmQuit(false)}>✕</Button>
                </div>
              ) : (
                <Button size="sm" variant="ghost" className="shrink-0 text-white/80 hover:bg-white/10 hover:text-white" onClick={() => setConfirmQuit(true)}>🏳️ {t("abandon")}</Button>
              )
            ) : phase !== "end" ? (
              <Button size="sm" variant="ghost" className="shrink-0 text-white/80 hover:bg-white/10 hover:text-white" onClick={() => setPhase("end")}>{t("skip")}</Button>
            ) : null}
          </div>

          <div className="mt-3 grid flex-1 gap-3 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:items-start">
            <div className="space-y-3">
              <Scoreboard me={view.me} opp={view.opp} score={score} stamina={stamina} clock={clock} regulation={view.regulation} golden={golden} t={t}
                winner={phase === "end" && view.result ? (view.result.won ? "me" : "opp") : null} />
              <Tatami className="h-40 sm:h-52 lg:h-64" tone="blue">
                <div className="absolute inset-x-0 bottom-4 flex items-end justify-center gap-1 sm:gap-3">
                  <Judoka belt={view.me.belt} pose={phase === "end" ? (view.result?.won ? "win" : "idle") : p.me} size={78} />
                  <Judoka belt={view.opp.belt} gi="#1d4ed8" pose={phase === "end" ? (view.result?.won ? "idle" : "win") : p.opp} flip skin="#c68642" size={78} />
                </div>
                <AnimatePresence mode="wait">
                  {current && phase === "result" && (
                    <motion.div key={current.seq} initial={{ opacity: 0, y: 10, scale: 0.85 }} animate={{ opacity: 1, y: 0, scale: current.points === "IPPON" ? 1.15 : 1 }} exit={{ opacity: 0, y: -8 }}
                      className={cn("absolute left-1/2 top-1 -translate-x-1/2 whitespace-nowrap rounded-full px-4 py-1.5 text-sm font-black shadow-lift",
                        current.points === "IPPON" ? "bg-accent-400 text-lg text-ink-900" : current.points === "WAZA" || current.points === "YUKO" ? "bg-white text-ink-900" : current.points === "SHIDO" ? "bg-amber-500 text-ink-900" : "bg-black/70 text-white ring-1 ring-white/20")}
                      role="status">
                      {outcomeTitle(current, view.opp.name, t)}
                    </motion.div>
                  )}
                </AnimatePresence>
              </Tatami>
            </div>

            <div className="min-w-0">
              <AnimatePresence mode="wait">
                {phase === "ask" && view.prompt && (
                  <motion.div key={`ask-${view.prompt.seq}`} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}>
                    <PromptCard prompt={view.prompt} busy={busy} t={t} onChoose={choose} />
                  </motion.div>
                )}
                {phase === "result" && current && (
                  <motion.div key={`res-${current.seq}`} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}>
                    <ResultCard ex={current} oppName={view.opp.name} t={t} showPrompt={replay} />
                    {!replay && (
                      <Button size="xl" variant={finished ? "accent" : "primary"} className="mt-3 w-full" onClick={() => setPhase(finished ? "end" : "ask")}>
                        {finished ? t("seeResult") : t("next")} ▶
                      </Button>
                    )}
                  </motion.div>
                )}
                {phase === "result" && !current && replay && (
                  <motion.p key="hajime" initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="py-10 text-center font-display text-4xl text-accent-300">{t("hajime")}</motion.p>
                )}
                {phase === "end" && (
                  <motion.div key="end" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                    <EndCard view={view} t={t} label={finishLabel ?? t("close")} onClose={() => onClose(view)} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>
    </MotionConfig>,
    document.body,
  );
}

function outcomeTitle(ex: Exchange, oppName: string, t: FightT): string {
  if (ex.points === "IPPON" || ex.points === "WAZA" || ex.points === "YUKO") return t(`out_${ex.points}`);
  if (ex.points === "SHIDO") return ex.by === "me" ? t("shidoMe") : t("shidoOpp", { name: oppName });
  return t("matte");
}

function Scoreboard({ me, opp, score, stamina, clock, regulation, golden, winner, t }: {
  me: FightSide; opp: FightSide; score: { me: FightScore; opp: FightScore }; stamina: { me: number; opp: number };
  clock: number; regulation: number; golden: boolean; winner: "me" | "opp" | null; t: FightT;
}) {
  return (
    <div className="overflow-hidden rounded-2xl bg-black/60 shadow-lift ring-1 ring-white/10">
      <div className="flex items-center gap-2 bg-white/5 px-3 py-1.5">
        <span className={cn("rounded-md px-2 py-0.5 font-mono text-xl font-black tabular-nums tracking-wider", golden ? "bg-amber-400 text-ink-900" : "bg-black/50 text-accent-300")} aria-label="clock">
          {clockText(clock, regulation, golden)}
        </span>
        {golden && <span className="text-[11px] font-black uppercase tracking-wider text-amber-300">{t("golden")}</span>}
        <span className="ml-auto flex gap-1 text-[10px] font-bold uppercase tracking-wider text-white/60" aria-hidden="true">
          <span className="w-7 text-center">W</span><span className="w-7 text-center">Y</span><span className="w-12 text-center">S</span>
        </span>
      </div>
      <ScoreRow side={me} label={`${me.name} (${t("you")})`} s={score.me} sta={stamina.me} tone={ROW_TONE.me} win={winner === "me"} t={t} />
      <ScoreRow side={opp} label={opp.club ? `${opp.name} · ${opp.club}` : opp.name} s={score.opp} sta={stamina.opp} tone={ROW_TONE.opp} win={winner === "opp"} t={t} />
    </div>
  );
}

function ScoreRow({ side, label, s, sta, tone, win, t }: {
  side: FightSide; label: string; s: FightScore; sta: number; tone: string; win: boolean; t: FightT;
}) {
  const ippon = s.ippon > 0 || s.waza >= 2;
  return (
    <div className={cn("flex items-center gap-2 px-3 py-2", tone)}>
      <span className="h-3 w-3 shrink-0 rounded-full ring-1 ring-white/50" style={{ background: BELT_HEX[side.belt] }} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-bold">{label} {win && <span aria-hidden="true">🏆</span>}</p>
        <div className="mt-1 flex items-center gap-1.5" title={`${t("stamina")} ${sta}`}>
          <span className="text-[10px] text-white/60" aria-hidden="true">💨</span>
          <span className="h-1.5 w-20 overflow-hidden rounded-full bg-white/15 sm:w-28">
            <motion.span className={cn("block h-full rounded-full", sta < 30 ? "bg-rose-400" : "bg-emerald-400")} initial={false} animate={{ width: `${Math.max(0, Math.min(100, sta))}%` }} />
          </span>
          {side.hp < 100 && <span className="text-[10px] font-bold text-rose-300">🤕 {side.hp}%</span>}
        </div>
      </div>
      {ippon ? (
        <span className="w-[3.75rem] text-center font-display text-sm font-black text-accent-300">IPPON</span>
      ) : (
        <>
          <span className="w-7 text-center text-2xl font-black tabular-nums" aria-label="waza-ari">{s.waza}</span>
          <span className="w-7 text-center text-2xl font-black tabular-nums" aria-label="yuko">{s.yuko}</span>
        </>
      )}
      <span className="flex w-12 justify-center gap-0.5" aria-label={`shido ${s.shido}`}>
        {Array.from({ length: 3 }, (_, i) => (
          <span key={i} className={cn("h-5 w-2.5 rounded-sm", i < s.shido ? (s.shido >= 3 ? "bg-rose-500" : "bg-accent-400") : "bg-white/15")} />
        ))}
      </span>
    </div>
  );
}

/** Il conto alla rovescia di uno scambio: si rimonta a ogni scambio (key). */
function Countdown({ seconds, onExpire }: { seconds: number; onExpire: () => void }) {
  const [left, setLeft] = useState(seconds);
  const expire = useRef(onExpire);
  useEffect(() => { expire.current = onExpire; });
  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => {
      const l = Math.max(0, seconds - (Date.now() - start) / 1000);
      setLeft(l);
      if (l <= 0) { clearInterval(id); expire.current(); }
    }, 200);
    return () => clearInterval(id);
  }, [seconds]);
  const pct = (left / seconds) * 100;
  return (
    <div className="flex items-center gap-2" role="timer" aria-live="off">
      <span className="h-2 flex-1 overflow-hidden rounded-full bg-white/15">
        <span className={cn("block h-full rounded-full transition-[width] duration-200", pct < 30 ? "bg-rose-400" : pct < 60 ? "bg-amber-300" : "bg-emerald-400")} style={{ width: `${pct}%` }} />
      </span>
      <span className="w-9 text-right font-mono text-sm font-bold tabular-nums">{Math.ceil(left)}s</span>
    </div>
  );
}

function PromptCard({ prompt, busy, t, onChoose }: { prompt: Prompt; busy: boolean; t: FightT; onChoose: (id: string | null) => void }) {
  return (
    <div className="rounded-3xl bg-white p-4 text-ink-900 shadow-lift sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-ink-900 px-2.5 py-1 text-[11px] font-black text-white">{t(`kind_${prompt.kind}`)}</span>
        {prompt.attack && <span className="rounded-full bg-rose-100 px-2.5 py-1 text-[11px] font-black text-rose-800">{t("attack", { tech: prompt.attack })}</span>}
      </div>
      <p className="mt-3 font-display text-xl leading-snug sm:text-2xl">{prompt.text}</p>
      <p className="mt-1 text-sm font-semibold text-ink-500">{t("whatDo")}</p>
      <div className="mt-3"><Countdown key={prompt.seq} seconds={prompt.seconds} onExpire={() => onChoose(null)} /></div>
      <div className="mt-3 grid gap-2">
        {prompt.options.map((o, i) => (
          <motion.button key={o.id} type="button" disabled={busy} whileTap={{ scale: 0.97 }} onClick={() => onChoose(o.id)}
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 * i }}
            className="flex min-h-14 w-full cursor-pointer items-center gap-3 rounded-2xl bg-ink-50 px-3 py-2.5 text-left text-sm font-bold text-ink-900 ring-2 ring-transparent transition hover:bg-brand-50 hover:ring-brand-300 disabled:cursor-wait disabled:opacity-60 sm:text-base">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-ink-900 font-display text-sm text-white">{String.fromCharCode(65 + i)}</span>
            <span>{o.label}</span>
          </motion.button>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-ink-400">{t("timeHint")}</p>
    </div>
  );
}

const QUALITY_TONE = { BEST: "bg-emerald-100 text-emerald-800", GOOD: "bg-sky-100 text-sky-800", RISKY: "bg-amber-100 text-amber-800", BAD: "bg-rose-100 text-rose-800" } as const;

function ResultCard({ ex, oppName, t, showPrompt }: { ex: Exchange; oppName: string; t: FightT; showPrompt: boolean }) {
  const scored = ex.points && ex.points !== "SHIDO";
  return (
    <div className="rounded-3xl bg-white p-4 text-ink-900 shadow-lift sm:p-5">
      {showPrompt && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-ink-900 px-2.5 py-1 text-[11px] font-black text-white">{t(`kind_${ex.kind}`)}</span>
          <span className="text-sm font-semibold text-ink-600">{ex.prompt}</span>
        </div>
      )}
      <p className={cn("rounded-2xl px-4 py-3 text-center font-display text-2xl",
        scored ? (ex.by === "me" ? "bg-gradient-to-r from-accent-200 to-accent-400" : "bg-rose-100 text-rose-900") : ex.points === "SHIDO" ? "bg-amber-100 text-amber-900" : "bg-ink-100 text-ink-700")}>
        {outcomeTitle(ex, oppName, t)}
      </p>
      {scored && ex.tech && (
        <p className="mt-2 text-center text-sm font-bold text-ink-700">{ex.by === "me" ? t("youScored", { tech: ex.tech }) : t("scoredBy", { name: oppName, tech: ex.tech })}</p>
      )}
      <div className="mt-3 rounded-2xl bg-ink-50 p-3">
        <p className="text-[11px] font-bold uppercase tracking-wider text-ink-400">{t("yourAnswer")}</p>
        <p className="mt-0.5 font-bold">{ex.choice}</p>
        <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs font-bold">
          <span className={cn("rounded-full px-2 py-0.5", QUALITY_TONE[ex.quality])}>{t(`q_${ex.quality}`)}</span>
          <span className="text-ink-500">{ex.success ? t("worked") : t("failed")}</span>
        </p>
      </div>
      <p className="mt-3 flex gap-2 text-sm text-ink-700"><span aria-hidden="true">💡</span><span><strong>{t("why")}:</strong> {ex.why}</span></p>
    </div>
  );
}

function EndCard({ view, t, label, onClose }: { view: FightView; t: FightT; label: string; onClose: () => void }) {
  const r = view.result;
  if (!r) return null;
  return (
    <div className="rounded-3xl bg-white p-4 text-ink-900 shadow-lift sm:p-5">
      <motion.p initial={{ scale: 0.6 }} animate={{ scale: [0.6, 1.1, 1] }} className="text-center text-5xl" aria-hidden="true">{r.won ? "🏆" : "🙇"}</motion.p>
      <p className="mt-1 text-center font-display text-2xl">{r.won ? t("won") : t("lost")}</p>
      <p className="text-center text-sm font-semibold text-ink-500">{t(`reason_${r.reason}`)}</p>
      {view.kind === "RANDORI" && r.points > 0 && (
        <p className={cn("mx-auto mt-3 w-fit rounded-full px-4 py-1.5 font-display text-lg", r.won ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800")}>
          {r.won ? t("pointsWon", { n: r.points }) : t("pointsLost", { n: r.points })}
        </p>
      )}
      {view.history.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-sm font-bold text-ink-900">📚 {t("lessons")}</p>
          <ol className="max-h-64 space-y-2 overflow-y-auto pr-1 lg:max-h-[40vh]">
            {view.history.map((e) => (
              <li key={e.seq} className="rounded-2xl bg-ink-50 p-2.5 text-xs">
                <p className="flex items-center gap-1.5 font-bold text-ink-800">
                  <span className={cn("rounded-full px-1.5 py-0.5 text-[10px]", QUALITY_TONE[e.quality])}>{t(`q_${e.quality}`)}</span>
                  <span className="truncate">{e.choice}</span>
                </p>
                <p className="mt-1 text-ink-600">{e.why}</p>
              </li>
            ))}
          </ol>
        </div>
      )}
      <Button size="xl" variant="accent" className="mt-4 w-full" onClick={onClose}>{label}</Button>
    </div>
  );
}
