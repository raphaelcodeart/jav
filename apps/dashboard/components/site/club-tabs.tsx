"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface ClubTab {
  id: string;
  label: string;
  icon: ReactNode;
  /** Altri indirizzi che aprono questa scheda ("#mensagem" → Contactos). */
  aliases?: string[];
}

function subscribeHash(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    window.removeEventListener("hashchange", onChange);
    window.removeEventListener("popstate", onChange);
  };
}
const currentHash = () => decodeURIComponent(window.location.hash.replace(/^#/, ""));

/** La pagina del club a schede, come un piccolo sito: una barra di bottoni
 *  grandi che resta in alto, e sotto una scheda alla volta. La scheda sta
 *  nell'indirizzo (#horarios), così un link porta alla scheda giusta e il
 *  tasto "indietro" torna alla precedente. Tutte le schede sono già nella
 *  pagina (le legge anche un motore di ricerca): si nascondono, non si
 *  caricano. */
export function ClubTabs({ tabs, panels, label }: { tabs: ClubTab[]; panels: Record<string, ReactNode>; label: string }) {
  const hash = useSyncExternalStore(subscribeHash, currentHash, () => "");
  const active = tabs.find((t) => t.id === hash || t.aliases?.includes(hash))?.id ?? tabs[0]?.id;

  function open(id: string) {
    if (id !== active) window.history.pushState(null, "", `#${id}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
    // La scheda nuova comincia sotto la barra, non a metà di quella vecchia.
    const bar = document.getElementById("club-tabs");
    if (bar && bar.getBoundingClientRect().top < 0) {
      window.scrollTo({ top: window.scrollY + bar.getBoundingClientRect().top - 72, behavior: "smooth" });
    }
  }

  return (
    <>
      <div id="club-tabs" className="sticky top-20 z-30 border-y border-ink-900/5 bg-white/90 backdrop-blur-md sm:top-24">
        <div role="tablist" aria-label={label} className="mx-auto flex max-w-7xl gap-2 overflow-x-auto px-4 py-3 [scrollbar-width:none] sm:px-6">
          {tabs.map((tab) => {
            const on = tab.id === active;
            return (
              <a
                key={tab.id}
                href={`#${tab.id}`}
                role="tab"
                id={`tab-${tab.id}`}
                aria-selected={on}
                aria-controls={`panel-${tab.id}`}
                onClick={(e) => { e.preventDefault(); open(tab.id); }}
                className={cn(
                  "group flex shrink-0 items-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-semibold transition-all duration-200 motion-reduce:transition-none",
                  "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-club/30",
                  on
                    ? "bg-club text-club-on shadow-lift"
                    : "bg-ink-50 text-ink-700 ring-1 ring-ink-900/5 hover:-translate-y-0.5 hover:bg-white hover:text-club-ink hover:shadow-soft hover:ring-club/40",
                )}
              >
                <span className={cn("flex h-6 w-6 items-center justify-center", on ? "text-club-on" : "text-club-ink")} aria-hidden="true">{tab.icon}</span>
                {tab.label}
              </a>
            );
          })}
        </div>
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`panel-${tab.id}`}
          aria-labelledby={`tab-${tab.id}`}
          hidden={tab.id !== active}
          className="animate-fade-in"
        >
          {panels[tab.id]}
        </div>
      ))}
    </>
  );
}

/** Un bottone che apre un'altra scheda ("Ver horários e preços"). */
export function TabLink({ to, className, children }: { to: string; className?: string; children: ReactNode }) {
  return (
    <a
      href={`#${to}`}
      className={className}
      onClick={(e) => {
        e.preventDefault();
        window.history.pushState(null, "", `#${to}`);
        window.dispatchEvent(new PopStateEvent("popstate"));
        const bar = document.getElementById("club-tabs");
        if (bar) window.scrollTo({ top: window.scrollY + bar.getBoundingClientRect().top - 72, behavior: "smooth" });
      }}
    >
      {children}
    </a>
  );
}
