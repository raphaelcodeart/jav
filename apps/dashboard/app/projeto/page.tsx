import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/site/blocks";
import { siteI18n } from "@/components/site/i18n";
import { linkButton } from "@/components/site/link-button";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { DarkBand, SectionTitle, StoryHero } from "@/components/site/story";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: `${t("site.nav.project")} · Judo Arte e Vida`, description: t("site.project.heroText") };
}

const AUDIENCES = [
  { key: "families", icon: "👪", items: 5 },
  { key: "clubs", icon: "🏯", items: 6 },
  { key: "athletes", icon: "🥋", items: 4 },
] as const;

/** Il progetto: che cos'è la piattaforma JudoArteVida, per chi, e come
 *  funziona. Descrive solo ciò che il gestionale fa davvero oggi. */
export default async function ProjectPage() {
  const { t } = await siteI18n();
  return (
    <SiteShell>
      <StoryHero image="/site/judo-adults.jpg" eyebrow={t("site.nav.project")} title={t("site.project.heroTitle")} text={t("site.project.heroText")} />
      <section className="py-20">
        <Container>
          <SectionTitle eyebrow={t("site.project.forEyebrow")} title={t("site.project.forTitle")} />
          <div className="grid gap-6 lg:grid-cols-3">
            {AUDIENCES.map((a, i) => (
              <Reveal key={a.key} delay={i * 0.08}>
                <div className={`h-full rounded-3xl p-8 ${i === 1 ? "bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-brand" : "bg-white shadow-soft ring-1 ring-ink-900/5"}`}>
                  <span className="text-4xl" aria-hidden="true">{a.icon}</span>
                  <h3 className={`mt-4 text-2xl ${i === 1 ? "text-white" : "text-ink-900"}`}>{t(`site.project.${a.key}.title`)}</h3>
                  <ul className="mt-5 space-y-3">
                    {Array.from({ length: a.items }, (_, n) => (
                      <li key={n} className={`flex gap-3 text-sm leading-relaxed ${i === 1 ? "text-white/90" : "text-ink-700"}`}>
                        <span className={i === 1 ? "text-accent-300" : "text-brand-500"} aria-hidden="true">✓</span>
                        {t.dyn(`site.project.${a.key}.item${n + 1}`, "")}
                      </li>
                    ))}
                  </ul>
                </div>
              </Reveal>
            ))}
          </div>
        </Container>
      </section>
      <DarkBand>
        <p className="text-xs font-bold uppercase tracking-[0.25em] text-accent-300">{t("site.project.howEyebrow")}</p>
        <h2 className="mt-2 font-display text-3xl sm:text-4xl">{t("site.project.howTitle")}</h2>
        <ol className="mt-10 grid gap-5 md:grid-cols-4">
          {([1, 2, 3, 4] as const).map((n) => (
            <Reveal key={n} delay={n * 0.06}>
              <li className="h-full rounded-3xl bg-white/[0.06] p-6 ring-1 ring-white/10">
                <span className="font-display text-4xl text-accent-300">{n}</span>
                <p className="mt-3 font-semibold">{t(`site.project.how.step${n}.title`)}</p>
                <p className="mt-1 text-sm text-white/70">{t(`site.project.how.step${n}.text`)}</p>
              </li>
            </Reveal>
          ))}
        </ol>
      </DarkBand>
      <section className="py-20">
        <Container className="text-center">
          <Reveal>
            <h2 className="mx-auto max-w-3xl font-display text-3xl text-ink-900 sm:text-4xl">{t("site.project.ctaTitle")}</h2>
            <p className="mx-auto mt-4 max-w-2xl text-lg text-ink-600">{t("site.project.ctaText")}</p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Link href="/contactos" className={linkButton({ size: "lg" })}>{t("site.project.ctaClub")}</Link>
              <Link href="/clubes" className={linkButton({ variant: "secondary", size: "lg" })}>{t("site.project.ctaFamily")}</Link>
            </div>
          </Reveal>
        </Container>
      </section>
    </SiteShell>
  );
}
