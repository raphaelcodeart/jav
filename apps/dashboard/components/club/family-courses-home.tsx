"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { FamilyToday } from "@/components/club/family-today";
import { SchoolLogo, useWeekday } from "@/components/club/jav-courses";
import { FamilyMonthCard } from "@/components/club/month-board";
import { cn } from "@/lib/cn";
import { clubGet, type AthleteCard, type Course, type Family } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

/** La home di una famiglia dei corsi JAV nelle scuole (docs/club-portal.md,
 *  "Cursos JAV"). Il genitore viene qui per tre cose: sapere dove e quando va
 *  il figlio, pagare la mensilità con la foto della ricevuta, vedere se è
 *  andato a lezione. Cinture, traguardi, gare, Shop e area dell'atleta nei
 *  corsi non esistono, e qui non compaiono. */
export function FamilyCoursesHome({ family, onPay, onAdd, onOpenFees, onOpenCourses, fees }: {
  family: Family;
  /** Senza id: tutte le quote da pagare già spuntate. */
  onPay: (feeIds?: string[]) => void;
  onAdd: () => void;
  onOpenFees: (athleteId: string) => void;
  onOpenCourses: () => void;
  /** Le quote da pagare e le ricevute caricate, come nella home dei club. */
  fees: ReactNode;
}) {
  const { t, fmt } = useI18n();
  // Gli stessi corsi della pagina «Corsi»: my_athlete_ids dice chi ci va.
  const { data: courses } = useQuery({ queryKey: ["club", "courses"], queryFn: () => clubGet<Course[]>("/courses") });
  const coursesOf = (athleteId: string) => (courses ?? []).filter((c) => c.active && c.my_athlete_ids.includes(athleteId));
  const noAthletes = family.athletes.length === 0;
  const due = family.due_cents > 0;

  return (
    <div className="space-y-8">
      <motion.section
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-[32px] bg-gradient-to-br from-ink-900 via-ink-800 to-brand-800 text-white p-6 sm:p-8"
      >
        <div className="absolute inset-0 opacity-30 bg-[radial-gradient(circle_at_85%_15%,#f9e40f,transparent_35%),radial-gradient(circle_at_10%_100%,#e43f21,transparent_45%)]" aria-hidden="true" />
        <div className="relative space-y-6">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-accent-300">🏫 {t("jcx.eyebrow")} · {family.season_label}</p>
            <h2 className="text-3xl sm:text-4xl mt-2 leading-tight">{t("jcx.heroTitle")}</h2>
            <p className="text-white/75 mt-3 max-w-md text-sm">
              {noAthletes
                ? t("jcx.heroEmpty")
                : due
                  ? t("family.heroDue", { amount: fmt.euro(family.due_cents) })
                  : t("family.heroAllPaid")}
            </p>
          </div>

          {!noAthletes && (
            <ul className="grid gap-3 sm:grid-cols-2">
              {family.athletes.map((a, i) => (
                <motion.li key={a.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.06 }}
                  className="rounded-2xl bg-white/10 ring-1 ring-white/15 p-3">
                  <div className="flex items-center gap-3">
                    <Avatar athlete={a} className="h-11 w-11 ring-2 ring-white/40" />
                    <p className="min-w-0 flex-1 truncate font-semibold">{a.first_name}</p>
                    {a.plan && <span className="text-xs text-white/70">{t("athlete.perMonth", { amount: fmt.euro(a.plan.monthly_fee_cents) })}</span>}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {coursesOf(a.id).length === 0 && <span className="text-xs text-white/70">{t("jcx.noCourse")}</span>}
                    {coursesOf(a.id).map((c) => <CourseChip key={c.id} course={c} />)}
                  </div>
                </motion.li>
              ))}
            </ul>
          )}

          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            {noAthletes ? (
              <Button size="xl" variant="accent" onClick={onAdd}>＋ {t("family.addFirst")}</Button>
            ) : (
              <Button size="xl" variant={due ? "accent" : "secondary"} onClick={() => onPay()}>📸 {t("jcx.payButton")}</Button>
            )}
            {!noAthletes && <p className="text-xs text-white/70 max-w-sm">{t("jcx.payHint")}</p>}
          </div>
        </div>
      </motion.section>

      {/* Prima di tutto il mese: la mensilità di ogni figlio e se è pagata. */}
      {!noAthletes && family.this_month && <FamilyMonthCard board={family.this_month} onPay={(ids) => onPay(ids)} />}

      {!noAthletes && <FamilyToday />}

      <section>
        <div className="flex items-end justify-between gap-3 mb-4">
          <div>
            <h2 className="text-xl text-ink-900">{t("jcx.childrenTitle")}</h2>
            <p className="text-sm text-ink-500">{t("jcx.childrenHint")}</p>
          </div>
          <Button variant="secondary" onClick={onAdd} icon={<span>＋</span>}>{t("family.add")}</Button>
        </div>
        {noAthletes ? (
          <EmptyState
            icon={<span className="text-3xl">🏫</span>}
            title={t("family.noAthletes")}
            text={t("jcx.noAthletesText")}
            action={<Button size="lg" onClick={onAdd}>{t("family.addFirst")}</Button>}
          />
        ) : (
          <div className="grid gap-5 lg:grid-cols-2">
            {family.athletes.map((a) => (
              <ChildCard key={a.id} athlete={a} courses={coursesOf(a.id)} onOpenFees={() => onOpenFees(a.id)} onOpenCourses={onOpenCourses} />
            ))}
          </div>
        )}
      </section>

      {!noAthletes && fees}
    </div>
  );
}

