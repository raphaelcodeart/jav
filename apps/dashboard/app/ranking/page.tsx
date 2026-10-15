import type { Metadata } from "next";
import { Podium } from "@/components/ui/gamification";
import { Chip, Container, EmptyNote, FilterRow, RankingTable } from "@/components/site/blocks";
import { HeroStat, PageHero } from "@/components/site/page-hero";
import { ageBandLabel, siteI18n } from "@/components/site/i18n";
import { SiteShell } from "@/components/site/site-shell";
import { publicSite } from "@/lib/public-site";

type Search = { searchParams: Promise<{ age_band?: string; club?: string; year?: string }> };

// Le fasce del Jav Ranking (club/competitions.py::AGE_BANDS), nello stesso ordine.
const AGE_BANDS = ["GRUPO_1", "GRUPO_2", "GRUPO_3", "VETERANOS"] as const;

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: t("site.meta.rankingTitle"), description: t("site.ranking.intro") };
}

/** Il Jav Ranking della stagione, di tutta la rete: punti calcolati dai
 *  risultati (mai scritti a mano), solo per i judoca con il consenso. */
export default async function RankingPage({ searchParams }: Search) {
  const params = await searchParams;
  const ageBand = AGE_BANDS.find((b) => b === params.age_band);
  const club = params.club || undefined;
  const thisYear = new Date().getFullYear();
  const year = [thisYear, thisYear - 1, thisYear - 2].includes(Number(params.year)) ? Number(params.year) : thisYear;
  const [{ t }, ranking, clubs, photos] = await Promise.all([
    siteI18n(), publicSite.ranking({ age_band: ageBand, club, season: year === thisYear ? undefined : String(year) }),
    publicSite.clubs(), publicSite.photos(),
  ]);
  const rows = ranking?.rows ?? [];
  const points = rows.reduce((sum, r) => sum + r.points, 0);

  const href = (change: { age_band?: string; club?: string; year?: string }) => {
    const next = { age_band: ageBand as string | undefined, club, year: year === thisYear ? undefined : String(year), ...change };
    const q = new URLSearchParams();
    if (next.age_band) q.set("age_band", next.age_band);
    if (next.club) q.set("club", next.club);
    if (next.year) q.set("year", next.year);
    const s = q.toString();
    return s ? `/ranking?${s}` : "/ranking";
  };

  return (
    <SiteShell>
      <PageHero
        theme="ranking" icon="🏆" photos={photos ?? []}
        eyebrow={`Ranking ${ranking?.season_label ?? year}`} title={t("site.ranking.title")} text={t("site.ranking.intro")}
      >
        <div className="flex flex-wrap gap-2">
          <HeroStat value={rows.length} label={t("site.rank.heroAthletes")} />
          <HeroStat value={new Set(rows.map((r) => r.club.slug)).size} label={t("site.rank.heroClubs")} />
          <HeroStat value={points} label={t("site.rank.heroPoints")} />
        </div>
      </PageHero>
      <Container className="py-10">
        <div className="glass-card mb-8 space-y-3 rounded-3xl border-t-4 border-t-accent-400 p-4">
          <FilterRow label={t("site.ev.viewYear")}>
            {[thisYear, thisYear - 1, thisYear - 2].map((y) => (
              <Chip key={y} href={href({ year: y === thisYear ? undefined : String(y) })} active={year === y}>{y}</Chip>
            ))}
          </FilterRow>
          <FilterRow label={t("site.filter.ageBand")}>
            <Chip href={href({ age_band: undefined })} active={!ageBand}>{t("site.filter.all")}</Chip>
            {AGE_BANDS.map((b) => <Chip key={b} href={href({ age_band: b })} active={ageBand === b}>{ageBandLabel(t, b)}</Chip>)}
          </FilterRow>
          {(clubs?.length ?? 0) > 1 && (
            <FilterRow label={t("site.filter.club")}>
              <Chip href={href({ club: undefined })} active={!club}>{t("site.filter.allClubs")}</Chip>
              {clubs?.map((c) => <Chip key={c.slug} href={href({ club: c.slug })} active={club === c.slug}>{c.name}</Chip>)}
            </FilterRow>
          )}
        </div>
        {rows.length > 0 ? (
          <>
            {rows.length >= 3 && (
              <div className="mb-10">
                <Podium entries={rows.slice(0, 3).map((r) => ({ name: r.display_name, points: r.points, photoUrl: r.photo_url, href: r.has_page === false ? undefined : `/judocas/${r.id}` }))} />
              </div>
            )}
            <RankingTable rows={rows} t={t} />
          </>
        ) : (
          <EmptyNote>{t("site.ranking.empty")}</EmptyNote>
        )}
        <p className="mt-6 text-sm text-ink-500">{t("site.ranking.howPoints")}</p>
      </Container>
    </SiteShell>
  );
}
