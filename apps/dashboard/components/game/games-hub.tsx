"use client";

import { MotionConfig, motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { JudoCareer } from "@/components/game/career/judo-career";
import { DojoAcademy } from "@/components/game/dojo-academy";
import { GameFrame } from "@/components/game/game-frame";
import { BeltSwatch } from "@/components/game/belt";
import { BELT_COLORS, QUALIFICATION_LABELS, useGameText } from "@/components/game/i18n";
import { ClubRandori } from "@/components/game/randori/club-randori";
import { friendlyApiError } from "@/lib/api-error";
import { cn } from "@/lib/cn";

// JAV Games, la vetrina: il profilo del giocatore (livello, XP, posizione,
// cintura del gioco), i giochi come in un app store e la classifica di
// tutti i club. Un mondo a parte (apps/api/app/game, docs/games.md): niente
// di quello che succede qui tocca il gestionale.

interface Me {
  id: string; display_name: string; club_label: string | null; xp: number; quiz_xp: number; career_xp: number;
  level: number; level_from: number; level_to: number; position: number; exams_passed: string[]; belt: string;
  grade: string; qualifications: string[];
}
interface Board {
  scope: string;
  rows: { position: number; display_name: string; club_label: string | null; xp: number; level: number; belt: string; grade: string; career_belt: string | null; is_me: boolean }[];
  clubs: { club_label: string; xp: number; players: number }[];
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

type View = "hub" | "academy" | "career" | "randori";

export function GamesHub() {
  const { g } = useGameText();
  const [view, setView] = useState<View>("hub");
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["game", "me"], queryFn: () => getJson<Me>("/api/proxy/game/me") });
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["game"] });

  // Ogni gioco nella sua cornice, con lo schermo intero (game-frame.tsx).
  if (view === "academy") {
    return (
      <GameFrame title={g("academyName")} icon="🎓">
        <DojoAcademy onBack={() => setView("hub")} onXpChange={refresh} />
      </GameFrame>
    );
  }
  if (view === "career") {
    return (
      <GameFrame title={g("careerName")} icon="🏆" onBack={() => setView("hub")}>
        {me.data ? (
          <JudoCareer playerName={me.data.display_name} examsPassed={me.data.exams_passed} onGoAcademy={() => setView("academy")} onXpChange={refresh} />
        ) : <Skeleton className="h-96" />}
      </GameFrame>
    );
  }
  if (view === "randori") {
    return (
      <GameFrame title={g("randoriName")} icon="🤼" onBack={() => setView("hub")}>
        <ClubRandori onGoCareer={() => setView("career")} />
      </GameFrame>
    );
  }

  return (
    <MotionConfig reducedMotion="user">
      <div className="space-y-8">
        <PlayerHero me={me.data} loading={me.isLoading} />

        <section>
          <h2 className="mb-4 text-xl text-ink-900">🎮 {g("apps")}</h2>
          <ul className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            <AppCard
              icon="🎓" name={g("academyName")} tag={g("academyTag")} text={g("academyText")}
              gradient="from-indigo-500 via-violet-600 to-fuchsia-600" onPlay={() => setView("academy")} delay={0}
              art={<div className="grid grid-cols-3 gap-1.5 text-2xl">{["🏯", "🙇", "🥋", "⚖️", "🗾", "🎖️"].map((e, i) => (
                <motion.span key={e} animate={{ y: [0, -5, 0] }} transition={{ duration: 2, delay: i * 0.2, repeat: Infinity }}>{e}</motion.span>
              ))}</div>}
            />
            <AppCard
              icon="🏆" name={g("careerName")} tag={g("careerTag")} text={g("careerText")}
              gradient="from-brand-500 via-orange-500 to-accent-400" onPlay={() => setView("career")} delay={0.08}
              art={<TatamiArt />}
            />
            <AppCard
              icon="🤼" name={g("randoriName")} tag={g("randoriTag")} text={g("randoriText")}
              gradient="from-sky-500 via-blue-600 to-indigo-700" onPlay={() => setView("randori")} delay={0.16}
              art={<RandoriArt />}
            />
          </ul>
        </section>

        <Leaderboard hasClub={!!me.data?.club_label} />
        <p className="text-center text-xs text-ink-400">{g("disclaimer")}</p>
      </div>
    </MotionConfig>
  );
}

