import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { CSSProperties, ReactNode } from "react";
import { Avatar, Container, EmptyNote, EventCard, JudokaCard, MedalList, SectionHeading } from "@/components/site/blocks";
import { TatamiBackdrop } from "@/components/site/club-carousel";
import { CountUp, NextTraining } from "@/components/site/club-live";
import { ClubMap, ClubVideos, MobileClubBar, NewsFeed, type PlayableVideo } from "@/components/site/club-media";
import { ClubTabs, TabLink, type ClubTab } from "@/components/site/club-tabs";
import { ContactForm } from "@/components/site/contact-form";
import { Gallery } from "@/components/site/gallery";
import { AthleteRanking } from "@/components/site/ranking-explorer";
import { ageRange, siteI18n } from "@/components/site/i18n";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { SocialIcons, type SocialLink } from "@/components/site/social-icons";
import { themeStyle } from "@/lib/brand";
import { cn } from "@/lib/cn";
import type { Formatters, Translator } from "@/lib/i18n/translate";
import { publicSite, type ChannelVideo, type ClubGroup, type ClubPage, type Coach, type ScheduleDay } from "@/lib/public-site";

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const [{ t }, club] = await Promise.all([siteI18n(), publicSite.club(slug)]);
  if (!club) return { title: t("site.notFound.club") };
  const description = club.tagline ?? t("site.meta.clubDescription", { club: club.name });
  // L'anteprima di un link condiviso: la copertina (grande) e il logo.
  const images = [club.hero_image_url, club.logo_url].filter((u): u is string => Boolean(u));
  return {
    title: `${club.name} · Judo Arte e Vida`,
    description,
    alternates: { canonical: `/clubes/${club.slug}` },
    openGraph: {
      type: "website",
      title: club.name,
      description,
      images: images.length > 0 ? images.map((url) => ({ url, alt: club.name })) : ["/judoartevida-logo.jpg"],
    },
    twitter: { card: club.hero_image_url ? "summary_large_image" : "summary", title: club.name, description },
  };
}

/** La pagina di un club come la sua pagina Facebook, ma sua: copertina e
 *  logo, i colori del club (il tema arriva calcolato dall'API, contrasto
 *  compreso), i numeri, le schede (Sobre, Grupos, Horário, Treinadores,
 *  Fotos, Provas, Ranking) e in fondo il modulo per scrivere al club. Testi
 *  e foto li scrive la segreteria; gruppi, orari, eventi, judoca e ranking
 *  arrivano da soli dal gestionale. Nessun dato personale: l'API manda solo
 *  ciò che può essere pubblico. */
