import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { BeltBadge } from "@/components/ui/belt";
import { Container, EmptyNote, EventCard, MedalCounts, MedalDot } from "@/components/site/blocks";
import { WaveDivider } from "@/components/site/decor";
import { Gallery } from "@/components/site/gallery";
import { ageBandLabel, levelLabel, placementLabel, siteI18n } from "@/components/site/i18n";
import { JudokaVideos } from "@/components/site/judoka-videos";
import { linkButton } from "@/components/site/link-button";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { cn } from "@/lib/cn";
import type { Translator } from "@/lib/i18n/translate";
import { isUuid, publicSite, type JudokaProfile } from "@/lib/public-site";

type Params = { params: Promise<{ id: string }> };

async function load(id: string) {
  return isUuid(id) ? publicSite.judoka(id) : null;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const [{ t }, judoka] = await Promise.all([siteI18n(), load(id)]);
  if (!judoka) return { title: t("site.notFound.judoka") };
  const title = `${judoka.display_name} · ${judoka.club.name}`;
  const description = t("site.judoka.metaDescription", { name: judoka.display_name, club: judoka.club.name });
  return {
    title,
    description,
    // Un minore non deve finire nei motori di ricerca con il suo nome, anche
    // con il consenso: la pagina si raggiunge dal sito, non da Google. Vale
    // per ogni scheda (docs/club-portal.md): l'età non si espone nemmeno
    // per decidere chi indicizzare.
    robots: { index: false, follow: true },
    // L'anteprima di un link condiviso usa la foto solo se c'è: l'API la
    // manda soltanto quando la famiglia l'ha permessa.
    openGraph: {
      type: "profile",
      title,
      description,
      images: judoka.photo_url ? [{ url: judoka.photo_url, alt: judoka.display_name }] : undefined,
    },
  };
}

/** La scheda pubblica di un judoca, in stile IJF: ritratto sul gradiente
 *  del club, numeri chiave, scheda tecnica, risultati, prove in programma,
 *  foto, video e percorso delle cinture. Mostra solo ciò che l'API manda,
 *  e l'API manda solo ciò che la famiglia ha permesso e il club pubblicato:
 *  senza consenso è 404, e qui "non trovato". */
