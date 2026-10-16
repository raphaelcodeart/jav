import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/site/blocks";
import { PageHero } from "@/components/site/page-hero";
import { siteI18n } from "@/components/site/i18n";
import { linkButton } from "@/components/site/link-button";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { publicSite } from "@/lib/public-site";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: `${t("site.shopJoin.title")} · Judo Arte e Vida`, description: t("site.shopJoin.text") };
}

/** «Comprar» dallo shop pubblico: per comprare bisogna essere soci di un club
 *  della rete. Chi ha già un account entra e trova lo Shop nella sua area;
 *  chi no sceglie un club (/c/<slug>, l'iscrizione al club). */
export default async function ShopJoinPage() {
  const [{ t }, clubs, photos] = await Promise.all([siteI18n(), publicSite.clubs(), publicSite.photos()]);
  return (
    <SiteShell>
      <PageHero theme="clubs" icon="🛒" photos={photos ?? []} eyebrow={t("site.nav.shop")} title={t("site.shopJoin.title")} text={t("site.shopJoin.text")} />
      <Container className="py-10">
        <div className="glass-card mx-auto flex max-w-3xl flex-col items-center gap-3 rounded-3xl p-6 text-center sm:flex-row sm:text-left">
          <span className="text-4xl" aria-hidden="true">🔑</span>
          <p className="flex-1 text-sm text-ink-700">{t("site.shopJoin.member")}</p>
          <Link href={`/login?next=${encodeURIComponent("/customer?tab=products")}`} className={linkButton({})}>{t("site.nav.login")}</Link>
        </div>
        <h2 className="mt-10 text-center text-2xl text-ink-900">{t("site.shopJoin.choose")}</h2>
        <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {(clubs ?? []).map((club, i) => (
            <li key={club.slug}>
              <Reveal delay={i * 0.05} className="h-full">
                <div className="glass-card flex h-full items-center gap-4 rounded-3xl p-5">
                  {club.logo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element -- logo caricato dal club
                    <img src={club.logo_url} alt="" className="h-14 w-14 shrink-0 rounded-2xl bg-white object-contain p-1 shadow-soft" />
                  ) : <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-2xl">🏯</span>}
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-ink-900">{club.name}</p>
                    {club.city && <p className="text-xs text-ink-500">{club.city}</p>}
                  </div>
                  <Link href={`/c/${club.slug}`} className={linkButton({ size: "sm" })}>{t("site.join")}</Link>
                </div>
              </Reveal>
            </li>
          ))}
        </ul>
        <p className="mt-8 text-center text-sm text-ink-500">
          {t("site.shopJoin.noClub")} <Link href="/criar-clube" className="font-semibold text-brand-700 underline">{t("site.nav.newClub")}</Link>
        </p>
      </Container>
    </SiteShell>
  );
}
