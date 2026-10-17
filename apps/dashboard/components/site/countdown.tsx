"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

/** «2026-10-17» + «18:30» (o niente) → l'istante, nell'ora del browser.
 *  Senza ora: la scadenza vale fino alla fine del giorno, l'inizio della gara
 *  alle 9 (l'ora tipica del controllo del peso), così il conto non mente. */
export function moment(dateIso: string, time: string | null | undefined, fallback: "endOfDay" | "morning"): number {
  const [y, m, d] = dateIso.split("-").map(Number) as [number, number, number];
  if (time) {
    const [hh, mm] = time.split(":").map(Number) as [number, number];
    return new Date(y, m - 1, d, hh, mm).getTime();
  }
  return fallback === "endOfDay" ? new Date(y, m - 1, d, 23, 59, 59).getTime() : new Date(y, m - 1, d, 9, 0).getTime();
}

const noop = () => () => {};

/** L'ora che scorre, un secondo alla volta; null sul server (niente conto
 *  diverso tra server e browser). */
function useNow(): number | null {
  const client = useSyncExternalStore(noop, () => true, () => false);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return client ? now : null;
}

function parts(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return { d: Math.floor(s / 86400), h: Math.floor((s % 86400) / 3600), m: Math.floor((s % 3600) / 60), s: s % 60 };
}

/** Il conto alla rovescia: giorni, ore, minuti, secondi.
 *  `size="sm"` per le righe degli elenchi, `"lg"` per la pagina della gara.
 *  `tone`: verde per le iscrizioni, rosso per la gara. Arrivato a zero, sparisce. */
export function Countdown({ target, label, size = "sm", tone = "emerald", className }: {
  target: number; label: string; size?: "sm" | "lg"; tone?: "emerald" | "brand"; className?: string;
}) {
  const { t } = useI18n();
  const now = useNow();
  if (now === null || target <= now) return null;
  const p = parts(target - now);
  const pad = (n: number) => String(n).padStart(2, "0");
  const cells: [string, string][] = [
    [String(p.d), t("countdown.days")], [pad(p.h), t("countdown.hours")], [pad(p.m), t("countdown.minutes")], [pad(p.s), t("countdown.seconds")],
  ];
  const urgent = target - now < 3 * 86_400_000;
  if (size === "sm") {
    return (
      <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold tabular-nums ring-1",
        tone === "emerald"
          ? urgent ? "bg-rose-50 text-rose-700 ring-rose-200" : "bg-emerald-50 text-emerald-800 ring-emerald-200"
          : "bg-brand-50 text-brand-800 ring-brand-200", className)} aria-label={`${label}: ${p.d} ${t("countdown.days")} ${p.h}:${pad(p.m)}:${pad(p.s)}`}>
        <span aria-hidden="true">{tone === "emerald" ? "⏳" : "🥋"}</span>
        <span>{label}</span>
        <span className="font-bold">{p.d}{t("countdown.d")} {pad(p.h)}:{pad(p.m)}:{pad(p.s)}</span>
      </span>
    );
  }
  return (
    <div className={cn("rounded-3xl p-4 text-white shadow-lift",
      tone === "emerald" ? (urgent ? "bg-gradient-to-br from-rose-500 to-rose-700" : "bg-gradient-to-br from-emerald-500 to-teal-700")
        : "bg-gradient-to-br from-brand-500 to-ink-900", className)}>
      <p className="text-xs font-bold uppercase tracking-[0.2em] text-white/85">{label}</p>
      <div className="mt-2 grid grid-cols-4 gap-2" role="timer" aria-live="off">
        {cells.map(([value, unit]) => (
          <div key={unit} className="rounded-2xl bg-white/15 px-1 py-2 text-center ring-1 ring-white/20">
            <span className="block font-display text-3xl leading-none tabular-nums sm:text-4xl">{value}</span>
            <span className="mt-1 block text-[10px] font-semibold uppercase tracking-wider text-white/80">{unit}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
