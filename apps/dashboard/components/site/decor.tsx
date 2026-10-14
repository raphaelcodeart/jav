import type { ReactNode } from "react";

/** I raccordi tra le sezioni del portale: un'onda che porta da un colore di
 *  sfondo al successivo, invece di uno stacco netto. `className` dà il colore
 *  (text-*: l'onda usa currentColor). */
export function WaveDivider({ className = "text-ink-950", flip = false }: { className?: string; flip?: boolean }) {
  return (
    <div className={`relative -mb-px leading-[0] ${flip ? "rotate-180" : ""} ${className}`} aria-hidden="true">
      <svg viewBox="0 0 1440 90" preserveAspectRatio="none" className="block h-12 w-full sm:h-20">
        <path fill="currentColor" d="M0,64 C240,96 480,16 720,40 C960,64 1200,96 1440,48 L1440,90 L0,90 Z" />
        <path fill="currentColor" opacity="0.35" d="M0,40 C260,70 520,0 760,24 C1000,48 1220,80 1440,30 L1440,90 L0,90 Z" />
      </svg>
    </div>
  );
}

/** Una fascia a tutta larghezza con una foto dietro, velata nei colori del
 *  club: separa le sezioni e dà respiro alla pagina. Niente parallasse con
 *  background-attachment: fixed, che su iPhone non funziona e altrove fa
 *  scattare lo scorrimento. */
export function ImageBand({ image, children, tone = "dark" }: { image: string; children: ReactNode; tone?: "dark" | "brand" }) {
  return (
    <section className="relative isolate overflow-hidden">
      {/* eslint-disable-next-line @next/next/no-img-element -- foto decorativa statica */}
      <img src={image} alt="" loading="lazy" className="absolute inset-0 -z-20 h-full w-full object-cover" aria-hidden="true" />
      <div
        className={`absolute inset-0 -z-10 ${tone === "brand"
          ? "bg-gradient-to-br from-brand-700/90 via-brand-600/80 to-ink-950/85"
          : "bg-gradient-to-r from-ink-950/90 via-ink-950/70 to-ink-950/40"}`}
        aria-hidden="true"
      />
      <div className="mx-auto max-w-7xl px-4 py-24 text-white sm:px-6 sm:py-32">{children}</div>
    </section>
  );
}

/** Le parole del judo che scorrono: un nastro tra due sezioni. Si ferma con
 *  "meno movimento" (globals.css). */
export function WordMarquee({ words }: { words: string[] }) {
  const row = [...words, ...words];
  return (
    <div className="relative overflow-hidden border-y border-white/10 bg-brand-600 py-4 text-white" aria-hidden="true">
      <div className="flex w-max gap-10 whitespace-nowrap font-display text-2xl uppercase tracking-[0.2em] animate-marquee sm:text-3xl">
        {row.map((w, i) => (
          <span key={i} className="flex items-center gap-10">
            {w}
            <span className="text-accent-300">✦</span>
          </span>
        ))}
      </div>
    </div>
  );
}
