import type { Metadata } from "next";
import { Container } from "@/components/site/blocks";
import { EventsExplorer, type ExplorerState, type View } from "@/components/site/events-explorer";
import { siteI18n } from "@/components/site/i18n";
import { HeroStat, PageHero } from "@/components/site/page-hero";
import { SiteShell } from "@/components/site/site-shell";
import { publicSite } from "@/lib/public-site";

type Search = { searchParams: Promise<Record<string, string | undefined>> };

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: t("site.meta.eventsTitle"), description: t("site.events.intro") };
}

const VIEWS: View[] = ["list", "calendar", "year"];

/** Il calendario degli eventi della rete e dei club: lista, calendario
 *  mensile e anno intero, con ricerca e filtri (components/site/events-explorer).
 *  Il server prepara l'anno chiesto (per i motori di ricerca e per non far
 *  aspettare); il resto lo fa il browser. Lo stato è nell'URL. */
export default async function EventsPage({ searchParams }: Search) {
  const params = await searchParams;
  const now = new Date();
  const todayIso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const year = Number(params.year) >= 2000 && Number(params.year) <= 2100 ? Number(params.year) : now.getFullYear();
  const month = Number(params.month) >= 1 && Number(params.month) <= 12 ? Number(params.month) - 1 : now.getMonth();
  const initial: ExplorerState = {
    view: VIEWS.includes(params.view as View) ? (params.view as View) : "list",
    year, month, q: (params.q ?? "").slice(0, 80), kind: params.kind ?? "", level: params.level ?? "",
    club: params.club ?? "", age: params.age ?? "", open: params.open === "1",
  };
  const [{ t }, events, clubs, photos, upcoming] = await Promise.all([
    siteI18n(),
    publicSite.events({ from: `${year}-01-01`, to: `${year}-12-31`, limit: "500", club: initial.club || undefined }),
    publicSite.clubs(),
    publicSite.photos(),
    publicSite.events({ when: "upcoming", limit: "500" }),
  ]);
  const yearEvents = events ?? [];
  const open = (upcoming ?? []).filter((e) => e.status === "OPEN" && e.registration_deadline >= todayIso).length;

  return (
    <SiteShell>
      <PageHero
        theme="events" icon="📅" photos={photos ?? []}
        eyebrow={t("site.events.eyebrow")} title={t("site.events.pageTitle")} text={t("site.events.intro")}
      >
        <div className="flex flex-wrap gap-2">
          <HeroStat value={yearEvents.length} label={t("site.ev.heroYear", { year })} />
          <HeroStat value={(upcoming ?? []).length} label={t("site.ev.heroUpcoming")} />
          <HeroStat value={open} label={t("site.ev.heroOpen")} />
        </div>
      </PageHero>
      <Container className="py-8">
        <EventsExplorer
          initial={initial} initialEvents={yearEvents} todayIso={todayIso}
          clubs={(clubs ?? []).map((c) => ({ slug: c.slug, name: c.name }))}
        />
      </Container>
    </SiteShell>
  );
}
