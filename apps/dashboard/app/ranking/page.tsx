import type { Metadata } from "next";
import Link from "next/link";
import { Podium } from "@/components/ui/gamification";
import { Chip, Container, EmptyNote, FilterRow } from "@/components/site/blocks";
import { HeroStat, PageHero } from "@/components/site/page-hero";
import { ageBandLabel, siteI18n } from "@/components/site/i18n";
import { AthleteRanking, ClubCup } from "@/components/site/ranking-explorer";
import { SiteShell } from "@/components/site/site-shell";
import { cn } from "@/lib/cn";
import { publicSite, type RankingPeriod } from "@/lib/public-site";

type Params = { tab?: string; period?: string; age_band?: string; club?: string; year?: string; month?: string };
type Search = { searchParams: Promise<Params> };

// Le fasce del Jav Ranking (club/competitions.py::AGE_BANDS), nello stesso ordine.
const AGE_BANDS = ["GRUPO_1", "GRUPO_2", "GRUPO_3", "VETERANOS"] as const;
const PERIODS: RankingPeriod[] = ["year", "month", "all"];
const FIRST_YEAR = 2020;

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: t("site.meta.rankingTitle"), description: t("site.ranking.intro") };
}

/** Il Jav Ranking di tutta la rete: i judoca (con la ricerca e la scheda in
 *  popup) e la Taça dos Clubes. Dell'anno solare (quello che conta: a fine
 *  anno il primo club vince la coppa), di un mese, o di sempre. Punti
 *  calcolati dai risultati, mai scritti a mano. */