export default async function ClubLandingPage({ params }: Params) {
  const { slug } = await params;
  const [{ t, fmt }, club, channel] = await Promise.all([
    siteI18n(), publicSite.club(slug),
    // Il canale del club: un video nuovo su YouTube compare qui da solo. Se
    // YouTube non risponde la pagina c'è lo stesso, senza quei video.
    publicSite.clubVideos(slug).catch((): ChannelVideo[] => []),
  ]);
  if (!club) notFound();

  const medals = club.judoka.reduce((n, j) => n + j.gold + j.silver + j.bronze, 0);
  const weeklyClasses = club.schedule.reduce((n, d) => n + d.slots.length, 0);
  const socials: SocialLink[] = ([
    { kind: "facebook", url: club.facebook_url, label: "Facebook" },
    { kind: "instagram", url: club.instagram_url, label: "Instagram" },
    { kind: "youtube", url: club.youtube_url, label: "YouTube" },
    { kind: "website", url: club.website_url, label: t("site.club.website") },
  ] as const).filter((s) => Boolean(s.url)).map((s) => ({ ...s, url: s.url as string }));
  // I video: prima quelli scelti dal club, poi gli ultimi del suo canale.
  const videos: PlayableVideo[] = [
    ...club.videos.map((v, i) => ({ youtube_id: v.youtube_id, title: v.caption ?? t("site.fan.videoOf", { club: club.name, n: i + 1 }) })),
    ...(channel ?? []).map((v) => ({ youtube_id: v.id, title: v.title, published: v.published })),
  ].filter((v, i, all) => all.findIndex((w) => w.youtube_id === v.youtube_id) === i).slice(0, 9);
  const mapQuery = [club.venue, club.address, club.city].filter(Boolean).join(", ");
  const since = club.founded_year ? new Date().getFullYear() - club.founded_year : 0;
  const prices = club.groups.map((g) => g.monthly_price_cents).filter((c): c is number => c !== null);
  const fromPrice = prices.length > 0 ? Math.min(...prices) : null;
  // I numeri del club, contati e mai scritti a mano; quelli a zero non si dicono.
  const facts = [
    { value: club.athletes_active, label: t("site.fan.factAthletes") },
    { value: club.groups.length, label: t("site.fan.factGroups") },
    { value: weeklyClasses, label: t("site.fan.factClasses") },
    { value: club.coaches.length, label: t("site.fan.factCoaches") },
    { value: medals, label: t("site.fan.factMedals") },
  ].filter((f) => f.value > 0);

  const tabs: (ClubTab & { show: boolean })[] = [
    { id: "inicio", label: t("site.fan.tabHome"), icon: <Icon d="M3 11.5 12 4l9 7.5M5.5 9.5V20h13V9.5" />, show: true },
    { id: "horarios", label: t("site.fan.tabPrices"), icon: <Icon d="M4 6.5h16M4 6.5V20h16V6.5M8 3v5M16 3v5M8 12h3M8 16h6" />, aliases: ["grupos", "horario"], show: true },
    { id: "equipa", label: t("site.fan.tabCoaches"), icon: <Icon d="M16 19v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 17.5V19M10 10.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM20 19v-1.5a3.5 3.5 0 0 0-2.5-3.35M15.5 4.6a3 3 0 0 1 0 5.8" />, aliases: ["treinadores"], show: club.coaches.length > 0 },
    { id: "galeria", label: t("site.fan.tabMedia"), icon: <Icon d="M4 5h16v14H4zM4 15l4.5-4.5 4 4L16 11l4 4M15 8.5h.01" />, aliases: ["fotos", "videos"], show: club.gallery.length > 0 || videos.length > 0 || Boolean(club.youtube_url) },
    { id: "novidades", label: t("site.fan.tabNews"), icon: <Icon d="M5 4h11l3 3v13H5zM8.5 9h7M8.5 13h7M8.5 17h4" />, aliases: ["historia"], show: club.news.length > 0 || club.history.length > 0 },
    { id: "competicao", label: t("site.fan.tabCompetition"), icon: <Icon d="M8 4h8v5a4 4 0 0 1-8 0V4ZM8 6H5v1.5A3.5 3.5 0 0 0 8.5 11M16 6h3v1.5a3.5 3.5 0 0 1-3.5 3.5M12 13v4M8.5 20h7" />, aliases: ["provas", "ranking"], show: true },
    { id: "contactos", label: t("site.fan.tabMessage"), icon: <Icon d="M4 6h16v12H4zM4.5 6.5 12 13l7.5-6.5" />, aliases: ["mensagem", "onde"], show: true },
  ];
  const visibleTabs = tabs.filter((tab) => tab.show).map(({ show: _show, ...tab }) => tab);

  const panels: Record<string, ReactNode> = {
    inicio: (
      <Container className="space-y-14 py-10 sm:py-14">
        <div className="grid gap-10 lg:grid-cols-[1fr_22rem]">
          <Panel eyebrow={t("site.club.aboutEyebrow")} title={t("site.club.about", { club: club.name })}>
            {club.about ? (
              <div className="max-w-3xl space-y-4 text-lg leading-relaxed text-ink-700">
                {club.about.split(/\n\s*\n/).map((para, i) => (
                  <p key={i} className={cn("whitespace-pre-line", i === 0 && "first-letter:float-left first-letter:mr-2 first-letter:font-display first-letter:text-6xl first-letter:leading-[0.85] first-letter:text-club-ink")}>{para}</p>
                ))}
              </div>
            ) : (
              <EmptyNote>{t("site.fan.aboutEmpty")}</EmptyNote>
            )}
          </Panel>
          {/* Le scorciatoie: le cose per cui si apre la pagina di un club. */}
          <div className="space-y-4">
            <TabLink to="horarios" className="group block overflow-hidden rounded-3xl bg-gradient-to-br from-club-cover-from to-club-cover-to p-6 text-white shadow-lift transition hover:-translate-y-1 motion-reduce:transition-none">
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-club-glow">{t("site.fan.tabPrices")}</p>
              {fromPrice !== null ? (
                <p className="mt-3 font-display text-4xl leading-none">
                  <span className="text-base font-sans text-white/80">{t("site.fan.from")} </span>{fmt.euro(fromPrice, { maximumFractionDigits: 0 })}
                  <span className="text-base font-sans text-white/80">{t("site.fan.perMonth")}</span>
                </p>
              ) : (
                <p className="mt-3 text-2xl font-semibold">{t("site.fan.groupsCount", { n: club.groups.length })}</p>
              )}
              <p className="mt-2 text-sm text-white/85">{t("site.fan.pricesTeaser", { n: club.groups.length, classes: weeklyClasses })}</p>
              <span className="mt-5 inline-flex items-center gap-2 rounded-xl bg-club-accent px-4 py-2 text-sm font-semibold text-club-on-accent">
                {t("site.fan.seePrices")} <span aria-hidden="true" className="transition-transform group-hover:translate-x-1">→</span>
              </span>
            </TabLink>
            <InfoCard club={club} socials={socials} t={t} />
          </div>
        </div>

        {(club.highlights.length > 0 || since > 0) && (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" aria-label={t("site.fan.highlightsLabel")}>
            {since > 0 && <Highlight value={String(since)} label={t("site.fan.yearsOfJudo")} />}
            {club.highlights.map((h) => <Highlight key={`${h.value}-${h.label}`} value={h.value} label={h.label} />)}
          </ul>
        )}

        {club.pillars.length > 0 && (
          <Panel eyebrow={club.name} title={t("site.fan.pillarsTitle")}>
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {club.pillars.map((p, i) => (
                <li key={p.title} className="glass-card group relative overflow-hidden rounded-3xl p-6">
                  <span className="absolute -right-3 -top-6 font-display text-8xl text-club/10 transition-transform duration-500 group-hover:-translate-y-1 motion-reduce:transition-none" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
                  <span className="mb-3 block h-1 w-10 rounded-full bg-club" aria-hidden="true" />
                  <h3 className="relative text-lg text-ink-900">{p.title}</h3>
                  {p.text && <p className="relative mt-2 text-sm leading-relaxed text-ink-600">{p.text}</p>}
                </li>
              ))}
            </ul>
          </Panel>
        )}

        {club.news[0] && (
          <Panel eyebrow={t("site.fan.newsEyebrow")} title={t("site.fan.latestNews")}
            action={<TabLink to="novidades" className={btn("secondary", "sm")}>{t("site.fan.allNews")}</TabLink>}>
            <div className="max-w-2xl">
              <NewsFeed posts={club.news.slice(0, 1)} clubName={club.name} logoUrl={club.logo_url} initials={initials(club.name)} />
            </div>
          </Panel>
        )}
      </Container>
    ),

    horarios: (
      <Container className="space-y-14 py-10 sm:py-14">
        <Panel eyebrow={t("site.fan.groupsEyebrow")} title={t("site.fan.groupsTitle")}
          text={club.show_prices ? t("site.fan.groupsText") : t("site.fan.groupsTextNoPrices")}>
          {club.groups.length > 0 ? (
            <ul className="grid gap-5 lg:grid-cols-3">
              {club.groups.map((g, i) => <li key={g.name}><GroupCard group={g} index={i} slug={club.slug} t={t} fmt={fmt} /></li>)}
            </ul>
          ) : (
            <EmptyNote>{t("site.fan.groupsEmpty")}</EmptyNote>
          )}
        </Panel>
        <Panel eyebrow={t("site.club.scheduleEyebrow", { season: club.season_label })} title={t("site.fan.weekTitle")} text={t("site.club.scheduleText")}>
          {club.schedule.length > 0 ? <WeekTimetable schedule={club.schedule} t={t} /> : <EmptyNote>{t("site.club.scheduleEmpty")}</EmptyNote>}
        </Panel>
        <JoinBanner club={club} t={t} />
      </Container>
    ),

    equipa: (
      <Container className="py-10 sm:py-14">
        <Panel eyebrow={t("site.club.coachesEyebrow")} title={t("site.club.coaches")}>
          <ul className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {club.coaches.map((c) => <li key={c.name}><CoachCard coach={c} /></li>)}
          </ul>
        </Panel>
      </Container>
    ),

    galeria: (
      <Container className="space-y-14 py-10 sm:py-14">
        {club.gallery.length > 0 && (
          <Panel eyebrow={t("site.club.galleryEyebrow")} title={t("site.fan.photosTitle")}>
            <Gallery items={club.gallery} clubName={club.name} />
          </Panel>
        )}
        {(videos.length > 0 || club.youtube_url) && (
          <Panel eyebrow={t("site.fan.videosEyebrow")} title={t("site.fan.videosSectionTitle")}>
            <ClubVideos videos={videos} />
            {club.youtube_url && (
              <a href={club.youtube_url} target="_blank" rel="noopener noreferrer"
                className="mt-6 flex items-center gap-4 rounded-2xl bg-ink-950 p-5 text-white shadow-soft transition hover:-translate-y-0.5">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-club text-xl text-club-on" aria-hidden="true">▶</span>
                <span>
                  <span className="block font-semibold">{t("site.fan.videosTitle")}</span>
                  <span className="block text-sm text-white/70">{t("site.fan.videosText", { club: club.name })}</span>
                </span>
              </a>
            )}
          </Panel>
        )}
      </Container>
    ),

    novidades: (
      <Container className="grid gap-14 py-10 sm:py-14 lg:grid-cols-[1.3fr_1fr]">
        {club.news.length > 0 && (
          <Panel eyebrow={t("site.fan.newsEyebrow")} title={t("site.fan.newsTitle")}>
            <NewsFeed posts={club.news} clubName={club.name} logoUrl={club.logo_url} initials={initials(club.name)} />
          </Panel>
        )}
        {club.history.length > 0 && (
          <Panel eyebrow={t("site.fan.historyEyebrow")} title={t("site.fan.historyTitle", { club: club.name })}>
            <ol className="relative ml-3 border-l-2 border-club/25">
              {club.history.map((h) => (
                <li key={`${h.year}-${h.title}`} className="relative pb-8 pl-8 last:pb-0">
                  <span className="absolute -left-[9px] top-1.5 h-4 w-4 rounded-full bg-club ring-4 ring-white" aria-hidden="true" />
                  <p className="font-display text-2xl text-club-ink">{h.year}</p>
                  <h3 className="mt-0.5 text-lg text-ink-900">{h.title}</h3>
                  {h.text && <p className="mt-1 max-w-2xl text-ink-600">{h.text}</p>}
                </li>
              ))}
            </ol>
          </Panel>
        )}
      </Container>
    ),

    competicao: (
      <Container className="space-y-14 py-10 sm:py-14">
        <Panel eyebrow={t("site.events.eyebrow")} title={t("site.fan.eventsTitle")}
          action={<Link href={`/eventos?club=${club.slug}`} className={btn("secondary", "sm")}>{t("site.events.all")}</Link>}>
          {club.upcoming_events.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2">
              {club.upcoming_events.map((e) => <EventCard key={e.id} event={e} t={t} fmt={fmt} />)}
            </div>
          ) : (
            <EmptyNote>{t("site.events.empty")}</EmptyNote>
          )}
        </Panel>
        <Panel eyebrow={t("site.fan.rankingEyebrow", { season: club.season_label })} title={t("site.fan.rankingTitle")} text={t("site.club.judokaText")}
          action={<Link href={`/ranking?club=${club.slug}`} className={btn("secondary", "sm")}>{t("site.ranking.full")}</Link>}>
          {club.ranking.length > 0 ? (
            <AthleteRanking rows={club.ranking} showClub={false} />
          ) : club.judoka.length > 0 ? (
            <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              {club.judoka.map((j) => <li key={j.id}><JudokaCard judoka={j} t={t} showClub={false} /></li>)}
            </ul>
          ) : (
            <EmptyNote>{t("site.club.judokaEmpty")}</EmptyNote>
          )}
          {club.recent_medals.length > 0 && (
            <div className="mt-8">
              <h3 className="mb-3 text-lg text-ink-900">{t("site.medals.title")}</h3>
              <div className="glass-card rounded-2xl px-4"><MedalList medals={club.recent_medals} t={t} fmt={fmt} showClub={false} /></div>
            </div>
          )}
        </Panel>
      </Container>
    ),

    contactos: (
      <>
        <Container className="grid gap-8 py-10 sm:py-14 lg:grid-cols-[22rem_1fr]">
          <InfoCard club={club} socials={socials} t={t} />
          {mapQuery && (club.address || club.venue) ? (
            <div>
              <SectionHeading eyebrow={t("site.fan.whereEyebrow")} title={t("site.fan.whereTitle")} />
              <ClubMap query={mapQuery} mapUrl={club.map_url} />
            </div>
          ) : <span />}
        </Container>
        <section id="mensagem" aria-labelledby="mensagem-title" className="relative isolate overflow-hidden bg-gradient-to-br from-club-cover-from to-club-cover-to py-16 text-white sm:py-20">
          <div className="pointer-events-none absolute -right-24 -top-24 -z-10 h-96 w-96 rounded-full bg-club-2/25 blur-[100px] animate-aurora" aria-hidden="true" />
          <Container className="grid items-start gap-10 lg:grid-cols-[1fr_1.3fr]">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.25em] text-club-glow">{t("site.fan.messageEyebrow")}</p>
              <h2 id="mensagem-title" className="mt-2 text-3xl sm:text-4xl">{t("site.fan.messageTitle")}</h2>
              <p className="mt-4 max-w-md text-white/85">{t("site.fan.messageText", { club: club.name })}</p>
              <div className="mt-8 rounded-3xl bg-white/10 p-6 ring-1 ring-white/20 backdrop-blur">
                <h3 className="text-xl">{t("site.club.joinTitle", { club: club.name })}</h3>
                <p className="mt-2 text-sm text-white/85">{t("site.club.joinText")}</p>
                <Link href={`/c/${club.slug}`} className="mt-5 inline-flex h-12 items-center justify-center rounded-2xl bg-club-accent px-6 font-semibold text-club-on-accent shadow-soft transition hover:-translate-y-px">
                  {t("site.fan.join")}
                </Link>
              </div>
            </div>
            <div className="text-ink-900">
              <ContactForm target={{ kind: "club", slug: club.slug, name: club.name }} />
            </div>
          </Container>
        </section>
      </>
    ),
  };

  return (
    <SiteShell>
      {/* Il tema del club vale per tutto ciò che sta qui dentro (token club-*). */}
      <div style={themeStyle(club.theme) as CSSProperties}>
        <Cover club={club} t={t} />

        {/* --- La barra del club, nel suo colore: logo che sporge dalla
            copertina, nome, numeri, azioni. Il colore e il contrasto del
            testo arrivano dal tema (club/brand.py): si legge sempre. --- */}
        <section className="relative isolate overflow-hidden bg-gradient-to-r from-club via-club to-club-cover-from text-club-on shadow-lift">
          {/* Le strisce diagonali e il riflesso che passa: decorazione. */}
          <div className="pointer-events-none absolute inset-0 -z-10 opacity-[0.12] [background-image:repeating-linear-gradient(135deg,currentColor_0_2px,transparent_2px_22px)]" aria-hidden="true" />
          <div className="pointer-events-none absolute inset-y-0 -left-1/3 -z-10 w-1/3 skew-x-[-20deg] bg-gradient-to-r from-transparent via-white/25 to-transparent animate-club-shine motion-reduce:hidden" aria-hidden="true" />
          <div className="pointer-events-none absolute -right-16 -top-24 -z-10 h-72 w-72 rounded-full bg-club-accent/40 blur-[80px] animate-aurora" aria-hidden="true" />
          <Container className="relative pb-6 pt-4 md:pb-7">
            <div className="flex flex-col items-center gap-4 text-center md:flex-row md:items-end md:gap-6 md:text-left">
              <Reveal className="-mt-20 shrink-0 sm:-mt-24">
                <div className="flex h-36 w-36 items-center justify-center overflow-hidden rounded-full bg-white shadow-lift ring-[6px] ring-club-accent sm:h-44 sm:w-44">
                  {club.logo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element -- logo caricato dal club
                    <img src={club.logo_url} alt={t("site.club.logoAlt", { club: club.name })} className="h-full w-full object-contain p-3" />
                  ) : (
                    <span className="flex h-full w-full items-center justify-center bg-club font-display text-5xl text-club-on" aria-hidden="true">
                      {initials(club.name)}
                    </span>
                  )}
                </div>
              </Reveal>
              <Reveal delay={0.05} className="min-w-0 flex-1">
                <p className="text-xs font-bold uppercase tracking-[0.25em] opacity-85">
                  {[club.city, club.founded_year ? t("site.fan.since", { year: club.founded_year }) : null].filter(Boolean).join(" · ")}
                </p>
                <h1 className="mt-1 flex flex-wrap items-center justify-center gap-x-3 font-display text-4xl leading-tight drop-shadow-sm sm:text-6xl md:justify-start">
                  {club.name}
                  <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-club-accent text-club-on-accent shadow sm:h-9 sm:w-9" title={t("site.fan.networkBadge")}>
                    <svg viewBox="0 0 24 24" className="h-4 w-4 sm:h-5 sm:w-5" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
                    <span className="sr-only">{t("site.fan.networkBadge")}</span>
                  </span>
                </h1>
                {club.venue && <p className="mt-1 text-sm opacity-85">📍 {club.venue}</p>}
              </Reveal>
              <Reveal delay={0.1} className="flex flex-col items-center gap-3 md:items-end">
                <div className="flex flex-wrap justify-center gap-2">
                  <Link href={`/c/${club.slug}`} className="inline-flex h-12 items-center justify-center rounded-2xl bg-club-accent px-6 font-semibold text-club-on-accent shadow-soft transition hover:-translate-y-px hover:brightness-105">
                    {t("site.fan.join")}
                  </Link>
                  <TabLink to="contactos" className="inline-flex h-12 items-center justify-center gap-2 rounded-2xl bg-white/15 px-5 font-semibold ring-1 ring-current/30 backdrop-blur transition hover:bg-white/25">
                    <span aria-hidden="true">✉</span> {t("site.fan.sendMessage")}
                  </TabLink>
                </div>
                <SocialIcons links={socials} />
              </Reveal>
            </div>
            {facts.length > 0 && (
              <Reveal delay={0.15}>
                <ul className="mt-5 flex flex-wrap justify-center gap-2 md:justify-start" aria-label={t("site.fan.factsLabel")}>
                  {facts.map((f) => (
                    <li key={f.label} className="inline-flex items-baseline gap-2 rounded-full bg-white/15 px-4 py-1.5 ring-1 ring-white/20 backdrop-blur">
                      <strong className="font-display text-xl"><CountUp value={f.value} /></strong>
                      <span className="text-xs font-semibold uppercase tracking-wide opacity-85">{f.label}</span>
                    </li>
                  ))}
                </ul>
              </Reveal>
            )}
          </Container>
          {/* Il filo nel colore d'accento, come la cintura sotto il nome. */}
          <div className="h-1.5 bg-gradient-to-r from-club-accent via-club-2 to-club-accent" aria-hidden="true" />
        </section>

        {(club.tagline || club.schedule.length > 0) && (
          <Container className="pb-2 pt-6">
            <Reveal className="flex flex-col items-center gap-4 md:flex-row md:justify-between">
              {club.tagline ? (
                <p className="max-w-3xl border-l-4 border-club pl-4 text-center font-display text-xl text-ink-800 md:text-left">“{club.tagline}”</p>
              ) : <span />}
              <NextTraining schedule={club.schedule} />
            </Reveal>
          </Container>
        )}

        <ClubTabs tabs={visibleTabs} panels={panels} label={t("site.fan.tabsLabel")} />
        <MobileClubBar joinHref={`/c/${club.slug}`} joinLabel={t("site.fan.join")} messageLabel={t("site.fan.messageShort")} />
      </div>
    </SiteShell>
  );
}