export default async function JudokaPage({ params }: Params) {
  const { id } = await params;
  const [{ t, fmt }, judoka] = await Promise.all([siteI18n(), load(id)]);
  if (!judoka) notFound();

  // "Tiago M." → "Tiago" grande e "M." in giallo, come il cognome nelle schede IJF.
  const parts = judoka.display_name.split(" ");
  const initial = parts.length > 1 ? parts.pop() : "";
  const firstName = parts.join(" ");
  const medals = judoka.gold + judoka.silver + judoka.bronze;
  const sections = [
    { id: "results", label: t("site.judoka.results"), show: true },
    { id: "upcoming", label: t("site.judoka.upcoming"), show: true },
    { id: "photos", label: t("site.judoka.photos"), show: judoka.photos.length > 0 },
    { id: "videos", label: t("site.judoka.videos"), show: judoka.videos.length > 0 },
    { id: "path", label: t("site.judoka.path"), show: judoka.belt_history.length > 0 },
  ].filter((s) => s.show);

  return (
    <SiteShell>
      {/* --- Il ritratto --- */}
      <section className="relative isolate overflow-hidden bg-ink-950 text-white">
        <div className="absolute inset-0 -z-20 bg-gradient-to-br from-brand-700 via-brand-600 to-ink-950" aria-hidden="true" />
        <div className="pointer-events-none absolute -right-24 top-10 -z-10 h-[26rem] w-[26rem] rounded-full bg-accent-300/25 blur-[110px] animate-aurora" aria-hidden="true" />
        <div className="pointer-events-none absolute -left-32 bottom-0 -z-10 h-80 w-80 rounded-full bg-ink-950/60 blur-3xl" aria-hidden="true" />
        {/* Il nome enorme dietro a tutto, come una scritta sul tatami. */}
        <p className="pointer-events-none absolute inset-x-0 bottom-10 -z-10 select-none overflow-hidden whitespace-nowrap text-center font-display text-[24vw] uppercase leading-none text-white/[0.06]" aria-hidden="true">
          {firstName}
        </p>
        <Container className="relative grid items-end gap-10 pb-28 pt-12 sm:pt-16 lg:grid-cols-[1fr_auto] lg:pb-32">
          <Reveal className="order-2 text-center lg:order-1 lg:text-left">
            <p className="text-xs font-bold uppercase tracking-[0.25em] text-accent-300">
              <span aria-hidden="true">🇵🇹</span> <abbr title={t("site.judoka.countryName")} className="no-underline">POR</abbr>
              {" · "}{ageBandLabel(t, judoka.age_band)}
            </p>
            <h1 className="mt-3 font-display text-5xl uppercase leading-[0.95] sm:text-7xl">
              {firstName} {initial && <span className="text-accent-300">{initial}</span>}
            </h1>
            <p className="mt-4">
              <Link href={`/clubes/${judoka.club.slug}`} className="inline-flex items-center gap-2 font-semibold text-white/90 hover:text-accent-300">
                {judoka.club.logo_url && (
                  // eslint-disable-next-line @next/next/no-img-element -- logo caricato dal club
                  <img src={judoka.club.logo_url} alt="" className="h-7 w-7 rounded-full bg-white object-cover ring-2 ring-white/40" />
                )}
                {judoka.club.name}
              </Link>
            </p>
            {judoka.belt && (
              <div className="mt-5 inline-flex rounded-full bg-white/95 px-4 py-2 shadow-soft">
                <BeltBadge code={judoka.belt} size="md" />
              </div>
            )}
            {judoka.bio && <p className="mx-auto mt-5 max-w-xl text-lg text-white/85 lg:mx-0">“{judoka.bio}”</p>}
            <div className="mt-8 flex flex-wrap justify-center gap-3 lg:justify-start">
              {judoka.ijf_profile_url && (
                <a
                  href={judoka.ijf_profile_url} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 rounded-2xl bg-white px-5 py-3 font-semibold text-ink-900 shadow-soft transition hover:bg-accent-300"
                >
                  {t("site.judoka.ijfProfile")} <span aria-hidden="true">↗</span>
                </a>
              )}
              <Link href="/ranking" className="inline-flex items-center rounded-2xl px-5 py-3 font-semibold ring-1 ring-white/50 hover:bg-white/10">
                {t("site.ranking.full")}
              </Link>
            </div>
          </Reveal>
          <Reveal delay={0.1} className="order-1 mx-auto lg:order-2">
            <Portrait judoka={judoka} />
          </Reveal>
        </Container>
        <WaveDivider className="text-white" />
      </section>

      {/* --- I numeri --- */}
      <Container className="relative z-10 -mt-20 sm:-mt-24">
        <Reveal>
          <dl className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-5">
            <Stat
              highlight
              label={t("site.judoka.rankingTile", { band: ageBandLabel(t, judoka.age_band) })}
              value={judoka.ranking ? `#${judoka.ranking.position}` : "—"}
              sub={judoka.ranking ? t("site.judoka.rankingOf", { total: judoka.ranking.total }) : t("site.judoka.notRanked")}
            />
            <Stat label={t("site.judoka.seasonPoints", { season: judoka.season_label })} value={judoka.season_points} />
            <Stat label={t("site.judoka.totalPoints")} value={judoka.points} />
            <Stat
              label={t("site.judoka.medals")} value={medals}
              sub={medals > 0 ? <MedalCounts gold={judoka.gold} silver={judoka.silver} bronze={judoka.bronze} t={t} /> : undefined}
            />
            <Stat label={t("site.judoka.competitions")} value={judoka.competitions} />
          </dl>
        </Reveal>
      </Container>

      <Container className="grid gap-10 py-12 lg:grid-cols-[18rem_1fr] lg:py-16">
        {/* --- La scheda --- */}
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <Reveal>
            <div className="glass-card rounded-3xl p-6">
              <h2 className="text-xs font-bold uppercase tracking-[0.22em] text-brand-600">{t("site.judoka.profileTitle")}</h2>
              <dl className="mt-4 space-y-3 text-sm">
                <Fact label={t("site.judoka.club")}>
                  <Link href={`/clubes/${judoka.club.slug}`} className="font-semibold text-ink-900 hover:text-brand-700">{judoka.club.name}</Link>
                </Fact>
                <Fact label={t("site.judoka.country")}><span aria-hidden="true">🇵🇹</span> {t("site.judoka.countryName")}</Fact>
                <Fact label={t("site.judoka.ageBand")}>{ageBandLabel(t, judoka.age_band)}</Fact>
                {judoka.category && <Fact label={t("site.judoka.category")}>{judoka.category}</Fact>}
                {judoka.belt && <Fact label={t("site.judoka.belt")}><BeltBadge code={judoka.belt} size="sm" /></Fact>}
                {judoka.favorite_technique && <Fact label={t("site.judoka.technique")}>{judoka.favorite_technique}</Fact>}
                {judoka.dominant_side && <Fact label={t("site.judoka.side")}>{t.dyn(`site.judoka.side.${judoka.dominant_side}`, judoka.dominant_side)}</Fact>}
              </dl>
            </div>
            {sections.length > 1 && (
              <nav aria-label={t("site.judoka.sections")} className="mt-4 flex flex-wrap gap-2 lg:flex-col">
                {sections.map((s) => (
                  <a key={s.id} href={`#${s.id}`} className="rounded-full bg-white px-3.5 py-1.5 text-sm font-semibold text-ink-600 ring-1 ring-ink-200 hover:text-brand-700 hover:ring-brand-300 lg:rounded-xl">
                    {s.label}
                  </a>
                ))}
              </nav>
            )}
          </Reveal>
        </aside>

        <div className="min-w-0 space-y-16">
          {/* --- Resultados --- */}
          <section id="results" aria-labelledby="results-title" className="scroll-mt-24">
            <SectionTitle id="results-title">{t("site.judoka.results")}</SectionTitle>
            {judoka.results.length > 0 ? (
              <ol className="relative space-y-4 border-l-2 border-brand-100 pl-6">
                {judoka.results.map((r) => (
                  <li key={r.event_id} className="relative">
                    <span className="absolute -left-[33px] top-5 h-4 w-4 rounded-full bg-brand-500 ring-4 ring-white" aria-hidden="true" />
                    <div className="glass-card flex items-center gap-4 rounded-2xl p-4">
                      {r.placement >= 1 && r.placement <= 3 ? <MedalDot place={r.placement as 1 | 2 | 3} className="h-10 w-10 text-sm" /> : (
                        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ink-100 font-display text-sm text-ink-600" aria-hidden="true">
                          {r.placement > 0 ? r.placement : "·"}
                        </span>
                      )}
                      <div className="min-w-0 flex-1">
                        <Link href={`/eventos/${r.event_id}`} className="font-semibold text-ink-900 hover:text-brand-700">{r.event_name}</Link>
                        <p className="text-sm text-ink-500">
                          {[fmt.shortDate(r.date), r.location, levelLabel(t, r.level), r.category].filter(Boolean).join(" · ")}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-sm font-semibold text-ink-800">{placementLabel(t, r.placement)}</p>
                        <p className="font-display text-brand-600">{t("site.points", { n: r.points })}</p>
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyNote>{t("site.judoka.noResults")}</EmptyNote>
            )}
          </section>

          {/* --- Próximas provas --- */}
          <section id="upcoming" aria-labelledby="upcoming-title" className="scroll-mt-24">
            <SectionTitle id="upcoming-title">{t("site.judoka.upcoming")}</SectionTitle>
            {judoka.upcoming.length > 0 ? (
              <ul className="grid gap-4 md:grid-cols-2">
                {judoka.upcoming.map((e) => (
                  <li key={e.id}>
                    <EventCard event={e} t={t} fmt={fmt} />
                    {e.category && <p className="mt-2 pl-2 text-xs font-semibold text-ink-500">{t("site.judoka.category")}: {e.category}</p>}
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyNote>{t("site.judoka.noUpcoming")}</EmptyNote>
            )}
          </section>

          {/* --- Fotos --- */}
          {judoka.photos.length > 0 && (
            <section id="photos" aria-labelledby="photos-title" className="scroll-mt-24">
              <SectionTitle id="photos-title">{t("site.judoka.photos")}</SectionTitle>
              <Gallery items={judoka.photos.map((p) => ({ url: p.url, caption: p.caption }))} clubName={judoka.display_name} />
            </section>
          )}

          {/* --- Vídeos --- */}
          {judoka.videos.length > 0 && (
            <section id="videos" aria-labelledby="videos-title" className="scroll-mt-24">
              <SectionTitle id="videos-title">{t("site.judoka.videos")}</SectionTitle>
              <JudokaVideos videos={judoka.videos} name={judoka.display_name} />
            </section>
          )}

          {/* --- Percurso --- */}
          {judoka.belt_history.length > 0 && (
            <section id="path" aria-labelledby="path-title" className="scroll-mt-24">
              <SectionTitle id="path-title">{t("site.judoka.path")}</SectionTitle>
              <BeltPath steps={judoka.belt_history} current={judoka.belt} t={t} date={fmt.shortDate} />
            </section>
          )}

          <div className="flex flex-wrap gap-3">
            <Link href={`/clubes/${judoka.club.slug}`} className={linkButton({ variant: "secondary" })}>{t("site.judoka.backToClub", { club: judoka.club.name })}</Link>
            <Link href="/ranking" className={linkButton({ variant: "ghost" })}>{t("site.ranking.full")}</Link>
          </div>
        </div>
      </Container>
    </SiteShell>
  );
}

/** Il ritratto ritagliato: una finestra ad arco sul gradiente del club, con
 *  la foto che sfuma in basso come una figura scontornata. Senza foto (la
 *  famiglia non l'ha permessa) le iniziali, grandi: mai un'immagine rotta. */
function Portrait({ judoka }: { judoka: JudokaProfile }) {
  const initials = judoka.display_name.split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
  return (
    <div className="relative h-80 w-64 sm:h-[26rem] sm:w-80">
      <div className="absolute inset-x-4 bottom-0 top-8 rounded-b-3xl rounded-t-[10rem] bg-gradient-to-b from-accent-300/40 to-white/5 ring-1 ring-white/20" aria-hidden="true" />
      <div className="absolute inset-0 overflow-hidden rounded-b-3xl rounded-t-[10rem]">
        {judoka.photo_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- foto caricata dalla famiglia, servita da /media
          <img
            src={judoka.photo_url} alt={judoka.display_name}
            className="h-full w-full object-cover object-top [mask-image:linear-gradient(to_bottom,black_70%,transparent)]"
          />
        ) : (
          <span className="flex h-full w-full items-center justify-center font-display text-8xl text-white/90" aria-hidden="true">{initials}</span>
        )}
      </div>
      {judoka.ranking && judoka.ranking.position <= 3 && (
        <span className="absolute -right-2 top-6">
          <MedalDot place={judoka.ranking.position as 1 | 2 | 3} className="h-14 w-14 text-xl ring-4" />
        </span>
      )}
    </div>
  );
}

function Stat({ label, value, sub, highlight = false }: { label: string; value: ReactNode; sub?: ReactNode; highlight?: boolean }) {
  return (
    <div className={cn(
      "flex flex-col-reverse justify-end rounded-3xl p-5 shadow-soft",
      highlight ? "col-span-2 bg-gradient-to-br from-ink-900 to-ink-800 text-white lg:col-span-1" : "bg-white ring-1 ring-ink-900/5",
    )}>
      <dt className={cn("text-xs font-semibold uppercase tracking-wider", highlight ? "text-accent-300" : "text-ink-500")}>{label}</dt>
      <dd>
        <span className={cn("block font-display", highlight ? "text-5xl" : "text-4xl text-ink-900")}>{value}</span>
        {sub && <span className={cn("mt-1 block text-xs font-semibold", highlight ? "text-white/70" : "text-ink-600")}>{sub}</span>}
      </dd>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-ink-900/5 pb-3 last:border-0 last:pb-0">
      <dt className="text-ink-500">{label}</dt>
      <dd className="text-right font-semibold text-ink-900">{children}</dd>
    </div>
  );
}

function SectionTitle({ id, children }: { id: string; children: ReactNode }) {
  return <h2 id={id} className="mb-6 text-2xl text-ink-900 sm:text-3xl">{children}</h2>;
}

/** Le cinture una dopo l'altra, dalla prima: il percorso, con la data di
 *  ogni passaggio. L'ultima (la più alta) è quella di adesso. */
function BeltPath({ steps, current, t, date }: {
  steps: JudokaProfile["belt_history"]; current: string | null; t: Translator; date: (iso: string) => string;
}) {
  return (
    <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {steps.map((s, i) => (
        <li key={s.grade} className={cn("glass-card flex items-center gap-4 rounded-2xl p-4", s.grade === current && "ring-2 ring-brand-300")}>
          <span className="font-display text-2xl text-ink-300" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
          <div className="min-w-0">
            <BeltBadge code={s.grade} size="md" />
            <p className="mt-1 text-xs text-ink-500">
              {t("site.judoka.beltSince", { date: date(s.awarded_on) })}
              {s.grade === current && <> · <strong className="text-brand-700">{t("site.judoka.beltNow")}</strong></>}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
