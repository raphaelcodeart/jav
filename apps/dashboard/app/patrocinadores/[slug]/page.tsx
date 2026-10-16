import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Container } from "@/components/site/blocks";
import { siteI18n } from "@/components/site/i18n";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { SponsorTile } from "@/components/site/sponsor-marquee";
import { publicSite } from "@/lib/public-site";

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const [{ t }, sponsor] = await Promise.all([siteI18n(), publicSite.sponsor(slug)]);
  if (!sponsor) return { title: t("site.nav.sponsor") };
  return {
    title: `${sponsor.name} · ${t("site.sponsors.eyebrow")} · Judo Arte e Vida`,
    description: sponsor.tagline ?? t("site.sponsors.pageText", { name: sponsor.name }),
    openGraph: { title: sponsor.name, images: sponsor.logo_url ? [sponsor.logo_url] : ["/judoartevida-logo.jpg"] },
  };
}

/** La pagina di uno sponsor: chi è, perché sostiene la rete, e un bottone
 *  grande verso il suo sito. La scrive lo staff di JudoArteVida (console →
 *  Sponsor). */
export default async function SponsorPage({ params }: Params) {
  const { slug } = await params;
  const [{ t }, sponsor, all] = await Promise.all([siteI18n(), publicSite.sponsor(slug), publicSite.sponsors()]);
  if (!sponsor) notFound();
  const color = sponsor.color ?? "#E13F22";
  const others = (all ?? []).filter((s) => s.id !== sponsor.id);

  return (
    <SiteShell>
      <section className="relative isolate overflow-hidden text-white" style={{ background: `linear-gradient(135deg, ${color} 0%, #0a0a0a 120%)` }}>
        <div className="pointer-events-none absolute inset-0 -z-10 opacity-10 [background-image:repeating-linear-gradient(135deg,#fff_0_2px,transparent_2px_24px)]" aria-hidden="true" />
        <div className="pointer-events-none absolute -right-24 -top-24 -z-10 h-96 w-96 rounded-full bg-white/20 blur-[100px] animate-aurora" aria-hidden="true" />
        <Container className="grid items-center gap-10 py-16 sm:py-20 lg:grid-cols-[1.2fr_1fr]">
          <Reveal>
            <nav className="mb-6 text-sm text-white/75" aria-label={t("site.breadcrumb")}>
              <Link href="/patrocinadores" className="hover:text-white">{t("site.nav.sponsor")}</Link> <span aria-hidden="true">/</span> {sponsor.name}
            </nav>
            <p className="text-xs font-bold uppercase tracking-[0.25em] text-white/80">★ {t("site.sponsors.eyebrow")}</p>
            <h1 className="mt-2 font-display text-4xl leading-tight sm:text-6xl">{sponsor.name}</h1>
            {sponsor.tagline && <p className="mt-3 text-xl text-white/85">{sponsor.tagline}</p>}
            {sponsor.website_url && (
              <a href={sponsor.website_url} target="_blank" rel="noopener noreferrer"
                className="mt-8 inline-flex h-16 items-center gap-3 rounded-2xl bg-white px-8 text-lg font-bold text-ink-900 shadow-lift transition hover:-translate-y-1 hover:shadow-2xl">
                {t("site.sponsors.visit")} <span aria-hidden="true">↗</span>
              </a>
            )}
          </Reveal>
          <Reveal delay={0.1} className="flex justify-center">
            <div className="flex aspect-square w-64 items-center justify-center rounded-[2.5rem] bg-white p-8 shadow-2xl ring-8 ring-white/20 sm:w-80">
              {sponsor.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element -- logo caricato dalla piattaforma
                <img src={sponsor.logo_url} alt={sponsor.name} className="max-h-full max-w-full object-contain" />
              ) : (
                <SponsorTile sponsor={sponsor} className="h-auto shadow-none ring-0" />
              )}
            </div>
          </Reveal>
        </Container>
      </section>

      <Container className="grid gap-10 py-14 lg:grid-cols-[1.4fr_1fr]">
        <Reveal>
          <h2 className="text-2xl text-ink-900">{t("site.sponsors.about", { name: sponsor.name })}</h2>
          {sponsor.description ? (
            <div className="mt-4 space-y-4 text-lg leading-relaxed text-ink-700">
              {sponsor.description.split(/\n\s*\n/).map((p, i) => <p key={i} className="whitespace-pre-line">{p}</p>)}
            </div>
          ) : (
            <p className="mt-4 text-lg text-ink-600">{t("site.sponsors.pageText", { name: sponsor.name })}</p>
          )}
          {sponsor.website_url && (
            <a href={sponsor.website_url} target="_blank" rel="noopener noreferrer"
              className="mt-8 inline-flex h-14 items-center gap-3 rounded-2xl px-7 font-bold text-white shadow-lift transition hover:-translate-y-0.5"
              style={{ backgroundColor: color }}>
              🌐 {t("site.sponsors.visit")} <span aria-hidden="true">↗</span>
            </a>
          )}
        </Reveal>
        <Reveal delay={0.1} className="space-y-4">
          <div className="rounded-3xl bg-gradient-to-br from-brand-500 to-brand-700 p-6 text-white shadow-brand">
            <p className="text-lg font-semibold">{t("site.sponsors.thanksTitle")}</p>
            <p className="mt-1 text-sm text-white/90">{t("site.sponsors.thanksText", { name: sponsor.name })}</p>
            <Link href="/patrocinadores#contacto" className="mt-4 inline-flex h-10 items-center rounded-xl bg-white px-4 text-sm font-semibold text-ink-900 hover:bg-accent-50">
              {t("site.sponsors.become")}
            </Link>
          </div>
          {others.length > 0 && (
            <div className="glass-card rounded-3xl p-5">
              <p className="mb-3 text-xs font-bold uppercase tracking-[0.22em] text-ink-500">{t("site.sponsors.others")}</p>
              <ul className="space-y-2">
                {others.map((s) => (
                  <li key={s.id}><Link href={`/patrocinadores/${s.slug}`} className="block transition hover:-translate-y-0.5"><SponsorTile sponsor={s} className="h-16" /></Link></li>
                ))}
              </ul>
            </div>
          )}
        </Reveal>
      </Container>
    </SiteShell>
  );
}
