import type { Metadata } from "next";
import Link from "next/link";
import { Podium } from "@/components/ui/gamification";
import { ClubCarousel } from "@/components/site/club-carousel";
import { CourseCards } from "@/components/site/course-cards";
import { Container, EmptyNote, EventCard, MedalList, RankingTable, SectionHeading } from "@/components/site/blocks";
import { siteI18n } from "@/components/site/i18n";
import { linkButton } from "@/components/site/link-button";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { ImageBand, WaveDivider, WordMarquee } from "@/components/site/decor";
import { VideoCarousel3D } from "@/components/site/video-carousel-3d";
import { VideoHero } from "@/components/site/video-hero";
import { HERO_VIDEO_ID, publicSite, type PortalHome } from "@/lib/public-site";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return {
    title: t("site.meta.homeTitle"),
    description: t("site.meta.homeDescription"),
    openGraph: { title: t("site.meta.homeTitle"), description: t("site.meta.homeDescription"), images: ["/judoartevida-logo.jpg"] },
  };
}

const EMPTY: PortalHome = {
  season: 0, season_label: "", clubs: [], totals: { clubs: 0, athletes_active: 0, judoka_public: 0 },
  upcoming_events: [], top_ranking: [], latest_medals: [],
};

const DATE_LOCALES: Record<string, string> = { pt: "pt-PT", it: "it-IT", en: "en-GB" };

const VALUES = [
  { key: "art", icon: "M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5z" },
  { key: "discipline", icon: "M4 12h16M12 4v16M6 6l12 12" },
  { key: "life", icon: "M12 21s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.5-7 10-7 10z" },
] as const;

/** La home del portale JudoArteVida: cos'è il progetto, i club attivi, cosa
 *  succede (eventi, ranking, medaglie) e come entrarci. Prima era solo un
 *  rimando al login: il login resta a un clic, in alto a destra e nel hero. */
const BENEFITS = [
  { key: "education", icon: "📚" },
  { key: "selfEsteem", icon: "💪" },
  { key: "proactive", icon: "🛡️" },
  { key: "focus", icon: "🎯" },
  { key: "selfControl", icon: "🧘" },
  { key: "respect", icon: "🤝" },
] as const;

