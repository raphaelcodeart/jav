"use client";

import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { linkButton } from "@/components/site/link-button";

const WIDE = "(min-width: 768px)";

function subscribeWide(onChange: () => void) {
  const query = window.matchMedia(WIDE);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

export interface HeroStat {
  value: number;
  label: string;
}

/** L'header del portale: il video di JudoArteVida a tutto schermo dietro,
 *  e sopra luce e movimento -- un'aurora nei colori del club, una scia di
 *  luce, i cerchi che pulsano come un ippon, il kanji 柔道 che segue il mouse,
 *  il titolo che entra parola per parola.
 *
 *  Il video è il lettore di YouTube incorporato (non si scarica niente), muto
 *  e in loop, solo su schermi grandi e solo se chi guarda non ha chiesto
 *  meno movimento: altrimenti resta la foto, che c'è comunque sotto e
 *  copre il tempo di caricamento. */
export function VideoHero({
  videoId, eyebrow, titleA, titleB, text, ctaPrimary, ctaSecondary, stats, scrollLabel,
}: {
  videoId: string | null;
  eyebrow: string;
  titleA: string;
  titleB: string;
  text: string;
  ctaPrimary: { href: string; label: string };
  ctaSecondary: { href: string; label: string };
  stats: HeroStat[];
  scrollLabel: string;
}) {
  const reduce = useReducedMotion();
  // Il video di sfondo solo da tablet in su: sul telefono costa dati e
  // batteria, e la foto basta.
  const wide = useSyncExternalStore(subscribeWide, () => window.matchMedia(WIDE).matches, () => false);
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const sx = useSpring(mx, { stiffness: 60, damping: 18 });
  const sy = useSpring(my, { stiffness: 60, damping: 18 });
  const kanjiX = useTransform(sx, (v) => v * -40);
  const kanjiY = useTransform(sy, (v) => v * -30);
  const glowX = useTransform(sx, (v) => `${50 + v * 20}%`);
  const glowY = useTransform(sy, (v) => `${40 + v * 20}%`);

  const showVideo = !!videoId && wide && !reduce;
  const words = titleA.split(" ");

  return (
    <section
      className="relative isolate flex min-h-[92vh] items-center overflow-hidden bg-ink-950 text-white"
      onPointerMove={(e) => {
        if (reduce) return;
        const r = e.currentTarget.getBoundingClientRect();
        mx.set((e.clientX - r.left) / r.width - 0.5);
        my.set((e.clientY - r.top) / r.height - 0.5);
      }}
    >
      {/* Sfondo: la foto sempre, il video sopra quando c'è. */}
      <Image src="/site/judo-hero.jpg" alt="" fill priority sizes="100vw" className="-z-30 object-cover opacity-60" />
      {showVideo && <BackgroundVideo videoId={videoId} />}

      {/* Luce e colore. */}
      <div className="absolute inset-0 -z-10 bg-gradient-to-b from-ink-950/70 via-ink-950/40 to-ink-950" aria-hidden="true" />
      <div className="absolute inset-0 -z-10 bg-gradient-to-r from-ink-950/90 via-ink-950/40 to-transparent" aria-hidden="true" />
      <div className="pointer-events-none absolute -left-40 -top-40 -z-10 h-[40rem] w-[40rem] rounded-full bg-brand-600/40 blur-[120px] animate-aurora" aria-hidden="true" />
      <div className="pointer-events-none absolute -bottom-52 right-[-12rem] -z-10 h-[38rem] w-[38rem] rounded-full bg-accent-400/25 blur-[120px] animate-aurora [animation-delay:-6s]" aria-hidden="true" />
      <motion.div
        className="pointer-events-none absolute -z-10 h-[30rem] w-[30rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/10 blur-[90px]"
        style={{ left: glowX, top: glowY }}
        aria-hidden="true"
      />
      <div className="pointer-events-none absolute inset-y-0 left-0 -z-10 w-1/3 bg-gradient-to-r from-transparent via-white/10 to-transparent animate-light-sweep" aria-hidden="true" />

      {/* Il kanji e i cerchi dell'ippon. */}
      <motion.p
        className="pointer-events-none absolute right-[4%] top-1/2 -z-10 -translate-y-1/2 select-none font-display text-[16rem] leading-none text-white/[0.07] sm:text-[24rem]"
        style={{ x: kanjiX, y: kanjiY }}
        aria-hidden="true"
      >
        柔道
      </motion.p>
      <div className="pointer-events-none absolute right-[18%] top-[30%] -z-10 hidden lg:block" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span key={i} className="absolute -left-40 -top-40 h-80 w-80 rounded-full border border-accent-300/40 animate-ring-pulse" style={{ animationDelay: `${i * 1.3}s` }} />
        ))}
      </div>

      <div className="mx-auto w-full max-w-7xl px-4 py-24 sm:px-6">
        <motion.p
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
          className="mb-6 inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-1.5 text-xs font-bold uppercase tracking-[0.25em] text-accent-300 ring-1 ring-white/20 backdrop-blur"
        >
          <span className="h-2 w-2 rounded-full bg-brand-500 animate-pulse-ring" aria-hidden="true" />
          {eyebrow}
        </motion.p>
        <h1 className="max-w-4xl font-display text-5xl leading-[1.02] sm:text-7xl lg:text-8xl">
          {words.map((w, i) => (
            <motion.span key={`${w}-${i}`} className="mr-[0.25em] inline-block"
              initial={{ opacity: 0, y: 40, rotateX: -60 }} animate={{ opacity: 1, y: 0, rotateX: 0 }}
              transition={{ delay: 0.15 + i * 0.12, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}>
              {w}
            </motion.span>
          ))}
          <motion.span className="block bg-gradient-to-r from-brand-400 via-accent-300 to-brand-500 bg-clip-text text-transparent"
            initial={{ opacity: 0, scale: 0.9, filter: "blur(12px)" }} animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
            transition={{ delay: 0.25 + words.length * 0.12, duration: 0.9, ease: [0.22, 1, 0.36, 1] }}>
            {titleB}
          </motion.span>
        </h1>
        <motion.p initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.9, duration: 0.7 }}
          className="mt-8 max-w-2xl text-lg leading-relaxed text-white/80 sm:text-xl">
          {text}
        </motion.p>
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.05, duration: 0.7 }}
          className="mt-10 flex flex-wrap gap-3">
          <Link href={ctaPrimary.href} className={linkButton({ size: "lg" })}>{ctaPrimary.label}</Link>
          <Link href={ctaSecondary.href} className="inline-flex items-center justify-center rounded-2xl px-6 py-3 font-semibold text-white ring-1 ring-white/40 backdrop-blur transition hover:bg-white/10">
            {ctaSecondary.label}
          </Link>
        </motion.div>
        {stats.length > 0 && (
          <motion.dl initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.3, duration: 0.8 }}
            className="mt-16 grid max-w-2xl grid-cols-3 gap-4">
            {stats.map((s) => (
              <div key={s.label} className="rounded-2xl bg-white/[0.06] p-4 ring-1 ring-white/10 backdrop-blur">
                <dd className="font-display text-3xl text-white sm:text-4xl">{s.value}</dd>
                <dt className="mt-1 text-xs uppercase tracking-wider text-white/60">{s.label}</dt>
              </div>
            ))}
          </motion.dl>
        )}
      </div>

      <a href="#tv" className="absolute bottom-6 left-1/2 flex -translate-x-1/2 flex-col items-center gap-2 text-xs uppercase tracking-[0.2em] text-white/60 hover:text-white">
        {scrollLabel}
        <motion.span animate={reduce ? undefined : { y: [0, 8, 0] }} transition={{ repeat: Infinity, duration: 1.6 }} aria-hidden="true">↓</motion.span>
      </a>
    </section>
  );
}

