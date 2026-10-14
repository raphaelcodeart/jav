// I mattoni delle pagine del sito pubblico. Sono server component: ricevono
// traduttore e formati da chi li usa (components/site/i18n.ts) e producono
// HTML già pronto, indicizzabile. Le parti che si muovono (carosello,
// comparse allo scroll, cinture) sono client component importati qui dentro.

import Link from "next/link";
import type { ReactNode } from "react";
import { BeltBadge } from "@/components/ui/belt";
import { ageBandLabel, ageRange, eventDates, levelLabel, placementLabel } from "@/components/site/i18n";
import { cn } from "@/lib/cn";
import type { Formatters, Translator } from "@/lib/i18n/translate";
import type { ClubRef, Judoka, Medal, PublicEvent, RankingRow, ScheduleDay } from "@/lib/public-site";

export function Container({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto max-w-7xl px-4 sm:px-6", className)}>{children}</div>;
}

export function SectionHeading({ eyebrow, title, text, action, id }: { eyebrow?: ReactNode; title: ReactNode; text?: ReactNode; action?: ReactNode; id?: string }) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-2xl">
        {/* club-ink: il colore del club sulla sua pagina, il rosso di JAV altrove (globals.css). */}
        {eyebrow && <p className="mb-2 text-xs font-bold uppercase tracking-[0.22em] text-club-ink">{eyebrow}</p>}
        <h2 id={id} className="text-2xl text-ink-900 sm:text-3xl">{title}</h2>
        {text && <p className="mt-2 text-ink-500">{text}</p>}
      </div>
      {action}
    </div>
  );
}

/** L'intestazione delle pagine interne (/clubes, /eventos, /ranking). */
export function PageIntro({ eyebrow, title, text, children }: { eyebrow: ReactNode; title: ReactNode; text?: ReactNode; children?: ReactNode }) {
  return (
    <section className="relative overflow-hidden border-b border-ink-900/5 bg-gradient-to-b from-brand-50/60 to-white">
      <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-accent-300/30 blur-3xl" aria-hidden="true" />
      <Container className="relative py-14 sm:py-20">
        <p className="mb-3 text-xs font-bold uppercase tracking-[0.22em] text-brand-600">{eyebrow}</p>
        <h1 className="max-w-3xl text-3xl text-ink-900 sm:text-5xl">{title}</h1>
        {text && <p className="mt-4 max-w-2xl text-lg text-ink-600">{text}</p>}
        {children && <div className="mt-8">{children}</div>}
      </Container>
    </section>
  );
}

/** La foto di un judoca, o le iniziali in un disco con i colori del club
 *  quando la famiglia non ha permesso la foto: mai un'immagine rotta. */
export function Avatar({ name, photoUrl, size = "md", className }: { name: string; photoUrl: string | null; size?: "sm" | "md" | "lg" | "xl"; className?: string }) {
  const dims = { sm: "h-9 w-9 text-xs", md: "h-12 w-12 text-sm", lg: "h-20 w-20 text-xl", xl: "h-32 w-32 text-4xl" }[size];
  const initials = name.split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
  return (
    <span className={cn("relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-brand-500 to-brand-700 font-display text-white ring-2 ring-white shadow-soft", dims, className)}>
      {photoUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- foto caricate dai club, servite da /media
        <img src={photoUrl} alt="" className="h-full w-full object-cover" loading="lazy" />
      ) : (
        <span aria-hidden="true">{initials}</span>
      )}
    </span>
  );
}

function ClubLink({ club, className }: { club: ClubRef; className?: string }) {
  return (
    <Link href={`/clubes/${club.slug}`} className={cn("inline-flex items-center gap-1.5 text-sm font-semibold text-ink-600 hover:text-brand-700", className)}>
      {club.logo_url && (
        // eslint-disable-next-line @next/next/no-img-element -- logo caricato dal club
        <img src={club.logo_url} alt="" className="h-5 w-5 rounded-full object-cover ring-1 ring-ink-100" loading="lazy" />
      )}
      {club.name}
    </Link>
  );
}

/** Il giorno di un evento come su un calendario da muro. */
function DateTile({ iso, fmt }: { iso: string; fmt: Formatters }) {
  const d = new Date(`${iso}T12:00:00`);
  return (
    <div className="flex h-16 w-16 shrink-0 flex-col items-center justify-center rounded-2xl bg-ink-900 text-white shadow-soft">
      <span className="text-[10px] font-bold uppercase tracking-widest text-accent-300">{fmt.date(d, { month: "short" }).replace(".", "")}</span>
      <span className="font-display text-2xl leading-none">{d.getDate()}</span>
    </div>
  );
}

