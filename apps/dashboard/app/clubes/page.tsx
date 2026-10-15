import type { Metadata } from "next";
import Link from "next/link";
import { Container, EmptyNote } from "@/components/site/blocks";
import { HeroStat, PageHero } from "@/components/site/page-hero";
import { TatamiBackdrop } from "@/components/site/club-carousel";
import { siteI18n } from "@/components/site/i18n";
import { linkButton } from "@/components/site/link-button";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { publicSite } from "@/lib/public-site";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: t("site.meta.clubsTitle"), description: t("site.clubs.text") };
}

/** Tutti i club della rete con la pagina pubblicata. */
export default async function ClubsPage() {
  const [{ t }, clubsOrNull, photos] = await Promise.all([siteI18n(), publicSite.clubs(), publicSite.photos()]);
  const clubs = clubsOrNull ?? [];
  return (
    <SiteShell>
      <PageHero theme="clubs" icon="🏯" photos={photos ?? []} eyebrow={t("site.clubs.eyebrow")} title={t("site.clubs.title")} text={t("site.clubs.text")}>
        <HeroStat value={clubs.length} label={t("site.rank.heroClubs")} />
      </PageHero>
      <Container className="py-12">
        {clubs.length === 0 ? (
          <EmptyNote>{t("site.clubs.empty")}</EmptyNote>
        ) : (
          <ul className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {clubs.map((club, i) => (
              <li key={club.slug}>
                <Reveal delay={i * 0.05} className="h-full">
                  <article className="glass-card group relative flex h-full flex-col overflow-hidden rounded-3xl">
                    <div className="relative h-44 overflow-hidden">
                      {club.hero_image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element -- copertina caricata dal club
                        <img src={club.hero_image_url} alt="" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" loading="lazy" />
                      ) : (
                        <TatamiBackdrop />
                      )}
                      {club.logo_url && (
                        // eslint-disable-next-line @next/next/no-img-element -- logo caricato dal club
                        <img src={club.logo_url} alt="" className="absolute bottom-3 left-3 h-14 w-14 rounded-2xl bg-white object-contain p-1 shadow-soft" />
                      )}
                    </div>
                    <div className="flex flex-1 flex-col p-5">
                      {club.city && <p className="text-xs font-bold uppercase tracking-[0.2em] text-brand-600">{club.city}</p>}
                      <h2 className="mt-1 text-xl text-ink-900">
                        <Link href={`/clubes/${club.slug}`} className="after:absolute after:inset-0 hover:text-brand-700">{club.name}</Link>
                      </h2>
                      {club.tagline && <p className="mt-2 text-sm text-ink-600">{club.tagline}</p>}
                      <p className="mt-4 text-xs font-semibold text-ink-500">
                        {t("site.clubs.counts", { athletes: club.athletes_active, judoka: club.judoka_public })}
                      </p>
                      <div className="relative z-10 mt-5 flex gap-2">
                        <Link href={`/c/${club.slug}`} className={linkButton({ size: "sm" })}>{t("site.join")}</Link>
                      </div>
                    </div>
                  </article>
                </Reveal>
              </li>
            ))}
          </ul>
        )}
      </Container>
    </SiteShell>
  );
}
