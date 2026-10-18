"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { BeltSwatch } from "@/components/game/belt";
import { BeltExams } from "@/components/game/belt-exams";
import { MedalCase, type Diploma } from "@/components/game/diploma";
import { QUALIFICATION_LABELS, useGameText } from "@/components/game/i18n";
import { friendlyApiError } from "@/lib/api-error";
import { cn } from "@/lib/cn";

// Dojo Academy (apps/api/app/game): gli esami di grado (mezze cinture fino
// alla marrone, poi i dan fino al 10°), i corsi che danno le qualifiche
// (arbitraggio, arbitro, treinador di 1° livello) e i percorsi a tema, a tempo. Il server sceglie domande e ordine delle
// risposte e corregge ogni risposta: qui arriva solo il testo, e la
// risposta giusta solo dopo aver risposto.

export interface QuizCard {
  id: string; kind: "TOPIC" | "EXAM" | "COURSE"; icon: string; title: string; description: string; topic: string | null; belt: string | null;
  questions: number; seconds: number; pass_pct: number; pass_xp: number; locked: boolean; lock_reason: string | null; passed: boolean;
  best: number; max: number; attempts: number; group: string | null; qualification: string | null; min_grade: string | null; jp: string | null;
  focus: string | null; history: { pct: number; score: number; passed: boolean; on: string }[]; best_pct: number;
  passed_on: string | null; passed_pct: number | null;
}
interface AcademyMe { grade: string; qualifications: string[]; display_name: string; diplomas: Diploma[] }
interface Started { attempt_id: string; title: string; kind: string; belt: string | null; seconds: number; pass_pct: number;
  questions: { id: string; topic: string; text: string; choices: string[] }[] }
interface Answered { correct: boolean; correct_choice: number; points: number; score: number; explanation: string; streak: number }
interface Finished { score: number; max_score: number; correct: number; total: number; pct: number; passed: boolean; pass_pct: number;
  xp_earned: number; new_belt: string | null; new_qualification: string | null; level: number; level_up: boolean; previous_best: number }

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}
const post = (body?: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });

const TOPIC_BG: Record<string, string> = {
  history: "from-rose-500 to-brand-700", etiquette: "from-amber-400 to-amber-700", techniques: "from-sky-500 to-indigo-700",
  rules: "from-violet-500 to-violet-800", vocabulary: "from-emerald-500 to-teal-700", kata: "from-ink-700 to-ink-950",
  pt_history: "from-emerald-600 to-rose-600", fpj_rules: "from-sky-600 to-sky-900",
};

type Tab = "grades" | "courses" | "paths";
const QUALS = ["REF_COURSE", "REFEREE", "COACH1"] as const;

/** Il motivo per cui un quiz è chiuso, in parole («Serve la cintura verde»). */
function useLockText() {
  const { g, grade, qualification } = useGameText();
  return (reason: string | null) => {
    if (!reason) return g("locked");
    const [kind, code = ""] = reason.split(":");
    return kind === "QUAL" ? `${g("needQual")} ${qualification(code)}` : `${g("needGrade")} ${grade(code)}`;
  };
}

