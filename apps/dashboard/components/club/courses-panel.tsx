"use client";

import { motion } from "motion/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { SchoolLogo, useClubFeatures } from "@/components/club/jav-courses";
import { clubGet, clubSend, type Course, type Family } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

// 1 January 2024 was a Monday: weekday 0 of the API is Monday too. Intl names
// the days in the reader's language, where the API only has Italian ones.
const weekdayNames = (tag: string) =>
  Array.from({ length: 7 }, (_, i) => new Date(2024, 0, 1 + i).toLocaleDateString(tag, { weekday: "short" }).replace(".", ""));
const hhmm = (t: string) => t.slice(0, 5);

/** The weekly timetable, and which of your children are in each course. */
export function CoursesPanel() {
  const { data: courses, isLoading, error } = useQuery({ queryKey: ["club", "courses"], queryFn: () => clubGet<Course[]>("/courses") });
  const { data: family } = useQuery({ queryKey: ["club", "family"], queryFn: () => clubGet<Family>("/family") });
  const { t, fmt } = useI18n();
  const days = weekdayNames(fmt.tag);
  // Nei corsi JAV ogni corso è in una scuola diversa: l'orario di tutte
  // insieme non serve a nessuno. Prima i corsi dei figli, poi gli altri.
  const { courses: schools } = useClubFeatures();
  const active = (courses ?? []).filter((c) => c.active)
    .sort((a, b) => (schools ? Number(b.my_athlete_ids.length > 0) - Number(a.my_athlete_ids.length > 0) : 0));

  return (
    <div>
      <PageHeader eyebrow={t("courses.eyebrow")} title={t("courses.title")} subtitle={t("courses.subtitle")} />
      {isLoading && <Skeleton className="h-72" />}
      {error && <EmptyState title={t("courses.unavailable")} text={(error as Error).message} />}
      {!isLoading && !error && active.length === 0 && <EmptyState icon={<span className="text-3xl">📅</span>} title={t("courses.empty")} text={t("courses.emptyText")} />}

      {active.length > 0 && (
        <>
          {!schools && <div className="grid grid-cols-7 gap-2 mb-8 overflow-x-auto min-w-0">
            {days.map((d, wd) => {
              const slots = active.flatMap((c) => c.slots.filter((s) => s.weekday === wd).map((s) => ({ c, s }))).sort((a, b) => a.s.starts_at.localeCompare(b.s.starts_at));
              return (
                <div key={d} className="min-w-[96px]">
                  <p className="text-center text-xs font-bold uppercase tracking-wider text-ink-500 mb-2">{d}</p>
                  <div className="space-y-2">
                    {slots.length === 0 && <div className="h-16 rounded-2xl bg-ink-50 ring-1 ring-ink-100" />}
                    {slots.map(({ c, s }, i) => (
                      <motion.div
                        key={s.id}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: wd * 0.04 + i * 0.03 }}
                        className={`rounded-2xl p-2.5 text-white shadow-soft ${c.my_athlete_ids.length > 0 ? "bg-gradient-to-br from-brand-500 to-brand-700" : "bg-gradient-to-br from-ink-600 to-ink-800"}`}
                      >
                        <p className="text-[11px] font-bold">{hhmm(s.starts_at)}–{hhmm(s.ends_at)}</p>
                        <p className="text-xs font-semibold leading-tight mt-0.5">{c.name}</p>
                        {s.room && <p className="text-[10px] opacity-75 mt-0.5">{s.room}</p>}
                      </motion.div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>}

          <div className="grid md:grid-cols-2 gap-5">
            {active.map((c) => (
              <CourseCard key={c.id} course={c} athletes={family?.athletes ?? []} days={days} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function CourseCard({ course: c, athletes, days }: { course: Course; athletes: Family["athletes"]; days: string[] }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const { t } = useI18n();

  async function toggle(athleteId: string, enrolled: boolean) {
    setBusy(athleteId);
    try {
      if (enrolled) await clubSend(`/courses/${c.id}/athletes/${athleteId}`, "DELETE");
      else await clubSend(`/courses/${c.id}/athletes`, "POST", { athlete_id: athleteId });
      await queryClient.invalidateQueries({ queryKey: ["club", "courses"] });
    } catch (e) {
      toast({ tone: "error", title: t("common.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="glass-card rounded-3xl p-5">
      <div className="flex items-start justify-between gap-3">
        {c.venue_name && <SchoolLogo url={c.venue_logo_url} />}
        <div className="min-w-0 flex-1">
          {c.venue_name && <p className="text-xs font-bold uppercase tracking-wider text-brand-600">{[c.venue_name, c.venue_city].filter(Boolean).join(" · ")}</p>}
          <h3 className="text-base text-ink-900">{c.name}</h3>
          <p className="text-sm text-ink-500">
            {[c.level, c.min_age != null ? t("club.yearsOld", { n: `${c.min_age}${c.max_age != null ? `–${c.max_age}` : "+"}` }) : null, c.instructor_name ? t("courses.with", { name: c.instructor_name }) : null].filter(Boolean).join(" · ")}
          </p>
        </div>
        <Badge tone="neutral">{t("courses.enrolled", { n: c.athletes_count })}</Badge>
      </div>
      {c.description && <p className="text-sm text-ink-600 mt-2">{c.description}</p>}
      <div className="flex flex-wrap gap-1.5 mt-3">
        {c.slots.map((s) => (
          <Badge key={s.id} tone="brand">{days[s.weekday]} {hhmm(s.starts_at)}</Badge>
        ))}
      </div>
      {athletes.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-ink-100">
          {athletes.map((a) => {
            const enrolled = c.my_athlete_ids.includes(a.id);
            return (
              <motion.button
                key={a.id}
                whileTap={{ scale: 0.94 }}
                disabled={busy === a.id}
                onClick={() => toggle(a.id, enrolled)}
                className={`inline-flex items-center gap-2 rounded-full px-3.5 h-9 text-sm font-semibold ring-1 cursor-pointer transition ${
                  enrolled ? "bg-brand-500 text-white ring-brand-500 shadow-brand" : "bg-white text-ink-700 ring-ink-200 hover:ring-brand-300"
                }`}
              >
                {enrolled ? "✓" : "＋"} {a.first_name}
              </motion.button>
            );
          })}
        </div>
      )}
    </div>
  );
}