// L'API del lettore YouTube: il minimo che serve qui.
interface YTPlayer { mute(): void; playVideo(): void; destroy(): void }
interface YTNamespace {
  Player: new (el: HTMLElement, options: {
    videoId: string; host?: string; playerVars?: Record<string, number | string>;
    events?: { onReady?: (e: { target: YTPlayer }) => void; onStateChange?: (e: { data: number }) => void };
  }) => YTPlayer;
}
declare global {
  interface Window { YT?: YTNamespace; onYouTubeIframeAPIReady?: () => void }
}

function loadYouTubeApi(): Promise<YTNamespace> {
  return new Promise((resolve) => {
    if (window.YT?.Player) return resolve(window.YT);
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => { previous?.(); if (window.YT) resolve(window.YT); };
    if (!document.querySelector('script[src="https://www.youtube.com/iframe_api"]')) {
      const tag = document.createElement("script");
      tag.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(tag);
    }
  });
}

/** Il video dietro l'header, che compare solo quando sta davvero
 *  girando: finché YouTube carica (o se mostra un avviso, o se il browser
 *  blocca l'autoplay) si vede la foto, mai il riquadro del lettore con loghi
 *  e scritte. */
function BackgroundVideo({ videoId }: { videoId: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    let player: YTPlayer | null = null;
    let cancelled = false;
    void loadYouTubeApi().then((YT) => {
      if (cancelled || !host.current) return;
      player = new YT.Player(host.current, {
        videoId,
        host: "https://www.youtube-nocookie.com",
        playerVars: {
          autoplay: 1, mute: 1, loop: 1, playlist: videoId, controls: 0, modestbranding: 1,
          playsinline: 1, rel: 0, disablekb: 1, iv_load_policy: 3, fs: 0,
        },
        events: {
          onReady: (e) => { e.target.mute(); e.target.playVideo(); },
          onStateChange: (e) => setPlaying(e.data === 1),
        },
      });
    });
    return () => { cancelled = true; player?.destroy(); };
  }, [videoId]);
  return (
    <div className={`pointer-events-none absolute inset-0 -z-20 overflow-hidden transition-opacity duration-1000 ${playing ? "opacity-70" : "opacity-0"}`} aria-hidden="true">
      <div className="absolute left-1/2 top-1/2 h-[56.25vw] min-h-full w-[177.78vh] min-w-full -translate-x-1/2 -translate-y-1/2 [&>iframe]:h-full [&>iframe]:w-full">
        <div ref={host} />
      </div>
    </div>
  );
}
