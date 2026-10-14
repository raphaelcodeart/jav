import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/site/blocks";
import { ImageBand } from "@/components/site/decor";
import { siteI18n } from "@/components/site/i18n";
import { linkButton } from "@/components/site/link-button";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { FeatureGrid, SectionTitle, StoryHero } from "@/components/site/story";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: `${t("site.nav.vision")} · Judo Arte e Vida`, description: t("site.vision.heroText") };
}

const PILLARS = [
  { key: "inclusion", icon: "🤲" },
  { key: "family", icon: "👪" },
  { key: "excellence", icon: "🥇" },
  { key: "values", icon: "🙇" },
  { key: "community", icon: "🌍" },
  { key: "innovation", icon: "⚡" },
] as const;

/** La visione: perché esiste JudoArteVida e dove vuole arrivare. */
export default async function VisionPage() {
  const { t } = await siteI18n();
  return (
    <SiteShell>
      <StoryHero image="/site/judo-hero.jpg" eyebrow={t("site.nav.vision")} title={t("site.vision.heroTitle")} text={t("site.vision.heroText")} />
      <section className="py-20">
        <Container className="grid items-start gap-12 lg:grid-cols-[1fr_1.3fr]">
          <Reveal>
            <SectionTitle eyebrow={t("site.vision.missionEyebrow")} title={t("site.vision.missionTitle")} />
          </Reveal>
          <Reveal delay={0.1}>
            <div className="space-y-5 text-lg leading-relaxed text-ink-700">
              <p>{t("site.vision.mission1")}</p>
              <p>{t("site.vision.mission2")}</p>
            </div>
          </Reveal>
        </Container>
      </section>
      <section className="bg-ink-50/60 py-20">
        <Container>
          <SectionTitle eyebrow={t("site.vision.pillarsEyebrow")} title={t("site.vision.pillarsTitle")} />
          <FeatureGrid items={PILLARS.map((p) => ({ icon: p.icon, title: t(`site.vision.pillar.${p.key}.title`), text: t(`site.vision.pillar.${p.key}.text`) }))} />
        </Container>
      </section>
      <ImageBand image="/site/judo-competition.jpg" tone="brand">
        <Reveal>
          <h2 className="max-w-3xl font-display text-4xl sm:text-5xl">{t("site.vision.goalTitle")}</h2>
          <p className="mt-5 max-w-2xl text-lg text-white/85">{t("site.vision.goalText")}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/projeto" className={linkButton({ variant: "dark" })}>{t("site.nav.project")}</Link>
            <Link href="/patrocinadores" className="inline-flex items-center rounded-2xl px-5 py-3 font-semibold ring-1 ring-white/60 hover:bg-white/10">★ {t("site.nav.sponsor")}</Link>
          </div>
        </Reveal>
      </ImageBand>
    </SiteShell>
  );
}
