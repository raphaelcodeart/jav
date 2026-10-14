import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { BeltBadge } from "@/components/ui/belt";
import { Avatar, Container, EmptyNote, KindBadge, MedalDot } from "@/components/site/blocks";
import { ageBandLabel, eventDates, levelLabel, placementLabel, siteI18n } from "@/components/site/i18n";
import { linkButton } from "@/components/site/link-button";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { isUuid, publicSite } from "@/lib/public-site";

type Params = { params: Promise<{ id: string }> };

async function load(id: string) {
  return isUuid(id) ? publicSite.event(id) : null;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const [{ t, fmt }, event] = await Promise.all([siteI18n(), load(id)]);
  if (!event) return { title: t("site.notFound.event") };
  return {
    title: `${event.name} · Judo Arte e Vida`,
    description: [eventDates(fmt, event.starts_on, event.ends_on), event.location, event.club.name].filter(Boolean).join(" · "),
  };
}

/** Un evento: le informazioni pratiche e, a gara finita, i risultati dei
 *  judoca pubblici. Gli altri iscritti contano nel totale ma non hanno nome. */
export default async function EventPage({ params }: Params) {
  const { id } = await params;
  const [{ t, fmt }, event] = await Promise.all([siteI18n(), load(id)]);
  if (!event) notFound();

  const isCompetition = event.kind === "COMPETITION";
  const hasResults = isCompetition && event.participants.some((p) => p.placement !== null);
  const facts = [
    { label: t("site.event.dates"), value: eventDates(fmt, event.starts_on, event.ends_on) },
    { label: t("site.event.location"), value: event.location },
    { label: t("site.event.organizer"), value: event.organizer },
    { label: t("site.event.level"), value: levelLabel(t, event.level) },
    { label: t("site.event.deadline"), value: event.status === "OPEN" ? fmt.shortDate(event.registration_deadline) : null },
    { label: t("site.event.participants"), value: event.participants_count > 0 ? String(event.participants_count) : null },
  ].filter((f): f is { label: string; value: string } => Boolean(f.value));

  return (
    <SiteShell>
      <section className="relative overflow-hidden bg-ink-950 text-white">
        <div className="pointer-events-none absolute -left-24 top-0 h-80 w-80 rounded-full bg-brand-500/40 blur-3xl" aria-hidden="true" />
        <div className="pointer-events-none absolute right-0 -top-20 h-72 w-72 rounded-full bg-accent-400/25 blur-3xl" aria-hidden="true" />
        <Container className="relative py-14 sm:py-20">
          <Reveal>
            <nav aria-label={t("site.breadcrumb")} className="mb-6 text-sm text-white/70">
              <Link href="/eventos" className="hover:text-white">{t("site.nav.events")}</Link> <span aria-hidden="true">/</span>{" "}
              <Link href={`/clubes/${event.club.slug}`} className="hover:text-white">{event.club.name}</Link>
            </nav>
            <KindBadge kind={event.kind} t={t} />
            <h1 className="mt-3 max-w-4xl text-3xl sm:text-5xl">{event.name}</h1>
            <p className="mt-3 text-lg text-white/80">{eventDates(fmt, event.starts_on, event.ends_on)}{event.location ? ` · ${event.location}` : ""}</p>
          </Reveal>
        </Container>
      </section>

      <Container className="grid gap-10 py-12 lg:grid-cols-[1fr_2fr]">
        <aside className="space-y-6">
          <dl className="glass-card space-y-4 rounded-3xl p-6">
            {facts.map((f) => (
              <div key={f.label}>
                <dt className="text-xs font-bold uppercase tracking-widest text-ink-400">{f.label}</dt>
                <dd className="mt-0.5 text-ink-800">{f.value}</dd>
              </div>
            ))}
          </dl>
          {event.status === "OPEN" && (
            <div className="rounded-3xl bg-brand-50 p-6 ring-1 ring-brand-100">
              <p className="text-sm text-ink-700">{t("site.event.howToJoin", { club: event.club.name })}</p>
              <Link href="/login" className={linkButton({ size: "sm", className: "mt-4" })}>{t("site.nav.login")}</Link>
            </div>
          )}
        </aside>

        <div className="space-y-10">
          {event.description && (
            <section>
              <h2 className="mb-3 text-xl text-ink-900">{t("site.event.about")}</h2>
              <p className="whitespace-pre-line leading-relaxed text-ink-700">{event.description}</p>
            </section>
          )}
          {event.categories && (
            <section>
              <h2 className="mb-3 text-xl text-ink-900">{t("site.event.categories")}</h2>
              <p className="whitespace-pre-line text-ink-700">{event.categories}</p>
            </section>
          )}
          <section>
            <h2 className="mb-4 text-xl text-ink-900">{hasResults ? t("site.event.results") : t("site.event.judoka")}</h2>
            {event.participants.length > 0 ? (
              <ul className="glass-card divide-y divide-ink-900/5 rounded-2xl px-4">
                {event.participants.map((p) => (
                  <li key={p.athlete_id} className="flex items-center gap-3 py-3">
                    {p.placement !== null && p.placement >= 1 && p.placement <= 3 ? (
                      <MedalDot place={p.placement as 1 | 2 | 3} />
                    ) : (
                      <span className="w-6" aria-hidden="true" />
                    )}
                    <Avatar name={p.display_name} photoUrl={p.photo_url} size="sm" />
                    <div className="min-w-0 flex-1">
                      <Link href={`/judocas/${p.athlete_id}`} className="font-semibold text-ink-900 hover:text-brand-700">{p.display_name}</Link>
                      <p className="text-xs text-ink-500">{[ageBandLabel(t, p.age_band), p.category].filter(Boolean).join(" · ")}</p>
                    </div>
                    {p.belt && <span className="hidden sm:inline-flex"><BeltBadge code={p.belt} size="sm" showLabel={false} /></span>}
                    {p.placement !== null && (
                      <div className="text-right">
                        <p className="text-sm font-semibold text-ink-800">{placementLabel(t, p.placement)}</p>
                        <p className="text-xs text-brand-600">{t("site.points", { n: p.points })}</p>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyNote>{t("site.event.noPublicJudoka")}</EmptyNote>
            )}
          </section>
        </div>
      </Container>
    </SiteShell>
  );
}
