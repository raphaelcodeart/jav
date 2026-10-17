"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface JudokaTab {
  id: string;
  label: string;
  icon: string;
  count?: number;
  content: ReactNode;
}

/** Le schede della pagina di un judoca (risultati, prove, biografia, foto,
 *  video, percorso). Il contenuto arriva già reso dal server; qui si sceglie
 *  quale mostrare. L'ancora nell'indirizzo (#fotos) apre la scheda giusta. */
export function JudokaTabs({ tabs, label }: { tabs: JudokaTab[]; label: string }) {
  const [active, setActive] = useState(tabs[0]?.id ?? "");

  useEffect(() => {
    const fromHash = () => {
      const id = window.location.hash.slice(1);
      if (tabs.some((t) => t.id === id)) setActive(id);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, [tabs]);

  const current = tabs.find((t) => t.id === active) ?? tabs[0];

  return (
    <div>
      <div role="tablist" aria-label={label}
        className="sticky top-20 z-20 -mx-4 mb-8 flex gap-2 overflow-x-auto bg-white/90 px-4 py-3 backdrop-blur-md [scrollbar-width:none] sm:top-24 sm:mx-0 sm:rounded-2xl sm:px-2 sm:ring-1 sm:ring-ink-900/5">
        {tabs.map((t) => {
          const on = t.id === current?.id;
          return (
            <button key={t.id} type="button" role="tab" id={`tab-${t.id}`} aria-selected={on} aria-controls={`panel-${t.id}`}
              onClick={() => {
                setActive(t.id);
                history.replaceState(null, "", `#${t.id}`);
              }}
              className={cn(
                "relative inline-flex shrink-0 cursor-pointer items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition",
                on ? "text-white" : "text-ink-600 hover:bg-ink-50 hover:text-ink-900",
              )}>
              {on && <motion.span layoutId="judoka-tab" className="absolute inset-0 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 shadow-brand" transition={{ type: "spring", stiffness: 480, damping: 36 }} />}
              <span className="relative" aria-hidden="true">{t.icon}</span>
              <span className="relative">{t.label}</span>
              {t.count !== undefined && (
                <span className={cn("relative rounded-full px-2 py-0.5 text-[11px] tabular-nums", on ? "bg-white/20" : "bg-ink-100 text-ink-500")}>{t.count}</span>
              )}
            </button>
          );
        })}
      </div>
      <AnimatePresence mode="wait" initial={false}>
        {current && (
          <motion.div key={current.id} role="tabpanel" id={`panel-${current.id}`} aria-labelledby={`tab-${current.id}`}
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }}>
            {current.content}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
