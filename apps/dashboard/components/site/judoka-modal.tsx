"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { BeltBadge } from "@/components/ui/belt";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import type { JudokaProfile, RankingCard } from "@/lib/public-site";

// La scheda di un judoca in popup, dalla classifica pubblica, in stile IJF:
// foto grande, a destra i dati sportivi (club, fascia, categoria, cintura,
// posto nel ranking, punti, medaglie), poi risultati, prove in programma,
// percorso delle cinture, foto e video. I dati li decide l'API
// (club/site.py::ranking_card): senza il consenso della famiglia arriva
// solo la scheda ridotta, senza foto, categoria, media né prove future.

type Card = NonNullable<RankingCard["card"]>;
type Data = { profile: JudokaProfile; reduced: false } | { profile: Card; reduced: true };

const MEDAL = { 1: "from-accent-300 to-accent-500 text-ink-900", 2: "from-ink-200 to-ink-400 text-ink-900", 3: "from-amber-600 to-amber-800 text-white" } as const;

function initials(name: string) {
  return name.split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

export function JudokaModal({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { t } = useI18n();
  const [data, setData] = useState<{ id: string; value: Data | "error" } | null>(null);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    fetch(`/api/public/judoka/${id}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(String(res.status));
        const body = (await res.json()) as RankingCard;
        const value: Data = body.has_page && body.profile
          ? { profile: body.profile, reduced: false }
          : { profile: body.card as Card, reduced: true };
        if (alive) setData({ id, value });
      })
      .catch(() => { if (alive) setData({ id, value: "error" }); });
    return () => { alive = false; };
  }, [id]);

  useEffect(() => {
    if (!id) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; };
  }, [id, onClose]);

  const current = data && data.id === id ? data.value : null;

  return (
    <MotionConfig reducedMotion="user">
      <AnimatePresence>
        {id && (
          <motion.div
            key="judoka-modal"
            className="fixed inset-0 z-[80] flex items-end justify-center bg-ink-950/70 p-0 backdrop-blur-sm sm:items-center sm:p-6"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={onClose}
            role="dialog" aria-modal="true" aria-label={t("site.judoka.profileTitle")}
          >
            <motion.div
              className="relative max-h-[94vh] w-full max-w-4xl overflow-y-auto rounded-t-[2rem] bg-white shadow-2xl sm:rounded-[2rem]"
              initial={{ y: 40, scale: 0.98, opacity: 0 }} animate={{ y: 0, scale: 1, opacity: 1 }} exit={{ y: 30, opacity: 0 }}
              transition={{ type: "spring", damping: 26, stiffness: 260 }}
              onClick={(e) => e.stopPropagation()}
            >
              <button type="button" onClick={onClose} aria-label={t("common.close")}
                className="absolute right-4 top-4 z-10 flex h-10 w-10 cursor-pointer items-center justify-center rounded-full bg-white/90 text-xl text-ink-700 shadow ring-1 ring-ink-900/10 hover:bg-white">
                ×
              </button>
              {current === null ? <Loading /> : current === "error" ? (
                <p className="p-10 text-center text-ink-600">{t("site.rankx.cardError")}</p>
              ) : <CardBody data={current} />}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </MotionConfig>
  );
}

function Loading() {
  return (
    <div className="animate-pulse">
      <div className="h-56 bg-gradient-to-br from-ink-200 to-ink-100" />
      <div className="space-y-3 p-8"><div className="h-6 w-1/2 rounded bg-ink-100" /><div className="h-4 w-1/3 rounded bg-ink-100" /><div className="h-32 rounded-2xl bg-ink-50" /></div>
    </div>
  );
}

function CardBody({ data }: { data: Data }) {
  const { t, fmt } = useI18n();
  const p = data.profile;
  const full = data.reduced ? null : data.profile;
  const band = t.dyn(`club.ageBand.${p.age_band}`, p.age_band);
  const facts: { label: string; value: React.ReactNode }[] = [
    { label: t("site.judoka.club"), value: p.club.name },
    { label: t("site.judoka.ageBand"), value: band },
    ...(full?.category ? [{ label: t("site.judoka.category"), value: full.category }] : []),
    { label: t("site.judoka.belt"), value: p.belt ? <BeltBadge code={p.belt} size="sm" /> : "—" },
    { label: t("site.judoka.country"), value: `🇵🇹 ${t("site.judoka.countryName")}` },
    ...(full?.favorite_technique ? [{ label: t("site.judoka.technique"), value: full.favorite_technique }] : []),
    ...(full?.dominant_side ? [{ label: t("site.judoka.side"), value: t(`site.judoka.side.${full.dominant_side}`) }] : []),
  ];

  return (
    <div>
      {/* --- La testata: foto grande a sinistra, i dati a destra --- */}
      <div className="relative overflow-hidden bg-gradient-to-br from-brand-700 via-brand-600 to-ink-950 text-white">
        <motion.div aria-hidden="true" className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-accent-400/30 blur-3xl"
          animate={{ scale: [1, 1.2, 1] }} transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }} />
        <div className="relative grid gap-6 p-6 sm:grid-cols-[220px_1fr] sm:p-8">
          <motion.div initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.05 }}
            className="mx-auto aspect-[4/5] w-44 overflow-hidden rounded-3xl bg-white/10 shadow-xl ring-4 ring-white/20 sm:w-full">
            {p.photo_url ? (
              // eslint-disable-next-line @next/next/no-img-element -- foto pubblicata dal club con il consenso
              <img src={p.photo_url} alt={p.display_name} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-white/20 to-white/5 font-display text-6xl text-white/90">{initials(p.display_name)}</div>
            )}
          </motion.div>
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.22em] text-white/75">
              {p.club.logo_url && (
                // eslint-disable-next-line @next/next/no-img-element -- logo del club
                <img src={p.club.logo_url} alt="" className="h-7 w-7 rounded-full bg-white object-cover ring-2 ring-white/40" />
              )}
              {p.club.name}
            </p>
            <h2 className="mt-2 font-display text-4xl leading-tight sm:text-5xl">{p.display_name}</h2>
            <div className="mt-5 grid grid-cols-3 gap-2">
              <Stat value={p.ranking ? `#${p.ranking.position}` : "—"} label={p.ranking ? t("site.judoka.rankingOf", { total: p.ranking.total }) : t("site.judoka.notRanked")} />
              <Stat value={String(p.season_points)} label={t("site.judoka.seasonPoints")} />
              <Stat value={String(p.points)} label={t("site.judoka.totalPoints")} />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {([[1, p.gold, "site.judoka.gold"], [2, p.silver, "site.judoka.silver"], [3, p.bronze, "site.judoka.bronze"]] as const).map(([place, n, key]) => (
                <span key={place} className={cn("inline-flex items-center gap-2 rounded-full bg-gradient-to-br px-3 py-1 text-sm font-bold shadow", MEDAL[place])}>
                  {["🥇", "🥈", "🥉"][place - 1]} {n} <span className="text-xs font-semibold opacity-80">{t(key)}</span>
                </span>
              ))}
              <span className="inline-flex items-center gap-2 rounded-full bg-white/15 px-3 py-1 text-sm font-semibold ring-1 ring-white/25">
                🏟️ {p.competitions} <span className="text-xs opacity-80">{t("site.judoka.competitions")}</span>
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-8 p-6 sm:p-8">
        {/* --- I dati --- */}
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {facts.map((f) => (
            <div key={f.label} className="rounded-2xl bg-ink-50 px-4 py-3 ring-1 ring-ink-100">
              <dt className="text-[11px] font-bold uppercase tracking-wider text-ink-400">{f.label}</dt>
              <dd className="mt-1 truncate font-semibold text-ink-900">{f.value}</dd>
            </div>
          ))}
        </dl>
        {full?.bio && <p className="whitespace-pre-line text-ink-700">{full.bio}</p>}

        {/* --- I risultati --- */}
        <section>
          <h3 className="mb-3 text-xl text-ink-900">🏆 {t("site.judoka.results")}</h3>
          {p.results.length === 0 ? <p className="text-sm text-ink-500">{t("site.judoka.noResults")}</p> : (
            <ol className="divide-y divide-ink-100 overflow-hidden rounded-2xl ring-1 ring-ink-100">
              {p.results.map((r, i) => (
                <motion.li key={`${r.event_id}-${i}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 10) * 0.03 }}
                  className="flex items-center gap-4 bg-white px-4 py-3">
                  <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br font-display text-lg shadow-sm",
                    r.placement <= 3 ? MEDAL[r.placement as 1 | 2 | 3] : "from-ink-100 to-ink-200 text-ink-700")}>{r.placement}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-ink-900">{r.event_name}</p>
                    <p className="truncate text-xs text-ink-500">
                      {fmt.shortDate(r.date)} · {t.dyn(`club.level.${r.level}`, r.level)}{r.location ? ` · ${r.location}` : ""}
                      {"category" in r && r.category ? ` · ${r.category}` : ""}
                    </p>
                  </div>
                  <span className="shrink-0 font-display text-lg text-brand-600">+{r.points}</span>
                </motion.li>
              ))}
            </ol>
          )}
        </section>

        {full && full.upcoming.length > 0 && (
          <section>
            <h3 className="mb-3 text-xl text-ink-900">📅 {t("site.judoka.upcoming")}</h3>
            <ul className="grid gap-2 sm:grid-cols-2">
              {full.upcoming.map((e) => (
                <li key={e.id} className="rounded-2xl bg-ink-50 px-4 py-3 ring-1 ring-ink-100">
                  <p className="font-semibold text-ink-900">{e.name}</p>
                  <p className="text-xs text-ink-500">{fmt.shortDate(e.starts_on)}{e.location ? ` · ${e.location}` : ""}{e.category ? ` · ${e.category}` : ""}</p>
                </li>
              ))}
            </ul>
          </section>
        )}

        {full && full.belt_history.length > 0 && (
          <section>
            <h3 className="mb-3 text-xl text-ink-900">🥋 {t("site.judoka.path")}</h3>
            <ol className="flex flex-wrap items-center gap-2">
              {full.belt_history.map((b, i) => (
                <li key={`${b.grade}-${i}`} className="flex items-center gap-2">
                  <span className="rounded-2xl bg-white px-3 py-2 shadow-sm ring-1 ring-ink-100">
                    <BeltBadge code={b.grade} size="sm" />
                    <span className="mt-1 block text-[11px] text-ink-500">{t("site.judoka.beltSince", { date: fmt.shortDate(b.awarded_on) })}</span>
                  </span>
                  {i < full.belt_history.length - 1 && <span className="text-ink-300" aria-hidden="true">→</span>}
                </li>
              ))}
            </ol>
          </section>
        )}

        {full && full.photos.length > 0 && (
          <section>
            <h3 className="mb-3 text-xl text-ink-900">📸 {t("site.judoka.photos")}</h3>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {full.photos.map((ph) => (
                // eslint-disable-next-line @next/next/no-img-element -- foto pubblicata dal club
                <img key={ph.id} src={ph.url} alt={ph.caption ?? ""} loading="lazy" className="aspect-square w-full rounded-2xl object-cover" />
              ))}
            </div>
          </section>
        )}

        {full && full.videos.length > 0 && (
          <section>
            <h3 className="mb-3 text-xl text-ink-900">🎬 {t("site.judoka.videos")}</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              {full.videos.map((v, i) => (
                <div key={v.id} className="aspect-video overflow-hidden rounded-2xl bg-ink-950">
                  <iframe src={`https://www.youtube-nocookie.com/embed/${v.youtube_id}`} title={t("site.judoka.videoOf", { n: i + 1, name: p.display_name })}
                    className="h-full w-full" loading="lazy" allow="encrypted-media; picture-in-picture; fullscreen" allowFullScreen />
                </div>
              ))}
            </div>
          </section>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-ink-100 pt-6">
          {full ? (
            <Link href={`/judocas/${p.id}`} className="inline-flex h-11 items-center rounded-2xl bg-brand-600 px-5 font-semibold text-white shadow-brand hover:bg-brand-700">
              {t("site.rankx.fullPage")} →
            </Link>
          ) : (
            <p className="text-sm text-ink-500">🔒 {t("site.rankx.reducedNote")}</p>
          )}
          {full?.ijf_profile_url && (
            <a href={full.ijf_profile_url} target="_blank" rel="noopener noreferrer" className="text-sm font-semibold text-brand-700 hover:underline">{t("site.judoka.ijfProfile")} ↗</a>
          )}
          <Link href={`/clubes/${p.club.slug}`} className="ml-auto text-sm font-semibold text-ink-600 hover:text-brand-700">{p.club.name} →</Link>
        </div>
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-2xl bg-white/15 px-3 py-3 text-center ring-1 ring-white/20 backdrop-blur">
      <p className="font-display text-2xl leading-none sm:text-3xl">{value}</p>
      <p className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-white/75">{label}</p>
    </div>
  );
}
