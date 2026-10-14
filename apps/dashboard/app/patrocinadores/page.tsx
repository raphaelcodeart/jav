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
  return { title: `${t("site.nav.sponsor")} · Judo Arte e Vida`, description: t("site.sponsor.heroText") };
}

const WHY = [
  { key: "visibility", icon: "📣" },
  { key: "events", icon: "🏆" },
  { key: "values", icon: "🤝" },
  { key: "local", icon: "📍" },
] as const;

const FORMATS = [
  { key: "network", icon: "🌟" },
  { key: "club", icon: "🏯" },
  { key: "event", icon: "🎪" },
  { key: "kind", icon: "🎁" },
] as const;

const MAIL = "mailto:info@judoartevida.com?subject=Patroc%C3%ADnio%20JudoArteVida";

/** Diventa sponsor: perché sostenere la rete, in che forme, come contattarci.
 *  Niente prezzi: le condizioni si concordano caso per caso. */
export default async function SponsorPage() {
  const { t } = await siteI18n();
  return (
    <SiteShell>
      <StoryHero image="/site/judo-competition.jpg" eyebrow={`★ ${t("site.nav.sponsor")}`} title={t("site.sponsor.heroTitle")} text={t("site.sponsor.heroText")}>
        <a href={MAIL} className={linkButton({ size: "lg" })}>{t("site.sponsor.cta")}</a>
      </StoryHero>
      <section className="py-20">
        <Container>
          <SectionTitle eyebrow={t("site.sponsor.whyEyebrow")} title={t("site.sponsor.whyTitle")} />
          <FeatureGrid columns={2} items={WHY.map((w) => ({ icon: w.icon, title: t(`site.sponsor.why.${w.key}.title`), text: t(`site.sponsor.why.${w.key}.text`) }))} />
        </Container>
      </section>
      <section className="bg-accent-50/60 py-20">
        <Container>
          <SectionTitle eyebrow={t("site.sponsor.formatsEyebrow")} title={t("site.sponsor.formatsTitle")} text={t("site.sponsor.formatsText")} />
          <FeatureGrid columns={2} items={FORMATS.map((f) => ({ icon: f.icon, title: t(`site.sponsor.format.${f.key}.title`), text: t(`site.sponsor.format.${f.key}.text`) }))} />
        </Container>
      </section>
      <ImageBand image="/site/judo-kids.jpg">
        <Reveal>
          <div className="grid items-center gap-8 lg:grid-cols-[1.3fr_1fr]">
            <div>
              <h2 className="font-display text-4xl sm:text-5xl">{t("site.sponsor.contactTitle")}</h2>
              <p className="mt-4 max-w-2xl text-lg text-white/85">{t("site.sponsor.contactText")}</p>
            </div>
            <div className="flex flex-col gap-3">
              <a href={MAIL} className="rounded-2xl bg-white px-6 py-4 font-semibold text-ink-900 hover:bg-accent-50">✉️ info@judoartevida.com</a>
              <a href="tel:+351931148585" className="rounded-2xl bg-white/10 px-6 py-4 font-semibold ring-1 ring-white/30 backdrop-blur hover:bg-white/20">📞 +351 931 148 585</a>
              <Link href="/contactos" className="rounded-2xl px-6 py-3 text-sm font-semibold text-white/90 underline-offset-4 hover:underline">{t("site.footer.writeUs")} →</Link>
            </div>
          </div>
        </Reveal>
      </ImageBand>
    </SiteShell>
  );
}