/** Le icone delle schede: un tratto solo, nel colore del testo. */
function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

function Panel({ eyebrow, title, text, action, children }: { eyebrow: string; title: string; text?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section>
      <SectionHeading eyebrow={eyebrow} title={title} text={text} action={action} />
      {children}
    </section>
  );
}

/** I tre stili dei gruppi, gli stessi nelle card e nell'orario: così "il
 *  verde è il mio gruppo" si capisce senza leggere. */
const GROUP_STYLES = [
  { solid: "bg-club text-club-on", soft: "bg-club/10 text-club-ink ring-club/30" },
  { solid: "bg-club-accent text-club-on-accent", soft: "bg-club-accent/25 text-ink-900 ring-club-accent/60" },
  { solid: "bg-ink-900 text-white", soft: "bg-ink-900/10 text-ink-900 ring-ink-900/25" },
];

/** L'orario della settimana come un calendario: una colonna per giorno,
 *  un blocco per allenamento, colorato come il suo gruppo. */
function WeekTimetable({ schedule, t }: { schedule: ScheduleDay[]; t: Translator }) {
  const courses = [...new Set(schedule.flatMap((d) => d.slots.map((s) => s.course)))];
  const days = [...schedule].sort((a, b) => a.weekday - b.weekday);
  return (
    <div>
      <ul className="mb-4 flex flex-wrap gap-2" aria-label={t("site.fan.legend")}>
        {courses.map((c, i) => (
          <li key={c} className={cn("inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ring-1", GROUP_STYLES[i % 3]?.soft)}>
            <span className={cn("h-2.5 w-2.5 rounded-full", GROUP_STYLES[i % 3]?.solid)} aria-hidden="true" />{c}
          </li>
        ))}
      </ul>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[repeat(auto-fit,minmax(9rem,1fr))]">
        {days.map((d) => (
          <div key={d.weekday} className="overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/5">
            <p className="bg-ink-950 px-4 py-2.5 text-sm font-bold uppercase tracking-[0.18em] text-white">{t.dyn(`site.weekday.${d.weekday}`, String(d.weekday))}</p>
            <ul className="space-y-2 p-3">
              {[...d.slots].sort((a, b) => a.starts_at.localeCompare(b.starts_at)).map((s, i) => (
                <li key={i} className={cn("rounded-2xl p-3", GROUP_STYLES[courses.indexOf(s.course) % 3]?.solid)}>
                  <p className="font-display text-lg leading-none">{s.starts_at}<span className="opacity-70">–{s.ends_at}</span></p>
                  <p className="mt-1.5 text-xs font-semibold leading-snug opacity-90">{s.course}</p>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

/** In fondo alla scheda dei prezzi: il passo successivo, grande. */
function JoinBanner({ club, t }: { club: ClubPage; t: Translator }) {
  return (
    <div className="relative isolate overflow-hidden rounded-[2rem] bg-gradient-to-br from-club-cover-from to-club-cover-to p-8 text-white shadow-lift sm:p-10">
      <div className="pointer-events-none absolute -right-16 -top-16 -z-10 h-64 w-64 rounded-full bg-club-2/30 blur-3xl" aria-hidden="true" />
      <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-2xl sm:text-3xl">{t("site.fan.trialTitle")}</h2>
          <p className="mt-2 max-w-xl text-white/85">{t("site.fan.trialText", { club: club.name })}</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link href={`/c/${club.slug}`} className="inline-flex h-12 items-center justify-center rounded-2xl bg-club-accent px-6 font-semibold text-club-on-accent shadow-soft transition hover:-translate-y-px">{t("site.fan.join")}</Link>
          <TabLink to="contactos" className="inline-flex h-12 items-center justify-center rounded-2xl px-6 font-semibold text-white ring-1 ring-white/50 transition hover:bg-white/10">{t("site.fan.askQuestion")}</TabLink>
        </div>
      </div>
    </div>
  );
}

/** Le iniziali del club al posto del logo che ancora non c'è ("JCL"). */
function initials(name: string): string {
  return name.split(/\s+/).filter((w) => w.length > 2).map((w) => w[0]).join("").slice(0, 3).toUpperCase() || name.slice(0, 2).toUpperCase();
}

/** I bottoni della pagina, nei colori del club. */
function btn(kind: "primary" | "secondary", size: "md" | "sm" = "md"): string {
  return cn(
    "inline-flex items-center justify-center gap-2 font-semibold transition hover:-translate-y-px focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-club/30",
    size === "md" ? "h-12 rounded-2xl px-6" : "h-9 rounded-xl px-3.5 text-sm",
    kind === "primary" ? "bg-club text-club-on shadow-soft hover:brightness-110" : "bg-white text-ink-900 ring-1 ring-ink-200 shadow-soft hover:text-club-ink hover:ring-club",
  );
}

/** La copertina: la foto del club velata nei suoi colori (o, senza foto, il
 *  tatami sul gradiente), con le luci sfumate del colore secondario. Sopra
 *  c'è solo testo bianco, e il tema garantisce che si legga. */
function Cover({ club, t }: { club: ClubPage; t: Translator }) {
  return (
    <section className="relative isolate h-72 overflow-hidden bg-club-cover-to sm:h-96 lg:h-[30rem]" aria-label={t("site.fan.coverLabel", { club: club.name })}>
      {club.hero_image_url ? (
        // eslint-disable-next-line @next/next/no-img-element -- copertina caricata dal club
        <img src={club.hero_image_url} alt="" className="absolute inset-0 -z-20 h-full w-full object-cover animate-ken-burns" />
      ) : (
        <TatamiBackdrop className="-z-20" />
      )}
      <div className="absolute inset-0 -z-10 bg-gradient-to-br from-club-cover-from/75 via-club-cover-from/25 to-club-cover-to/90" aria-hidden="true" />
      <div className="pointer-events-none absolute -left-20 -top-24 -z-10 h-80 w-80 rounded-full bg-club-2/30 blur-[90px] animate-aurora" aria-hidden="true" />
      <Container className="pt-6">
        <nav aria-label={t("site.breadcrumb")} className="text-sm text-white/80">
          <Link href="/clubes" className="hover:text-white">{t("site.nav.clubs")}</Link> <span aria-hidden="true">/</span> {club.name}
        </nav>
      </Container>
    </section>
  );
}

/** Contatti, mappa e social del club, sempre a portata di mano. */
function InfoCard({ club, socials, t }: { club: ClubPage; socials: SocialLink[]; t: Translator }) {
  const has = club.address || club.contact_phone || club.contact_email || club.map_url;
  return (
    <div className="glass-card space-y-4 rounded-3xl p-6">
      <h2 className="text-xs font-bold uppercase tracking-[0.22em] text-club-ink">{t("site.fan.infoTitle")}</h2>
      {club.city && <Info icon="📍" label={t("site.fan.infoCity")}>{club.city}</Info>}
      {club.address && <Info icon="🏠" label={t("site.club.address")}>{club.address}</Info>}
      {club.contact_phone && (
        <Info icon="📞" label={t("site.club.phone")}>
          <a className="hover:text-club-ink" href={`tel:${club.contact_phone.replace(/\s+/g, "")}`}>{club.contact_phone}</a>
        </Info>
      )}
      {club.contact_email && (
        <Info icon="✉️" label="Email">
          <a className="break-all hover:text-club-ink" href={`mailto:${club.contact_email}`}>{club.contact_email}</a>
        </Info>
      )}
      {!has && <p className="text-sm text-ink-500">{t("site.fan.infoEmpty")}</p>}
      {club.map_url && (
        <a href={club.map_url} target="_blank" rel="noopener noreferrer" className={btn("secondary", "sm")}>{t("site.club.openMap")}</a>
      )}
      {socials.length > 0 && <SocialIcons links={socials} tone="plain" className="border-t border-ink-900/5 pt-4" />}
      <a href="#mensagem" className={cn(btn("primary", "sm"), "w-full")}>{t("site.fan.sendMessage")}</a>
    </div>
  );
}

function Info({ icon, label, children }: { icon: string; label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="mt-0.5 text-lg leading-none" aria-hidden="true">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-400">{label}</p>
        <p className="text-sm text-ink-800">{children}</p>
      </div>
    </div>
  );
}

/** Un gruppo come un listino: il numero del gruppo, l'età grande, la
 *  mensilità grandissima, gli allenamenti e il bottone per iscriversi.
 *  Senza prezzi, l'invito a chiederli al club. */
function GroupCard({ group, index, slug, t, fmt }: { group: ClubGroup; index: number; slug: string; t: Translator; fmt: Formatters }) {
  const ages = ageRange(t, group.min_age, group.max_age);
  const number = group.name.match(/\d+/)?.[0] ?? String(index + 1);
  const title = group.name.replace(/^Grupos?\s*[\d\s e]+·\s*/i, "");
  const style = GROUP_STYLES[index % 3];
  const featured = index === 1;
  return (
    <article className={cn("relative flex h-full flex-col overflow-hidden rounded-[2rem] bg-white shadow-soft ring-1 ring-ink-900/5 transition hover:-translate-y-1 hover:shadow-lift motion-reduce:transition-none", featured && "ring-2 ring-club lg:-translate-y-2")}>
      <div className={cn("relative px-6 pb-6 pt-5", style?.solid)}>
        <p className="text-xs font-bold uppercase tracking-[0.22em] opacity-80">{t("site.fan.groupN", { n: number })}</p>
        <h3 className="mt-1 text-xl leading-snug">{title}</h3>
        {ages && <p className="mt-3 inline-flex rounded-full bg-white/90 px-3 py-1 text-sm font-bold text-ink-900">{ages}</p>}
        <span className="pointer-events-none absolute -bottom-5 right-4 font-display text-[7rem] leading-none opacity-15" aria-hidden="true">{number}</span>
      </div>
      <div className="flex flex-1 flex-col p-6">
        {group.monthly_price_cents !== null ? (
          <p className="flex items-end gap-1">
            <span className="font-display text-5xl leading-none text-ink-900">{fmt.euro(group.monthly_price_cents, { maximumFractionDigits: 0 })}</span>
            <span className="pb-1 text-sm text-ink-500">{t("site.fan.perMonth")}</span>
          </p>
        ) : (
          <TabLink to="contactos" className="text-sm font-semibold text-club-ink hover:underline">{t("site.fan.askPrices")}</TabLink>
        )}
        {group.slots.length > 0 ? (
          <ul className="mt-5 space-y-2" aria-label={t("site.fan.trainings")}>
            {group.slots.map((s, i) => (
              <li key={i} className="flex items-center justify-between gap-3 rounded-xl bg-ink-50 px-3 py-2 text-sm">
                <strong className="font-semibold text-ink-900">{t.dyn(`site.weekday.${s.weekday}`, String(s.weekday))}</strong>
                <span className="font-mono text-ink-700">{s.starts_at}–{s.ends_at}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-5 rounded-xl bg-ink-50 px-3 py-2 text-sm text-ink-500">{t("site.fan.noTrainings")}</p>
        )}
        {(group.enrollment_price_cents || group.due_day || group.description) ? (
          <ul className="mt-4 space-y-1 text-xs text-ink-500">
            {group.enrollment_price_cents ? <li>• {t("site.fan.enrollment", { amount: fmt.euro(group.enrollment_price_cents) })}</li> : null}
            {group.due_day ? <li>• {t("site.fan.dueDay", { day: group.due_day })}</li> : null}
            {group.description ? <li>• {group.description}</li> : null}
          </ul>
        ) : null}
        <div className="mt-auto pt-6">
          <Link href={`/c/${slug}`} className={cn("flex h-12 items-center justify-center rounded-2xl font-semibold transition hover:-translate-y-px", featured ? "bg-club text-club-on shadow-soft" : "bg-ink-950 text-white")}>
            {t("site.fan.joinGroup")}
          </Link>
        </div>
      </div>
    </article>
  );
}

/** Un numero grande nel colore del club ("40+ · anos de judo"). */
function Highlight({ value, label }: { value: string; label: string }) {
  return (
    <li className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-club-cover-from to-club-cover-to p-5 text-white shadow-soft">
      <span className="pointer-events-none absolute -right-6 -top-6 h-20 w-20 rounded-full bg-club-2/30 blur-2xl" aria-hidden="true" />
      <p className="relative font-display text-4xl leading-none text-club-glow sm:text-5xl">{value}</p>
      <p className="relative mt-2 text-sm font-semibold text-white/90">{label}</p>
    </li>
  );
}

/** Un allenatore: foto (o iniziali), nome, ruolo, grado su una striscia
 *  nera come la cintura, e due righe. Tutto scritto dal club. */
function CoachCard({ coach }: { coach: Coach }) {
  return (
    <article className="glass-card flex h-full gap-4 rounded-3xl p-5">
      <Avatar name={coach.name} photoUrl={coach.photo_url} size="lg" className="ring-4 ring-club/20" />
      <div className="min-w-0">
        <h3 className="text-lg leading-snug text-ink-900">{coach.name}</h3>
        {coach.role && <p className="text-sm font-semibold text-club-ink">{coach.role}</p>}
        {coach.grade && (
          <p className="mt-2 inline-flex items-center gap-2 rounded-md bg-ink-950 px-2.5 py-1 text-xs font-semibold text-white">
            <span className="h-2 w-5 rounded-sm bg-club-accent" aria-hidden="true" />{coach.grade}
          </p>
        )}
        {coach.bio && <p className="mt-2 text-sm leading-relaxed text-ink-600">{coach.bio}</p>}
      </div>
    </article>
  );
}
