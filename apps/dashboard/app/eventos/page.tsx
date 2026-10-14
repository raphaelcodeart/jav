import type { Metadata } from "next";
import { Chip, Container, EmptyNote, EventCard, FilterRow, PageIntro } from "@/components/site/blocks";
import { siteI18n } from "@/components/site/i18n";
import { SiteShell } from "@/components/site/site-shell";
import { publicSite } from "@/lib/public-site";

type Search = { searchParams: Promise<{ when?: string; kind?: string; club?: string }> };

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: t("site.meta.eventsTitle"), description: t("site.events.intro") };
}

/** Gare e stage di tutti i club. I filtri sono link (?when=past&kind=STAGE):
 *  funzionano senza JavaScript, si condividono e i motori li seguono. */
export default async function EventsPage({ searchParams }: Search) {
  const params = await searchParams;
  const when = params.when === "past" ? "past" : "upcoming";
  const kind = params.kind === "COMPETITION" || params.kind === "STAGE" ? params.kind : undefined;
  const club = params.club || undefined;
  const [{ t, fmt }, events, clubs] = await Promise.all([
    siteI18n(), publicSite.events({ when, kind, club }), publicSite.clubs(),
  ]);

  const href = (change: Record<string, string | undefined>) => {
    const next = { when, kind, club, ...change };
    const q = new URLSearchParams();
    if (next.when && next.when !== "upcoming") q.set("when", next.when);
    if (next.kind) q.set("kind", next.kind);
    if (next.club) q.set("club", next.club);
    const s = q.toString();
    return s ? `/eventos?${s}` : "/eventos";
  };

  return (
    <SiteShell>
      <PageIntro eyebrow={t("site.events.eyebrow")} title={t("site.events.pageTitle")} text={t("site.events.intro")} />
      <Container className="py-10">
        <div className="mb-8 space-y-3">
          <FilterRow label={t("site.filter.when")}>
            <Chip href={href({ when: "upcoming" })} active={when === "upcoming"}>{t("site.filter.upcoming")}</Chip>
            <Chip href={href({ when: "past" })} active={when === "past"}>{t("site.filter.past")}</Chip>
          </FilterRow>
          <FilterRow label={t("site.filter.kind")}>
            <Chip href={href({ kind: undefined })} active={!kind}>{t("site.filter.all")}</Chip>
            <Chip href={href({ kind: "COMPETITION" })} active={kind === "COMPETITION"}>{t("site.kind.COMPETITION")}</Chip>
            <Chip href={href({ kind: "STAGE" })} active={kind === "STAGE"}>{t("site.kind.STAGE")}</Chip>
          </FilterRow>
          {(clubs?.length ?? 0) > 1 && (
            <FilterRow label={t("site.filter.club")}>
              <Chip href={href({ club: undefined })} active={!club}>{t("site.filter.allClubs")}</Chip>
              {clubs?.map((c) => <Chip key={c.slug} href={href({ club: c.slug })} active={club === c.slug}>{c.name}</Chip>)}
            </FilterRow>
          )}
        </div>
        {events && events.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {events.map((e) => <EventCard key={e.id} event={e} t={t} fmt={fmt} />)}
          </div>
        ) : (
          <EmptyNote>{when === "past" ? t("site.events.emptyPast") : t("site.events.empty")}</EmptyNote>
        )}
      </Container>
    </SiteShell>
  );
}