export function DojoAcademy({ onBack, onXpChange }: { onBack: () => void; onXpChange: () => void }) {
  const { g, grade, lang } = useGameText();
  const { data, isLoading } = useQuery({ queryKey: ["game", "quizzes", lang], queryFn: () => call<QuizCard[]>(`/api/proxy/game/quizzes?lang=${lang}`) });
  const me = useQuery({ queryKey: ["game", "me"], queryFn: () => call<AcademyMe>("/api/proxy/game/me") });
  const [playing, setPlaying] = useState<QuizCard | null>(null);
  const [tab, setTab] = useState<Tab>("grades");
  const queryClient = useQueryClient();

  if (playing) {
    return <QuizPlayer quiz={playing} onClose={() => { setPlaying(null); void queryClient.invalidateQueries({ queryKey: ["game"] }); onXpChange(); }} />;
  }
  const all = data ?? [];
  const topics = all.filter((q) => q.kind === "TOPIC");
  const exams = all.filter((q) => q.kind === "EXAM");
  const courses = all.filter((q) => q.kind === "COURSE");
  const current = me.data?.grade ?? "WHITE";
  const nextExam = exams.find((q) => !q.passed && !q.locked) ?? null;
  const passedCount = exams.filter((q) => q.passed).length;
  const tabs: [Tab, string][] = [["grades", `🎖️ ${g("tabGrades")}`], ["courses", `🎓 ${g("tabCourses")}`], ["paths", `🧭 ${g("tabPaths")}`]];
  return (
    <MotionConfig reducedMotion="user">
      <div className="space-y-6">
        <button type="button" onClick={onBack} className="cursor-pointer text-sm font-semibold text-brand-700 hover:underline">← {g("back")}</button>
        <section className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-ink-950 via-indigo-950 to-violet-900 p-6 text-white shadow-lift sm:p-8">
          <motion.span aria-hidden="true" className="pointer-events-none absolute -right-4 -top-6 select-none text-[9rem] leading-none opacity-10"
            animate={{ rotate: [-6, 6, -6] }} transition={{ duration: 9, repeat: Infinity }}>🎓</motion.span>
          <div className="relative grid gap-6 lg:grid-cols-[1fr_minmax(0,26rem)] lg:items-center">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-accent-200">JAV Games</p>
              <h1 className="mt-1 font-display text-4xl">{g("academyName")}</h1>
              <p className="mt-2 max-w-xl text-white/80">{g("academyText")}</p>
            </div>
            <div className="rounded-3xl bg-white/[0.07] p-5 ring-1 ring-white/15 backdrop-blur">
              <p className="text-[0.7rem] font-bold uppercase tracking-[0.2em] text-white/60">{g("passbook")}</p>
              <div className="mt-3 flex items-center gap-4">
                <BeltSwatch grade={current} className="h-7 w-24" />
                <div className="min-w-0">
                  <p className="text-xs text-white/60">{g("currentGrade")}</p>
                  <p className="truncate font-display text-2xl leading-tight">{grade(current)}</p>
                </div>
              </div>
              <div className="mt-4 flex justify-between text-xs text-white/70">
                <span>{g("gradeOf")} {passedCount} / {exams.length || 20}</span>
                {nextExam ? <span>{g("nextExam")}: {nextExam.questions} {g("questions")}</span> : passedCount > 0 && <span>🏆</span>}
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/15">
                <motion.div className="h-full rounded-full bg-gradient-to-r from-accent-300 to-emerald-400" initial={{ width: 0 }}
                  animate={{ width: `${exams.length ? (passedCount / exams.length) * 100 : 0}%` }} transition={{ duration: 0.8 }} />
              </div>
              {nextExam ? (
                <button type="button" onClick={() => setPlaying(nextExam)}
                  className="mt-4 flex w-full cursor-pointer items-center justify-between gap-3 rounded-2xl bg-accent-400 px-4 py-3 text-left font-bold text-ink-900 transition hover:bg-accent-300">
                  <span className="flex min-w-0 items-center gap-3"><BeltSwatch grade={nextExam.belt ?? "WHITE"} /><span className="truncate">{nextExam.title}</span></span>
                  <span aria-hidden="true">→</span>
                </button>
              ) : passedCount > 0 && <p className="mt-4 text-sm font-semibold text-accent-200">{g("allGrades")}</p>}
              <p className="mt-5 text-[0.7rem] font-bold uppercase tracking-[0.2em] text-white/60">{g("qualifications")}</p>
              <ul className="mt-2 grid grid-cols-3 gap-2">
                {QUALS.map((code) => <QualificationBadge key={code} code={code} earned={me.data?.qualifications.includes(code) ?? false} />)}
              </ul>
            </div>
          </div>
        </section>

        <div role="tablist" className="flex gap-1 overflow-x-auto rounded-2xl bg-ink-100 p-1">
          {tabs.map(([key, label]) => (
            <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
              className={cn("min-h-11 flex-1 cursor-pointer whitespace-nowrap rounded-xl px-4 text-sm font-semibold transition",
                tab === key ? "bg-white text-ink-900 shadow-soft" : "text-ink-600 hover:text-ink-900")}>{label}</button>
          ))}
        </div>

        {isLoading ? <Skeleton className="h-64" /> : tab === "grades" ? (
          <div className="space-y-6">
            <BeltExams exams={exams} next={nextExam} diplomas={me.data?.diplomas ?? []} name={me.data?.display_name ?? ""} onPlay={setPlaying} />
            {me.data && <MedalCase diplomas={me.data.diplomas} name={me.data.display_name} />}
          </div>
        ) : tab === "courses" ? (
          <div className="space-y-6">
            <CoursePath title={`🧑‍⚖️ ${g("refPath")}`} text={g("refPathText")} cards={courses.filter((q) => q.group === "referee")} onPlay={setPlaying} />
            <CoursePath title={`🎓 ${g("coachPath")}`} text={g("coachPathText")} cards={courses.filter((q) => q.group === "coach1")} onPlay={setPlaying}
              qualification={me.data?.qualifications.includes("COACH1") ?? false} grid />
          </div>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {topics.map((q, i) => (
              <motion.li key={q.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
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
        )}
      </div>
    </MotionConfig>
  );
}

function QualificationBadge({ code, earned }: { code: string; earned: boolean }) {
  const { g, qualification } = useGameText();
  return (
    <li className={cn("flex flex-col items-center gap-1 rounded-2xl px-2 py-2.5 text-center ring-1",
      earned ? "bg-emerald-400/15 ring-emerald-300/50" : "bg-white/5 ring-white/10 opacity-70")}>
      <span className={cn("text-2xl", !earned && "grayscale")} aria-hidden="true">{QUALIFICATION_LABELS[code]?.icon}</span>
      <span className="text-[0.7rem] font-semibold leading-tight">{qualification(code)}</span>
      <span className={cn("text-[0.65rem]", earned ? "text-emerald-200" : "text-white/50")}>{earned ? `✓ ${g("earned")}` : g("notYet")}</span>
    </li>
  );
}

/** Un percorso di corsi: l'arbitraggio (due corsi in fila) o il treinador (9 moduli). */
function CoursePath({ title, text, cards, onPlay, qualification, grid }: {
  title: string; text: string; cards: QuizCard[]; onPlay: (q: QuizCard) => void; qualification?: boolean; grid?: boolean;
}) {
  const { g } = useGameText();
  const lockText = useLockText();
  const done = cards.filter((c) => c.passed).length;
  return (
    <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg text-ink-900">{title}</h2>
          <p className="mt-1 text-sm text-ink-500">{text}</p>
        </div>
        {grid && (
          <span className={cn("shrink-0 rounded-full px-3 py-1 text-sm font-bold", qualification ? "bg-emerald-100 text-emerald-700" : "bg-ink-100 text-ink-700")}>
            {qualification ? `✓ ${g("earned")}` : `${done}/${cards.length} ${g("modulesDone")}`}
          </span>
        )}
      </div>
      {grid && (
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-ink-100">
          <div className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-brand-500" style={{ width: `${cards.length ? (done / cards.length) * 100 : 0}%` }} />
        </div>
      )}
      <ul className={cn("mt-4 grid gap-3", grid ? "sm:grid-cols-2 lg:grid-cols-3" : "sm:grid-cols-2")}>
        {cards.map((q) => (
          <li key={q.id}>
            <button type="button" disabled={q.locked} onClick={() => onPlay(q)}
              className={cn("flex h-full w-full items-start gap-3 rounded-2xl p-4 text-left ring-1 transition",
                q.locked ? "cursor-not-allowed bg-ink-50 ring-transparent opacity-70" : "cursor-pointer bg-white ring-ink-900/10 hover:-translate-y-0.5 hover:shadow-soft",
                q.passed && "bg-emerald-50 ring-emerald-200")}>
              <span className="text-3xl" aria-hidden="true">{q.icon}</span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold text-ink-900">{q.title}</span>
                {!grid && <span className="mt-0.5 block text-xs text-ink-500">{q.description}</span>}
                <span className="mt-1 block text-xs text-ink-500">
                  {q.passed ? `✓ ${g("passed")} · ${g("best")} ${q.best}` : q.locked ? `🔒 ${lockText(q.lock_reason)}`
                    : `${q.questions} ${g("questions")} · ≥ ${q.pass_pct}% · +${q.pass_xp} XP`}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Il quiz: una domanda alla volta, il tempo che scorre, la risposta che
 *  si colora, la spiegazione, e alla fine il risultato con l'XP. */
function QuizPlayer({ quiz, onClose }: { quiz: QuizCard; onClose: () => void }) {
  const { g, grade, qualification, lang } = useGameText();
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
            <p className="flex items-center gap-2 font-display text-xl">
              {quiz.kind === "EXAM" && quiz.belt ? <BeltSwatch grade={quiz.belt} /> : <span className="text-2xl">{quiz.icon}</span>}{quiz.title}
            </p>
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
              <ResultView key="done" done={done} beltName={done.new_belt ? grade(done.new_belt) : null} newGrade={done.new_belt}
                qualificationName={done.new_qualification ? qualification(done.new_qualification) : null} onRetry={begin} onClose={onClose} busy={busy} />
            ) : q ? (
              <motion.div key={q.id} initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }} transition={{ duration: 0.3 }} className="relative mt-5">
                {run.questions.length > 15 && (
                  <div className="mb-3" aria-label={g("examProgress")}>
                    <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                      <div className="h-full rounded-full bg-white/60" style={{ width: `${(index / run.questions.length) * 100}%` }} />
                    </div>
                  </div>
                )}
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

function ResultView({ done, beltName, newGrade, qualificationName, onRetry, onClose, busy }: {
  done: Finished; beltName: string | null; newGrade: string | null; qualificationName: string | null; onRetry: () => void; onClose: () => void; busy: boolean;
}) {
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
      {(beltName || qualificationName) && (
        <div className="mx-auto mt-5 max-w-sm rounded-2xl bg-white p-5 text-ink-900 shadow-lift ring-4 ring-accent-300/60">
          <p className="text-[0.7rem] font-bold uppercase tracking-[0.2em] text-ink-500">{g("certificate")}</p>
          {beltName && newGrade && (
            <p className="mt-2 flex items-center justify-center gap-3 font-display text-2xl"><BeltSwatch grade={newGrade} className="h-5 w-16" />{beltName}</p>
          )}
          {qualificationName && <p className="mt-2 font-display text-xl">🎓 {g("newQualification")} {qualificationName}</p>}
          <p className="mt-2 text-xs text-ink-500">{g("diplomaHint")}</p>
          <p className="mt-1 text-sm text-ink-500">{done.pct}% · {done.correct}/{done.total}</p>
        </div>
      )}
      {done.xp_earned === 0 && <p className="mt-3 text-sm text-white/70">{g("noNewXp")}</p>}
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <button type="button" onClick={onRetry} disabled={busy} className="inline-flex h-12 cursor-pointer items-center rounded-2xl bg-white/15 px-6 font-semibold ring-1 ring-white/30 hover:bg-white/25">↻ {g("retry")}</button>
        <button type="button" onClick={onClose} className="inline-flex h-12 cursor-pointer items-center rounded-2xl bg-accent-400 px-6 font-bold text-ink-900 hover:bg-accent-300">{g("backToAcademy")}</button>
      </div>
    </motion.div>
  );
}