export function KindBadge({ kind, t }: { kind: string; t: Translator }) {
  const stage = kind === "STAGE";
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset", stage ? "bg-sky-50 text-sky-700 ring-sky-200" : "bg-brand-50 text-brand-700 ring-brand-200")}>
      {t.dyn(`site.kind.${kind}`, kind)}
    </span>
  );
}

export function EventCard({ event, t, fmt }: { event: PublicEvent; t: Translator; fmt: Formatters }) {
  return (
    <article className="glass-card group relative flex gap-4 rounded-2xl p-4 transition-transform hover:-translate-y-0.5">
      <DateTile iso={event.starts_on} fmt={fmt} />
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <KindBadge kind={event.kind} t={t} />
          <span className="text-xs font-semibold text-ink-500">{levelLabel(t, event.level)}</span>
        </div>
        <h3 className="text-base leading-snug text-ink-900">
          <Link href={`/eventos/${event.id}`} className="after:absolute after:inset-0 hover:text-brand-700">{event.name}</Link>
        </h3>
        <p className="mt-1 text-sm text-ink-500">
          {eventDates(fmt, event.starts_on, event.ends_on)}
          {event.location ? ` · ${event.location}` : ""}
        </p>
        <p className="relative z-10 mt-2"><ClubLink club={event.club} className="text-xs" /></p>
      </div>
    </article>
  );
}

export function JudokaCard({ judoka, t, showClub = true }: { judoka: Judoka; t: Translator; showClub?: boolean }) {
  const medals = judoka.gold + judoka.silver + judoka.bronze;
  return (
    <article className="glass-card group relative flex flex-col items-center rounded-2xl p-5 text-center transition-transform hover:-translate-y-1">
      <Avatar name={judoka.display_name} photoUrl={judoka.photo_url} size="lg" />
      <h3 className="mt-3 text-base text-ink-900">
        <Link href={`/judocas/${judoka.id}`} className="after:absolute after:inset-0 hover:text-brand-700">{judoka.display_name}</Link>
      </h3>
      <p className="text-xs text-ink-500">{ageBandLabel(t, judoka.age_band)}</p>
      {judoka.belt && <div className="mt-2"><BeltBadge code={judoka.belt} size="sm" /></div>}
      <div className="mt-3 flex items-center gap-3 text-xs font-semibold text-ink-600">
        {medals > 0 && <MedalCounts gold={judoka.gold} silver={judoka.silver} bronze={judoka.bronze} t={t} />}
        <span>{t("site.points", { n: judoka.points })}</span>
      </div>
      {showClub && <p className="relative z-10 mt-3"><ClubLink club={judoka.club} className="text-xs" /></p>}
    </article>
  );
}

const MEDAL_COLORS = { 1: "from-accent-300 to-accent-500", 2: "from-ink-200 to-ink-400", 3: "from-amber-600 to-amber-800" } as const;

export function MedalDot({ place, className }: { place: 1 | 2 | 3; className?: string }) {
  return (
    <span className={cn("inline-flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br text-[11px] font-bold text-white shadow-sm ring-2 ring-white", MEDAL_COLORS[place], className)} aria-hidden="true">
      {place}
    </span>
  );
}

export function MedalCounts({ gold, silver, bronze, t }: { gold: number; silver: number; bronze: number; t: Translator }) {
  return (
    <span className="inline-flex items-center gap-2" aria-label={t("site.medalsAria", { gold, silver, bronze })}>
      {([[1, gold], [2, silver], [3, bronze]] as const).filter(([, n]) => n > 0).map(([place, n]) => (
        <span key={place} className="inline-flex items-center gap-1"><MedalDot place={place} className="h-4 w-4 text-[9px] ring-1" />{n}</span>
      ))}
    </span>
  );
}

export function MedalList({ medals, t, fmt, showClub = true }: { medals: Medal[]; t: Translator; fmt: Formatters; showClub?: boolean }) {
  return (
    <ul className="divide-y divide-ink-900/5">
      {medals.map((m) => (
        <li key={`${m.event_id}-${m.athlete_id}`} className="flex items-center gap-3 py-3">
          <MedalDot place={m.placement as 1 | 2 | 3} />
          <Avatar name={m.display_name} photoUrl={m.photo_url} size="sm" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink-900">
              <Link href={`/judocas/${m.athlete_id}`} className="hover:text-brand-700">{m.display_name}</Link>
              <span className="font-normal text-ink-500"> · {placementLabel(t, m.placement)}</span>
            </p>
            <p className="truncate text-xs text-ink-500">
              <Link href={`/eventos/${m.event_id}`} className="hover:text-brand-700">{m.event_name}</Link>
              {" · "}{fmt.shortDate(m.date)}{m.category ? ` · ${m.category}` : ""}
            </p>
          </div>
          {showClub && <ClubLink club={m.club} className="hidden text-xs sm:inline-flex" />}
        </li>
      ))}
    </ul>
  );
}