function Avatar({ athlete: a, className }: { athlete: AthleteCard; className?: string }) {
  return (
    <span className={cn("flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-brand-400 to-brand-700 font-display text-lg text-white", className)}>
      {a.photo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={a.photo_url} alt="" className="h-full w-full object-cover" />
      ) : (
        a.first_name.slice(0, 1)
      )}
    </span>
  );
}

/** Nel riquadro scuro: la scuola (con il logo) e i giorni del corso. */
function CourseChip({ course: c }: { course: Course }) {
  const weekday = useWeekday();
  return (
    <span className="inline-flex max-w-full items-center gap-2 rounded-xl bg-white/10 py-1 pl-1 pr-2.5 text-xs">
      <SchoolLogo url={c.venue_logo_url} size="sm" className="ring-0" />
      <span className="min-w-0">
        <span className="block truncate font-semibold">{c.venue_name ?? c.name}</span>
        <span className="block truncate text-white/70">
          {c.slots.map((s) => `${weekday(s.weekday)} ${s.starts_at.slice(0, 5)}`).join(" · ") || c.name}
        </span>
      </span>
    </span>
  );
}

function ChildCard({ athlete: a, courses, onOpenFees, onOpenCourses }: {
  athlete: AthleteCard; courses: Course[]; onOpenFees: () => void; onOpenCourses: () => void;
}) {
  const { t, fmt } = useI18n();
  const weekday = useWeekday();
  return (
    <motion.article initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="glass-card rounded-3xl p-5 space-y-4">
      <div className="flex items-center gap-4">
        <Avatar athlete={a} className="h-14 w-14 text-xl" />
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-lg text-ink-900">{a.first_name} {a.last_name}</h3>
          <p className="text-sm text-ink-500">{t("club.yearsOld", { n: a.age })}</p>
        </div>
        {a.due_cents > 0 ? (
          <Badge tone={a.overdue_count > 0 ? "danger" : "warning"} dot>
            {a.overdue_count > 0 ? t("athlete.overdueFees") : t("family.statDue")} {fmt.euro(a.due_cents)}
          </Badge>
        ) : (
          <Badge tone="success" dot>{t("athlete.upToDate")}</Badge>
        )}
      </div>

      {courses.length === 0 ? (
        <div className="rounded-2xl bg-accent-50 ring-1 ring-accent-200 p-4">
          <p className="text-sm font-semibold text-ink-900">{t("jcx.noCourse")}</p>
          <p className="text-xs text-ink-600 mt-0.5">{t("jcx.noCourseText")}</p>
          <Button size="sm" className="mt-3" onClick={onOpenCourses}>{t("jcx.chooseCourse")}</Button>
        </div>
      ) : (
        <ul className="space-y-2">
          {courses.map((c) => (
            <li key={c.id} className="flex items-start gap-3 rounded-2xl bg-white ring-1 ring-ink-100 p-3">
              <SchoolLogo url={c.venue_logo_url} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink-900">{c.venue_name ?? c.name}</p>
                {c.venue_name && <p className="truncate text-xs text-ink-600">{c.name}</p>}
                {(c.venue_address || c.venue_city) && (
                  <p className="truncate text-xs text-ink-500">{[c.venue_address, c.venue_city].filter(Boolean).join(", ")}</p>
                )}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {c.slots.map((s) => (
                    <span key={s.id} className="rounded-full bg-brand-50 ring-1 ring-brand-200 px-2.5 py-0.5 text-xs font-semibold text-brand-800 first-letter:uppercase">
                      {weekday(s.weekday, "long")} {s.starts_at.slice(0, 5)}–{s.ends_at.slice(0, 5)}
                    </span>
                  ))}
                </div>
                {(c.public_coach_name || c.instructor_name) && (
                  <p className="mt-1.5 text-xs text-ink-500">{t("jcx.coach", { name: (c.public_coach_name || c.instructor_name)! })}</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {courses.length > 0 && <ChildAttendance athleteId={a.id} />}

      <div className="flex justify-end">
        <Button size="sm" variant="secondary" onClick={onOpenFees}>💶 {t("jcx.openFees")} →</Button>
      </div>
    </motion.article>
  );
}

/** Le lezioni del mese di GET /club/athlete-area/{id}: il genitore è titolare,
 *  e l'area la può leggere anche se il figlio un accesso non ce l'ha. */
interface AreaMonth {
  month_present: number;
  month_total: number;
  lessons: { date: string; course_id: string; course_name: string; starts_at: string; ends_at: string; status: string }[];
}

const LESSON_STYLE: Record<string, { box: string; mark: string }> = {
  PRESENT: { box: "bg-emerald-500 text-white", mark: "✓" },
  ABSENT: { box: "bg-rose-100 text-rose-700", mark: "✕" },
  MISSED: { box: "bg-rose-50 text-rose-600 ring-1 ring-rose-200", mark: "–" },
  TODAY: { box: "bg-accent-300 text-ink-900", mark: "•" },
  UPCOMING: { box: "bg-ink-50 text-ink-400 ring-1 ring-ink-100", mark: "" },
};

function ChildAttendance({ athleteId }: { athleteId: string }) {
  const { t, fmt } = useI18n();
  const { data } = useQuery({ queryKey: ["club", "athlete-area", athleteId], queryFn: () => clubGet<AreaMonth>(`/athlete-area/${athleteId}`) });
  if (!data) return null;
  return (
    <div className="rounded-2xl bg-ink-50 p-3">
      <p className="text-xs font-bold uppercase tracking-wide text-ink-500">{t("jcx.attendanceTitle")}</p>
      {data.lessons.length === 0 ? (
        <p className="mt-1 text-sm text-ink-600">{t("jcx.noLessons")}</p>
      ) : (
        <>
          <p className="mt-1 text-sm font-semibold text-ink-900">{t("jcx.attendanceMonth", { present: data.month_present, total: data.month_total })}</p>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {data.lessons.map((l) => {
              const style = LESSON_STYLE[l.status] ?? LESSON_STYLE.UPCOMING!;
              const label = `${fmt.shortDate(l.date)} · ${t.dyn(`jcx.lesson.${l.status}`, l.status)}`;
              return (
                <li key={`${l.course_id}-${l.date}`} title={label}
                  className={cn("flex h-9 w-9 flex-col items-center justify-center rounded-lg text-[10px] font-semibold leading-none", style.box)}>
                  <span aria-hidden="true" className="tabular-nums">{Number(l.date.slice(8, 10))}</span>
                  <span aria-hidden="true" className="mt-0.5 text-[11px]">{style.mark}</span>
                  <span className="sr-only">{label}</span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
