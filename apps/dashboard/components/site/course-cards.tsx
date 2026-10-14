import Link from "next/link";
import { ageRange, type SiteI18n } from "@/components/site/i18n";
import { linkButton } from "@/components/site/link-button";
import { Reveal } from "@/components/site/reveal";
import type { PublicCourse } from "@/lib/public-site";

/** Le card dei corsi JAV nelle scuole: la scuola e la città, i giorni e le
 *  ore, l'età, due righe per le famiglie e "Inscrever", che porta alla
 *  registrazione dell'unità con il corso già scelto (/c/<slug>?curso=<id>).
 *  Nessuna persona, se non il nome che JAV ha scritto apposta per il sito. */
export function CourseCards({ courses, i18n }: { courses: PublicCourse[]; i18n: SiteI18n }) {
  const { t, fmt } = i18n;
  // Il 1° gennaio 2024 era lunedì, e 0 è lunedì anche per l'API.
  const weekday = (d: number) => fmt.date(new Date(2024, 0, 1 + d), { weekday: "long" });
  return (
    <ul className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      {courses.map((course, i) => {
        const ages = ageRange(t, course.min_age, course.max_age);
        return (
          <li key={course.id}>
            <Reveal delay={i * 0.05} className="h-full">
              <article className="glass-card flex h-full flex-col rounded-3xl p-6">
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-brand-600">
                  🏫 {[course.venue_city, ages].filter(Boolean).join(" · ")}
                </p>
                <h3 className="mt-2 text-xl text-ink-900">{course.venue_name ?? course.name}</h3>
                {course.venue_name && <p className="text-sm font-semibold text-ink-600">{course.name}</p>}
                {course.venue_address && <p className="mt-1 text-xs text-ink-500">{course.venue_address}</p>}
                {course.description && <p className="mt-3 text-sm text-ink-600 whitespace-pre-line">{course.description}</p>}
                {course.slots.length > 0 && (
                  <ul className="mt-4 space-y-1 text-sm text-ink-700" aria-label={t("site.courses.schedule")}>
                    {course.slots.map((s) => (
                      <li key={`${s.weekday}-${s.starts_at}`} className="flex justify-between gap-3 rounded-xl bg-ink-50 px-3 py-1.5">
                        <span className="capitalize">{weekday(s.weekday)}</span>
                        <span className="tabular-nums font-semibold">{s.starts_at}–{s.ends_at}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {course.coach_name && <p className="mt-3 text-xs text-ink-500">{t("site.courses.coach", { name: course.coach_name })}</p>}
                <div className="mt-auto pt-5">
                  <Link href={course.signup_path} className={linkButton({ size: "sm" })}>{t("site.courses.signup")}</Link>
                </div>
              </article>
            </Reveal>
          </li>
        );
      })}
    </ul>
  );
}