function PlayerHero({ me, loading }: { me?: Me; loading: boolean }) {
  const { g, belt, grade, qualification } = useGameText();
  if (loading || !me) return <Skeleton className="h-48" />;
  const span = Math.max(1, me.level_to - me.level_from);
  const pct = Math.min(100, Math.round(((me.xp - me.level_from) / span) * 100));
  return (
    <section className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-ink-950 via-indigo-950 to-brand-800 p-6 text-white shadow-lift sm:p-8">
      <motion.div aria-hidden="true" className="pointer-events-none absolute -right-20 -top-24 h-80 w-80 rounded-full bg-fuchsia-500/30 blur-3xl"
        animate={{ scale: [1, 1.2, 1] }} transition={{ duration: 8, repeat: Infinity }} />
      <motion.div aria-hidden="true" className="pointer-events-none absolute -bottom-24 -left-10 h-72 w-72 rounded-full bg-accent-400/25 blur-3xl"
        animate={{ scale: [1.2, 1, 1.2] }} transition={{ duration: 9, repeat: Infinity }} />
      <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.25em] text-accent-200">🎮 {g("hubEyebrow")}</p>
          <h1 className="mt-1 font-display text-3xl sm:text-4xl">{g("hubTitle")}</h1>
          <p className="mt-2 max-w-xl text-white/80">{g("hubText")}</p>
        </div>
        <div className="w-full max-w-sm rounded-3xl bg-white/10 p-5 ring-1 ring-white/20 backdrop-blur">
          <div className="flex items-center gap-4">
            <motion.div whileHover={{ rotate: -6, scale: 1.05 }}
              className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-300 to-brand-500 font-display text-2xl text-ink-900 shadow-lg">
              {me.level}
              <span className="absolute -bottom-1.5 left-1/2 h-2.5 w-12 -translate-x-1/2 rounded-full ring-1 ring-black/20" style={{ backgroundColor: BELT_COLORS[me.belt] }} />
            </motion.div>
            <div className="min-w-0">
              <p className="truncate text-lg font-semibold">{me.display_name}</p>
              <p className="truncate text-xs text-white/70">{me.club_label ?? "—"} · {g("beltGame")}: {belt(me.belt)}</p>
            </div>
          </div>
          <div className="mt-4 flex justify-between text-xs text-white/75">
            <span>{g("level")} {me.level}</span><span>{me.xp} / {me.level_to} {g("xp")}</span>
          </div>
          <div className="mt-1 h-3 overflow-hidden rounded-full bg-white/15">
            <motion.div className="h-full rounded-full bg-gradient-to-r from-accent-300 to-fuchsia-400" initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 1 }} />
          </div>
          <p className="mt-3 flex items-center gap-2 text-sm">
            <BeltSwatch grade={me.grade} /> <span className="text-white/75">{g("currentGrade")}:</span> <strong>{grade(me.grade)}</strong>
          </p>
          {me.qualifications.length > 0 && (
            <p className="mt-2 flex flex-wrap gap-1.5">
              {me.qualifications.map((q) => (
                <span key={q} className="rounded-full bg-emerald-400/20 px-2.5 py-0.5 text-xs font-semibold text-emerald-100 ring-1 ring-emerald-300/40">
                  {QUALIFICATION_LABELS[q]?.icon} {qualification(q)}
                </span>
              ))}
            </p>
          )}
          <p className="mt-3 text-sm">🏅 {g("rank")} <strong className="font-display text-xl">#{me.position}</strong></p>
        </div>
      </div>
    </section>
  );
}

function AppCard({ icon, name, tag, text, gradient, onPlay, art, delay }: {
  icon: string; name: string; tag: string; text: string; gradient: string; onPlay: () => void; art: React.ReactNode; delay: number;
}) {
  const { g } = useGameText();
  return (
    <motion.li initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }}
      whileHover={{ y: -6, rotateX: 4, rotateY: -4 }} style={{ transformPerspective: 900 }}
      className="group flex flex-col overflow-hidden rounded-[2rem] bg-white shadow-soft ring-1 ring-ink-900/5 hover:shadow-lift">
      <div className={cn("relative flex h-40 items-center justify-center overflow-hidden bg-gradient-to-br text-white", gradient)}>
        <div className="pointer-events-none absolute inset-0 opacity-20 [background-image:repeating-linear-gradient(135deg,#fff_0_2px,transparent_2px_18px)]" aria-hidden="true" />
        {art}
      </div>
      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-center gap-3">
          <span className={cn("flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br text-2xl text-white shadow", gradient)}>{icon}</span>
          <div>
            <p className="font-display text-xl text-ink-900">{name}</p>
            <p className="text-xs font-semibold text-ink-500">{tag}</p>
          </div>
        </div>
        <p className="mt-3 flex-1 text-sm text-ink-600">{text}</p>
        <button type="button" onClick={onPlay}
          className={cn("mt-5 inline-flex h-12 cursor-pointer items-center justify-center gap-2 rounded-2xl bg-gradient-to-r font-bold text-white shadow-lift transition group-hover:brightness-110", gradient)}>
          ▶ {g("play")}
        </button>
      </div>
    </motion.li>
  );
}

/** Un piccolo tatami in prospettiva, con due judoka che si studiano. */
function TatamiArt() {
  return (
    <div className="relative h-32 w-56 [perspective:600px]">
      <div className="absolute inset-0 grid grid-cols-6 grid-rows-4 gap-0.5 rounded-xl bg-emerald-900/40 p-1 shadow-2xl [transform:rotateX(58deg)]">
        {Array.from({ length: 24 }, (_, i) => (
          <span key={i} className={cn("rounded-sm", (i + Math.floor(i / 6)) % 2 ? "bg-emerald-300/80" : "bg-emerald-200/80", i >= 7 && i <= 10 || i >= 13 && i <= 16 ? "bg-rose-300/80" : "")} />
        ))}
      </div>
      <motion.span className="absolute bottom-6 left-14 text-4xl drop-shadow-lg" animate={{ x: [0, 10, 0] }} transition={{ duration: 1.6, repeat: Infinity }}>🥋</motion.span>
      <motion.span className="absolute bottom-6 right-14 text-4xl drop-shadow-lg [transform:scaleX(-1)]" animate={{ x: [0, -10, 0] }} transition={{ duration: 1.6, repeat: Infinity, delay: 0.3 }}>🥋</motion.span>
    </div>
  );
}

