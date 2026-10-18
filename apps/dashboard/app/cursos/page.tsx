import type { Metadata } from "next";
import { Container, EmptyNote, PageIntro } from "@/components/site/blocks";
import { ExtFamilyArea } from "@/components/ext-courses/family-area";
import { CourseCards, ExtCourseCards } from "@/components/site/course-cards";
import { siteI18n } from "@/components/site/i18n";
import { SiteShell } from "@/components/site/site-shell";
import { publicExtCourses, publicSite } from "@/lib/public-site";
import { decodeRolesFromAccessToken, getSession } from "@/lib/session";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: t("site.courses.metaTitle"), description: t("site.courses.text") };
}

/** "Cursos JAV nas escolas": i corsi extrascolastici di JudoArteVida nelle
 *  scuole, separati dai club. Solo i corsi pubblicati, senza persone
 *  (docs/club-portal.md, "Cursos JAV").
 *
 *  Lo stesso indirizzo è l'area del genitore dei corsi esterni: chi ha il
 *  ruolo EXT_FAMILY qui trova i suoi figli, gli avvisi e le mensilità.
 *  `?area=familia` la apre anche quando il ruolo non è ancora nel token
 *  (subito dopo un'iscrizione da dentro, prima del rinnovo della sessione);
 *  `?area=site` mostra il sito anche a lui. */
export default async function CoursesPage({ searchParams }: { searchParams: Promise<{ area?: string }> }) {
  const [session, { area }] = await Promise.all([getSession(), searchParams]);
  if (session && area !== "site" && (area === "familia" || decodeRolesFromAccessToken(session.accessToken).includes("EXT_FAMILY"))) {
    return <ExtFamilyArea email={session.email} />;
  }
  const i18n = await siteI18n();
  const { t } = i18n;
  const [data, extData] = await Promise.all([publicSite.courses().catch(() => null), publicExtCourses().catch(() => null)]);
  const courses = data?.courses ?? [];
  const extCourses = extData ?? [];
  const unit = data?.unit ?? null;
  return (
    <SiteShell bot={false}>
      <PageIntro eyebrow={t("site.courses.eyebrow")} title={t("site.courses.title")} text={unit?.tagline ?? t("site.courses.text")} />
      <Container className="py-12 space-y-10">
        <div className="grid gap-4 md:grid-cols-3">
          {(["free", "monthly", "move"] as const).map((k) => (
            <div key={k} className="rounded-3xl bg-white/80 p-5 ring-1 ring-ink-100">
              <p className="font-semibold text-ink-900">{t(`site.courses.point.${k}`)}</p>
              <p className="mt-1 text-sm text-ink-500">{t(`site.courses.point.${k}Text`)}</p>
            </div>
          ))}
        </div>
        {unit?.about && <p className="max-w-3xl whitespace-pre-line text-ink-600">{unit.about}</p>}
        {courses.length === 0 && extCourses.length === 0 && <EmptyNote>{t("site.courses.empty")}</EmptyNote>}
        {extCourses.length > 0 && <ExtCourseCards courses={extCourses} i18n={i18n} />}
        {courses.length > 0 && <CourseCards courses={courses} i18n={i18n} />}
        {unit && (unit.contact_email || unit.contact_phone) && (
          <p className="text-sm text-ink-500">
            {t("site.courses.contacts")}{" "}
            {unit.contact_email && <a className="font-semibold text-brand-700 hover:underline" href={`mailto:${unit.contact_email}`}>{unit.contact_email}</a>}
            {unit.contact_email && unit.contact_phone && " · "}
            {unit.contact_phone && <a className="font-semibold text-brand-700 hover:underline" href={`tel:${unit.contact_phone.replace(/\s+/g, "")}`}>{unit.contact_phone}</a>}
          </p>
        )}
      </Container>
    </SiteShell>
  );
}
