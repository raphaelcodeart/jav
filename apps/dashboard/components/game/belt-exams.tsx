"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { BeltSwatch, beltBackground } from "@/components/game/belt";
import { downloadDiploma, type Diploma } from "@/components/game/diploma";
import type { QuizCard } from "@/components/game/dojo-academy";
import { GAME_INTL, useGameText } from "@/components/game/i18n";
import { cn } from "@/lib/cn";

// Gli esami di grado della Dojo Academy: in alto i numeri del judoka, poi la
// rastrelliera con tutte le cinture (dalla bianca-gialla al 10° dan) da
// scorrere, e sotto la scheda della cintura scelta con il programma, i
// risultati salvati di ogni tentativo e il diploma.

const isDan = (grade: string | null) => /^(BLACK|DAN)/.test(grade ?? "");

export function BeltExams({ exams, next, diplomas, name, onPlay }: {
  exams: QuizCard[]; next: QuizCard | null; diplomas: Diploma[]; name: string; onPlay: (q: QuizCard) => void;
}) {
  const { g, grade, lang } = useGameText();
  const [picked, setPicked] = useState<string | null>(null);
  const rack = useRef<HTMLOListElement>(null);
  const lastPassed = [...exams].reverse().find((q) => q.passed) ?? null;
  const selected = exams.find((q) => q.id === picked) ?? next ?? lastPassed ?? exams[0] ?? null;
  const passed = exams.filter((q) => q.passed);
  const average = passed.length ? Math.round(passed.reduce((n, q) => n + (q.passed_pct ?? 0), 0) / passed.length) : 0;
  const attempts = exams.reduce((n, q) => n + q.attempts, 0);
  const startId = next?.id ?? lastPassed?.id;

  // All'apertura la rastrelliera scorre fino al prossimo esame (solo DOM, niente stato).
  useEffect(() => {
    if (!startId) return;
    rack.current?.querySelector<HTMLElement>(`[data-exam="${startId}"]`)?.scrollIntoView({ inline: "center", block: "nearest" });
  }, [startId]);

  const scroll = (dir: number) => rack.current?.scrollBy({ left: dir * rack.current.clientWidth * 0.8, behavior: "smooth" });

  return (
    <div className="space-y-5">
      <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat icon="🎖️" label={g("statPassed")} value={`${passed.length}/${exams.length}`} pct={exams.length ? passed.length / exams.length : 0} />
        <Stat icon="📊" label={g("statAverage")} value={passed.length ? `${average}%` : "—"} pct={average / 100} />
        <Stat icon="🔁" label={g("statAttempts")} value={String(attempts)} />
        <Stat icon="🎯" label={g("statNext")} value={next ? grade(next.belt ?? "") : "🏆"} belt={next?.belt ?? undefined} />
      </ul>

      <section className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-ink-950 via-ink-900 to-indigo-950 p-5 text-white shadow-lift sm:p-6">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-accent-400/15 blur-3xl" aria-hidden="true" />
        <div className="relative flex items-end justify-between gap-3">
          <div>
            <h2 className="font-display text-2xl">🥋 {g("beltRack")}</h2>
            <p className="text-sm text-white/65">{g("beltRackText")}</p>
          </div>
          <div className="hidden gap-2 sm:flex">
            <button type="button" onClick={() => scroll(-1)} aria-label={g("scrollLeft")}
              className="h-10 w-10 cursor-pointer rounded-full bg-white/10 text-lg ring-1 ring-white/20 hover:bg-white/20">←</button>
            <button type="button" onClick={() => scroll(1)} aria-label={g("scrollRight")}
              className="h-10 w-10 cursor-pointer rounded-full bg-white/10 text-lg ring-1 ring-white/20 hover:bg-white/20">→</button>
          </div>
        </div>
        <ol ref={rack} className="relative mt-5 flex snap-x snap-mandatory gap-3 overflow-x-auto pb-3 [scrollbar-width:thin]">
          {exams.map((q, i) => {
            const active = selected?.id === q.id;
            const isNext = next?.id === q.id;
            const firstDan = isDan(q.belt) && !isDan(exams[i - 1]?.belt ?? null);
            return (
              <li key={q.id} data-exam={q.id} className="flex shrink-0 snap-center items-stretch gap-3">
                {firstDan && <span className="my-4 w-px bg-white/20" aria-hidden="true" />}
                <motion.button type="button" onClick={() => setPicked(q.id)} whileHover={{ y: -4 }} whileTap={{ scale: 0.97 }}
                  aria-pressed={active}
                  className={cn("relative flex w-28 cursor-pointer flex-col items-center gap-2 rounded-2xl px-2 pb-3 pt-4 text-center ring-1 transition sm:w-32",
                    active ? "bg-white text-ink-900 ring-2 ring-accent-300 shadow-lift" : "bg-white/[0.06] ring-white/10 hover:bg-white/10",
                    q.locked && !active && "opacity-45")}>
                  {isNext && !active && (
                    <motion.span aria-hidden="true" className="absolute inset-0 rounded-2xl ring-2 ring-accent-300"
                      animate={{ opacity: [0.2, 1, 0.2] }} transition={{ duration: 2, repeat: Infinity }} />
                  )}
                  <span className="relative flex h-16 w-16 items-center justify-center">
                    <motion.span className="absolute h-5 w-16 rounded-md shadow-md ring-1 ring-black/20" style={{ background: beltBackground(q.belt ?? "WHITE") }}
                      animate={active ? { rotate: [-4, 4, -4] } : { rotate: 0 }} transition={{ duration: 3, repeat: active ? Infinity : 0 }} />
                    <span className="absolute h-9 w-4 rounded-sm shadow ring-1 ring-black/20" style={{ background: beltBackground(q.belt ?? "WHITE") }} />
                  </span>
                  <span className={cn("text-xs font-bold leading-tight", active ? "text-ink-900" : "text-white")}>{grade(q.belt ?? "")}</span>
                  <span className={cn("text-[0.65rem]", active ? "text-ink-500" : "text-white/55")}>{q.questions} {g("questions")}</span>
                  <span className={cn("mt-auto rounded-full px-2 py-0.5 text-[0.65rem] font-bold",
                    q.passed ? "bg-emerald-400 text-ink-900" : isNext ? "bg-accent-400 text-ink-900" : q.locked ? "bg-white/10 text-white/60" : "bg-white/15 text-white",
                    active && !q.passed && !isNext && "bg-ink-100 text-ink-600")}>
                    {q.passed ? `✓ ${q.passed_pct}%` : isNext ? g("nextBadge") : q.locked ? "🔒" : q.best_pct ? `${q.best_pct}%` : "—"}
                  </span>
                </motion.button>
              </li>
            );
          })}
        </ol>
      </section>

      <AnimatePresence mode="wait">
        {selected && (
          <ExamDetail key={selected.id} q={selected} isNext={next?.id === selected.id} name={name}
            diploma={diplomas.find((d) => d.kind === "GRADE" && d.code === selected.belt) ?? null} onPlay={onPlay} lang={lang} />
        )}
      </AnimatePresence>
    </div>
  );
}

