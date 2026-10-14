import type { Metadata } from "next";
import { Podium } from "@/components/ui/gamification";
import { Chip, Container, EmptyNote, FilterRow, PageIntro, RankingTable } from "@/components/site/blocks";
import { ageBandLabel, siteI18n } from "@/components/site/i18n";
import { SiteShell } from "@/components/site/site-shell";
import { publicSite } from "@/lib/public-site";

type Search = { searchParams: Promise<{ age_band?: string; club?: string }> };

// Le fasce del Jav Ranking (club/competitions.py::AGE_BANDS), nello stesso ordine.
const AGE_BANDS = ["BAMBINI", "FANCIULLI", "RAGAZZI", "ESORDIENTI", "CADETTI", "JUNIORES", "SENIORES"] as const;

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
  const [{ t }, ranking, clubs] = await Promise.all([
    siteI18n(), publicSite.ranking({ age_band: ageBand, club }), publicSite.clubs(),
  ]);
  const rows = ranking?.rows ?? [];

  const href = (change: { age_band?: string; club?: string }) => {
    const next = { age_band: ageBand as string | undefined, club, ...change };
    const q = new URLSearchParams();
    if (next.age_band) q.set("age_band", next.age_band);
    if (next.club) q.set("club", next.club);
    const s = q.toString();
    return s ? `/ranking?${s}` : "/ranking";
  };

  return (
    <SiteShell>
      <PageIntro
        eyebrow={ranking ? t("site.ranking.season", { season: ranking.season_label }) : t("site.ranking.eyebrow")}
        title={t("site.ranking.title")}
        text={t("site.ranking.intro")}
      />
      <Container className="py-10">
        <div className="mb-8 space-y-3">
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
                <Podium entries={rows.slice(0, 3).map((r) => ({ name: r.display_name, points: r.points, photoUrl: r.photo_url, href: `/judocas/${r.id}` }))} />
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
