"use client";

import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BeltBadge } from "@/components/ui/belt";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend, type Lesson, type Roster } from "@/lib/club";
import { AthleteMarks } from "@/components/club/person-marks";
import { AthleteSheetModal, LessonNoteModal } from "@/components/club/coach-notebook";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/cn";

const S = (path: string) => `/staff${path}`;
const hhmm = (t: string) => t.slice(0, 5);

/** Le presenze sul tatami: si apre sulla lezione di oggi in corso (o la
 *  prossima), un tocco per atleta segna l'entrata, una nota per la
 *  segreteria se serve. Treinador e segreteria possono tornare sui giorni
 *  passati per correggere; il genitore no (lo fa dalla sua pagina, solo
 *  oggi). Compatto: pensato per un telefono tenuto con una mano. */
export function AttendanceTool({ initial }: { initial?: { date: string; courseId?: string } } = {}) {
  const { t, fmt } = useI18n();
  // Dall'Início: «Marcar presenças» di una lezione (anche di un giorno passato).
  const [date, setDate] = useState<string | null>(initial?.date ?? null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [wantedCourse, setWantedCourse] = useState<string | null>(initial?.courseId ?? null);
  const { data: lessons, isLoading } = useQuery({
    queryKey: ["club", "staff", "lessons", date ?? "today"],
    queryFn: () => clubGet<Lesson[]>(S(`/lessons${date ? `?from=${date}&to=${date}` : ""}`)),
  });
  const day = date ?? lessons?.[0]?.date ?? null;
  const lesson = lessons?.find((l) => `${l.course_id}|${l.slot_id}` === chosen)
    ?? (wantedCourse ? lessons?.find((l) => l.course_id === wantedCourse) : undefined)
    ?? lessons?.find((l) => l.current) ?? lessons?.[0];
  const pick = (d: string | null) => { setDate(d); setChosen(null); setWantedCourse(null); };

  return (
    <div className="space-y-4">
      {/* La striscia si rimonta sul mese del giorno scelto (anche dal calendario sotto). */}
      <DayStrip key={(date ?? "").slice(0, 7) || "now"} selected={day} onPick={pick} />
      <div className="flex flex-wrap items-center gap-2">
        <div className="w-44">
          <Input type="date" value={date ?? day ?? ""} onChange={(e) => pick(e.target.value || null)}
            aria-label={t("attendance.day")} />
        </div>
        {date && <Button size="sm" variant="ghost" onClick={() => pick(null)}>{t("attendance.today")}</Button>}
      </div>
      {isLoading ? <Skeleton className="h-40" /> : !lessons?.length ? (
        <EmptyState icon={<span className="text-3xl">📅</span>} title={t("attendance.noLessons")} text={t("attendance.noLessonsText")} />
      ) : (
        <>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {lessons.map((l) => {
              const key = `${l.course_id}|${l.slot_id}`;
              const on = lesson && `${lesson.course_id}|${lesson.slot_id}` === key;
              return (
                <button key={key} type="button" onClick={() => setChosen(key)}
                  className={`shrink-0 rounded-2xl px-4 py-2.5 text-left ring-1 cursor-pointer transition-colors ${on ? "bg-brand-500 text-white ring-brand-500" : "bg-white ring-ink-200 hover:ring-ink-300"}`}>
                  <span className="block text-sm font-semibold">
                    {l.course_name}
                    {l.mine && <span className={`ml-1.5 rounded-full px-1.5 py-0.5 text-[10px] font-bold uppercase ${on ? "bg-white/25" : "bg-accent-100 text-ink-800"}`}>★ {t("attendance.mine")}</span>}
                  </span>
                  <span className={`block text-xs ${on ? "text-white/80" : "text-ink-500"}`}>
                    {hhmm(l.starts_at)}–{hhmm(l.ends_at)}{l.current && !date ? ` · ${t("attendance.now")}` : ""} · {l.present}/{l.enrolled}
                  </span>
                </button>
              );
            })}
          </div>
          {lesson && <LessonRoster key={`${lesson.course_id}-${lesson.date}`} courseId={lesson.course_id} date={lesson.date}
            title={`${lesson.course_name} · ${fmt.shortDate(lesson.date)}`} />}
        </>
      )}
    </div>
  );
}

function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** I giorni del mese con lezioni, come bottoni (come nell'area dell'atleta):
 *  una scorciatoia per aprire la giornata, e a colpo d'occhio dove le
 *  presenze ci sono già (colorati) e dove no. Le frecce cambiano mese. */
function DayStrip({ selected, onPick }: { selected: string | null; onPick: (day: string) => void }) {
  const { t, fmt } = useI18n();
  const now = new Date();
  const [month, setMonth] = useState(() => {
    const d = selected ? new Date(`${selected}T12:00:00`) : now;
    return { y: d.getFullYear(), m: d.getMonth() };
  });
  const first = iso(new Date(month.y, month.m, 1));
  const last = iso(new Date(month.y, month.m + 1, 0));
  const today = iso(now);
  const { data } = useQuery({
    queryKey: ["club", "staff", "lessons", "month", first],
    queryFn: () => clubGet<Lesson[]>(S(`/lessons?from=${first}&to=${last}`)),
    staleTime: 30_000,
  });
  const days = useMemo(() => {
    const byDay = new Map<string, { lessons: number; present: number; enrolled: number }>();
    for (const l of data ?? []) {
      const d = byDay.get(l.date) ?? { lessons: 0, present: 0, enrolled: 0 };
      byDay.set(l.date, { lessons: d.lessons + 1, present: d.present + l.present, enrolled: d.enrolled + l.enrolled });
    }
    return [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [data]);
  const go = (delta: number) => setMonth((v) => {
    const d = new Date(v.y, v.m + delta, 1);
    return { y: d.getFullYear(), m: d.getMonth() };
  });

  return (
    <section className="rounded-3xl bg-white p-3 shadow-soft ring-1 ring-ink-900/5">
      <div className="mb-2 flex items-center justify-between gap-2 px-1">
        <button type="button" onClick={() => go(-1)} aria-label={t("attendance.prevMonth")} className="h-8 w-8 cursor-pointer rounded-full text-ink-600 hover:bg-ink-50">‹</button>
        <p className="font-display text-lg capitalize text-ink-900">{fmt.date(new Date(month.y, month.m, 1), { month: "long", year: "numeric" })}</p>
        <button type="button" onClick={() => go(1)} aria-label={t("attendance.nextMonth")} className="h-8 w-8 cursor-pointer rounded-full text-ink-600 hover:bg-ink-50">›</button>
      </div>
      {data && days.length === 0 ? (
        <p className="px-1 pb-1 text-xs text-ink-500">{t("attendance.noDays")}</p>
      ) : (
        <div className="flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:thin]">
          {days.map(([d, info]) => {
            const date = new Date(`${d}T12:00:00`);
            const on = d === selected;
            const done = info.present > 0;
            const future = d > today;
            return (
              <button key={d} type="button" onClick={() => onPick(d)} aria-pressed={on}
                title={t("attendance.dayInfo", { lessons: info.lessons, present: info.present })}
                className={cn("flex w-14 shrink-0 cursor-pointer flex-col items-center rounded-2xl py-2 text-center ring-1 transition",
                  on ? "bg-brand-600 text-white ring-brand-600 shadow-brand"
                    : done ? "bg-emerald-50 text-emerald-900 ring-emerald-200 hover:ring-emerald-300"
                    : future ? "bg-white text-ink-400 ring-ink-100 hover:ring-ink-300"
                    : "bg-amber-50 text-amber-900 ring-amber-200 hover:ring-amber-300",
                  d === today && !on && "ring-2 ring-accent-400")}>
                <span className="text-[10px] font-bold uppercase">{t.dyn(`site.weekdayShort.${(date.getDay() + 6) % 7}`, "")}</span>
                <span className="font-display text-xl leading-none">{date.getDate()}</span>
                <span className={cn("mt-1 text-[10px] font-semibold tabular-nums", on ? "text-white/85" : "opacity-75")}>
                  {done ? `✓ ${info.present}` : `${info.lessons}×`}
                </span>
              </button>
            );
          })}
        </div>
      )}
      <p className="mt-1 flex flex-wrap gap-3 px-1 text-[10px] text-ink-500">
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-400" />{t("attendance.legendDone")}</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-amber-400" />{t("attendance.legendMissing")}</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-ink-200" />{t("attendance.legendFuture")}</span>
      </p>
    </section>
  );
}

function LessonRoster({ courseId, date, title }: { courseId: string; date: string; title: string }) {
  const { t } = useI18n();
  const [sheetFor, setSheetFor] = useState<string | null>(null);
  const [writing, setWriting] = useState(false);
  // Un giorno futuro si guarda, non si segna (il server lo rifiuterebbe).
  const future = date > iso(new Date());
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = ["club", "staff", "roster", courseId, date];
  const { data: roster, isLoading } = useQuery({ queryKey: key, queryFn: () => clubGet<Roster>(S(`/courses/${courseId}/roster?date=${date}`)) });
  const [noteFor, setNoteFor] = useState<{ id: string; name: string; note: string; present: boolean } | null>(null);

  async function mark(athleteId: string, present: boolean, note?: string) {
    queryClient.setQueryData<Roster>(key, (r) => (r ? { ...r, rows: r.rows.map((x) => (x.athlete_id === athleteId ? { ...x, present, note: note ?? x.note } : x)) } : r));
    try {
      await clubSend(S(`/courses/${courseId}/attendance`), "POST", { date, athlete_id: athleteId, present, ...(note !== undefined ? { note } : {}) });
      void queryClient.invalidateQueries({ queryKey: ["club", "staff", "lessons"] });
    } catch (e) {
      toast({ tone: "error", title: t("attendance.notSaved"), text: (e as Error).message });
      void queryClient.invalidateQueries({ queryKey: key });
    }
  }

  if (isLoading || !roster) return <Skeleton className="h-64" />;
  const rows = roster.rows;
  const present = rows.filter((r) => r.present).length;
  const unmarked = rows.filter((r) => r.present == null);
  async function allPresent() {
    for (const r of unmarked) await mark(r.athlete_id, true);
  }
  return (
    <div className="glass-card rounded-3xl p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="font-semibold text-ink-900 truncate">{title}</p>
        <span className="shrink-0 rounded-full bg-ink-900 text-white px-3 py-1 text-sm font-display">{present}/{rows.length}</span>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={() => setWriting(true)}>📓 {t("coach2.att.lessonNote")}</Button>
        {!future && unmarked.length > 1 && (
          <Button size="sm" variant="ghost" onClick={allPresent}>✓ {t("coach2.att.allPresent", { n: unmarked.length })}</Button>
        )}
      </div>
      {future && <p className="rounded-2xl bg-sky-50 px-3 py-2 text-xs text-sky-800 ring-1 ring-sky-200">🔮 {t("coach2.att.future")}</p>}
      {rows.length === 0 ? <p className="text-sm text-ink-500 py-6 text-center">{t("attendance.noAthletes")}</p> : (
        <ul className="divide-y divide-ink-100">
          {rows.map((r) => (
            <li key={r.athlete_id} className="flex items-center gap-3 py-2">
              <motion.button type="button" whileTap={{ scale: 0.92 }} onClick={() => mark(r.athlete_id, !r.present)} disabled={future}
                aria-pressed={!!r.present} aria-label={t("attendance.toggle", { name: r.first_name })}
                className={`relative h-11 w-11 shrink-0 rounded-full flex items-center justify-center font-bold ring-2 cursor-pointer transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${r.present ? "bg-emerald-500 text-white ring-emerald-500" : "bg-white text-ink-400 ring-ink-200"}`}>
                <AnimatePresence mode="wait">
                  {r.present ? <motion.span key="y" initial={{ scale: 0 }} animate={{ scale: 1 }}>✓</motion.span>
                    : <motion.span key="n" initial={{ scale: 0 }} animate={{ scale: 1 }}>{r.first_name.slice(0, 1)}</motion.span>}
                </AnimatePresence>
              </motion.button>
              <button type="button" onClick={() => mark(r.athlete_id, !r.present)} disabled={future} className="min-w-0 flex-1 text-left cursor-pointer disabled:cursor-default">
                <span className="block text-sm font-semibold text-ink-900 truncate">{r.first_name} {r.last_name} <AthleteMarks id={r.athlete_id} /></span>
                {r.note && <span className="block text-xs text-amber-700 truncate">📝 {r.note}</span>}
              </button>
              <BeltBadge belt={r.belt} size="sm" showLabel={false} />
              <button type="button" onClick={() => setNoteFor({ id: r.athlete_id, name: r.first_name, note: r.note ?? "", present: r.present ?? true })}
                disabled={future}
                className="h-9 w-9 shrink-0 rounded-xl text-ink-400 hover:bg-ink-50 hover:text-ink-900 cursor-pointer disabled:opacity-40" aria-label={t("attendance.addNote")}>
                📝
              </button>
              <button type="button" onClick={() => setSheetFor(r.athlete_id)}
                className="h-9 w-9 shrink-0 rounded-xl text-ink-400 hover:bg-ink-50 hover:text-ink-900 cursor-pointer" aria-label={t("coach2.att.openSheet", { name: r.first_name })}>
                📓
              </button>
            </li>
          ))}
        </ul>
      )}
      {noteFor && (
        <Modal open onClose={() => setNoteFor(null)} size="sm" title={t("attendance.noteTitle", { name: noteFor.name })}
          footer={<><Button variant="ghost" onClick={() => setNoteFor(null)}>{t("common.cancel")}</Button>
            <Button onClick={() => { void mark(noteFor.id, noteFor.present, noteFor.note); setNoteFor(null); }}>{t("attendance.saveNote")}</Button></>}>
          <Input autoFocus value={noteFor.note} maxLength={300} placeholder={t("attendance.notePlaceholder")}
            onChange={(e) => setNoteFor({ ...noteFor, note: e.target.value })} />
        </Modal>
      )}
      {sheetFor && <AthleteSheetModal athleteId={sheetFor} onClose={() => setSheetFor(null)} />}
      {writing && <LessonNoteModal note={null} defaultCourse={courseId} defaultDate={date} onClose={() => setWriting(false)} />}
    </div>
  );
}
