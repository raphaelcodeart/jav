"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useGameText } from "@/components/game/i18n";
import { cn } from "@/lib/cn";

// La cornice di ogni gioco: una barra sottile con «torna ai giochi» e il
// bottone ⛶ per lo schermo intero. Lo schermo intero è la Fullscreen API
// sulla pagina (document.documentElement) più il gioco steso su tutta la
// finestra con `fixed inset-0`: così le finestre (Modal), i toast e le scene
// dei combattimenti, che vivono in un portal su <body>, restano visibili
// sopra il gioco. Dove la Fullscreen API non c'è (Safari su iPhone) resta
// solo la sovrapposizione a tutta finestra, che si chiude con ✕ o Esc.

const FrameContext = createContext<{ full: boolean }>({ full: false });

/** Il gioco sa se è a schermo intero (per adattare altezze e barre fisse). */
export function useGameFrame() {
  return useContext(FrameContext);
}

function nativeFullscreen(): boolean {
  return typeof document !== "undefined" && !!document.fullscreenElement;
}

export function GameFrame({ title, icon, onBack, children }: {
  title: string; icon: string; onBack?: () => void; children: ReactNode;
}) {
  const { g } = useGameText();
  const [full, setFull] = useState(false);

  useEffect(() => {
    // Esc o il gesto del sistema chiudono lo schermo intero vero: si
    // chiude anche la sovrapposizione.
    const onChange = () => { if (!nativeFullscreen()) setFull(false); };
    document.addEventListener("fullscreenchange", onChange);
    return () => {
      document.removeEventListener("fullscreenchange", onChange);
      // si esce dal gioco (anche dal suo «indietro»): niente schermo intero orfano
      if (nativeFullscreen()) document.exitFullscreen().catch(() => { /* già uscito */ });
    };
  }, []);

  useEffect(() => {
    if (!full) return;
    const onKey = (e: KeyboardEvent) => {
      // con una finestra aperta Esc chiude prima quella
      if (e.key === "Escape" && !nativeFullscreen() && !document.querySelector("[role=dialog]")) setFull(false);
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [full]);

  function enter() {
    setFull(true);
    const el = document.documentElement;
    if (el.requestFullscreen && !nativeFullscreen()) el.requestFullscreen({ navigationUI: "hide" }).catch(() => { /* resta la sovrapposizione */ });
  }

  function exit() {
    setFull(false);
    if (nativeFullscreen()) document.exitFullscreen().catch(() => { /* già uscito */ });
  }

  return (
    <FrameContext.Provider value={{ full }}>
      <div
        className={cn(
          full
            ? "fixed inset-0 z-[90] overflow-y-auto overscroll-contain bg-gradient-to-b from-indigo-50 via-white to-white px-3 pb-6 [--game-top:3.5rem] sm:px-5"
            : "relative [--game-top:4.75rem]",
        )}
        style={full ? { paddingTop: "max(0.5rem, env(safe-area-inset-top))" } : undefined}
      >
        <div className={cn("flex items-center gap-2", full ? "mx-auto mb-2 max-w-7xl" : "mb-3")}>
          {onBack ? (
            <button type="button" onClick={() => { exit(); onBack(); }}
              className="cursor-pointer rounded-xl px-2 py-1.5 text-sm font-semibold text-brand-700 hover:bg-brand-50">
              ← {g("back")}
            </button>
          ) : null}
          {full && <span className="truncate font-display text-base text-ink-900"><span aria-hidden="true">{icon}</span> {title}</span>}
          <button
            type="button"
            onClick={full ? exit : enter}
            aria-label={full ? g("exitFullscreen") : g("fullscreen")}
            title={full ? g("exitFullscreen") : g("fullscreen")}
            className="ml-auto inline-flex h-10 cursor-pointer items-center gap-2 rounded-xl bg-white px-3 text-sm font-bold text-ink-700 shadow-soft ring-1 ring-ink-200 transition hover:text-brand-700 hover:ring-brand-300"
          >
            <span aria-hidden="true" className="text-lg leading-none">{full ? "✕" : "⛶"}</span>
            <span className="hidden sm:inline">{full ? g("exitFullscreen") : g("fullscreen")}</span>
          </button>
        </div>
        <div className={cn(full && "mx-auto max-w-7xl")}>{children}</div>
      </div>
    </FrameContext.Provider>
  );
}
