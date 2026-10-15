"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BeltBadge } from "@/components/ui/belt";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/field";
import { Podium } from "@/components/ui/gamification";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { clubGet, type ClubConfig, type Ranking } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

/** Jav Ranking: points from competition results × the competition's level,
 *  per season, sex and age band. Families see everyone (it's a ranking),
 *  their own athletes highlighted. `admin` reads the staff endpoint. */
export function RankingPanel({ admin = false }: { admin?: boolean }) {
  const { data: config } = useQuery({ queryKey: ["club", "config"], queryFn: () => clubGet<ClubConfig>("/config") });
  const [sex, setSex] = useState<"" | "M" | "F">("");
  const { t } = useI18n();
  const [band, setBand] = useState("");
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  // Di tutta la rete (come nel gestionale dei club) o solo del proprio club.
  const [clubOnly, setClubOnly] = useState(false);
  const params = new URLSearchParams();
  if (sex) params.set("sex", sex);
  if (band) params.set("age_band", band);
  params.set("season", String(year));
  if (clubOnly) params.set("club_only", "true");
  const qs = params.toString();
  const { data, isLoading, error } = useQuery({
    queryKey: ["club", "ranking", admin, sex, band, year, clubOnly],
    queryFn: () => clubGet<Ranking>(`${admin ? "/admin" : ""}/ranking${qs ? `?${qs}` : ""}`),
  });
  const rows = data?.rows ?? [];

  return (
    <div>
      <PageHeader
        eyebrow={t("ranking.year", { year })}
        title={<>Jav <span className="text-gradient-brand">Ranking</span></>}
        subtitle={t("ranking.subtitle")}
      />
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <Tabs
          value={sex || "ALL"}
          onChange={(k) => setSex(k === "ALL" ? "" : (k as "M" | "F"))}
          items={[{ key: "ALL", label: t("ranking.all") }, { key: "M", label: t("ranking.male") }, { key: "F", label: t("ranking.female") }]}
        />
        <Select value={String(year)} onChange={(e) => setYear(Number(e.target.value))} className="sm:max-w-[8rem]" aria-label={t("ranking.yearLabel")}>
          {[thisYear, thisYear - 1, thisYear - 2].map((y) => <option key={y} value={y}>{y}</option>)}
        </Select>
        <Tabs
          value={clubOnly ? "CLUB" : "NETWORK"}
          onChange={(k) => setClubOnly(k === "CLUB")}
          items={[{ key: "NETWORK", label: t("ranking.network") }, { key: "CLUB", label: t("ranking.myClub") }]}
        />
        <Select value={band} onChange={(e) => setBand(e.target.value)} className="sm:max-w-xs" aria-label={t("ranking.ageBand")}>
          <option value="">{t("ranking.allAges")}</option>
          {(config?.age_bands ?? []).map((b) => (
            <option key={b.code} value={b.code}>{t.dyn(`club.ageBand.${b.code}`, b.label)}</option>
          ))}
        </Select>
      </div>

      {isLoading && <Skeleton className="h-80" />}
      {error && <EmptyState title={t("ranking.unavailable")} text={(error as Error).message} />}
      {!isLoading && !error && rows.length === 0 && (
        <EmptyState icon={<span className="text-3xl">🏆</span>} title={t("ranking.empty")} text={t("ranking.emptyText")} />
      )}

      {rows.length > 0 && (
        <>
          <div className="relative overflow-hidden rounded-[32px] bg-gradient-to-b from-accent-50 via-white to-white ring-1 ring-accent-200 px-4 pb-0 mb-6">
            <div className="absolute inset-x-0 top-0 h-40 bg-[radial-gradient(ellipse_at_top,rgb(249_228_15/0.35),transparent_70%)]" aria-hidden="true" />
            <div className="relative">
              <Podium entries={rows.slice(0, 3).map((r) => ({ name: r.display_name, points: r.points, photoUrl: r.photo_url }))} />
            </div>
          </div>
          <div className="glass-card rounded-3xl divide-y divide-ink-100 overflow-hidden">
            {rows.map((r, i) => (
              <motion.div
                key={r.athlete_id}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: Math.min(i, 15) * 0.03 }}
                className={`flex items-center gap-3 sm:gap-4 px-4 py-3 ${r.is_mine ? "bg-brand-50/70" : ""}`}
              >
                <span className={`w-9 text-center font-display text-lg ${r.position <= 3 ? "text-brand-600" : "text-ink-400"}`}>{r.position}</span>
                <div className="h-10 w-10 rounded-full overflow-hidden bg-gradient-to-br from-ink-200 to-ink-400 shrink-0 flex items-center justify-center font-display text-white">
                  {r.photo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={r.photo_url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    r.display_name.slice(0, 1)
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-ink-900 truncate">
                    {r.display_name}
                    {r.is_mine && <span className="ml-2 text-[10px] font-bold uppercase tracking-wide text-brand-600">{t("ranking.yours")}</span>}
                  </p>
                  <div className="flex items-center gap-2 mt-0.5">
                    {r.belt && <BeltBadge code={r.belt} size="sm" showLabel={false} />}
                    <span className="text-xs text-ink-500">{t(r.competitions === 1 ? "ranking.competitionOne" : "ranking.competitionMany", { n: r.competitions })}</span>
                    {r.club_name && <span className="truncate text-xs text-ink-400">· {r.club_name}</span>}
                  </div>
                </div>
                <div className="hidden sm:flex items-center gap-2 text-sm">
                  <span title={t("ranking.golds")}>🥇 {r.gold}</span>
                  <span title={t("ranking.silvers")}>🥈 {r.silver}</span>
                  <span title={t("ranking.bronzes")}>🥉 {r.bronze}</span>
                </div>
                <span className="font-display text-lg text-ink-900 tabular-nums w-16 text-right">{r.points}</span>
              </motion.div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
