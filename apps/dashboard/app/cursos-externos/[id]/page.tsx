import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Container, PageIntro } from "@/components/site/blocks";
import { ExtCourseCards } from "@/components/site/course-cards";
import { siteI18n } from "@/components/site/i18n";
import { SiteShell } from "@/components/site/site-shell";
import { ExtSignupForm } from "@/components/ext-courses/signup-form";
import { publicExtCourses } from "@/lib/public-site";
import { getSession } from "@/lib/session";

type Params = { params: Promise<{ id: string }> };

// Non c'è una rotta pubblica per un corso solo: l'elenco dei pubblicati è
// corto (uno per scuola) e dice già tutto quello che la pagina mostra.
async function findCourse(id: string) {
  const courses = await publicExtCourses().catch(() => []);
  return courses.find((c) => c.id === id) ?? null;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const [{ t }, course] = await Promise.all([siteI18n(), findCourse(id)]);
  return { title: course ? `${course.school_name} — ${t("ext.signup.metaTitle")}` : t("ext.signup.metaTitle") };
}

/** L'iscrizione a un corso esterno dal sito (extcourses): la scheda del corso
 *  e il modulo per iscrivere uno o più figli. Senza JAVBOT. */
export default async function ExtCourseSignupPage({ params }: Params) {
  const { id } = await params;
  const [i18n, course, session] = await Promise.all([siteI18n(), findCourse(id), getSession()]);
  if (!course) notFound();
  const { t } = i18n;
  return (
    <SiteShell bot={false}>
      <PageIntro eyebrow={`🏫 ${[course.school_city, t("ext.site.badge")].filter(Boolean).join(" · ")}`} title={t("ext.signup.title", { school: course.school_name })} text={t("ext.signup.intro")} />
      <Container className="grid gap-8 py-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] lg:items-start">
        <div className="lg:sticky lg:top-24 [&_ul]:!grid-cols-1">
          <ExtCourseCards courses={[course]} i18n={i18n} hideSignup />
        </div>
        <ExtSignupForm course={course} loggedIn={session !== null} />
      </Container>
    </SiteShell>
  );
}
