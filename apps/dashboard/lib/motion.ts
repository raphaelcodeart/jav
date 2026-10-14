"use client";

import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void) {
  const mq = window.matchMedia(QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

/** True when the user asked the OS for less motion. Everything that moves
 *  in JS -- the 3D hero, tilt cards, confetti, count-ups -- checks this; the
 *  CSS side is covered by the media query at the bottom of globals.css. */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => false,
  );
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia(QUERY).matches;
}

/** A burst of confetti in the brand colors, for the moments that deserve one
 *  (a payment uploaded, an order placed). Loaded on demand: the library is
 *  never part of the first page load. */
export async function celebrate(origin: { x: number; y: number } = { x: 0.5, y: 0.6 }): Promise<void> {
  if (prefersReducedMotion()) return;
  const confetti = (await import("canvas-confetti")).default;
  const colors = ["#e43f21", "#f9e40f", "#6b696a", "#161515", "#ffffff"];
  confetti({ particleCount: 90, spread: 75, startVelocity: 42, origin, colors, scalar: 1.05 });
  setTimeout(() => confetti({ particleCount: 50, spread: 110, startVelocity: 30, origin, colors, scalar: 0.8 }), 180);
}