export default async function RankingPage({ searchParams }: Search) {
  const params = await searchParams;
  const tab = params.tab === "clubes" ? "clubes" : "judocas";
  const now = new Date();
  const thisYear = now.getFullYear();
  const years = Array.from({ length: thisYear - FIRST_YEAR + 1 }, (_, i) => thisYear - i);
  const period: RankingPeriod = PERIODS.find((p) => p === params.period) ?? "year";
  const year = years.includes(Number(params.year)) ? Number(params.year) : thisYear;
  const monthParam = Number(params.month);
  const month = monthParam >= 1 && monthParam <= 12 ? monthParam : (year === thisYear ? now.getMonth() + 1 : 12);
  const ageBand = AGE_BANDS.find((b) => b === params.age_band);
  const club = params.club || undefined;
  const filters = { season: period === "all" ? undefined : String(year), period, month: period === "month" ? String(month) : undefined };

  const [{ t, fmt }, ranking, cup, clubs, photos] = await Promise.all([
    siteI18n(),
    tab === "judocas" ? publicSite.ranking({ ...filters, age_band: ageBand, club }) : Promise.resolve(null),
    publicSite.clubRanking(filters),
    publicSite.clubs(),
    publicSite.photos(),
  ]);
  const rows = ranking?.rows ?? [];

  const href = (change: Partial<Params>) => {
    const next: Params = {
      tab: tab === "clubes" ? "clubes" : undefined, period: period === "year" ? undefined : period,
      year: year === thisYear ? undefined : String(year), month: period === "month" ? String(month) : undefined,
      age_band: ageBand, club, ...change,
    };
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(next)) if (v) q.set(k, v);
    const s = q.toString();
    return s ? `/ranking?${s}` : "/ranking";
  };
  const monthName = (m: number) => fmt.date(new Date(2024, m - 1, 15), { month: "long" });
  const periodLabel = period === "all" ? t("site.rankx.periodAll")
    : period === "month" ? `${monthName(month)} ${year}` : String(year);

  return (
    <SiteShell>
      <PageHero
        theme="ranking" icon="🏆" photos={photos ?? []}
        eyebrow={`Ranking · ${periodLabel}`} title={t("site.ranking.title")} text={t("site.rankx.heroText")}
      >
        <div className="flex flex-wrap gap-2">
          {tab === "judocas" ? (
            <>
              <HeroStat value={rows.length} label={t("site.rank.heroAthletes")} />
              <HeroStat value={new Set(rows.map((r) => r.club.slug)).size} label={t("site.rank.heroClubs")} />
              <HeroStat value={rows.reduce((sum, r) => sum + r.points, 0)} label={t("site.rank.heroPoints")} />
            </>
          ) : (
            <>
              <HeroStat value={cup?.rows.length ?? 0} label={t("site.rank.heroClubs")} />
              <HeroStat value={cup?.rows.reduce((sum, r) => sum + r.points, 0) ?? 0} label={t("site.rank.heroPoints")} />
              {cup?.rows[0] && <HeroStat value={`🏆 ${cup.rows[0].club.name}`} label={cup.is_final ? t("site.rankx.winnerShort") : t("site.rankx.leaderShort")} />}
            </>
          )}
        </div>
      </PageHero>

      {/* --- Le due classifiche --- */}
      <div className="sticky top-20 z-30 border-b border-ink-900/5 bg-white/85 backdrop-blur sm:top-24">
        <Container className="flex gap-2 py-3">
          {([["judocas", "🥋", t("site.rankx.tabAthletes")], ["clubes", "🏆", t("site.rankx.tabClubs")]] as const).map(([key, icon, label]) => (
            <Link key={key} href={href({ tab: key === "clubes" ? "clubes" : undefined, age_band: key === "clubes" ? undefined : ageBand, club: key === "clubes" ? undefined : club })}
              className={cn("inline-flex h-11 items-center gap-2 rounded-2xl px-5 font-semibold transition",
                tab === key ? "bg-gradient-to-r from-accent-400 to-brand-600 text-white shadow-brand" : "bg-ink-50 text-ink-700 ring-1 ring-ink-900/5 hover:bg-white")}>
              <span aria-hidden="true">{icon}</span>{label}
            </Link>
          ))}
        </Container>
      </div>

      <Container className="py-10">
        <div className="glass-card mb-8 space-y-3 rounded-3xl border-t-4 border-t-accent-400 p-4">
          <FilterRow label={t("site.rankx.period")}>
            {PERIODS.map((p) => (
              <Chip key={p} href={href({ period: p === "year" ? undefined : p, month: p === "month" ? String(month) : undefined })} active={period === p}>
                {p === "year" ? `⭐ ${t("site.rankx.periodYear")}` : p === "month" ? `🗓️ ${t("site.rankx.periodMonth")}` : `♾️ ${t("site.rankx.periodAll")}`}
              </Chip>
            ))}
          </FilterRow>
          {period !== "all" && (
            <FilterRow label={t("site.ev.viewYear")}>
              {years.map((y) => <Chip key={y} href={href({ year: y === thisYear ? undefined : String(y) })} active={year === y}>{y}</Chip>)}
            </FilterRow>
          )}
          {period === "month" && (
            <FilterRow label={t("site.rankx.month")}>
              {Array.from({ length: 12 }, (_, i) => i + 1)
                .filter((m) => year < thisYear || m <= now.getMonth() + 1)
                .map((m) => <Chip key={m} href={href({ month: String(m) })} active={month === m}>{monthName(m)}</Chip>)}
            </FilterRow>
          )}
          {tab === "judocas" && (
            <FilterRow label={t("site.filter.ageBand")}>
              <Chip href={href({ age_band: undefined })} active={!ageBand}>{t("site.filter.all")}</Chip>
              {AGE_BANDS.map((b) => <Chip key={b} href={href({ age_band: b })} active={ageBand === b}>{ageBandLabel(t, b)}</Chip>)}
            </FilterRow>
          )}
          {tab === "judocas" && (clubs?.length ?? 0) > 1 && (
            <FilterRow label={t("site.filter.club")}>
              <Chip href={href({ club: undefined })} active={!club}>{t("site.filter.allClubs")}</Chip>
              {clubs?.map((c) => <Chip key={c.slug} href={href({ club: c.slug })} active={club === c.slug}>{c.name}</Chip>)}
            </FilterRow>
          )}
        </div>

        {tab === "judocas" ? (
          rows.length > 0 ? (
            <>
              {rows.length >= 3 && (
                <div className="mb-10">
                  <Podium entries={rows.slice(0, 3).map((r) => ({ name: r.display_name, points: r.points, photoUrl: r.photo_url, href: r.has_page === false ? undefined : `/judocas/${r.id}` }))} />
                </div>
              )}
              <AthleteRanking rows={rows} showClub={!club} />
            </>
          ) : (
            <EmptyNote>{t("site.ranking.empty")}</EmptyNote>
          )
        ) : cup ? <ClubCup data={cup} /> : <EmptyNote>{t("site.rankx.cupEmpty")}</EmptyNote>}
        <p className="mt-6 text-sm text-ink-500">{tab === "judocas" ? t("site.ranking.howPoints") : t("site.rankx.cupHow")}</p>
      </Container>
    </SiteShell>
  );
}
