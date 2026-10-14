"use client";

import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BeltBadge } from "@/components/ui/belt";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend, type Lesson, type Roster } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

const S = (path: string) => `/staff${path}`;
const hhmm = (t: string) => t.slice(0, 5);

/** Le presenze sul tatami: si apre sulla lezione di oggi in corso (o la
 *  prossima), un tocco per atleta segna l'entrata, una nota per la
 *  segreteria se serve. Treinador e segreteria possono tornare sui giorni
 *  passati per correggere; il genitore no (lo fa dalla sua pagina, solo
 *  oggi). Compatto: pensato per un telefono tenuto con una mano. */
export function AttendanceTool() {
  const { t, fmt } = useI18n();
  const [date, setDate] = useState<string | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const { data: lessons, isLoading } = useQuery({
    queryKey: ["club", "staff", "lessons", date ?? "today"],
    queryFn: () => clubGet<Lesson[]>(S(`/lessons${date ? `?from=${date}&to=${date}` : ""}`)),
  });
  const day = date ?? lessons?.[0]?.date ?? null;
  const lesson = lessons?.find((l) => `${l.course_id}|${l.slot_id}` === chosen) ?? lessons?.find((l) => l.current) ?? lessons?.[0];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Input type="date" value={date ?? day ?? ""} onChange={(e) => { setDate(e.target.value || null); setChosen(null); }}
          className="w-44" aria-label={t("attendance.day")} />
        {date && <Button size="sm" variant="ghost" onClick={() => { setDate(null); setChosen(null); }}>{t("attendance.today")}</Button>}
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
                  <span className="block text-sm font-semibold">{l.course_name}</span>
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

function LessonRoster({ courseId, date, title }: { courseId: string; date: string; title: string }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = ["club", "staff", "roster", courseId, date];
  const { data: roster, isLoading } = useQuery({ queryKey: key, queryFn: () => clubGet<Roster>(S(`/courses/${courseId}/roster?date=${date}`)) });
  const [noteFor, setNoteFor] = useState<{ id: string; name: string; note: string } | null>(null);

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
  return (
    <div className="glass-card rounded-3xl p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="font-semibold text-ink-900 truncate">{title}</p>
        <span className="shrink-0 rounded-full bg-ink-900 text-white px-3 py-1 text-sm font-display">{present}/{rows.length}</span>
      </div>
      {rows.length === 0 ? <p className="text-sm text-ink-500 py-6 text-center">{t("attendance.noAthletes")}</p> : (
        <ul className="divide-y divide-ink-100">
          {rows.map((r) => (
            <li key={r.athlete_id} className="flex items-center gap-3 py-2">
              <motion.button type="button" whileTap={{ scale: 0.92 }} onClick={() => mark(r.athlete_id, !r.present)}
                aria-pressed={!!r.present} aria-label={t("attendance.toggle", { name: r.first_name })}
                className={`relative h-11 w-11 shrink-0 rounded-full flex items-center justify-center font-bold ring-2 cursor-pointer transition-colors ${r.present ? "bg-emerald-500 text-white ring-emerald-500" : "bg-white text-ink-400 ring-ink-200"}`}>
                <AnimatePresence mode="wait">
                  {r.present ? <motion.span key="y" initial={{ scale: 0 }} animate={{ scale: 1 }}>✓</motion.span>
                    : <motion.span key="n" initial={{ scale: 0 }} animate={{ scale: 1 }}>{r.first_name.slice(0, 1)}</motion.span>}
                </AnimatePresence>
              </motion.button>
              <button type="button" onClick={() => mark(r.athlete_id, !r.present)} className="min-w-0 flex-1 text-left cursor-pointer">
                <span className="block text-sm font-semibold text-ink-900 truncate">{r.first_name} {r.last_name}</span>
                {r.note && <span className="block text-xs text-amber-700 truncate">📝 {r.note}</span>}
              </button>
              <BeltBadge belt={r.belt} size="sm" showLabel={false} />
              <button type="button" onClick={() => setNoteFor({ id: r.athlete_id, name: r.first_name, note: r.note ?? "" })}
                className="h-9 w-9 shrink-0 rounded-xl text-ink-400 hover:bg-ink-50 hover:text-ink-900 cursor-pointer" aria-label={t("attendance.addNote")}>
                📝
              </button>
            </li>
          ))}
        </ul>
      )}
      {noteFor && (
        <Modal open onClose={() => setNoteFor(null)} size="sm" title={t("attendance.noteTitle", { name: noteFor.name })}
          footer={<><Button variant="ghost" onClick={() => setNoteFor(null)}>{t("common.cancel")}</Button>
            <Button onClick={() => { void mark(noteFor.id, true, noteFor.note); setNoteFor(null); }}>{t("attendance.saveNote")}</Button></>}>
          <Input autoFocus value={noteFor.note} maxLength={300} placeholder={t("attendance.notePlaceholder")}
            onChange={(e) => setNoteFor({ ...noteFor, note: e.target.value })} />
        </Modal>
      )}
    </div>
  );
}