export function RankingTable({ rows, t, showClub = true }: { rows: RankingRow[]; t: Translator; showClub?: boolean }) {
  return (
    <div className="glass-card overflow-hidden rounded-2xl">
      <table className="w-full text-sm">
        <caption className="sr-only">{t("site.ranking.caption")}</caption>
        <thead className="bg-ink-50 text-left text-xs uppercase tracking-wider text-ink-500">
          <tr>
            <th scope="col" className="w-14 px-4 py-3">#</th>
            <th scope="col" className="px-4 py-3">{t("site.ranking.judoka")}</th>
            <th scope="col" className="hidden px-4 py-3 md:table-cell">{t("site.ranking.belt")}</th>
            {showClub && <th scope="col" className="hidden px-4 py-3 sm:table-cell">{t("site.ranking.club")}</th>}
            <th scope="col" className="hidden px-4 py-3 lg:table-cell">{t("site.ranking.medals")}</th>
            <th scope="col" className="px-4 py-3 text-right">{t("site.ranking.points")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-900/5">
          {rows.map((r) => (
            <tr key={r.id} className="hover:bg-brand-50/40">
              <td className="px-4 py-3">
                {r.position <= 3 ? <MedalDot place={r.position as 1 | 2 | 3} /> : <span className="font-display text-ink-500">{r.position}</span>}
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-3">
                  <Avatar name={r.display_name} photoUrl={r.photo_url} size="sm" />
                  <div className="min-w-0">
                    <Link href={`/judocas/${r.id}`} className="font-semibold text-ink-900 hover:text-brand-700">{r.display_name}</Link>
                    <p className="text-xs text-ink-500">{ageBandLabel(t, r.age_band)}</p>
                  </div>
                </div>
              </td>
              <td className="hidden px-4 py-3 md:table-cell">{r.belt && <BeltBadge code={r.belt} size="sm" />}</td>
              {showClub && <td className="hidden px-4 py-3 sm:table-cell"><ClubLink club={r.club} className="text-xs" /></td>}
              <td className="hidden px-4 py-3 lg:table-cell"><MedalCounts gold={r.gold} silver={r.silver} bronze={r.bronze} t={t} /></td>
              <td className="px-4 py-3 text-right font-display text-base text-brand-600">{r.points}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** L'orario della settimana, giorno per giorno, come lo calcola l'API dai
 *  corsi attivi. Sul telefono i giorni vanno uno sotto l'altro. */
export function ScheduleGrid({ schedule, t }: { schedule: ScheduleDay[]; t: Translator }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {schedule.map((day) => (
        <div key={day.weekday} className="glass-card rounded-2xl p-4">
          <h3 className="mb-3 text-sm uppercase tracking-widest text-club-ink">{t.dyn(`site.weekday.${day.weekday}`, String(day.weekday))}</h3>
          <ul className="space-y-3">
            {day.slots.map((s, i) => {
              const ages = ageRange(t, s.min_age, s.max_age);
              return (
                <li key={i} className="flex gap-3">
                  <span className="w-24 shrink-0 font-display text-sm text-ink-900">{s.starts_at}–{s.ends_at}</span>
                  <span className="min-w-0 text-sm">
                    <span className="block font-semibold text-ink-800">{s.course}</span>
                    <span className="block text-xs text-ink-500">{[s.level, ages, s.room].filter(Boolean).join(" · ")}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="rounded-2xl border border-dashed border-ink-200 bg-white/70 px-5 py-8 text-center text-sm text-ink-500">{children}</p>;
}

/** I filtri delle pagine elenco: link, non stato del browser, così una
 *  vista filtrata si condivide e funziona senza JavaScript. */
export function FilterRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label={label}>
      <span className="w-20 text-xs font-bold uppercase tracking-widest text-ink-400" aria-hidden="true">{label}</span>
      {children}
    </div>
  );
}

export function Chip({ href, active, children }: { href: string; active: boolean; children: ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      scroll={false}
      className={cn(
        "rounded-full px-3.5 py-1.5 text-sm font-semibold transition-colors",
        active ? "bg-ink-900 text-white" : "bg-white text-ink-600 ring-1 ring-ink-200 hover:ring-brand-300 hover:text-brand-700",
      )}
    >
      {children}
    </Link>
  );
}
