import Link from "next/link";
import { ageRange, type SiteI18n } from "@/components/site/i18n";
import { linkButton } from "@/components/site/link-button";
import { Reveal } from "@/components/site/reveal";
import type { ExtCourse } from "@/lib/ext-courses";
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
                <div className="mt-2 flex items-center gap-3">
                  {/* Il logo della scuola, quando la segreteria l'ha caricato: chi
                      cerca la scuola dei figli la riconosce prima del nome. */}
                  {course.venue_logo_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={course.venue_logo_url} alt="" className="h-12 w-12 shrink-0 rounded-xl bg-white object-contain p-1 ring-1 ring-ink-100" loading="lazy" />
                  )}
                  <div className="min-w-0">
                    <h3 className="text-xl text-ink-900">{course.venue_name ?? course.name}</h3>
                    {course.venue_name && <p className="text-sm font-semibold text-ink-600">{course.name}</p>}
                  </div>
                </div>
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

/** Le card dei corsi esterni (extcourses): il logo e il nome della scuola, la
 *  città, i gruppi con giorno, ora ed età, la mensilità e il treinador.
 *  "Inscrever" porta al modulo del corso (/cursos-externos/<id>), dove si
 *  iscrivono più figli in una volta. */
export function ExtCourseCards({ courses, i18n, hideSignup = false }: { courses: ExtCourse[]; i18n: SiteI18n; hideSignup?: boolean }) {
  const { t, fmt } = i18n;
  const weekday = (d: number) => fmt.date(new Date(2024, 0, 1 + d), { weekday: "long" });
  return (
    <ul className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      {courses.map((course, i) => {
        const groups = course.groups.filter((g) => g.active);
        return (
          <li key={course.id}>
            <Reveal delay={i * 0.05} className="h-full">
              <article className="glass-card flex h-full flex-col rounded-3xl p-6">
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-brand-600">
                  🏫 {[course.school_city, t("ext.site.badge")].filter(Boolean).join(" · ")}
                </p>
                <div className="mt-2 flex items-center gap-3">
                  {course.school_logo_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={course.school_logo_url} alt="" className="h-12 w-12 shrink-0 rounded-xl bg-white object-contain p-1 ring-1 ring-ink-100" loading="lazy" />
                  )}
                  <div className="min-w-0">
                    <h3 className="text-xl text-ink-900">{course.school_name}</h3>
                    <p className="text-sm font-semibold text-ink-600">{course.name}</p>
                  </div>
                </div>
                {course.school_address && <p className="mt-1 text-xs text-ink-500">{course.school_address}</p>}
                {course.description && <p className="mt-3 text-sm text-ink-600 whitespace-pre-line">{course.description}</p>}
                {groups.length > 0 && (
                  <ul className="mt-4 space-y-1.5 text-sm text-ink-700" aria-label={t("site.courses.schedule")}>
                    {groups.map((g) => (
                      <li key={g.id} className="rounded-xl bg-ink-50 px-3 py-2">
                        <span className="flex justify-between gap-3">
                          <span className="capitalize">{weekday(g.weekday)}</span>
                          <span className="tabular-nums font-semibold">{g.starts_at}–{g.ends_at}</span>
                        </span>
                        <span className="block text-xs text-ink-500">{[g.name, ageRange(t, g.min_age, g.max_age)].filter(Boolean).join(" · ")}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-4 text-sm text-ink-700">
                  <span className="font-display text-2xl text-ink-900">{fmt.euro(course.monthly_fee_cents)}</span> {t("ext.site.perMonth")}
                </p>
                {course.public_coach_name && <p className="mt-1 text-xs text-ink-500">{t("site.courses.coach", { name: course.public_coach_name })}</p>}
                {!hideSignup && <div className="mt-auto pt-5">
                  <Link href={`/cursos-externos/${course.id}`} className={linkButton({ size: "sm" })}>{t("ext.site.signup")}</Link>
                </div>}
              </article>
            </Reveal>
          </li>
        );
      })}
    </ul>
  );
}