/** Due judoka, bianco e blu, che si salutano e si afferrano (rei, kumikata). */
function RandoriArt() {
  return (
    <div className="relative flex h-32 w-56 items-end justify-center gap-1">
      <motion.span className="text-5xl drop-shadow-lg" animate={{ rotate: [0, 12, 0, 0], x: [0, 0, 8, 0] }} transition={{ duration: 2.4, repeat: Infinity }}>🥋</motion.span>
      <motion.span className="mb-10 text-3xl" animate={{ scale: [0.8, 1.2, 0.8], opacity: [0.4, 1, 0.4] }} transition={{ duration: 1.2, repeat: Infinity }} aria-hidden="true">⚡</motion.span>
      <span className="inline-block [transform:scaleX(-1)]">
        <motion.span className="inline-block text-5xl drop-shadow-lg [filter:hue-rotate(200deg)_saturate(3)]" animate={{ x: [0, 0, 8, 0] }} transition={{ duration: 2.4, repeat: Infinity, delay: 0.2 }}>🥋</motion.span>
      </span>
    </div>
  );
}

function Leaderboard({ hasClub }: { hasClub: boolean }) {
  const { g, grade } = useGameText();
  const [scope, setScope] = useState<"all" | "club" | "clubs">("all");
  const board = useQuery({
    queryKey: ["game", "leaderboard", scope === "club" ? "club" : "all"],
    queryFn: () => getJson<Board>(`/api/proxy/game/leaderboard?scope=${scope === "club" ? "club" : "all"}`),
  });
  type Scope = "all" | "club" | "clubs";
  const tabs: [Scope, string][] = [["all", `🌍 ${g("everyone")}`], ...(hasClub ? [["club", `🏯 ${g("myClub")}`] as [Scope, string]] : []), ["clubs", `🏆 ${g("clubsCup")}`]];
  return (
    <section className="rounded-[2rem] bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl text-ink-900">🏅 {g("leaderboard")}</h2>
        <div className="flex gap-1.5 rounded-full bg-ink-50 p-1">
          {tabs.map(([key, label]) => (
            <button key={key} type="button" onClick={() => setScope(key)}
              className={cn("h-9 cursor-pointer rounded-full px-4 text-sm font-semibold", scope === key ? "bg-ink-900 text-white" : "text-ink-600 hover:bg-white")}>{label}</button>
          ))}
        </div>
      </div>
      {board.isLoading ? <Skeleton className="h-48" /> : scope === "clubs" ? (
        <ol className="space-y-2">
          {(board.data?.clubs ?? []).map((c, i) => (
            <li key={c.club_label} className="flex items-center gap-3 rounded-2xl bg-ink-50 px-4 py-3">
              <span className="w-8 font-display text-xl text-ink-500">{i + 1}</span>
              <span className="min-w-0 flex-1 truncate font-semibold text-ink-900">{c.club_label}</span>
              <span className="text-xs text-ink-500">{c.players} {g("players")}</span>
              <span className="font-display text-lg text-brand-600">{c.xp} XP</span>
            </li>
          ))}
        </ol>
      ) : (board.data?.rows ?? []).length === 0 ? (
        <p className="py-8 text-center text-ink-500">{g("noPlayers")}</p>
      ) : (
        <ol className="space-y-2">
          {(board.data?.rows ?? []).map((r) => (
            <motion.li key={`${r.position}-${r.display_name}-${r.club_label}`} layout
              className={cn("flex items-center gap-3 rounded-2xl px-4 py-3", r.is_me ? "bg-accent-100 ring-2 ring-accent-300" : "bg-ink-50")}>
              <span className={cn("flex h-9 w-9 items-center justify-center rounded-full font-display",
                r.position === 1 ? "bg-accent-400 text-ink-900" : r.position === 2 ? "bg-ink-300 text-ink-900" : r.position === 3 ? "bg-amber-700 text-white" : "bg-white text-ink-600")}>{r.position}</span>
              <span title={grade(r.grade ?? r.belt)}><BeltSwatch grade={r.grade ?? r.belt} className="h-3 w-9" /></span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-semibold text-ink-900">{r.display_name}{r.is_me ? ` (${g("you")})` : ""}</span>
                <span className="block truncate text-xs text-ink-500">{r.club_label ?? "—"} · {g("level")} {r.level}</span>
              </span>
              <span className="font-display text-lg text-brand-600">{r.xp} XP</span>
            </motion.li>
          ))}
        </ol>
      )}
    </section>
  );
}
