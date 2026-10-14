"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";

/** Le schede della pagina del club, come quelle di una pagina Facebook:
 *  restano in alto mentre si scorre, e quella della sezione che si sta
 *  leggendo è sottolineata nel colore del club. Sono link ad ancore: senza
 *  JavaScript funzionano lo stesso, manca solo la sottolineatura. */
export function ClubSectionNav({ items, label }: { items: { id: string; label: string }[]; label: string }) {
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    const sections = items.map((i) => document.getElementById(i.id)).filter((el): el is HTMLElement => el !== null);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      // La fascia "letta" è quella sotto la barra e le schede, non tutto lo schermo.
      { rootMargin: "-170px 0px -55% 0px" },
    );
    sections.forEach((s) => observer.observe(s));
    return () => observer.disconnect();
  }, [items]);

  return (
    <nav aria-label={label} className="sticky top-20 z-30 border-b border-ink-900/5 bg-white/90 backdrop-blur-md sm:top-24">
      <ul className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-2 sm:px-4 [scrollbar-width:none]">
        {items.map((item) => (
          <li key={item.id} className="shrink-0">
            <a
              href={`#${item.id}`}
              aria-current={active === item.id ? "location" : undefined}
              className={cn(
                "relative block px-3.5 py-3.5 text-sm font-semibold transition-colors",
                active === item.id ? "text-club-ink" : "text-ink-500 hover:text-ink-900",
              )}
            >
              {item.label}
              <span
                className={cn("absolute inset-x-2 bottom-0 h-[3px] rounded-full bg-club transition-transform duration-300 motion-reduce:transition-none",
                  active === item.id ? "scale-x-100" : "scale-x-0")}
                aria-hidden="true"
              />
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
