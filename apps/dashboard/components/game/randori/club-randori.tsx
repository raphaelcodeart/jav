"use client";

import { MotionConfig, motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { BELT_HEX } from "@/components/game/career/ui";
import { FightArena } from "@/components/game/fight/fight-arena";
import { useFightT, type FightT } from "@/components/game/fight/i18n";
import { gameApi, postJson, type FightReason, type FightSide, type FightView } from "@/components/game/fight/types";
import { useGameFrame } from "@/components/game/game-frame";
import { useGameText } from "@/components/game/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/cn";

// Randori del Club (apps/api/app/game/fights.py): si sfidano gli amici del
// proprio club che giocano anche loro. L'amico non deve essere collegato:
// combatte con le statistiche della sua carriera. Chi vince prende i punti
// dell'altro (alla Elo, con un tetto); al giorno al massimo tre incontri
// con lo stesso amico e dieci sfide. Nomi sempre «Nome I.».

interface Friend {
  player_id: string; display_name: string; belt: FightSide["belt"]; points: number;
  edge: "STRONGER" | "EVEN" | "WEAKER"; left_today: number; stake_win: number; stake_loss: number; injured: boolean;
}
interface BoardRow { position: number; display_name: string; points: number; wins: number; losses: number; is_me: boolean }
interface HistoryRow { id: string; at: string; opponent: string; challenger: boolean; won: boolean; points: number; mode: "SIM" | "STEP"; reason: FightReason | null; can_review: boolean }
interface Overview {
  club_label: string | null;
  me: { display_name: string; points: number; fighter: FightSide; position: number; challenges_left: number };
  friends: Friend[]; board: BoardRow[]; history: HistoryRow[]; active_fight_id: string | null;
  limits: { pair_per_day: number; challenges_per_day: number };
}

const KEY = ["game", "randori"] as const;
const EDGE_TONE = { STRONGER: "bg-rose-100 text-rose-800", EVEN: "bg-sky-100 text-sky-800", WEAKER: "bg-emerald-100 text-emerald-800" } as const;

export function ClubRandori({ onGoCareer }: { onGoCareer: () => void }) {
  const t = useFightT();
  const { lang } = useGameText();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { full } = useGameFrame();
  const data = useQuery({ queryKey: KEY, queryFn: () => gameApi<Overview>("/api/proxy/game/randori") });
  const [picking, setPicking] = useState<Friend | null>(null);
  const [busy, setBusy] = useState(false);
  const [arena, setArena] = useState<{ view: FightView; name: string } | null>(null);
  const [side, setSide] = useState<"board" | "history">("board");

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["game"] });

  async function start(friend: Friend, mode: "SIM" | "STEP") {
    setBusy(true);
    try {
      const view = await gameApi<FightView>(`/api/proxy/game/randori/challenge?lang=${lang}`, postJson({ opponent_id: friend.player_id, mode }));
      setPicking(null);
      setArena({ view, name: friend.display_name });
    } catch (e) {
      toast({ tone: "error", title: t("error"), text: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
    }
  }

  async function open(id: string, name: string) {
    try {
      const view = await gameApi<FightView>(`/api/proxy/game/fights/${id}`);
      setArena({ view, name });
    } catch (e) {
      toast({ tone: "error", title: t("error"), text: e instanceof Error ? e.message : undefined });
    }
  }

  if (data.isLoading) return <Skeleton className="h-96" />;
  if (data.isError || !data.data) {
    return (
      <div className="mx-auto max-w-md rounded-3xl bg-white p-6 text-center shadow-soft ring-1 ring-rose-100">
        <p className="text-4xl" aria-hidden="true">😵</p>
        <p className="mt-2 font-bold text-ink-900">{t("error")}</p>
        <Button className="mt-4" onClick={() => void data.refetch()}>{t("retry")}</Button>
      </div>
    );
  }
  const o = data.data;
  const f = o.me.fighter;

  return (
    <MotionConfig reducedMotion="user">
      <div className="space-y-4">
        {/* la testata: io, i miei punti, le sfide di oggi */}
        <section className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-sky-500 via-blue-700 to-indigo-900 p-4 text-white shadow-lift sm:p-5">
          <div className="pointer-events-none absolute inset-0 opacity-15 [background-image:repeating-linear-gradient(90deg,#fff_0_2px,transparent_2px_12.5%)]" aria-hidden="true" />
          <motion.span aria-hidden="true" className="pointer-events-none absolute -right-2 -top-4 select-none text-[7rem] leading-none opacity-20"
            animate={{ rotate: [-6, 6, -6] }} transition={{ duration: 6, repeat: Infinity }}>🤼</motion.span>
          <div className="relative flex flex-wrap items-end justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-accent-200">{t("r_eyebrow")}{o.club_label ? ` · ${o.club_label}` : ""}</p>
              <h1 className="mt-1 font-display text-2xl leading-tight sm:text-3xl">{t("r_title")}</h1>
            </div>
            <div className="flex items-stretch gap-2">
              <div className="rounded-2xl bg-white/15 px-4 py-2 text-center ring-1 ring-white/25 backdrop-blur">
                <p className="font-display text-3xl tabular-nums">{o.me.points}</p>
                <p className="text-[11px] font-bold uppercase text-white/75">{t("r_points")}</p>
              </div>
              <div className="flex flex-col justify-center rounded-2xl bg-black/20 px-3 py-2 text-xs font-bold">
                <span>🏅 {t("r_position", { n: o.me.position })}</span>
                <span className="mt-1 text-white/80">⚔️ {t("r_left", { n: o.me.challenges_left, max: o.limits.challenges_per_day })}</span>
              </div>
            </div>
          </div>
        </section>

        {o.active_fight_id && (
          <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-amber-50 p-3 ring-2 ring-amber-300">
            <span className="text-2xl" aria-hidden="true">⏳</span>
            <div className="min-w-0 flex-1">
              <p className="font-bold text-amber-900">{t("r_active")}</p>
              <p className="text-xs text-amber-800">{t("r_activeText")}</p>
            </div>
            <Button onClick={() => void open(o.active_fight_id!, "")}>{t("r_resume")} ▶</Button>
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <div className="space-y-4">
            <FighterCard f={f} t={t} onGoCareer={onGoCareer} />
            <section className="rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-100">
              <h2 className="mb-1 font-display text-lg text-ink-900">👥 {t("r_friends")}</h2>
              <p className="mb-3 text-xs text-ink-500">{t("r_hint")}</p>
              {!o.club_label ? (
                <p className="rounded-2xl bg-ink-50 p-4 text-center text-sm text-ink-600">{t("r_noClub")}</p>
              ) : o.friends.length === 0 ? (
                <p className="rounded-2xl bg-ink-50 p-4 text-center text-sm text-ink-600">{t("r_noFriends")}</p>
              ) : (
                <ul className={cn("grid gap-2 overflow-y-auto pr-1 sm:grid-cols-2", full ? "lg:max-h-[calc(100dvh-24rem)]" : "lg:max-h-[30rem]")}>
                  {o.friends.map((fr, i) => (
                    <motion.li key={fr.player_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 10) * 0.03 }}
                      className="flex flex-col gap-2 rounded-2xl bg-ink-50 p-3 ring-1 ring-ink-100">
                      <div className="flex items-center gap-2">
                        <span className="h-3 w-7 shrink-0 rounded-full ring-1 ring-black/15" style={{ background: BELT_HEX[fr.belt] }} aria-hidden="true" />
                        <span className="min-w-0 flex-1 truncate font-bold text-ink-900">{fr.display_name}{fr.injured ? " 🤕" : ""}</span>
                        <span className="font-display text-ink-700 tabular-nums">{fr.points}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-bold">
                        <span className={cn("rounded-full px-2 py-0.5", EDGE_TONE[fr.edge])}>{t(`r_edge_${fr.edge}`)}</span>
                        <span className="text-ink-500">{t("r_stakes", { win: fr.stake_win, loss: fr.stake_loss })}</span>
                      </div>
                      <Button size="md" disabled={fr.left_today === 0 || o.me.challenges_left === 0 || !!o.active_fight_id} onClick={() => setPicking(fr)}>
                        {fr.left_today === 0 ? t("r_noneLeft") : `🤼 ${t("r_challenge")} · ${t("r_leftPair", { n: fr.left_today })}`}
                      </Button>
                    </motion.li>
                  ))}
                </ul>
              )}
              <p className="mt-3 text-[11px] text-ink-400">{t("r_rules", { pair: o.limits.pair_per_day, max: o.limits.challenges_per_day })}</p>
            </section>
          </div>

          <section className="rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-100">
            <div className="mb-3 flex gap-1.5 rounded-full bg-ink-50 p-1" role="tablist">
              {(["board", "history"] as const).map((k) => (
                <button key={k} type="button" role="tab" aria-selected={side === k} onClick={() => setSide(k)}
                  className={cn("h-9 flex-1 cursor-pointer rounded-full px-3 text-sm font-semibold", side === k ? "bg-ink-900 text-white" : "text-ink-600 hover:bg-white")}>
                  {k === "board" ? `🏆 ${t("r_board")}` : `📜 ${t("r_history")}`}
                </button>
              ))}
            </div>
            {side === "board" ? <Board rows={o.board} t={t} /> : <History rows={o.history} t={t} onReview={(h) => void open(h.id, h.opponent)} />}
          </section>
        </div>
      </div>

      {picking && (
        <Modal open onClose={() => setPicking(null)} title={t("r_modeTitle", { name: picking.display_name })} subtitle={t("r_modeText")} size="md">
          <div className="grid gap-3 sm:grid-cols-2">
            {([["SIM", "r_sim", "r_simText"], ["STEP", "r_step", "r_stepText"]] as const).map(([mode, title, text]) => (
              <button key={mode} type="button" disabled={busy} onClick={() => void start(picking, mode)}
                className={cn("flex cursor-pointer flex-col gap-1 rounded-2xl p-4 text-left text-white shadow-soft transition hover:-translate-y-0.5 hover:shadow-lift disabled:cursor-wait disabled:opacity-60 bg-gradient-to-br",
                  mode === "SIM" ? "from-sky-500 to-indigo-700" : "from-brand-500 to-brand-700")}>
                <span className="font-display text-lg">{t(title)}</span>
                <span className="text-sm text-white/85">{t(text)}</span>
              </button>
            ))}
          </div>
          <p className="mt-3 text-center text-sm font-semibold text-ink-600">{t("r_stakes", { win: picking.stake_win, loss: picking.stake_loss })}</p>
        </Modal>
      )}

      {arena && (
        <FightArena
          initial={arena.view}
          heading={`${t("r_eyebrow")} · ${arena.name || arena.view.opp.name}`}
          sub={arena.view.mode === "SIM" ? t("replay") : o.club_label ?? undefined}
          onClose={() => { setArena(null); refresh(); }}
        />
      )}
    </MotionConfig>
  );
}

function StatBar({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="min-w-0">
      <div className="mb-0.5 flex justify-between text-[11px] font-semibold text-ink-600"><span className="truncate">{label}</span><span className="tabular-nums">{value}</span></div>
      <div className="h-1.5 overflow-hidden rounded-full bg-ink-100">
        <motion.div className={cn("h-full rounded-full", tone)} initial={{ width: 0 }} animate={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
    </div>
  );
}

function FighterCard({ f, t, onGoCareer }: { f: FightSide; t: FightT; onGoCareer: () => void }) {
  const { belt } = useGameText();
  return (
    <section className="rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-100">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="font-display text-lg text-ink-900">🥋 {t("r_myJudoka")}</h2>
        <span className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-ink-50 px-2 py-0.5 text-[11px] font-bold text-ink-700">
          <span className="h-2 w-5 rounded-full ring-1 ring-black/15" style={{ background: BELT_HEX[f.belt] }} aria-hidden="true" />{belt(f.belt)}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        <StatBar label={`🥋 ${t("technique")}`} value={f.tec} tone="bg-gradient-to-r from-brand-400 to-brand-600" />
        <StatBar label={`💪 ${t("strength")}`} value={f.str} tone="bg-gradient-to-r from-emerald-400 to-green-600" />
        <StatBar label={`🧠 ${t("mind")}`} value={f.men} tone="bg-gradient-to-r from-sky-400 to-indigo-600" />
        <StatBar label={`💨 ${t("stamina")}`} value={f.sta} tone="bg-gradient-to-r from-lime-300 to-emerald-500" />
      </div>
      {f.hp < 100 && <p className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">🤕 {t("r_injured", { n: f.hp })}</p>}
      {f.hp >= 100 && f.sta < 40 && <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">😮‍💨 {t("r_tired")}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <p className="min-w-0 flex-1 text-xs text-ink-500">{t("r_fromCareer")}</p>
        <Button size="sm" variant="secondary" onClick={onGoCareer}>🏆 {t("r_goCareer")}</Button>
      </div>
    </section>
  );
}

function Board({ rows, t }: { rows: BoardRow[]; t: FightT }) {
  return (
    <ol className="space-y-1.5">
      {rows.map((r) => (
        <li key={`${r.position}-${r.display_name}`} className={cn("flex items-center gap-3 rounded-2xl px-3 py-2", r.is_me ? "bg-accent-100 ring-2 ring-accent-300" : "bg-ink-50")}>
          <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-display text-sm",
            r.position === 1 ? "bg-accent-400 text-ink-900" : r.position === 2 ? "bg-ink-300 text-ink-900" : r.position === 3 ? "bg-amber-700 text-white" : "bg-white text-ink-600")}>{r.position}</span>
          <span className="min-w-0 flex-1 truncate font-semibold text-ink-900">{r.display_name}{r.is_me ? ` (${t("you")})` : ""}</span>
          <span className="text-[11px] font-bold text-ink-500">{t("r_wl", { w: r.wins, l: r.losses })}</span>
          <span className="w-14 text-right font-display text-brand-600 tabular-nums">{r.points}</span>
        </li>
      ))}
    </ol>
  );
}

function History({ rows, t, onReview }: { rows: HistoryRow[]; t: FightT; onReview: (h: HistoryRow) => void }) {
  const { fmt } = useI18n();
  if (rows.length === 0) return <p className="py-8 text-center text-sm text-ink-500">{t("r_noHistory")}</p>;
  return (
    <ul className="space-y-1.5">
      {rows.map((h) => (
        <li key={h.id} className="flex items-center gap-3 rounded-2xl bg-ink-50 px-3 py-2">
          <span className="text-xl" aria-hidden="true">{h.won ? "🏆" : "🙇"}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-bold text-ink-900">{h.challenger ? t("r_youChallenged", { name: h.opponent }) : t("r_challengedYou", { name: h.opponent })}</p>
            <p className="truncate text-[11px] text-ink-500">
              {fmt.shortDate(h.at)} · {h.mode === "SIM" ? t("r_sim") : t("r_step")}{h.reason ? ` · ${t(`reason_${h.reason}`)}` : ""}
            </p>
          </div>
          <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-xs font-black tabular-nums", h.won ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800")}>
            {h.won ? "+" : "−"}{h.points}
          </span>
          {h.can_review && <Button size="sm" variant="ghost" onClick={() => onReview(h)}>{t("r_review")}</Button>}
        </li>
      ))}
    </ul>
  );
}
