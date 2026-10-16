"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { BeltBadge } from "@/components/ui/belt";
import { JudokaModal } from "@/components/site/judoka-modal";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import type { ClubRanking, ClubRef, RankingRow } from "@/lib/public-site";

// Le classifiche del sito, la parte che si tocca: la ricerca istantanea
// (nome o club), le righe grandi con foto e logo del club, il popup della
// scheda (judoka-modal.tsx) e la Taça dos Clubes. I filtri di periodo, anno
// e fascia restano link nella pagina (app/ranking/page.tsx): si condividono.

const MEDAL = { 1: "from-accent-300 to-accent-500 text-ink-900", 2: "from-ink-200 to-ink-400 text-ink-900", 3: "from-amber-600 to-amber-800 text-white" } as const;

function fold(s: string) {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function initials(name: string) {
  return name.split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function ClubLogo({ club, size = "md" }: { club: ClubRef; size?: "md" | "lg" | "xl" }) {
  const box = { md: "h-9 w-9 text-xs", lg: "h-12 w-12 text-sm", xl: "h-20 w-20 text-xl" }[size];
  return club.logo_url ? (
    // eslint-disable-next-line @next/next/no-img-element -- logo caricato dal club
    <img src={club.logo_url} alt="" className={cn("shrink-0 rounded-full bg-white object-cover shadow-sm ring-2 ring-white", box)} loading="lazy" />
  ) : (
    <span className={cn("flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 font-bold text-white shadow-sm ring-2 ring-white", box)}>
      {initials(club.name.replace(/^(judo )?(clube?|team)( de| do| da)?/i, "").trim() || club.name)}
    </span>
  );
}

function Place({ position, big = false }: { position: number; big?: boolean }) {
  return position <= 3 ? (
    <span className={cn("flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br font-display shadow ring-2 ring-white", MEDAL[position as 1 | 2 | 3],
      big ? "h-12 w-12 text-xl" : "h-10 w-10 text-lg")}>{position}</span>
  ) : (
    <span className={cn("flex shrink-0 items-center justify-center rounded-full bg-ink-100 font-display text-ink-600", big ? "h-12 w-12 text-xl" : "h-10 w-10 text-base")}>{position}</span>
  );
}

function Medals({ gold, silver, bronze }: { gold: number; silver: number; bronze: number }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm font-semibold text-ink-700">
      {gold > 0 && <span title="🥇">🥇{gold}</span>}
      {silver > 0 && <span title="🥈">🥈{silver}</span>}
      {bronze > 0 && <span title="🥉">🥉{bronze}</span>}
    </span>
  );
}

function SearchBox({ value, onChange, placeholder, count }: { value: string; onChange: (v: string) => void; placeholder: string; count: string }) {
  return (
    <div className="relative mb-6">
      <span className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-xl" aria-hidden="true">🔎</span>
      <input
        type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={placeholder}
        className="h-14 w-full rounded-2xl bg-white pl-14 pr-32 text-base text-ink-900 shadow-soft ring-1 ring-ink-900/10 placeholder:text-ink-400 focus:outline-none focus:ring-4 focus:ring-accent-300/60"
      />
      <span className="pointer-events-none absolute right-5 top-1/2 -translate-y-1/2 text-xs font-semibold uppercase tracking-wider text-ink-400">{count}</span>
    </div>
  );
}

/** La classifica dei judoca, con la ricerca e il popup della scheda. */
export function AthleteRanking({ rows, showClub = true }: { rows: RankingRow[]; showClub?: boolean }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const max = rows[0]?.points || 1;
  const shown = useMemo(() => {
    const needle = fold(q.trim());
    return needle ? rows.filter((r) => fold(`${r.display_name} ${r.club.name}`).includes(needle)) : rows;
  }, [rows, q]);

  return (
    <MotionConfig reducedMotion="user">
      <SearchBox value={q} onChange={setQ} placeholder={t("site.rankx.searchAthlete")} count={t("site.rankx.found", { n: shown.length })} />
      {shown.length === 0 ? (
        <p className="rounded-2xl bg-ink-50 p-8 text-center text-ink-500">{t("site.rankx.noMatch", { q })}</p>
      ) : (
        <ol className="space-y-2">
          <AnimatePresence initial={false}>
            {shown.map((r, i) => (
              <motion.li key={r.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                transition={{ delay: q ? 0 : Math.min(i, 12) * 0.025 }}>
                <button type="button" onClick={() => setOpen(r.id)}
                  className={cn("group relative flex w-full cursor-pointer items-center gap-3 overflow-hidden rounded-2xl bg-white p-3 text-left shadow-soft ring-1 ring-ink-900/5 transition hover:-translate-y-0.5 hover:shadow-lift hover:ring-accent-300 sm:gap-4 sm:p-4",
                    r.position <= 3 && "ring-2 ring-accent-200")}>
                  {/* La barra dei punti, dietro la riga. */}
                  <span aria-hidden="true" className="absolute inset-y-0 left-0 bg-gradient-to-r from-accent-100/70 to-transparent transition-all group-hover:from-accent-200/70"
                    style={{ width: `${Math.max(8, (r.points / max) * 100)}%` }} />
                  <span className="relative flex w-full items-center gap-3 sm:gap-4">
                    <Place position={r.position} />
                    <span className="relative shrink-0">
                      {r.photo_url ? (
                        // eslint-disable-next-line @next/next/no-img-element -- foto pubblicata con il consenso
                        <img src={r.photo_url} alt="" className="h-14 w-14 rounded-2xl object-cover shadow ring-2 ring-white sm:h-16 sm:w-16" loading="lazy" />
                      ) : (
                        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-ink-700 to-ink-900 font-display text-lg text-white shadow ring-2 ring-white sm:h-16 sm:w-16">{initials(r.display_name)}</span>
                      )}
                      {showClub && <span className="absolute -bottom-1.5 -right-1.5"><ClubLogo club={r.club} /></span>}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-lg font-semibold text-ink-900 group-hover:text-brand-700">{r.display_name}</span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-500">
                        {showClub && <span className="font-semibold text-ink-700">{r.club.name}</span>}
                        <span>{t.dyn(`club.ageBand.${r.age_band}`, r.age_band)}</span>
                        {r.belt && <span className="hidden sm:inline"><BeltBadge code={r.belt} size="sm" /></span>}
                      </span>
                    </span>
                    <span className="hidden shrink-0 md:block"><Medals gold={r.gold} silver={r.silver} bronze={r.bronze} /></span>
                    <span className="shrink-0 text-right">
                      <span className="block font-display text-2xl leading-none text-brand-600 sm:text-3xl">{r.points}</span>
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">{t("site.ranking.points")}</span>
                    </span>
                  </span>
                </button>
              </motion.li>
            ))}
          </AnimatePresence>
        </ol>
      )}
      <JudokaModal id={open} onClose={() => setOpen(null)} />
    </MotionConfig>
  );
}

/** La Taça dos Clubes: il podio dei club con la coppa, la classifica e
 *  l'albo d'oro degli anni chiusi. */
export function ClubCup({ data }: { data: ClubRanking }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const max = data.rows[0]?.points || 1;
  const shown = useMemo(() => {
    const needle = fold(q.trim());
    return needle ? data.rows.filter((r) => fold(`${r.club.name} ${r.city ?? ""}`).includes(needle)) : data.rows;
  }, [data.rows, q]);
  const leader = data.rows[0];
  const yearOpen = data.period === "year" && !data.is_final;

  return (
    <MotionConfig reducedMotion="user">
      {leader && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
          className="relative mb-8 overflow-hidden rounded-[2rem] bg-gradient-to-br from-accent-400 via-accent-500 to-brand-700 p-6 text-white shadow-lift sm:p-8">
          <motion.span aria-hidden="true" className="pointer-events-none absolute -right-6 -top-10 select-none text-[10rem] leading-none opacity-25"
            animate={{ rotate: [-6, 6, -6] }} transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}>🏆</motion.span>
          <p className="text-xs font-bold uppercase tracking-[0.25em] text-white/85">
            {data.is_final ? t("site.rankx.cupWinner", { year: data.season }) : yearOpen ? t("site.rankx.cupLeader", { year: data.season }) : t("site.rankx.cupTop")}
          </p>
          <div className="mt-3 flex items-center gap-4">
            <ClubLogo club={leader.club} size="xl" />
            <div className="min-w-0">
              <Link href={`/clubes/${leader.club.slug}`} className="block truncate font-display text-3xl hover:underline sm:text-4xl">{leader.club.name}</Link>
              <p className="mt-1 text-white/85">{leader.points} {t("site.ranking.points")} · {leader.athletes} {t("site.rankx.athletes")} · 🥇{leader.gold} 🥈{leader.silver} 🥉{leader.bronze}</p>
            </div>
          </div>
          {yearOpen && <p className="mt-4 max-w-xl text-sm text-white/85">{t("site.rankx.cupOpen", { year: data.season })}</p>}
        </motion.div>
      )}

      {data.rows.length > 3 && <SearchBox value={q} onChange={setQ} placeholder={t("site.rankx.searchClub")} count={t("site.rankx.found", { n: shown.length })} />}

      {data.rows.length === 0 ? (
        <p className="rounded-2xl bg-ink-50 p-8 text-center text-ink-500">{t("site.rankx.cupEmpty")}</p>
      ) : (
        <ol className="space-y-3">
          {shown.map((r, i) => (
            <motion.li key={r.club.slug} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i, 10) * 0.04 }}>
              <Link href={`/clubes/${r.club.slug}`}
                className="group relative flex items-center gap-4 overflow-hidden rounded-2xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5 transition hover:-translate-y-0.5 hover:shadow-lift hover:ring-accent-300">
                <span aria-hidden="true" className="absolute inset-y-0 left-0 bg-gradient-to-r from-brand-100/70 to-transparent" style={{ width: `${Math.max(8, (r.points / max) * 100)}%` }} />
                <span className="relative flex w-full items-center gap-4">
                  <Place position={r.position} big />
                  <ClubLogo club={r.club} size="lg" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-lg font-semibold text-ink-900 group-hover:text-brand-700">
                      {r.club.name} {r.position === 1 && (data.is_final || yearOpen) && <span aria-hidden="true">🏆</span>}
                    </span>
                    <span className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-ink-500">
                      {r.city && <span>📍 {r.city}</span>}
                      <span>👥 {r.athletes} {t("site.rankx.athletes")}</span>
                      <span>🏟️ {r.events} {t("site.rankx.events")}</span>
                      <span>🥋 {r.results} {t("site.rankx.results")}</span>
                    </span>
                  </span>
                  <span className="hidden shrink-0 sm:block"><Medals gold={r.gold} silver={r.silver} bronze={r.bronze} /></span>
                  <span className="shrink-0 text-right">
                    <span className="block font-display text-3xl leading-none text-brand-600">{r.points}</span>
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">{t("site.ranking.points")}</span>
                  </span>
                </span>
              </Link>
            </motion.li>
          ))}
        </ol>
      )}

      {data.winners.length > 0 && (
        <section className="mt-12">
          <h2 className="mb-4 text-2xl text-ink-900">🏆 {t("site.rankx.honours")}</h2>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.winners.map((w) => (
              <li key={w.year} className="flex items-center gap-4 rounded-2xl bg-gradient-to-br from-accent-50 to-white p-4 ring-1 ring-accent-200">
                <span className="font-display text-3xl text-accent-600">{w.year}</span>
                <ClubLogo club={w.club} />
                <span className="min-w-0">
                  <Link href={`/clubes/${w.club.slug}`} className="block truncate font-semibold text-ink-900 hover:text-brand-700">{w.club.name}</Link>
                  <span className="text-xs text-ink-500">{w.points} {t("site.ranking.points")}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </MotionConfig>
  );
}