function Stat({ icon, label, value, pct, belt }: { icon: string; label: string; value: string; pct?: number; belt?: string }) {
  return (
    <li className="rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
      <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ink-500"><span aria-hidden="true">{icon}</span>{label}</p>
      <p className="mt-1 flex items-center gap-2 truncate font-display text-2xl text-ink-900">{belt && <BeltSwatch grade={belt} className="h-3 w-9" />}{value}</p>
      {pct !== undefined && (
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink-100">
          <motion.div className="h-full rounded-full bg-gradient-to-r from-accent-400 to-emerald-500" initial={{ width: 0 }} animate={{ width: `${Math.min(100, pct * 100)}%` }} transition={{ duration: 0.8 }} />
        </div>
      )}
    </li>
  );
}

function ExamDetail({ q, isNext, name, diploma, onPlay, lang }: {
  q: QuizCard; isNext: boolean; name: string; diploma: Diploma | null; onPlay: (q: QuizCard) => void; lang: "pt" | "it" | "en";
}) {
  const { g, grade } = useGameText();
  const date = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString(GAME_INTL[lang], { day: "numeric", month: "short", year: "numeric" });
  const lockReason = q.lock_reason?.split(":")[1];
  return (
    <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.25 }}
      className="grid overflow-hidden rounded-[2rem] bg-white shadow-soft ring-1 ring-ink-900/5 lg:grid-cols-[1.1fr_1fr]">
      <div className="relative p-6">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-2" style={{ background: beltBackground(q.belt ?? "WHITE") }} aria-hidden="true" />
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-ink-400">{isDan(q.belt) ? "Dan" : "Kyu"}{q.jp ? ` · ${q.jp}` : ""}</p>
        <h3 className="mt-1 flex items-center gap-3 font-display text-3xl text-ink-900"><BeltSwatch grade={q.belt ?? "WHITE"} className="h-5 w-16" />{q.title}</h3>
        {q.focus && <p className="mt-3 text-ink-600"><strong className="text-ink-800">{g("programme")}:</strong> {q.focus}</p>}
        <ul className="mt-4 flex flex-wrap gap-2 text-sm">
          {[`📝 ${q.questions} ${g("questions")}`, `⏱ ${q.seconds}${g("seconds")}`, `🎯 ≥ ${q.pass_pct}%`, `⭐ +${q.pass_xp} XP`].map((c) => (
            <li key={c} className="rounded-full bg-ink-50 px-3 py-1 font-semibold text-ink-700 ring-1 ring-ink-900/5">{c}</li>
          ))}
        </ul>
        <div className="mt-6 flex flex-wrap gap-3">
          {q.locked ? (
            <p className="rounded-2xl bg-ink-50 px-4 py-3 text-sm text-ink-600">🔒 {g("needGrade")} {grade(lockReason ?? "")}</p>
          ) : (
            <button type="button" onClick={() => onPlay(q)}
              className={cn("inline-flex h-12 cursor-pointer items-center rounded-2xl px-6 font-bold transition hover:-translate-y-0.5",
                q.passed ? "bg-ink-900 text-white hover:bg-ink-800" : "bg-accent-400 text-ink-900 shadow-lift hover:bg-accent-300")}>
              {q.passed ? `↻ ${g("retakeExam")}` : `${g("takeExam")} →`}
            </button>
          )}
          {diploma && (
            <button type="button" onClick={() => downloadDiploma(diploma, { name, label: grade(diploma.code), lang })}
              className="inline-flex h-12 cursor-pointer items-center rounded-2xl bg-amber-50 px-5 font-semibold text-amber-800 ring-1 ring-amber-200 hover:bg-amber-100">
              📜 ⬇ Diploma
            </button>
          )}
        </div>
      </div>
      <div className="border-t border-ink-100 bg-ink-50/60 p-6 lg:border-l lg:border-t-0">
        <h4 className="text-sm font-bold uppercase tracking-wide text-ink-500">{g("yourResults")}</h4>
        {q.attempts === 0 ? <p className="mt-3 text-sm text-ink-500">{g("noAttempts")}</p> : (
          <>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <Result label={g("passedOn")} value={q.passed_on ? date(q.passed_on) : "—"} sub={q.passed_pct != null ? `${q.passed_pct}%` : undefined} good={!!q.passed_on} />
              <Result label={g("bestResult")} value={`${q.best_pct}%`} sub={`${q.best} ${g("points")}`} />
              <Result label={g("statAttempts")} value={String(q.attempts)} />
            </div>
            <p className="mt-5 text-xs font-semibold text-ink-500">{g("history")}</p>
            <div className="relative mt-2 flex h-32 items-end gap-2 rounded-2xl bg-white p-3 ring-1 ring-ink-900/5">
              <span className="pointer-events-none absolute inset-x-3 border-t-2 border-dashed border-accent-400" style={{ bottom: `calc(0.75rem + ${q.pass_pct}% * 0.8)` }} aria-hidden="true">
                <span className="absolute -top-4 right-0 text-[0.6rem] font-bold text-accent-600">{g("passMark")} {q.pass_pct}%</span>
              </span>
              {q.history.map((h, i) => (
                <div key={i} className="flex flex-1 flex-col items-center justify-end gap-1" title={`${date(h.on)} · ${h.pct}%`}>
                  <span className="text-[0.6rem] font-bold text-ink-600">{h.pct}</span>
                  <motion.span className={cn("w-full max-w-8 rounded-t-md", h.passed ? "bg-emerald-500" : "bg-rose-400")}
                    initial={{ height: 0 }} animate={{ height: `${Math.max(4, h.pct * 0.8)}%` }} transition={{ delay: i * 0.05, duration: 0.4 }}
                    style={{ minHeight: 3 }} />
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </motion.section>
  );
}

function Result({ label, value, sub, good }: { label: string; value: string; sub?: string; good?: boolean }) {
  return (
    <div className={cn("rounded-2xl bg-white p-3 ring-1", good ? "ring-emerald-200" : "ring-ink-900/5")}>
      <p className="text-[0.65rem] font-semibold uppercase text-ink-500">{label}</p>
      <p className={cn("mt-1 font-display text-lg leading-tight", good ? "text-emerald-700" : "text-ink-900")}>{value}</p>
      {sub && <p className="text-xs text-ink-500">{sub}</p>}
    </div>
  );
}
