"use client";

import { animate, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useSyncExternalStore } from "react";
import { useI18n } from "@/lib/i18n/provider";
import type { ScheduleDay } from "@/lib/public-site";

/** Un numero del club che sale da zero quando arriva sullo schermo, una
 *  volta sola. Con "riduci movimento" è subito il numero giusto. Il testo
 *  vero è nel markup dal primo momento (chi legge senza JavaScript, o un
 *  lettore di schermo, non vede mai lo zero). */
export function CountUp({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const reduce = useReducedMotion();
  useEffect(() => {
    const el = ref.current;
    if (!el || !inView || reduce) return;
    const controls = animate(0, value, {
      duration: 1.2,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => { el.textContent = String(Math.round(v)); },
    });
    return () => controls.stop();
  }, [inView, reduce, value]);
  return <span ref={ref}>{value}</span>;
}

type Next = { weekday: number; starts_at: string; ends_at: string; course: string; inDays: number; live: boolean };

/** Ora e giorno a Lisbona: l'orario del club è quello del tatami, non
 *  quello del telefono di chi guarda (magari da Londra o da Roma). */
function lisbonNow(): { weekday: number; minutes: number } {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Lisbon", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(new Date());
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  const weekday = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].indexOf(get("weekday"));
  return { weekday: Math.max(0, weekday), minutes: Number(get("hour")) * 60 + Number(get("minute")) };
}

const toMinutes = (hhmm: string) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));

/** Il prossimo allenamento (o quello in corso) a partire da adesso. */
function nextTraining(schedule: ScheduleDay[]): Next | null {
  const { weekday, minutes } = lisbonNow();
  for (let inDays = 0; inDays < 8; inDays++) {
    const day = (weekday + inDays) % 7;
    const slots = (schedule.find((d) => d.weekday === day)?.slots ?? []).slice().sort((a, b) => a.starts_at.localeCompare(b.starts_at));
    for (const s of slots) {
      if (inDays === 0 && toMinutes(s.ends_at) <= minutes) continue;
      return { weekday: day, starts_at: s.starts_at, ends_at: s.ends_at, course: s.course, inDays, live: inDays === 0 && toMinutes(s.starts_at) <= minutes };
    }
  }
  return null;
}

// L'orologio della pagina: cambia una volta al minuto; sul server non c'è
// (null), così il server non disegna un'ora che il browser smentirebbe.
function subscribeMinute(onChange: () => void): () => void {
  const id = window.setInterval(onChange, 15_000);
  return () => window.clearInterval(id);
}
const currentMinute = () => Math.floor(Date.now() / 60_000);

/** "Hoje às 18:00 · Infantis": il prossimo allenamento, calcolato nel
 *  browser dall'orario del club (che arriva dal gestionale). Si aggiorna
 *  ogni minuto; durante un allenamento dice "a decorrer agora". Prima di
 *  essere calcolato non mostra niente, così server e browser non litigano
 *  sull'ora. */
export function NextTraining({ schedule }: { schedule: ScheduleDay[] }) {
  const { t } = useI18n();
  const minute = useSyncExternalStore(subscribeMinute, currentMinute, () => null);
  const next = minute === null ? null : nextTraining(schedule);
  if (!next) return null;
  const when = next.live
    ? t("site.fan.liveNow")
    : next.inDays === 0 ? t("site.fan.today")
    : next.inDays === 1 ? t("site.fan.tomorrow")
    : t.dyn(`site.weekday.${next.weekday}`, String(next.weekday));
  return (
    <a href="#horario" className="group flex items-center gap-3 rounded-2xl bg-white/95 p-3 pr-4 text-left shadow-soft ring-1 ring-ink-900/5 transition hover:-translate-y-0.5">
      <span className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-club text-club-on" aria-hidden="true">
        {next.live && <span className="absolute inset-0 animate-ping rounded-xl bg-club opacity-40 motion-reduce:animate-none" />}
        <svg viewBox="0 0 24 24" className="relative h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
      </span>
      <span className="min-w-0">
        <span className="block text-[11px] font-bold uppercase tracking-[0.18em] text-club-ink">{t("site.fan.nextTraining")}</span>
        <span className="block truncate text-sm font-semibold text-ink-900">
          {when}{next.live ? "" : ` · ${next.starts_at}`} <span className="font-normal text-ink-500">· {next.course}</span>
        </span>
      </span>
    </a>
  );
}
