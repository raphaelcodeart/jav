import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { CSSProperties, ReactNode } from "react";
import { Avatar, Container, EmptyNote, EventCard, JudokaCard, MedalList, RankingTable, ScheduleGrid, SectionHeading } from "@/components/site/blocks";
import { TatamiBackdrop } from "@/components/site/club-carousel";
import { ClubSectionNav } from "@/components/site/club-section-nav";
import { ContactForm } from "@/components/site/contact-form";
import { Gallery } from "@/components/site/gallery";
import { ageRange, siteI18n } from "@/components/site/i18n";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { SocialIcons, type SocialLink } from "@/components/site/social-icons";
import { themeStyle } from "@/lib/brand";
import { cn } from "@/lib/cn";
import type { Formatters, Translator } from "@/lib/i18n/translate";
import { publicSite, type ClubGroup, type ClubPage } from "@/lib/public-site";

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
  const [{ t, fmt }, club] = await Promise.all([siteI18n(), publicSite.club(slug)]);
  if (!club) notFound();

  const medals = club.judoka.reduce((n, j) => n + j.gold + j.silver + j.bronze, 0);
  const weeklyClasses = club.schedule.reduce((n, d) => n + d.slots.length, 0);
  const socials: SocialLink[] = ([
    { kind: "facebook", url: club.facebook_url, label: "Facebook" },
    { kind: "instagram", url: club.instagram_url, label: "Instagram" },
    { kind: "youtube", url: club.youtube_url, label: "YouTube" },
    { kind: "website", url: club.website_url, label: t("site.club.website") },
  ] as const).filter((s) => Boolean(s.url)).map((s) => ({ ...s, url: s.url as string }));
  // I numeri del club, contati e mai scritti a mano; quelli a zero non si dicono.
  const facts = [
    { value: club.athletes_active, label: t("site.fan.factAthletes") },
    { value: club.groups.length, label: t("site.fan.factGroups") },
    { value: weeklyClasses, label: t("site.fan.factClasses") },
    { value: club.coaches.length, label: t("site.fan.factCoaches") },
    { value: medals, label: t("site.fan.factMedals") },
  ].filter((f) => f.value > 0);
  const tabs = [
    { id: "sobre", label: t("site.fan.tabAbout"), show: true },
    { id: "grupos", label: t("site.fan.tabGroups"), show: true },
    { id: "horario", label: t("site.fan.tabSchedule"), show: true },
    { id: "treinadores", label: t("site.fan.tabCoaches"), show: club.coaches.length > 0 },
    { id: "fotos", label: t("site.fan.tabPhotos"), show: club.gallery.length > 0 || Boolean(club.youtube_url) },
    { id: "provas", label: t("site.fan.tabEvents"), show: true },
    { id: "ranking", label: t("site.fan.tabRanking"), show: true },
    { id: "mensagem", label: t("site.fan.tabMessage"), show: true },
  ].filter((s) => s.show).map(({ id, label }) => ({ id, label }));

  return (
    <SiteShell>
      {/* Il tema del club vale per tutto ciò che sta qui dentro (token club-*). */}
      <div style={themeStyle(club.theme) as CSSProperties}>
        <Cover club={club} t={t} />

        {/* --- Il profilo: logo che sporge dalla copertina, nome, numeri, azioni --- */}
        <Container className="relative z-10">
          <div className="-mt-20 flex flex-col items-center gap-5 text-center sm:-mt-24 md:flex-row md:items-end md:text-left">
            <Reveal className="shrink-0">
              <div className="flex h-36 w-36 items-center justify-center overflow-hidden rounded-full bg-white shadow-lift ring-[6px] ring-white sm:h-44 sm:w-44">
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
            <Reveal delay={0.05} className="min-w-0 flex-1 md:pb-3">
              {club.city && <p className="text-xs font-bold uppercase tracking-[0.25em] text-club-ink">{club.city}</p>}
              <h1 className="mt-1 text-3xl text-ink-900 sm:text-5xl">{club.name}</h1>
              {facts.length > 0 && (
                <ul className="mt-3 flex flex-wrap justify-center gap-x-4 gap-y-1 text-sm text-ink-600 md:justify-start" aria-label={t("site.fan.factsLabel")}>
                  {facts.map((f) => (
                    <li key={f.label}><strong className="font-display text-ink-900">{f.value}</strong> {f.label}</li>
                  ))}
                </ul>
              )}
            </Reveal>
            <Reveal delay={0.1} className="flex flex-col items-center gap-3 md:items-end md:pb-3">
              <div className="flex flex-wrap justify-center gap-2">
                <Link href={`/c/${club.slug}`} className={btn("primary")}>{t("site.fan.join")}</Link>
                <a href="#mensagem" className={btn("secondary")}>
                  <span aria-hidden="true">✉</span> {t("site.fan.sendMessage")}
                </a>
              </div>
              <SocialIcons links={socials} />
            </Reveal>
          </div>
          {club.tagline && (
            <Reveal delay={0.15}>
              <p className="mx-auto mt-6 max-w-3xl text-center text-lg text-ink-600 md:mx-0 md:text-left">“{club.tagline}”</p>
            </Reveal>
          )}
        </Container>

        <div className="mt-8">
          <ClubSectionNav items={tabs} label={t("site.fan.tabsLabel")} />
        </div>

        <Container className="grid gap-10 py-10 lg:grid-cols-[1fr_20rem]">
          {/* --- Il riquadro "Informações", come l'introduzione di una pagina Facebook --- */}
          <aside className="order-first lg:order-last lg:sticky lg:top-44 lg:self-start">
            <Reveal>
              <InfoCard club={club} socials={socials} t={t} />
            </Reveal>
          </aside>

          <div className="min-w-0 space-y-16">
            <Section id="sobre" eyebrow={t("site.club.aboutEyebrow")} title={t("site.club.about", { club: club.name })}>
              {club.about ? (
                <div className="max-w-3xl whitespace-pre-line text-lg leading-relaxed text-ink-700">{club.about}</div>
              ) : (
                <EmptyNote>{t("site.fan.aboutEmpty")}</EmptyNote>
              )}
            </Section>

            <Section id="grupos" eyebrow={t("site.fan.groupsEyebrow")} title={t("site.fan.groupsTitle")}
              text={club.show_prices ? t("site.fan.groupsText") : t("site.fan.groupsTextNoPrices")}>
              {club.groups.length > 0 ? (
                <ul className="grid gap-4 md:grid-cols-2">
                  {club.groups.map((g) => <li key={g.name}><GroupCard group={g} t={t} fmt={fmt} /></li>)}
                </ul>
              ) : (
                <EmptyNote>{t("site.fan.groupsEmpty")}</EmptyNote>
              )}
            </Section>

            <Section id="horario" eyebrow={t("site.club.scheduleEyebrow", { season: club.season_label })} title={t("site.club.schedule")} text={t("site.club.scheduleText")}>
              {club.schedule.length > 0 ? <ScheduleGrid schedule={club.schedule} t={t} /> : <EmptyNote>{t("site.club.scheduleEmpty")}</EmptyNote>}
            </Section>

            {club.coaches.length > 0 && (
              <Section id="treinadores" eyebrow={t("site.club.coachesEyebrow")} title={t("site.club.coaches")}>
                <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  {club.coaches.map((c) => (
                    <li key={c.name} className="glass-card flex items-center gap-4 rounded-2xl p-4">
                      <Avatar name={c.name} photoUrl={c.photo_url} size="lg" />
                      <div className="min-w-0">
                        <p className="font-semibold text-ink-900">{c.name}</p>
                        {c.role && <p className="text-sm text-club-ink">{c.role}</p>}
                      </div>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {(club.gallery.length > 0 || club.youtube_url) && (
              <Section id="fotos" eyebrow={t("site.club.galleryEyebrow")} title={t("site.fan.photosTitle")}>
                {club.gallery.length > 0 && <Gallery items={club.gallery} clubName={club.name} />}
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
              </Section>
            )}

            <Section id="provas" eyebrow={t("site.events.eyebrow")} title={t("site.fan.eventsTitle")}
              action={<Link href={`/eventos?club=${club.slug}`} className={btn("secondary", "sm")}>{t("site.events.all")}</Link>}>
              {club.upcoming_events.length > 0 ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {club.upcoming_events.map((e) => <EventCard key={e.id} event={e} t={t} fmt={fmt} />)}
                </div>
              ) : (
                <EmptyNote>{t("site.events.empty")}</EmptyNote>
              )}
            </Section>

            <Section id="ranking" eyebrow={t("site.fan.rankingEyebrow", { season: club.season_label })} title={t("site.fan.rankingTitle")} text={t("site.club.judokaText")}
              action={<Link href={`/ranking?club=${club.slug}`} className={btn("secondary", "sm")}>{t("site.ranking.full")}</Link>}>
              {club.ranking.length > 0 ? (
                <RankingTable rows={club.ranking} t={t} showClub={false} />
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
            </Section>
          </div>
        </Container>

        {/* --- In fondo: scrivere al club --- */}
        <section id="mensagem" aria-labelledby="mensagem-title" className="relative isolate scroll-mt-40 overflow-hidden bg-gradient-to-br from-club-cover-from to-club-cover-to py-16 text-white sm:py-20">
          <div className="pointer-events-none absolute -right-24 -top-24 -z-10 h-96 w-96 rounded-full bg-club-2/25 blur-[100px] animate-aurora" aria-hidden="true" />
          <Container className="grid items-start gap-10 lg:grid-cols-[1fr_1.3fr]">
            <Reveal>
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
            </Reveal>
            <Reveal delay={0.1} className="text-ink-900">
              <ContactForm target={{ kind: "club", slug: club.slug, name: club.name }} />
            </Reveal>
          </Container>
        </section>
      </div>
    </SiteShell>
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
    <section className="relative isolate h-64 overflow-hidden bg-club-cover-to sm:h-80 lg:h-[24rem]" aria-label={t("site.fan.coverLabel", { club: club.name })}>
      {club.hero_image_url ? (
        // eslint-disable-next-line @next/next/no-img-element -- copertina caricata dal club
        <img src={club.hero_image_url} alt="" className="absolute inset-0 -z-20 h-full w-full object-cover" />
      ) : (
        <TatamiBackdrop className="-z-20" />
      )}
      <div className="absolute inset-0 -z-10 bg-gradient-to-br from-club-cover-from/80 via-club-cover-from/45 to-club-cover-to/90" aria-hidden="true" />
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

/** Un gruppo: età, allenamenti (i corsi la cui età lo tocca, come li dice
 *  JAVBOT) e, se il club li mostra, i prezzi. Senza prezzi, l'invito a
 *  chiederli al club con il modulo in fondo. */
function GroupCard({ group, t, fmt }: { group: ClubGroup; t: Translator; fmt: Formatters }) {
  const ages = ageRange(t, group.min_age, group.max_age);
  return (
    <article className="glass-card flex h-full flex-col rounded-3xl p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-lg leading-snug text-ink-900">{group.name}</h3>
          {ages && <p className="mt-1 inline-flex rounded-full bg-club/10 px-2.5 py-0.5 text-xs font-semibold text-club-ink">{ages}</p>}
        </div>
        {group.monthly_price_cents !== null && (
          <p className="shrink-0 text-right">
            <span className="block font-display text-2xl text-club-ink">{fmt.euro(group.monthly_price_cents)}</span>
            <span className="block text-xs text-ink-500">{t("site.fan.perMonth")}</span>
          </p>
        )}
      </div>
      {group.slots.length > 0 ? (
        <ul className="mt-4 flex flex-wrap gap-2" aria-label={t("site.fan.trainings")}>
          {group.slots.map((s, i) => (
            <li key={i} className="rounded-xl bg-ink-50 px-3 py-1.5 text-sm text-ink-700">
              <strong className="font-semibold text-ink-900">{t.dyn(`site.weekdayShort.${s.weekday}`, String(s.weekday))}</strong> {s.starts_at}–{s.ends_at}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-ink-500">{t("site.fan.noTrainings")}</p>
      )}
      {(group.enrollment_price_cents || group.due_day) ? (
        <p className="mt-4 text-sm text-ink-600">
          {[
            group.enrollment_price_cents ? t("site.fan.enrollment", { amount: fmt.euro(group.enrollment_price_cents) }) : null,
            group.due_day ? t("site.fan.dueDay", { day: group.due_day }) : null,
          ].filter(Boolean).join(" · ")}
        </p>
      ) : null}
      {group.description && <p className="mt-2 text-sm text-ink-500">{group.description}</p>}
      {group.monthly_price_cents === null && (
        <a href="#mensagem" className="mt-auto pt-4 text-sm font-semibold text-club-ink hover:underline">{t("site.fan.askPrices")}</a>
      )}
    </article>
  );
}

function Section({ id, eyebrow, title, text, action, children }: { id: string; eyebrow: string; title: string; text?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-40">
      <Reveal>
        <SectionHeading id={`${id}-title`} eyebrow={eyebrow} title={title} text={text} action={action} />
        {children}
      </Reveal>
    </section>
  );
}
