"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { BELT_COLORS, useGameText } from "@/components/game/i18n";
import { friendlyApiError } from "@/lib/api-error";
import { cn } from "@/lib/cn";

// Dojo Academy (apps/api/app/game): i percorsi a tema e gli esami di
// cintura del gioco, a tempo. Il server sceglie domande e ordine delle
// risposte e corregge ogni risposta: qui arriva solo il testo, e la
// risposta giusta solo dopo aver risposto.

export interface QuizCard {
  id: string; kind: "TOPIC" | "EXAM"; icon: string; title: string; description: string; topic: string | null; belt: string | null;
  questions: number; seconds: number; pass_pct: number; pass_xp: number; locked: boolean; passed: boolean; best: number; max: number; attempts: number;
}
interface Started { attempt_id: string; title: string; kind: string; belt: string | null; seconds: number; pass_pct: number;
  questions: { id: string; topic: string; text: string; choices: string[] }[] }
interface Answered { correct: boolean; correct_choice: number; points: number; score: number; explanation: string; streak: number }
interface Finished { score: number; max_score: number; correct: number; total: number; pct: number; passed: boolean; pass_pct: number;
  xp_earned: number; new_belt: string | null; level: number; level_up: boolean; previous_best: number }

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}
const post = (body?: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });

const TOPIC_BG: Record<string, string> = {
  history: "from-rose-500 to-brand-700", etiquette: "from-amber-400 to-amber-700", techniques: "from-sky-500 to-indigo-700",
  rules: "from-violet-500 to-violet-800", vocabulary: "from-emerald-500 to-teal-700",
};

export function DojoAcademy({ onBack, onXpChange }: { onBack: () => void; onXpChange: () => void }) {
  const { g, lang } = useGameText();
  const { data, isLoading } = useQuery({ queryKey: ["game", "quizzes", lang], queryFn: () => call<QuizCard[]>(`/api/proxy/game/quizzes?lang=${lang}`) });
  const [playing, setPlaying] = useState<QuizCard | null>(null);
  const queryClient = useQueryClient();

  if (playing) {
    return <QuizPlayer quiz={playing} onClose={() => { setPlaying(null); void queryClient.invalidateQueries({ queryKey: ["game"] }); onXpChange(); }} />;
  }
  const topics = (data ?? []).filter((q) => q.kind === "TOPIC");
  const exams = (data ?? []).filter((q) => q.kind === "EXAM");
  return (
    <MotionConfig reducedMotion="user">
      <div className="space-y-8">
        <button type="button" onClick={onBack} className="cursor-pointer text-sm font-semibold text-brand-700 hover:underline">← {g("back")}</button>
        <section className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-indigo-600 via-violet-700 to-ink-950 p-6 text-white shadow-lift sm:p-8">
          <motion.span aria-hidden="true" className="pointer-events-none absolute -right-4 -top-6 select-none text-[9rem] leading-none opacity-20"
            animate={{ rotate: [-8, 8, -8], y: [0, -6, 0] }} transition={{ duration: 7, repeat: Infinity }}>🎓</motion.span>
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-accent-200">JAV Games</p>
          <h1 className="mt-1 font-display text-4xl">{g("academyName")}</h1>
          <p className="mt-2 max-w-xl text-white/80">{g("academyText")}</p>
        </section>
        {isLoading ? <Skeleton className="h-64" /> : (
          <>
            <section>
              <h2 className="mb-3 text-xl text-ink-900">🧭 {g("paths")}</h2>
              <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {topics.map((q, i) => (
                  <motion.li key={q.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                    <button type="button" onClick={() => setPlaying(q)}
                      className="group flex h-full w-full cursor-pointer flex-col overflow-hidden rounded-3xl bg-white text-left shadow-soft ring-1 ring-ink-900/5 transition hover:-translate-y-1 hover:shadow-lift">
                      <span className={cn("flex items-center gap-3 bg-gradient-to-br p-5 text-white", TOPIC_BG[q.topic ?? ""] ?? "from-brand-500 to-brand-700")}>
                        <motion.span className="text-4xl" whileHover={{ scale: 1.2, rotate: 8 }}>{q.icon}</motion.span>
                        <span className="font-display text-xl leading-tight">{q.title}</span>
                      </span>
                      <span className="flex flex-1 flex-col gap-3 p-5">
                        <span className="text-sm text-ink-600">{q.description}</span>
                        <span className="mt-auto flex items-center justify-between text-xs text-ink-500">
                          <span>⏱ {q.questions} {g("questions")} · {q.seconds}{g("seconds")}</span>
                          {q.attempts > 0 && <span className="font-semibold text-brand-700">🏅 {g("best")} {q.best}</span>}
                        </span>
                        {q.max > 0 && (
                          <span className="h-2 overflow-hidden rounded-full bg-ink-100"><span className="block h-full rounded-full bg-gradient-to-r from-accent-400 to-brand-500" style={{ width: `${Math.min(100, (q.best / q.max) * 100)}%` }} /></span>
                        )}
                      </span>
                    </button>
                  </motion.li>
                ))}
              </ul>
            </section>
            <section>
              <h2 className="mb-3 text-xl text-ink-900">🎖️ {g("exams")}</h2>
              <ol className="relative grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {exams.map((q, i) => (
                  <motion.li key={q.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
                    <button type="button" disabled={q.locked} onClick={() => setPlaying(q)}
                      className={cn("flex w-full items-center gap-4 rounded-3xl p-4 text-left ring-2 transition",
                        q.locked ? "cursor-not-allowed bg-ink-50 opacity-60 ring-ink-100" : "cursor-pointer bg-white shadow-soft ring-ink-900/5 hover:-translate-y-0.5 hover:ring-accent-300",
                        q.passed && "ring-emerald-300")}>
                      <span className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl shadow-inner ring-1 ring-ink-900/10" style={{ backgroundColor: BELT_COLORS[q.belt ?? "WHITE"] }}>
                        <span className="h-3 w-full bg-ink-900/20" />
                        {q.passed && <span className="absolute -right-2 -top-2 rounded-full bg-emerald-500 px-1.5 text-xs text-white shadow">✓</span>}
                        {q.locked && <span className="absolute -right-2 -top-2 text-lg">🔒</span>}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block font-semibold text-ink-900">{q.title}</span>
                        <span className="block text-xs text-ink-500">
                          {q.locked ? g("locked") : q.passed ? `✅ ${g("passed")}` : `${q.questions} ${g("questions")} · ≥ ${q.pass_pct}% · +${q.pass_xp} XP`}
                        </span>
                      </span>
                    </button>
                  </motion.li>
                ))}
              </ol>
            </section>
          </>
        )}
      </div>
    </MotionConfig>
  );
}

