import type { Metadata } from "next";
import { Countdown, moment } from "@/components/site/countdown";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { BackToCalendar } from "@/components/site/back-to-calendar";
import { Container, EmptyNote, KindBadge } from "@/components/site/blocks";
import { EventParticipants } from "@/components/site/event-participants";
import { ageBandLabel, eventDates, levelLabel, siteI18n } from "@/components/site/i18n";
import { ClubLogo } from "@/components/site/ranking-explorer";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { isUuid, publicSite } from "@/lib/public-site";

type Params = { params: Promise<{ id: string }>; searchParams?: Promise<{ from?: string }> };

async function load(id: string) {
  return isUuid(id) ? publicSite.event(id) : null;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const [{ t, fmt }, event] = await Promise.all([siteI18n(), load(id)]);
  if (!event) return { title: t("site.notFound.event") };
  return {
    title: `${event.name} · Judo Arte e Vida`,
    description: [eventDates(fmt, event.starts_on, event.ends_on), event.location, event.club?.name].filter(Boolean).join(" · "),
  };
}

/** Un evento: la scheda pratica (date, luogo con la mappa, scadenza,
 *  quota, circolare, club) e gli iscritti come nel ranking: «Nome I.», club
 *  e cintura per tutti, il popup della scheda per chi ce l'ha. */
