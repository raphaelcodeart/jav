"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { linkButton } from "@/components/site/link-button";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import { usePrefersReducedMotion } from "@/lib/motion";
import type { ClubCard } from "@/lib/public-site";

const INTERVAL_MS = 6000;

/** I club attivi, uno alla volta in grande e tutti insieme in una fila di
 *  schede sotto: chi guarda capisce subito quanti sono e può saltare a
 *  quello che cerca. Scorre da solo, ma si ferma quando il mouse o il
 *  focus ci sono sopra, con il bottone pausa, e non parte affatto con
 *  "riduci movimento" del sistema (WCAG 2.2.2). */
export function ClubCarousel({ clubs }: { clubs: ClubCard[] }) {
  const { t } = useI18n();
  const reduced = usePrefersReducedMotion();
  const [index, setIndex] = useState(0);
  const [hovered, setHovered] = useState(false);
  const [paused, setPaused] = useState(false);
  const count = clubs.length;
  const playing = count > 1 && !reduced && !paused && !hovered;

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => setIndex((i) => (i + 1) % count), INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [playing, count]);

  if (count === 0) return null;
  const current = clubs[index % count] as ClubCard;
  const go = (delta: number) => setIndex((i) => (i + delta + count) % count);

  return (
    <section
      aria-roledescription={t("site.carousel.role")}
      aria-label={t("site.carousel.label")}
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocusCapture={() => setHovered(true)}
      onBlurCapture={() => setHovered(false)}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") go(1);
        if (e.key === "ArrowLeft") go(-1);
      }}
    >
      {/* Prima i club da scegliere, poi la copertina di quello scelto. */}
      {count > 1 && (
        <div className="mb-4 flex gap-3 overflow-x-auto pb-2" role="tablist" aria-label={t("site.carousel.choose")}>
          {clubs.map((club, i) => {
            const active = i === index % count;
            return (
              <button
                key={club.slug}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setIndex(i)}
                className={cn(
                  "relative flex min-w-[12rem] shrink-0 items-center gap-3 overflow-hidden rounded-2xl border px-4 py-3 text-left transition-colors cursor-pointer",
                  active ? "border-brand-300 bg-brand-50" : "border-ink-900/10 bg-white hover:border-brand-200",
                )}
              >
                <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl font-display text-sm", active ? "bg-brand-500 text-white" : "bg-ink-100 text-ink-700")}>
                  {club.logo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element -- logo caricato dal club
                    <img src={club.logo_url} alt="" className="h-full w-full bg-white object-contain p-0.5" />
                  ) : (
                    club.name.slice(0, 1)
                  )}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-ink-900">{club.name}</span>
                  {club.city && <span className="block truncate text-xs text-ink-500">{club.city}</span>}
                </span>
                {active && playing && (
                  <motion.span
                    key={`progress-${index}`}
                    className="absolute bottom-0 left-0 h-0.5 bg-brand-500"
                    initial={{ width: "0%" }}
                    animate={{ width: "100%" }}
                    transition={{ duration: INTERVAL_MS / 1000, ease: "linear" }}
                    aria-hidden="true"
                  />
                )}
              </button>
            );
          })}
        </div>
      )}
      <div className="relative overflow-hidden rounded-[2rem] bg-ink-950 shadow-lift min-h-[26rem] sm:min-h-[30rem]" aria-live={playing ? "off" : "polite"}>
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.div
            key={current.slug}
            role="group"
            aria-roledescription={t("site.carousel.slide")}
            aria-label={t("site.carousel.position", { n: (index % count) + 1, total: count })}
            initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 1.04 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduced ? 0.2 : 0.7, ease: [0.22, 1, 0.36, 1] }}
            className="absolute inset-0"
          >
            {current.hero_image_url ? (
              // eslint-disable-next-line @next/next/no-img-element -- copertina caricata dal club
              <img src={current.hero_image_url} alt="" className="absolute inset-0 h-full w-full object-cover" />
            ) : (
              <TatamiBackdrop />
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-ink-950 via-ink-950/60 to-ink-950/10" aria-hidden="true" />
            <div className="absolute inset-x-0 bottom-0 p-6 sm:p-10">
              <div className="flex items-center gap-4">
                {current.logo_url && (
                  // eslint-disable-next-line @next/next/no-img-element -- logo caricato dal club
                  <img src={current.logo_url} alt="" className="h-16 w-16 rounded-2xl bg-white object-contain p-1.5 shadow-soft sm:h-20 sm:w-20" />
                )}
                <div className="min-w-0">
                  {current.city && <p className="text-xs font-bold uppercase tracking-[0.22em] text-accent-300">{current.city}</p>}
                  <h3 className="text-2xl text-white sm:text-4xl">{current.name}</h3>
                </div>
              </div>
              {current.tagline && <p className="mt-4 max-w-2xl text-base text-white/85 sm:text-lg">{current.tagline}</p>}
              {/* Solo i numeri che ci sono: uno zero non racconta un club. */}
              {(current.athletes_active > 0 || current.judoka_public > 0) && (
                <dl className="mt-5 flex flex-wrap gap-x-8 gap-y-2 text-white">
                  {current.athletes_active > 0 && (
                    <div>
                      <dt className="text-xs uppercase tracking-widest text-white/60">{t("site.carousel.athletes")}</dt>
                      <dd className="font-display text-2xl">{current.athletes_active}</dd>
                    </div>
                  )}
                  {current.judoka_public > 0 && (
                    <div>
                      <dt className="text-xs uppercase tracking-widest text-white/60">{t("site.carousel.judoka")}</dt>
                      <dd className="font-display text-2xl">{current.judoka_public}</dd>
                    </div>
                  )}
                </dl>
              )}
              <div className="mt-6 flex flex-wrap gap-3">
                <Link href={`/clubes/${current.slug}`} className={linkButton({ variant: "primary" })}>{t("site.carousel.visit")}</Link>
                <Link href={`/c/${current.slug}`} className={linkButton({ variant: "light" })}>{t("site.join")}</Link>
              </div>
            </div>
          </motion.div>
        </AnimatePresence>

        {count > 1 && (
          <div className="absolute right-4 top-4 flex gap-2 sm:right-6 sm:top-6">
            <CarouselButton label={t("site.carousel.previous")} onClick={() => go(-1)}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 6l-6 6 6 6" />
            </CarouselButton>
            <CarouselButton label={paused ? t("site.carousel.play") : t("site.carousel.pause")} onClick={() => setPaused((p) => !p)}>
              {paused ? <path strokeLinejoin="round" d="M8 5v14l11-7z" /> : <path strokeLinecap="round" d="M9 6v12M15 6v12" />}
            </CarouselButton>
            <CarouselButton label={t("site.carousel.next")} onClick={() => go(1)}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 6l6 6-6 6" />
            </CarouselButton>
          </div>
        )}
      </div>

    </section>
  );
}

function CarouselButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-white/15 text-white ring-1 ring-inset ring-white/30 backdrop-blur transition-colors hover:bg-white/30 cursor-pointer focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-accent-300/60"
    >
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">{children}</svg>
    </button>
  );
}

/** Quando un club non ha ancora caricato la copertina: un tatami in CSS,
 *  con i colori del marchio, invece di un riquadro vuoto. */
export function TatamiBackdrop({ className }: { className?: string }) {
  return (
    <div className={cn("absolute inset-0 bg-ink-900", className)} aria-hidden="true">
      <div className="absolute inset-0 bg-[repeating-linear-gradient(90deg,rgb(255_255_255/0.04)_0_80px,transparent_80px_160px),repeating-linear-gradient(0deg,rgb(255_255_255/0.04)_0_160px,transparent_160px_320px)]" />
      <div className="absolute -left-20 top-10 h-80 w-80 rounded-full bg-brand-500/50 blur-3xl" />
      <div className="absolute right-0 -top-10 h-72 w-72 rounded-full bg-accent-400/30 blur-3xl" />
    </div>
  );
}
