"use client";

import { animate, useInView } from "motion/react";
import { useEffect, useRef } from "react";
import { prefersReducedMotion } from "@/lib/motion";

/** A number that rolls up to its value the first time it scrolls into view
 *  (and rolls again, from where it was, whenever the value changes). The DOM
 *  text is written directly, so a 60fps count costs no React re-renders. */
export function CountUp({
  value, format = (n) => Math.round(n).toLocaleString("it-IT"), duration = 1.1, className,
}: {
  value: number;
  format?: (n: number) => string;
  duration?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const from = useRef(0);
  const inView = useInView(ref, { once: true });

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (!inView || prefersReducedMotion()) {
      node.textContent = format(inView ? value : from.current);
      if (inView) from.current = value;
      return;
    }
    const controls = animate(from.current, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        node.textContent = format(v);
      },
    });
    from.current = value;
    return () => controls.stop();
  }, [value, inView, duration, format]);

  return <span ref={ref} className={className}>{format(0)}</span>;
}

export const formatEuroCents = (cents: number) =>
  (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
