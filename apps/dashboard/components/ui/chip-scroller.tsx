"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";

/** Una fila di pillole (le categorie dello Shop) che scorre di lato: frecce
 *  ‹ › quando c'è altro da vedere, bordi sfumati, e la pillola scelta
 *  (aria-current o aria-pressed) portata in vista all'apertura. Il margine
 *  verticale lascia vedere intero il bordo delle pillole. */
export function ChipScroller({ children, label, className }: { children: ReactNode; label: string; className?: string }) {
  const row = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });

  const measure = useCallback(() => {
    const el = row.current;
    if (!el) return;
    setEdges({ left: el.scrollLeft > 4, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 });
  }, []);

  useEffect(() => {
    const el = row.current;
    if (!el) return;
    const chosen = el.querySelector<HTMLElement>('[aria-current="page"], [aria-pressed="true"]');
    if (chosen && chosen.offsetLeft > el.clientWidth / 2) el.scrollLeft = chosen.offsetLeft - el.clientWidth / 3;
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [measure]);

  const go = (dir: 1 | -1) => row.current?.scrollBy({ left: dir * row.current.clientWidth * 0.75, behavior: "smooth" });
  const arrow = "absolute top-1/2 z-10 flex h-10 w-10 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full bg-white text-xl font-bold text-ink-800 shadow-lift ring-1 ring-ink-900/10 transition hover:bg-brand-600 hover:text-white";

  return (
    <nav aria-label={label} className={cn("relative", className)}>
      {edges.left && (
        <>
          <span className="pointer-events-none absolute inset-y-0 left-0 z-[5] w-14 bg-gradient-to-r from-white to-transparent" aria-hidden="true" />
          <button type="button" onClick={() => go(-1)} className={cn(arrow, "left-0")} aria-label="‹">‹</button>
        </>
      )}
      <div ref={row} onScroll={measure} className="flex gap-2 overflow-x-auto scroll-smooth px-1 py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {children}
      </div>
      {edges.right && (
        <>
          <span className="pointer-events-none absolute inset-y-0 right-0 z-[5] w-14 bg-gradient-to-l from-white to-transparent" aria-hidden="true" />
          <button type="button" onClick={() => go(1)} className={cn(arrow, "right-0")} aria-label="›">›</button>
        </>
      )}
    </nav>
  );
}
