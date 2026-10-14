import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/site/blocks";
import { siteI18n } from "@/components/site/i18n";
import { linkButton } from "@/components/site/link-button";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { DarkBand, FeatureGrid, SectionTitle, StoryHero, Timeline } from "@/components/site/story";
import { publicSite } from "@/lib/public-site";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: `${t("site.nav.about")} · Judo Arte e Vida`, description: t("site.about.heroText") };
}

/** Chi siamo: la storia di Judo Arte e Vida, il suo responsabile tecnico, la
 *  squadra e i club. I fatti vengono dal sito storico judoartevida.com. */
export default async function AboutPage() {
  const { t } = await siteI18n();
  const home = await publicSite.home().catch(() => null);
  return (
    <SiteShell>
      <StoryHero image="/site/judo-kids.jpg" eyebrow={t("site.nav.about")} title={t("site.about.heroTitle")} text={t("site.about.heroText")} />

      <section className="py-20">
        <Container className="grid gap-14 lg:grid-cols-[1.2fr_1fr]">
          <Reveal>
            <SectionTitle eyebrow={t("site.about.storyEyebrow")} title={t("site.about.storyTitle")} />
            <div className="space-y-5 text-lg leading-relaxed text-ink-700">
              <p>{t("site.about.story1")}</p>
              <p>{t("site.about.story2")}</p>
            </div>
            <blockquote className="mt-8 rounded-3xl bg-brand-50 p-6 font-display text-xl leading-relaxed text-ink-900 ring-1 ring-brand-100">
              “{t("site.founder.quote")}”
              <footer className="mt-3 font-sans text-sm text-ink-500">Matias Luwawa</footer>
            </blockquote>
          </Reveal>
          <div>
            <SectionTitle eyebrow={t("site.about.timelineEyebrow")} title={t("site.about.timelineTitle")} />
            <Timeline items={(["1994", "2006", "2009", "2017", "today"] as const).map((y) => ({
              year: y === "today" ? t("site.about.timeline.todayYear") : y,
              title: t(`site.about.timeline.${y}.title`),
              text: t(`site.about.timeline.${y}.text`),
            }))} />
          </div>
        </Container>
      </section>

      <DarkBand>
        <p className="text-xs font-bold uppercase tracking-[0.25em] text-accent-300">{t("site.about.teamEyebrow")}</p>
        <h2 className="mt-2 font-display text-3xl sm:text-4xl">{t("site.about.teamTitle")}</h2>
        <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {(["matias", "paul", "marco", "ariel"] as const).map((m, i) => (
            <Reveal key={m} delay={i * 0.06}>
              <li className="h-full rounded-3xl bg-white/[0.06] p-6 ring-1 ring-white/10">
                <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 font-display text-2xl" aria-hidden="true">
                  {t(`site.about.team.${m}.name`).slice(0, 1)}
                </span>
                <p className="mt-4 text-lg font-semibold">{t(`site.about.team.${m}.name`)}</p>
                <p className="text-sm text-accent-300">{t(`site.about.team.${m}.role`)}</p>
                <p className="mt-2 text-sm text-white/70">{t(`site.about.team.${m}.text`)}</p>
              </li>
            </Reveal>
          ))}
        </ul>
      </DarkBand>

      <section className="py-20">
        <Container>
          <SectionTitle eyebrow={t("site.about.clubsEyebrow")} title={t("site.about.clubsTitle")} text={t("site.about.clubsText")} />
          <FeatureGrid items={(home?.clubs ?? []).map((c) => ({ icon: "🏯", title: c.name, text: c.tagline ?? c.city ?? "" }))} />
          <div className="mt-10 flex flex-wrap gap-3">
            <Link href="/clubes" className={linkButton({ size: "lg" })}>{t("site.clubs.all")}</Link>
            <Link href="/visao" className={linkButton({ variant: "secondary", size: "lg" })}>{t("site.nav.vision")}</Link>
          </div>
        </Container>
      </section>
    </SiteShell>
  );
}