/** Il quiz: una domanda alla volta, il tempo che scorre, la risposta che
 *  si colora, la spiegazione, e alla fine il risultato con l'XP. */
function QuizPlayer({ quiz, onClose }: { quiz: QuizCard; onClose: () => void }) {
  const { g, belt, lang } = useGameText();
  const toast = useToast();
  const [run, setRun] = useState<Started | null>(null);
  const [index, setIndex] = useState(0);
  const [result, setResult] = useState<Answered | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [done, setDone] = useState<Finished | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(0);
  const [startedAt, setStartedAt] = useState(0);
  const [score, setScore] = useState(0);
  const answering = useRef(false);

  const q = run?.questions[index];
  const limit = (run?.seconds ?? quiz.seconds) * 1000;
  const elapsed = q && !result ? Math.min(limit, now - startedAt) : 0;
  const left = Math.max(0, limit - elapsed);

  async function begin() {
    setBusy(true);
    try {
      const started = await call<Started>(`/api/proxy/game/quizzes/${quiz.id}/start?lang=${lang}`, post());
      setRun(started);
      setIndex(0);
      setResult(null);
      setPicked(null);
      setDone(null);
      setScore(0);
      const t = performance.now();
      setStartedAt(t);
      setNow(t);
    } catch (e) {
      toast({ tone: "error", title: g("error"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function choose(choice: number | null) {
    if (!run || !q || result || answering.current) return;
    answering.current = true;
    setPicked(choice);
    try {
      const res = await call<Answered>(`/api/proxy/game/attempts/${run.attempt_id}/answer`, post({
        question_id: q.id, choice, ms: Math.round(performance.now() - startedAt),
      }));
      setResult(res);
      setScore(res.score);
    } catch (e) {
      toast({ tone: "error", title: g("error"), text: (e as Error).message });
    } finally {
      answering.current = false;
    }
  }

  // L'orologio: un tick ogni 100 ms finché la domanda è aperta; a zero, «tempo scaduto».
  useEffect(() => {
    if (!q || result) return;
    const id = window.setInterval(() => {
      const t = performance.now();
      setNow(t);
      if (t - startedAt >= limit) void choose(null);
    }, 100);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q?.id, result, limit, startedAt]);

  async function next() {
    if (!run) return;
    if (index + 1 < run.questions.length) {
      setIndex(index + 1);
      setResult(null);
      setPicked(null);
      const t = performance.now();
      setStartedAt(t);
      setNow(t);
      return;
    }
    setBusy(true);
    try {
      setDone(await call<Finished>(`/api/proxy/game/attempts/${run.attempt_id}/finish`, post()));
    } catch (e) {
      toast({ tone: "error", title: g("error"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <MotionConfig reducedMotion="user">
      <div className="mx-auto max-w-3xl space-y-5">
        <button type="button" onClick={onClose} className="cursor-pointer text-sm font-semibold text-brand-700 hover:underline">← {g("backToAcademy")}</button>
        <div className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-ink-900 via-indigo-900 to-violet-800 p-5 text-white shadow-lift sm:p-8">
          <div className="pointer-events-none absolute -left-16 -top-16 h-56 w-56 rounded-full bg-accent-400/25 blur-3xl" aria-hidden="true" />
          <div className="relative flex flex-wrap items-center justify-between gap-3">
            <p className="flex items-center gap-2 font-display text-xl"><span className="text-2xl">{quiz.icon}</span>{quiz.title}</p>
            {run && !done && (
              <p className="rounded-full bg-white/15 px-3 py-1 text-sm font-semibold">
                {g("question")} {index + 1} {g("of")} {run.questions.length} · ⭐ {score}
              </p>
            )}
          </div>

          <AnimatePresence mode="wait">
            {!run ? (
              <motion.div key="ready" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} className="relative py-10 text-center">
                <motion.p className="text-6xl" animate={{ y: [0, -10, 0] }} transition={{ duration: 1.6, repeat: Infinity }}>🥋</motion.p>
                <h2 className="mt-4 font-display text-3xl">{g("ready")}</h2>
                <p className="mx-auto mt-2 max-w-md text-white/80">{g("readyText")}</p>
                <p className="mt-2 text-sm text-white/70">⏱ {quiz.questions} {g("questions")} · {quiz.seconds}{g("seconds")}{quiz.kind === "EXAM" ? ` · ≥ ${quiz.pass_pct}%` : ""}</p>
                <button type="button" onClick={begin} disabled={busy}
                  className="mt-6 inline-flex h-14 cursor-pointer items-center rounded-2xl bg-accent-400 px-8 text-lg font-bold text-ink-900 shadow-lift transition hover:-translate-y-0.5 hover:bg-accent-300 disabled:opacity-60">
                  {g("start")} →
                </button>
              </motion.div>
            ) : done ? (
              <ResultView key="done" done={done} beltName={done.new_belt ? belt(done.new_belt) : null} onRetry={begin} onClose={onClose} busy={busy} />
            ) : q ? (
              <motion.div key={q.id} initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }} transition={{ duration: 0.3 }} className="relative mt-5">
                <div className="h-3 overflow-hidden rounded-full bg-white/15">
                  <div className={cn("h-full rounded-full transition-[width] duration-100 ease-linear", left < limit * 0.25 ? "bg-rose-400" : "bg-gradient-to-r from-emerald-400 to-accent-300")}
                    style={{ width: `${(left / limit) * 100}%` }} />
                </div>
                <p className="mt-1 text-right text-xs font-semibold text-white/70">{Math.ceil(left / 1000)} s</p>
                <h2 className="mt-3 text-2xl font-semibold leading-snug sm:text-3xl">{q.text}</h2>
                <ul className="mt-6 grid gap-3 sm:grid-cols-2">
                  {q.choices.map((c, i) => {
                    const isRight = result && result.correct_choice === i;
                    const isWrongPick = result && picked === i && !result.correct;
                    return (
                      <motion.li key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 * i }}>
                        <motion.button type="button" disabled={!!result} onClick={() => choose(i)}
                          whileTap={{ scale: 0.97 }}
                          animate={isWrongPick ? { x: [0, -8, 8, -6, 6, 0] } : isRight ? { scale: [1, 1.05, 1] } : {}}
                          className={cn("flex min-h-[4rem] w-full cursor-pointer items-center gap-3 rounded-2xl px-4 py-3 text-left text-base font-semibold ring-2 transition",
                            !result && "bg-white/10 ring-white/20 hover:bg-white/20",
                            isRight && "bg-emerald-500 text-white ring-emerald-300",
                            isWrongPick && "bg-rose-500 text-white ring-rose-300",
                            result && !isRight && !isWrongPick && "bg-white/5 text-white/50 ring-white/10")}>
                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white/15 font-display">{"ABCD"[i]}</span>
                          {c}
                        </motion.button>
                      </motion.li>
                    );
                  })}
                </ul>
                <AnimatePresence>
                  {result && (
                    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="mt-5 rounded-2xl bg-white/10 p-4 ring-1 ring-white/20">
                      <p className="text-lg font-bold">
                        {result.correct ? `✅ ${g("right")} +${result.points} ${g("points")}` : picked === null ? `⏰ ${g("timeUp")}` : `❌ ${g("wrong")}`}
                        {result.streak >= 3 && <span className="ml-2 text-accent-300">🔥 {result.streak} {g("streak")}</span>}
                      </p>
                      <p className="mt-1 text-sm text-white/85">{result.explanation}</p>
                      <button type="button" onClick={next} disabled={busy}
                        className="mt-4 inline-flex h-12 cursor-pointer items-center rounded-2xl bg-accent-400 px-6 font-bold text-ink-900 hover:bg-accent-300 disabled:opacity-60">
                        {index + 1 < run.questions.length ? `${g("next")} →` : `${g("finish")} 🏁`}
                      </button>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </div>
    </MotionConfig>
  );
}

function ResultView({ done, beltName, onRetry, onClose, busy }: { done: Finished; beltName: string | null; onRetry: () => void; onClose: () => void; busy: boolean }) {
  const { g } = useGameText();
  return (
    <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="relative py-8 text-center">
      {done.passed && Array.from({ length: 18 }, (_, i) => (
        <motion.span key={i} aria-hidden="true" className="pointer-events-none absolute left-1/2 top-16 text-2xl"
          initial={{ x: 0, y: 0, opacity: 1 }} animate={{ x: (i - 9) * 28, y: [0, -120 - (i % 4) * 30, 120], opacity: [1, 1, 0], rotate: i * 40 }}
          transition={{ duration: 1.8, ease: "easeOut" }}>{["🎉", "⭐", "🥋", "🏆"][i % 4]}</motion.span>
      ))}
      <p className="text-6xl">{done.passed ? "🏆" : "💪"}</p>
      <h2 className="mt-3 font-display text-3xl">{done.passed ? g("resultPassed") : g("resultFailed")}</h2>
      <p className="mt-2 font-display text-6xl">{done.pct}%</p>
      <p className="text-white/80">{done.correct}/{done.total} · {done.score} {g("points")}{!done.passed ? ` · ${g("needed")} ${done.pass_pct}%` : ""}</p>
      <div className="mx-auto mt-5 flex max-w-sm flex-wrap justify-center gap-2">
        <span className="rounded-full bg-accent-400 px-4 py-2 font-bold text-ink-900">+{done.xp_earned} {g("xpEarned")}</span>
        {done.level_up && <motion.span animate={{ scale: [1, 1.15, 1] }} transition={{ repeat: 3, duration: 0.6 }} className="rounded-full bg-emerald-400 px-4 py-2 font-bold text-ink-900">⬆ {g("levelUp")} {done.level}</motion.span>}
      </div>
      {beltName && <p className="mt-4 text-lg font-semibold text-accent-200">🎖️ {g("newBelt")} {beltName}!</p>}
      {done.xp_earned === 0 && <p className="mt-3 text-sm text-white/70">{g("noNewXp")}</p>}
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <button type="button" onClick={onRetry} disabled={busy} className="inline-flex h-12 cursor-pointer items-center rounded-2xl bg-white/15 px-6 font-semibold ring-1 ring-white/30 hover:bg-white/25">↻ {g("retry")}</button>
        <button type="button" onClick={onClose} className="inline-flex h-12 cursor-pointer items-center rounded-2xl bg-accent-400 px-6 font-bold text-ink-900 hover:bg-accent-300">{g("backToAcademy")}</button>
      </div>
    </motion.div>
  );
}
