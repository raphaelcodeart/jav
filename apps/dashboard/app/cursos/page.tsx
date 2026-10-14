import type { Metadata } from "next";
import { Container, EmptyNote, PageIntro } from "@/components/site/blocks";
import { CourseCards } from "@/components/site/course-cards";
import { siteI18n } from "@/components/site/i18n";
import { SiteShell } from "@/components/site/site-shell";
import { publicSite } from "@/lib/public-site";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: t("site.courses.metaTitle"), description: t("site.courses.text") };
}

/** "Cursos JAV nas escolas": i corsi extrascolastici di JudoArteVida nelle
 *  scuole, separati dai club. Solo i corsi pubblicati, senza persone
 *  (docs/club-portal.md, "Cursos JAV"). */
export default async function CoursesPage() {
  const i18n = await siteI18n();
  const { t } = i18n;
  const data = await publicSite.courses().catch(() => null);
  const courses = data?.courses ?? [];
  const unit = data?.unit ?? null;
  return (
    <SiteShell>
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
        {courses.length === 0 ? <EmptyNote>{t("site.courses.empty")}</EmptyNote> : <CourseCards courses={courses} i18n={i18n} />}
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
