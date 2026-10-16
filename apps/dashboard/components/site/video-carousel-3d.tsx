"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useThirdPartyAllowed } from "@/lib/cookie-consent";
import { ThirdPartyGate } from "@/components/legal/cookie-banner";

export interface ChannelVideo {
  id: string;
  title: string;
  published: string | null;
  thumbnail: string;
  url: string;
}

const CARD_W = 340;
const AUTOPLAY_MS = 3800;

/** Il carosello 3D dei video del canale YouTube: le copertine su un anello
 *  in prospettiva che gira da solo; si ferma quando ci passa sopra il mouse
 *  o il focus, si trascina col dito, si comanda con le frecce. Il video
 *  davanti si apre nel lettore di YouTube, a tutto schermo.
 *
 *  Con "meno movimento" non gira da solo e non anima: resta l'anello fermo
 *  con i pulsanti. */
export function VideoCarousel3D({ videos, labels, locale }: {
  videos: ChannelVideo[];
  labels: { play: string; prev: string; next: string; close: string; watchOnYoutube: string; region: string };
  locale: string;
}) {
  const thirdParty = useThirdPartyAllowed();
  const reduce = useReducedMotion();
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [playing, setPlaying] = useState<ChannelVideo | null>(null);
  const drag = useRef<number | null>(null);
  const n = videos.length;
  const angle = 360 / Math.max(n, 1);
  // Il raggio che fa stare le card affiancate senza sovrapporsi.
  const radius = Math.max(420, Math.round((CARD_W / 2 + 24) / Math.tan(Math.PI / Math.max(n, 3))));
  const front = ((index % n) + n) % n;

  useEffect(() => {
    if (reduce || paused || playing || n < 2) return;
    const timer = window.setInterval(() => setIndex((i) => i + 1), AUTOPLAY_MS);
    return () => window.clearInterval(timer);
  }, [reduce, paused, playing, n]);

  useEffect(() => {
    if (!playing) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setPlaying(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [playing]);

  if (n === 0) return null;
  const current = videos[front]!;
  const go = (delta: number) => setIndex((i) => i + delta);
  // Verso la card cliccata per la via più corta.
  const goTo = (i: number) => {
    let delta = i - front;
    if (delta > n / 2) delta -= n;
    if (delta < -n / 2) delta += n;
    setIndex((x) => x + delta);
  };

  return (
    <div
      className="relative"
      role="region"
      aria-roledescription="carousel"
      aria-label={labels.region}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <div
        className="relative mx-auto h-[300px] select-none outline-none sm:h-[380px] lg:h-[440px]"
        style={{ perspective: "1800px" }}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
          if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
          if (e.key === "Enter") setPlaying(current);
        }}
        onPointerDown={(e) => { drag.current = e.clientX; }}
        onPointerUp={(e) => {
          if (drag.current === null) return;
          const dx = e.clientX - drag.current;
          drag.current = null;
          if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1);
        }}
      >
        <div className="absolute left-1/2 top-1/2 scale-[0.6] sm:scale-[0.8] lg:scale-100" style={{ transformStyle: "preserve-3d" }}>
          <div
            className="relative transition-transform duration-[900ms] ease-[cubic-bezier(0.22,1,0.36,1)]"
            style={{ transformStyle: "preserve-3d", transform: `translateZ(${-radius}px) rotateY(${-index * angle}deg)` }}
          >
            {videos.map((v, i) => {
              let distance = Math.abs(i - front);
              distance = Math.min(distance, n - distance);
              const isFront = i === front;
              return (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => (isFront ? setPlaying(v) : goTo(i))}
                  aria-label={isFront ? `${labels.play}: ${v.title}` : v.title}
                  tabIndex={isFront ? 0 : -1}
                  className="group absolute overflow-hidden rounded-3xl bg-ink-900 shadow-2xl ring-1 ring-white/10 transition-[filter,opacity] duration-700"
                  style={{
                    width: CARD_W, height: Math.round(CARD_W * 0.5625) + 64,
                    left: -CARD_W / 2, top: -(Math.round(CARD_W * 0.5625) + 64) / 2,
                    transform: `rotateY(${i * angle}deg) translateZ(${radius}px)`,
                    filter: isFront ? "none" : `brightness(${Math.max(0.35, 1 - distance * 0.18)}) saturate(${isFront ? 1 : 0.7})`,
                    opacity: distance > 4 ? 0.35 : 1,
                    backfaceVisibility: "hidden",
                  }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {thirdParty ? <img src={v.thumbnail} alt="" loading="lazy" className="aspect-video w-full object-cover" draggable={false} /> : <span className="block aspect-video w-full bg-gradient-to-br from-ink-700 to-ink-950" />}
                  <span className={`absolute left-1/2 top-[38%] flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-brand-500 text-2xl text-white shadow-brand transition ${isFront ? "scale-100 opacity-100" : "scale-75 opacity-0"} group-hover:scale-110`}>
                    ▶
                  </span>
                  <span className="block h-16 px-4 py-2 text-left">
                    <span className="line-clamp-2 text-sm font-semibold leading-snug text-white">{v.title}</span>
                  </span>
                  {isFront && <span className="pointer-events-none absolute inset-0 rounded-3xl ring-2 ring-accent-300/80" aria-hidden="true" />}
                </button>
              );
            })}
          </div>
        </div>
        {/* Il riflesso del pavimento. */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-ink-950 to-transparent" aria-hidden="true" />
      </div>

      <div className="mt-6 flex flex-col items-center gap-4 text-center">
        <AnimatePresence mode="wait">
          <motion.div key={current.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.35 }}>
            <p className="max-w-2xl font-display text-xl text-white sm:text-2xl">{current.title}</p>
            {current.published && (
              <p className="mt-1 text-sm text-white/60">
                {new Date(`${current.published}T12:00:00`).toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" })}
              </p>
            )}
          </motion.div>
        </AnimatePresence>
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => go(-1)} aria-label={labels.prev}
            className="h-12 w-12 rounded-full bg-white/10 text-xl text-white ring-1 ring-white/20 transition hover:bg-white/20 cursor-pointer">‹</button>
          <button type="button" onClick={() => setPlaying(current)}
            className="rounded-full bg-brand-500 px-6 py-3 font-semibold text-white shadow-brand transition hover:bg-brand-600 cursor-pointer">
            ▶ {labels.play}
          </button>
          <button type="button" onClick={() => go(1)} aria-label={labels.next}
            className="h-12 w-12 rounded-full bg-white/10 text-xl text-white ring-1 ring-white/20 transition hover:bg-white/20 cursor-pointer">›</button>
        </div>
        <div className="flex flex-wrap justify-center gap-1.5" aria-hidden="true">
          {videos.map((v, i) => (
            <span key={v.id} className={`h-1.5 rounded-full transition-all ${i === front ? "w-6 bg-accent-300" : "w-1.5 bg-white/30"}`} />
          ))}
        </div>
      </div>

      <AnimatePresence>
        {playing && (
          <motion.div
            className="fixed inset-0 z-[80] flex items-center justify-center bg-ink-950/90 p-4 backdrop-blur"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setPlaying(null)}
            role="dialog" aria-modal="true" aria-label={playing.title}
          >
            <motion.div initial={{ scale: 0.92, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95 }}
              className="w-full max-w-5xl" onClick={(e) => e.stopPropagation()}>
              <div className="relative aspect-video overflow-hidden rounded-3xl bg-black shadow-2xl ring-1 ring-white/10">
                {!thirdParty ? <ThirdPartyGate provider="YouTube" className="absolute inset-0" /> : <iframe
                  src={`https://www.youtube-nocookie.com/embed/${playing.id}?autoplay=1&rel=0&modestbranding=1`}
                  title={playing.title}
                  allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
                  allowFullScreen
                  className="absolute inset-0 h-full w-full"
                />}
              </div>
              <div className="mt-4 flex items-center justify-between gap-4 text-white">
                <p className="font-semibold">{playing.title}</p>
                <div className="flex shrink-0 gap-2">
                  <a href={playing.url} target="_blank" rel="noopener noreferrer" className="rounded-full px-4 py-2 text-sm ring-1 ring-white/30 hover:bg-white/10">{labels.watchOnYoutube} ↗</a>
                  <button type="button" onClick={() => setPlaying(null)} className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-ink-900 cursor-pointer">{labels.close}</button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
