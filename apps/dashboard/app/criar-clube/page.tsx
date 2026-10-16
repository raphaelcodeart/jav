import type { Metadata } from "next";
import { Container } from "@/components/site/blocks";
import { PageHero } from "@/components/site/page-hero";
import { siteI18n } from "@/components/site/i18n";
import { NewClubForm } from "@/components/site/new-club-form";
import { SiteShell } from "@/components/site/site-shell";
import { publicSite } from "@/lib/public-site";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: `${t("site.nav.newClub")} · Judo Arte e Vida`, description: t("site.newClub.text") };
}

/** «Crea il tuo club»: la richiesta arriva a JudoArteVida (argomento NEW_CLUB). */
export default async function NewClubPage() {
  const [{ t }, photos] = await Promise.all([siteI18n(), publicSite.photos()]);
  return (
    <SiteShell>
      <PageHero theme="clubs" icon="🏯" photos={photos ?? []} eyebrow={t("site.newClub.eyebrow")} title={t("site.nav.newClub")} text={t("site.newClub.text")} />
      <Container className="py-10">
        <NewClubForm />
      </Container>
    </SiteShell>
  );
}