export default async function PortalHomePage() {
  const i18n = await siteI18n();
  const { t, fmt, locale } = i18n;
  // Se l'API non risponde la home si apre lo stesso, con la parte che non
  // dipende dai dati: chi cerca il login lo deve trovare comunque.
  const [homeData, videoData, coursesData] = await Promise.all([
    publicSite.home().catch(() => null),
    publicSite.videos().catch(() => null),
    publicSite.courses().catch(() => null),
  ]);
  const courses = coursesData?.courses ?? [];
  const home = homeData ?? EMPTY;
  const videos = (videoData ?? []).slice(0, 15);

  return (
    <SiteShell>
      {/* --- Header dinamico: il video di JudoArteVida dietro, luce e movimento sopra --- */}
      <VideoHero
        videoId={HERO_VIDEO_ID}
        eyebrow={t("site.hero.eyebrow")}
        titleA={t("site.hero.titleA")}
        titleB={t("site.hero.titleB")}
        text={t("site.hero.text")}
        ctaPrimary={{ href: "#clubes", label: t("site.hero.ctaClubs") }}
        ctaSecondary={{ href: "/login", label: t("site.hero.ctaLogin") }}
        // Un numero a zero (nessun evento in calendario) non dice niente:
        // si mostrano solo quelli che ci sono.
        stats={[
          { value: home.totals.clubs, label: t("site.stats.clubs") },
          { value: home.totals.athletes_active, label: t("site.stats.athletes") },
          { value: home.upcoming_events.length, label: t("site.stats.events") },
        ].filter((s) => s.value > 0)}
        scrollLabel={t("site.tv.scroll")}
      />

      {/* --- JudoArteVida TV: i video del canale YouTube in un anello 3D --- */}
      {videos.length > 0 && (
        <section id="tv" aria-labelledby="tv-title" className="relative scroll-mt-24 overflow-hidden bg-ink-950 pb-16 pt-12 text-white">
          <div className="pointer-events-none absolute left-1/2 top-0 h-[28rem] w-[60rem] -translate-x-1/2 rounded-full bg-brand-600/25 blur-[120px]" aria-hidden="true" />
          <Container className="relative">
            <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.25em] text-accent-300">{t("site.tv.eyebrow")}</p>
                <h2 id="tv-title" className="mt-2 font-display text-4xl sm:text-5xl">{t("site.tv.title")}</h2>
                <p className="mt-3 max-w-xl text-white/70">{t("site.tv.text")}</p>
              </div>
              <a href="https://www.youtube.com/@ml8126" target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-full bg-white/10 px-5 py-2.5 text-sm font-semibold ring-1 ring-white/20 hover:bg-white/20">
                ▶ {t("site.tv.channel")} ↗
              </a>
            </div>
            <VideoCarousel3D
              videos={videos}
              locale={DATE_LOCALES[locale] ?? "pt-PT"}
              labels={{
                play: t("site.tv.play"), prev: t("site.tv.prev"), next: t("site.tv.next"), close: t("site.tv.close"),
                watchOnYoutube: t("site.tv.youtube"), region: t("site.tv.title"),
              }}
            />
          </Container>
        </section>
      )}
      <WordMarquee words={[t("site.marquee.judo"), t("site.marquee.art"), t("site.marquee.life"), "柔道", t("site.marquee.discipline"), t("site.marquee.respect"), t("site.marquee.family")]} />

      {/* --- Club --- */}
      <section id="clubes" aria-labelledby="clubes-title" className="scroll-mt-20 py-12">
        <Container>
          <SectionHeading
            id="clubes-title"
            eyebrow={t("site.clubs.eyebrow")}
            title={t("site.clubs.title")}
            text={t("site.clubs.text")}
            action={<Link href="/clubes" className={linkButton({ variant: "secondary" })}>{t("site.clubs.all")}</Link>}
          />
          {home.clubs.length > 0 ? <ClubCarousel clubs={home.clubs} /> : <EmptyNote>{t("site.clubs.empty")}</EmptyNote>}
        </Container>
      </section>

      {/* --- I corsi JAV nelle scuole: separati dai club, senza persone --- */}
      {courses.length > 0 && (
        <section id="cursos" aria-labelledby="cursos-title" className="scroll-mt-20 pb-12">
          <Container>
            <SectionHeading
              id="cursos-title"
              eyebrow={t("site.courses.eyebrow")}
              title={t("site.courses.title")}
              text={t("site.courses.text")}
              action={<Link href="/cursos" className={linkButton({ variant: "secondary" })}>{t("site.courses.all")}</Link>}
            />
            <CourseCards courses={courses.slice(0, 6)} i18n={i18n} />
          </Container>
        </section>
      )}

      {/* --- La voce del fondatore, su una fascia fotografica --- */}
      <ImageBand image="/site/judo-kids.jpg">
        <Reveal>
          <figure className="mx-auto max-w-4xl text-center">
            <p className="font-display text-7xl leading-none text-accent-300" aria-hidden="true">“</p>
            <blockquote className="font-display text-2xl leading-relaxed sm:text-4xl">{t("site.founder.quote")}</blockquote>
            <figcaption className="mt-6 text-sm text-white/70">
              <span className="font-semibold text-white">Matias Luwawa</span> · {t("site.founder.role")}
            </figcaption>
          </figure>
        </Reveal>
      </ImageBand>

      {/* --- I benefici del judo, dal sito storico di Judo Arte e Vida --- */}
      <section aria-labelledby="beneficios" className="py-12">
        <Container>
          <SectionHeading id="beneficios" eyebrow={t("site.benefits.eyebrow")} title={t("site.benefits.title")} />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {BENEFITS.map((b, i) => (
              <Reveal key={b.key} delay={i * 0.05}>
                <div className="glass-card h-full rounded-3xl p-5">
                  <p className="text-2xl" aria-hidden="true">{b.icon}</p>
                  <h3 className="mt-2 text-base text-ink-900">{t(`site.benefits.${b.key}.title`)}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-ink-600">{t(`site.benefits.${b.key}.text`)}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </Container>
      </section>

      {/* --- Valori --- */}
      <section aria-labelledby="valores" className="py-12">
        <Container>
          <SectionHeading id="valores" eyebrow={t("site.values.eyebrow")} title={t("site.values.title")} text={t("site.values.text")} />
          <div className="grid gap-5 md:grid-cols-3">
            {VALUES.map((v, i) => (
              <Reveal key={v.key} delay={i * 0.08}>
                <div className="glass-card h-full rounded-3xl p-6">
                  <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
                    <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d={v.icon} /></svg>
                  </div>
                  <h3 className="text-lg text-ink-900">{t(`site.values.${v.key}.title`)}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-ink-600">{t(`site.values.${v.key}.text`)}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </Container>
      </section>

      {/* --- Eventi --- */}
      <section aria-labelledby="eventos-title" className="py-12">
        <Container>
          <SectionHeading
            id="eventos-title"
            eyebrow={t("site.events.eyebrow")}
            title={t("site.events.title")}
            action={<Link href="/eventos" className={linkButton({ variant: "secondary" })}>{t("site.events.all")}</Link>}
          />
          {home.upcoming_events.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {home.upcoming_events.map((e, i) => (
                <Reveal key={e.id} delay={i * 0.05}><EventCard event={e} t={t} fmt={fmt} /></Reveal>
              ))}
            </div>
          ) : (
            <EmptyNote>{t("site.events.empty")}</EmptyNote>
          )}
        </Container>
      </section>

      {/* --- La competizione --- */}
      <ImageBand image="/site/judo-competition.jpg" tone="brand">
        <Reveal>
          <div className="max-w-2xl">
            <p className="text-xs font-bold uppercase tracking-[0.25em] text-accent-300">{t("site.band.compete.eyebrow")}</p>
            <h2 className="mt-3 font-display text-4xl sm:text-6xl">{t("site.band.compete.title")}</h2>
            <p className="mt-5 text-lg text-white/80">{t("site.band.compete.text")}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/eventos" className={linkButton({ variant: "dark" })}>{t("site.events.all")}</Link>
              <Link href="/ranking" className="inline-flex items-center rounded-2xl px-5 py-3 font-semibold ring-1 ring-white/50 hover:bg-white/10">{t("site.ranking.full")}</Link>
            </div>
          </div>
        </Reveal>
      </ImageBand>

      {/* --- Ranking e medaglie --- */}
      <section aria-labelledby="ranking-title" className="py-12">
        <Container className="grid gap-10 lg:grid-cols-[1.3fr_1fr]">
          <div>
            <SectionHeading
              id="ranking-title"
              eyebrow={home.season_label ? t("site.ranking.season", { season: home.season_label }) : t("site.ranking.eyebrow")}
              title={t("site.ranking.title")}
              action={<Link href="/ranking" className={linkButton({ variant: "secondary" })}>{t("site.ranking.full")}</Link>}
            />
            {home.top_ranking.length > 0 ? (
              <>
                {home.top_ranking.length >= 3 && (
                  <div className="mb-6">
                    <Podium entries={home.top_ranking.slice(0, 3).map((r) => ({ name: r.display_name, points: r.points, photoUrl: r.photo_url, href: `/judocas/${r.id}` }))} />
                  </div>
                )}
                <RankingTable rows={home.top_ranking.slice(0, 5)} t={t} />
              </>
            ) : (
              <EmptyNote>{t("site.ranking.empty")}</EmptyNote>
            )}
          </div>
          <div>
            <SectionHeading eyebrow={t("site.medals.eyebrow")} title={t("site.medals.title")} />
            {home.latest_medals.length > 0 ? (
              <div className="glass-card rounded-2xl px-4"><MedalList medals={home.latest_medals} t={t} fmt={fmt} /></div>
            ) : (
              <EmptyNote>{t("site.medals.empty")}</EmptyNote>
            )}
          </div>
        </Container>
      </section>

      {/* --- Come funziona --- */}
      <section aria-labelledby="como-title" className="py-12">
        <Container>
          <SectionHeading id="como-title" eyebrow={t("site.how.eyebrow")} title={t("site.how.title")} />
          <div className="grid gap-6 lg:grid-cols-2">
            {(["families", "clubs"] as const).map((who) => (
              <Reveal key={who}>
                <div className={who === "families" ? "h-full rounded-3xl bg-gradient-to-br from-brand-500 to-brand-700 p-8 text-white shadow-brand" : "h-full rounded-3xl bg-ink-900 p-8 text-white shadow-lift"}>
                  <h3 className="text-2xl">{t(`site.how.${who}.title`)}</h3>
                  <ol className="mt-6 space-y-4">
                    {([1, 2, 3] as const).map((n) => (
                      <li key={n} className="flex gap-4">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/15 font-display text-sm ring-1 ring-white/30" aria-hidden="true">{n}</span>
                        <p className="text-white/90">{t(`site.how.${who}.step${n}`)}</p>
                      </li>
                    ))}
                  </ol>
                </div>
              </Reveal>
            ))}
          </div>
          <p className="mt-6 flex items-start gap-2 text-sm text-ink-500">
            <svg className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" /></svg>
            {t("site.privacyNote")}
          </p>
        </Container>
      </section>

      {/* --- Iscriviti --- */}
      <WaveDivider className="text-ink-950" />
      <ImageBand image="/site/judo-adults.jpg">
        <div className="grid items-center gap-10 lg:grid-cols-[1.2fr_1fr]">
          <Reveal>
            <h2 id="junta-title" className="font-display text-4xl sm:text-5xl">{t("site.cta.title")}</h2>
            <p className="mt-4 max-w-2xl text-lg text-white/80">{t("site.cta.text")}</p>
          </Reveal>
          <Reveal delay={0.1}>
            {home.clubs.length > 0 ? (
              <ul className="flex flex-col gap-3">
                {home.clubs.map((c) => (
                  <li key={c.slug}>
                    <Link href={`/c/${c.slug}`} className="group flex items-center justify-between rounded-2xl bg-white/10 px-5 py-4 font-semibold ring-1 ring-white/20 backdrop-blur transition hover:bg-white hover:text-ink-900">
                      {t("site.cta.joinClub", { club: c.name })}
                      <span className="transition group-hover:translate-x-1" aria-hidden="true">→</span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <Link href="/login" className={linkButton({ size: "lg" })}>{t("site.hero.ctaLogin")}</Link>
            )}
          </Reveal>
        </div>
      </ImageBand>
    </SiteShell>
  );
}