export default async function EventPage({ params, searchParams }: Params) {
  const { id } = await params;
  // Aperta dal calendario dell'area: il bottone per tornarci.
  const fromArea = (await searchParams)?.from === "area";
  const [{ t, fmt }, event] = await Promise.all([siteI18n(), load(id)]);
  if (!event) notFound();

  const isCompetition = event.kind === "COMPETITION";
  const hasResults = isCompetition && event.participants.some((p) => p.placement !== null);
  const today = new Date().toISOString().slice(0, 10);
  const daysTo = (iso: string) => Math.round((Date.parse(iso) - Date.parse(today)) / 86_400_000);
  const startsIn = daysTo(event.starts_on);
  const deadlineIn = daysTo(event.registration_deadline);
  const mapUrl = event.location ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(event.location)}` : null;
  const facts: { icon: string; label: string; value: ReactNode; hint?: string | null }[] = [
    {
      icon: "📅", label: t("site.event.dates"),
      value: <>{eventDates(fmt, event.starts_on, event.ends_on)}{event.starts_at_time ? ` · ${event.starts_at_time.slice(0, 5)}` : ""}</>,
      hint: startsIn > 0 ? t("site.event.startsIn", { n: startsIn }) : startsIn === 0 ? t("site.event.today") : null,
    },
    ...(event.location ? [{
      icon: "📍", label: t("site.event.location"),
      value: mapUrl ? <a href={mapUrl} target="_blank" rel="noopener noreferrer" className="underline decoration-ink-200 underline-offset-4 hover:text-brand-700 hover:decoration-brand-400">{event.location}</a> : event.location,
      hint: t("site.event.openMap"),
    }] : []),
    ...(event.organizer ? [{ icon: "🏛️", label: t("site.event.organizer"), value: event.organizer }] : []),
    { icon: "🏅", label: t("site.event.level"), value: levelLabel(t, event.level) },
    ...(event.age_groups && event.age_groups.length > 0 ? [{
      icon: "👶", label: t("site.event.ages"), value: event.age_groups.map((a) => ageBandLabel(t, a)).join(", "),
    }] : []),
    ...(event.price_cents > 0 ? [{ icon: "💶", label: t("site.event.price"), value: fmt.euro(event.price_cents) }] : []),
    ...(event.status === "OPEN" ? [{
      icon: "⏳", label: t("site.event.deadline"),
      value: <>{fmt.shortDate(event.registration_deadline)}{event.registration_deadline_time ? ` · ${event.registration_deadline_time.slice(0, 5)}` : ""}</>,
      hint: deadlineIn > 0 ? t("site.event.daysLeft", { n: deadlineIn }) : deadlineIn === 0 ? t("site.event.lastDay") : null,
    }] : []),
    ...(event.participants_count > 0 ? [{
      icon: "👥", label: t("site.event.participants"),
      value: event.places ? `${event.participants_count} / ${event.places}` : String(event.participants_count),
    }] : []),
  ];

  return (
    <SiteShell>
      <section className="relative overflow-hidden bg-ink-950 text-white">
        <div className="pointer-events-none absolute -left-24 top-0 h-80 w-80 rounded-full bg-brand-500/40 blur-3xl" aria-hidden="true" />
        <div className="pointer-events-none absolute right-0 -top-20 h-72 w-72 rounded-full bg-accent-400/25 blur-3xl" aria-hidden="true" />
        <Container className="relative py-14 sm:py-20">
          <Reveal>
            {fromArea && <BackToCalendar />}
            <nav aria-label={t("site.breadcrumb")} className="mb-6 text-sm text-white/70">
              <Link href="/eventos" className="hover:text-white">{t("site.nav.events")}</Link> <span aria-hidden="true">/</span>{" "}
              {event.club
                ? <Link href={`/clubes/${event.club.slug}`} className="hover:text-white">{event.club.name}</Link>
                : <span>{t("site.event.network")}</span>}
            </nav>
            <div className="flex flex-wrap items-center gap-2">
              <KindBadge kind={event.kind} t={t} />
              {startsIn > 0 && <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-white ring-1 ring-white/20">⏱️ {t("site.event.startsIn", { n: startsIn })}</span>}
              {event.status === "OPEN" && <span className="rounded-full bg-emerald-400/20 px-3 py-1 text-xs font-semibold text-emerald-200 ring-1 ring-emerald-300/30">✅ {t("site.event.open")}</span>}
            </div>
            <h1 className="mt-3 max-w-4xl text-3xl sm:text-5xl">{event.name}</h1>
            <p className="mt-3 text-lg text-white/80">{eventDates(fmt, event.starts_on, event.ends_on)}{event.location ? ` · ${event.location}` : ""}</p>
          </Reveal>
        </Container>
      </section>

      <Container className="grid gap-10 py-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <aside className="space-y-5 lg:sticky lg:top-28 lg:self-start">
          {/* I conti alla rovescia: chiusura delle iscrizioni e inizio della gara. */}
          {event.status === "OPEN" && deadlineIn >= 0 && (
            <Countdown size="lg" target={moment(event.registration_deadline, event.registration_deadline_time, "endOfDay")} label={t("countdown.registrationsClose")} />
          )}
          {startsIn >= 0 && (
            <Countdown size="lg" tone="brand" target={moment(event.starts_on, event.starts_at_time, "morning")} label={t("countdown.eventStarts")} />
          )}
          <div className="overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/5">
            <div className="h-1.5 bg-gradient-to-r from-brand-500 via-accent-400 to-ink-800" aria-hidden="true" />
            <dl className="divide-y divide-ink-900/5">
              {facts.map((f) => (
                <div key={f.label} className="flex items-start gap-4 px-5 py-4">
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-50 to-accent-50 text-xl ring-1 ring-brand-100" aria-hidden="true">{f.icon}</span>
                  <div className="min-w-0">
                    <dt className="text-[11px] font-bold uppercase tracking-widest text-ink-400">{f.label}</dt>
                    <dd className="mt-0.5 break-words font-semibold text-ink-900">{f.value}</dd>
                    {f.hint && <dd className="mt-0.5 text-xs text-brand-600">{f.hint}</dd>}
                  </div>
                </div>
              ))}
            </dl>
            {event.circular_url && (
              <a href={event.circular_url} target="_blank" rel="noopener noreferrer"
                className="flex items-center justify-between gap-3 border-t border-ink-900/5 bg-ink-50/70 px-5 py-4 text-sm font-semibold text-ink-800 hover:bg-accent-50">
                <span>📄 {t("site.event.circular")}</span><span aria-hidden="true">↗</span>
              </a>
            )}
          </div>

          {event.club && (
            <Link href={`/clubes/${event.club.slug}`} className="group flex items-center gap-4 rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5 transition hover:-translate-y-0.5 hover:shadow-lift">
              <ClubLogo club={event.club} size="lg" />
              <span className="min-w-0 flex-1">
                <span className="block text-[11px] font-bold uppercase tracking-widest text-ink-400">{t("site.event.club")}</span>
                <span className="block truncate font-semibold text-ink-900 group-hover:text-brand-700">{event.club.name}</span>
              </span>
              <span className="text-xl text-ink-300 group-hover:text-brand-600" aria-hidden="true">›</span>
            </Link>
          )}

          {event.status === "OPEN" && (
            <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-500 to-brand-700 p-6 text-white shadow-brand">
              <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-accent-300/30 blur-2xl" aria-hidden="true" />
              <p className="relative font-semibold">🥋 {t("site.event.joinTitle")}</p>
              <p className="relative mt-1 text-sm text-white/90">
                {event.club ? t("site.event.howToJoin", { club: event.club.name }) : t("site.event.howToJoinNetwork")}
              </p>
              <Link href="/login" className="relative mt-4 inline-flex h-10 items-center rounded-xl bg-white px-4 text-sm font-semibold text-ink-900 hover:bg-accent-50">
                {t("site.nav.login")} →
              </Link>
            </div>
          )}
        </aside>

        <div className="min-w-0 space-y-10">
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
            <h2 className="mb-4 flex items-baseline gap-3 text-xl text-ink-900">
              {hasResults ? t("site.event.results") : t("site.event.judoka")}
              {event.participants.length > 0 && <span className="text-sm font-normal text-ink-400">{event.participants.length}</span>}
            </h2>
            {event.participants.length > 0
              ? <EventParticipants participants={event.participants} withResults={hasResults} />
              : <EmptyNote>{t("site.event.noPublicJudoka")}</EmptyNote>}
          </section>
        </div>
      </Container>
    </SiteShell>
  );
}
