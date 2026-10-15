"use client";

import { MotionConfig, motion } from "motion/react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface HeroPhoto { url: string; club: string }

/** I colori di ogni pagina: il rosso degli eventi, l'oro del ranking, il blu
 *  dei club. Solo token del tema, niente hex. */
const THEMES = {
  events: { from: "from-brand-700", via: "via-brand-600", to: "to-ink-950", glow: "bg-accent-400/30" },
  ranking: { from: "from-accent-600", via: "via-brand-700", to: "to-ink-950", glow: "bg-accent-300/40" },
  clubs: { from: "from-sky-700", via: "via-brand-700", to: "to-ink-950", glow: "bg-sky-300/30" },
} as const;

/** Le strisce delle cinture, che scorrono piano dietro il titolo. */
const BELTS = ["bg-white", "bg-yellow-400", "bg-orange-500", "bg-green-600", "bg-blue-600", "bg-amber-900", "bg-ink-950"];

/** La testata delle pagine del sito: bassa (non ruba lo schermo alla
 *  pagina), con un collage delle foto che i club hanno già pubblicato, i
 *  colori della pagina e qualche movimento leggero. Con "riduci movimento"
 *  del sistema resta ferma. Senza foto resta il gradiente. */
export function PageHero({ eyebrow, title, text, photos = [], theme = "events", icon, children }: {
  eyebrow: ReactNode; title: ReactNode; text?: ReactNode; photos?: HeroPhoto[];
  theme?: keyof typeof THEMES; icon?: string; children?: ReactNode;
}) {
  const c = THEMES[theme];
  const shown = photos.slice(0, 4);
  return (
    <MotionConfig reducedMotion="user">
      <section className={cn("relative isolate overflow-hidden bg-gradient-to-br text-white", c.from, c.via, c.to)}>
        {/* Le foto, a destra, inclinate: decorazione, non contenuto. */}
        <div className="pointer-events-none absolute inset-y-0 right-0 hidden w-[58%] md:block" aria-hidden="true">
          <div className="absolute inset-0 grid grid-cols-4 gap-2 p-3 [transform:skewX(-8deg)] origin-top">
            {shown.map((p, i) => (
              <motion.div
                key={p.url}
                className="relative overflow-hidden rounded-2xl ring-1 ring-white/15"
                initial={{ opacity: 0, y: i % 2 ? -24 : 24 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.9, delay: 0.15 * i, ease: [0.22, 1, 0.36, 1] }}
              >
                <motion.img
                  src={p.url}
                  alt=""
                  loading="eager"
                  className="h-full w-full object-cover [transform:skewX(8deg)_scale(1.25)]"
                  animate={{ scale: [1.25, 1.35, 1.25] }}
                  transition={{ duration: 18 + i * 3, repeat: Infinity, ease: "easeInOut" }}
                />
              </motion.div>
            ))}
          </div>
          <div className={cn("absolute inset-0 bg-gradient-to-r to-transparent", c.from)} />
        </div>
        {/* Le cinture che scorrono, sotto il titolo. */}
        <div className="pointer-events-none absolute -left-10 bottom-6 flex w-[140%] -rotate-3 flex-col gap-1.5 opacity-20" aria-hidden="true">
          {[0, 1].map((row) => (
            <motion.div
              key={row}
              className="flex gap-1.5"
              animate={{ x: row ? ["-6%", "0%"] : ["0%", "-6%"] }}
              transition={{ duration: 22, repeat: Infinity, repeatType: "mirror", ease: "linear" }}
            >
              {Array.from({ length: 28 }, (_, i) => (
                <span key={i} className={cn("h-2 w-24 shrink-0 rounded-full", BELTS[(i + row * 3) % BELTS.length])} />
              ))}
            </motion.div>
          ))}
        </div>
        <motion.div
          className={cn("pointer-events-none absolute -left-16 -top-24 h-72 w-72 rounded-full blur-3xl", c.glow)}
          animate={{ scale: [1, 1.15, 1], opacity: [0.7, 1, 0.7] }}
          transition={{ duration: 9, repeat: Infinity, ease: "easeInOut" }}
          aria-hidden="true"
        />
        <div className="relative mx-auto max-w-7xl px-4 py-10 sm:px-6 sm:py-12 lg:px-8">
          <motion.p
            className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.22em] text-white/80"
            initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5 }}
          >
            {icon && <span className="text-base" aria-hidden="true">{icon}</span>}{eyebrow}
          </motion.p>
          <motion.h1
            className="max-w-2xl text-3xl leading-tight sm:text-4xl lg:text-5xl"
            initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.05 }}
          >
            {title}
          </motion.h1>
          {text && (
            <motion.p
              className="mt-3 max-w-xl text-base text-white/80 sm:text-lg"
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.12 }}
            >
              {text}
            </motion.p>
          )}
          {children && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.2 }} className="mt-5">
              {children}
            </motion.div>
          )}
        </div>
      </section>
    </MotionConfig>
  );
}

/** Un numero grande con la sua etichetta, nelle testate. */
export function HeroStat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <span className="inline-flex items-baseline gap-2 rounded-full bg-white/12 px-4 py-1.5 ring-1 ring-white/20 backdrop-blur">
      <span className="font-display text-xl">{value}</span>
      <span className="text-xs font-semibold uppercase tracking-wide text-white/75">{label}</span>
    </span>
  );
}
