"use client";

import { Countdown, moment } from "@/components/site/countdown";
import Link from "next/link";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Pagination } from "@/components/ui/pagination";
import { cn } from "@/lib/cn";
import { saveEventsReturn, type EventsReturn } from "@/lib/events-return";
import { useI18n } from "@/lib/i18n/provider";
import type { PublicEvent } from "@/lib/public-site";

// Il calendario degli eventi del sito: tutti gli eventi della rete e dei club,
// da cercare per anno e mese (anche indietro), in lista, in calendario o
// sull'anno intero. Si scarica un anno alla volta (API /public-site/events,
// from/to) e i filtri lavorano nel browser: cercare è immediato. Lo stato sta
// nell'URL, così una ricerca si condivide con un link.

export type View = "list" | "calendar" | "year";
export interface ExplorerState {
  view: View; year: number; month: number; q: string; kind: string; level: string; club: string; age: string;
  open: boolean;
  /** La pagina della lista (da 1); solo nell'area, dove si torna dalla pagina di un evento. */
  page?: number;
}

/** Il link alla pagina di un evento: nell'area porta con sé il modo di
 *  tornare (events-return.ts), sul sito è il link semplice. */
const OpenEvent = createContext<{ query: string; onOpen: () => void } | null>(null);

const API = "/backend/api/public-site/events";
const KINDS = ["COMPETITION", "STAGE", "REFEREEING", "EDUCATION", "MEETING", "OTHER"] as const;
const LEVELS = ["REGIONAL", "ZONAL", "OPENS", "NATIONAL", "EUROPEAN_CUP", "EUROPEAN_CHAMPIONSHIP", "WORLD_CHAMPIONSHIP", "OLYMPIC_GAMES", "CLUB"] as const;
const AGES = ["benj_inf_inic", "juvenis", "cadetes", "juniores", "sub23", "seniores", "veteranos", "adaptado", "katas", "formacao"] as const;
/** Il colore di ogni tipo di evento, lo stesso in lista, calendario e anno. */
const KIND_STYLE: Record<string, { chip: string; dot: string; tile: string }> = {
  COMPETITION: { chip: "bg-brand-500 text-white", dot: "bg-brand-500", tile: "from-brand-500 to-brand-700" },
  STAGE: { chip: "bg-sky-500 text-white", dot: "bg-sky-500", tile: "from-sky-500 to-sky-700" },
  REFEREEING: { chip: "bg-violet-500 text-white", dot: "bg-violet-500", tile: "from-violet-500 to-violet-700" },
  EDUCATION: { chip: "bg-emerald-500 text-white", dot: "bg-emerald-500", tile: "from-emerald-500 to-emerald-700" },
  MEETING: { chip: "bg-amber-500 text-ink-950", dot: "bg-amber-500", tile: "from-amber-400 to-amber-600" },
  OTHER: { chip: "bg-ink-500 text-white", dot: "bg-ink-500", tile: "from-ink-500 to-ink-700" },
};
const style = (kind: string) => KIND_STYLE[kind] ?? KIND_STYLE.OTHER!;

/** "2026-03-07" → la data locale, senza passare dal fuso orario. */
function day(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y!, (m ?? 1) - 1, d ?? 1);
}
function isoOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function norm(s: string): string {
  return s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
}
/** Le settimane del mese, da lunedì: 6 righe da 7 giorni (le date fuori mese comprese). */
function monthGrid(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const offset = (first.getDay() + 6) % 7;
  return Array.from({ length: 42 }, (_, i) => new Date(year, month, 1 - offset + i));
}

async function fetchYear(year: number, club: string, toYear = year): Promise<PublicEvent[]> {
  const q = new URLSearchParams({ from: `${year}-01-01`, to: `${toYear}-12-31`, limit: "500" });
  if (club) q.set("club", club);
  const res = await fetch(`${API}?${q}`);
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

/** `embedded`: dentro l'area riservata (atleti e famiglie): stesso calendario,
 *  ma l'URL della pagina non si tocca e la barra non si attacca sotto
 *  l'header del sito. */
export function EventsExplorer({ initial, initialEvents, clubs, todayIso, embedded = false, returnHref, restored }: {
  initial: ExplorerState; initialEvents?: PublicEvent[]; clubs: { slug: string; name: string }[]; todayIso: string;
  embedded?: boolean;
  /** Nell'area: l'indirizzo della sezione a cui torna il bottone della pagina dell'evento. */
  returnHref?: string;
  /** Dove si era prima di aprire un evento: si riparte da lì. */
  restored?: EventsReturn | null;
}) {
  const { t, fmt } = useI18n();
  const [s, setS] = useState<ExplorerState>(restored?.state ?? initial);
  const [selectedDay, setSelectedDay] = useState<string | null>(restored?.day ?? null);
  // Cambiare vista, anno o filtri riporta la lista alla prima pagina.
  const set = (change: Partial<ExplorerState>) => setS((prev) => ({ ...prev, page: 1, ...change }));
  const today = useMemo(() => day(todayIso), [todayIso]);

  const { data = [], isFetching, isError } = useQuery({
    queryKey: ["site-events", s.year, s.club],
    queryFn: () => fetchYear(s.year, s.club),
    initialData: initialEvents && s.year === initial.year && s.club === initial.club ? initialEvents : undefined,
    staleTime: 60_000,
  });
  // La lista dell'anno in corso arriva fino a dicembre dell'anno dopo: in
  // cima ci sono sempre i prossimi eventi, anche a cavallo d'anno.
  const extended = s.view === "list" && s.year === today.getFullYear();
  const { data: listData } = useQuery({
    queryKey: ["site-events-list", s.year, s.club],
    queryFn: () => fetchYear(s.year, s.club, s.year + 1),
    enabled: extended,
    staleTime: 60_000,
  });

  // La ricerca nell'URL: si condivide e sopravvive a un "indietro".
  useEffect(() => {
    if (embedded) return;
    const q = new URLSearchParams();
    if (s.view !== "list") q.set("view", s.view);
    if (s.year !== today.getFullYear()) q.set("year", String(s.year));
    if (s.view === "calendar") q.set("month", String(s.month + 1));
    for (const key of ["q", "kind", "level", "club", "age"] as const) if (s[key]) q.set(key, s[key]);
    if (s.open) q.set("open", "1");
    const qs = q.toString();
    window.history.replaceState(null, "", qs ? `/eventos?${qs}` : "/eventos");
  }, [s, today, embedded]);

  const source = extended && listData ? listData : data;
  const events = useMemo(() => {
    const needle = norm(s.q.trim());
    return source.filter((e) =>
      (!needle || norm(`${e.name} ${e.location ?? ""} ${e.organizer ?? ""}`).includes(needle))
      && (!s.kind || e.kind === s.kind)
      && (!s.level || (e.kind === "COMPETITION" && e.level === s.level))
      && (!s.age || (e.age_groups ?? []).length === 0 || (e.age_groups ?? []).includes(s.age))
      && (!s.open || (e.status === "OPEN" && e.registration_deadline >= todayIso)),
    );
  }, [source, s.q, s.kind, s.level, s.age, s.open, todayIso]);

  const filtersOn = Boolean(s.q || s.kind || s.level || s.club || s.age || s.open);
  const monthLabel = (y: number, m: number) => fmt.date(new Date(y, m, 1), { month: "long", year: "numeric" });

  function step(delta: number) {
    if (s.view === "calendar") {
      const d = new Date(s.year, s.month + delta, 1);
      set({ year: d.getFullYear(), month: d.getMonth() });
    } else {
      set({ year: s.year + delta });
    }
    setSelectedDay(null);
  }

  // Tornando da un evento: lo scorrimento di prima, appena gli eventi ci
  // sono. La pagina intorno (menu, intestazioni) può crescere ancora un
  // momento: si riprova per un secondo e mezzo, e ci si ferma se chi guarda
  // scorre da sé.
  const scrolled = useRef(false);
  const stopScroll = useRef<(() => void) | null>(null);
  useEffect(() => () => stopScroll.current?.(), []);
  useEffect(() => {
    if (!restored || scrolled.current || events.length === 0) return;
    scrolled.current = true;
    const y = restored.scrollY;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const stop = () => {
      clearTimeout(timer);
      for (const ev of ["wheel", "touchstart", "keydown"]) window.removeEventListener(ev, stop);
    };
    const go = () => {
      window.scrollTo({ top: y });
      if (Math.abs(window.scrollY - y) > 4 && tries++ < 30) timer = setTimeout(go, 50);
      else stop();
    };
    for (const ev of ["wheel", "touchstart", "keydown"]) window.addEventListener(ev, stop, { passive: true });
    stopScroll.current = stop;
    go();
    // Niente pulizia qui: se arrivano altri eventi i tentativi continuano;
    // si fermano da soli, o smontando il calendario.
  }, [restored, events.length]);

  const openEvent = useMemo(() => returnHref ? {
    query: "?from=area",
    onOpen: () => {
      saveEventsReturn({ url: returnHref, state: s, day: selectedDay, scrollY: window.scrollY });
      // Anche il «indietro» del browser torna alla sezione giusta dell'area.
      window.history.replaceState(window.history.state, "", returnHref);
    },
  } : null, [returnHref, s, selectedDay]);

  return (
    <OpenEvent.Provider value={openEvent}>
    <MotionConfig reducedMotion="user">
      <div className="space-y-6">
        {/* --- La barra degli strumenti --- */}
        <div className={cn("z-20 space-y-3", embedded ? "relative" : "sticky top-20 sm:top-24")}>
          <div className="flex flex-wrap items-center gap-3 rounded-3xl bg-gradient-to-r from-brand-600 via-brand-500 to-accent-500 p-2.5 text-white shadow-lift">
            <div className="flex rounded-2xl bg-white/15 p-1 ring-1 ring-white/25" role="tablist" aria-label={t("site.ev.views")}>
              {([["list", "☰", "site.ev.viewList"], ["calendar", "▦", "site.ev.viewCalendar"], ["year", "◫", "site.ev.viewYear"]] as const).map(([v, icon, key]) => (
                <button
                  key={v}
                  type="button"
                  role="tab"
                  aria-selected={s.view === v}
                  onClick={() => { set({ view: v }); setSelectedDay(null); }}
                  className={cn("relative cursor-pointer rounded-xl px-3 py-1.5 text-sm font-semibold transition-colors", s.view === v ? "text-brand-700" : "text-white hover:bg-white/10")}
                >
                  {s.view === v && <motion.span layoutId="ev-view" className="absolute inset-0 rounded-xl bg-white shadow-soft" transition={{ type: "spring", bounce: 0.2, duration: 0.4 }} />}
                  <span className="relative"><span aria-hidden="true" className="mr-1.5">{icon}</span>{t(key)}</span>
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1">
              <button type="button" onClick={() => step(-1)} aria-label={t("site.ev.previous")} className="h-9 w-9 cursor-pointer rounded-full bg-white/15 text-lg ring-1 ring-white/25 hover:bg-white/25">‹</button>
              <span className="min-w-[10rem] text-center font-display text-lg capitalize">
                {s.view === "calendar" ? monthLabel(s.year, s.month) : s.year}
              </span>
              <button type="button" onClick={() => step(1)} aria-label={t("site.ev.next")} className="h-9 w-9 cursor-pointer rounded-full bg-white/15 text-lg ring-1 ring-white/25 hover:bg-white/25">›</button>
              <button
                type="button"
                onClick={() => { set({ year: today.getFullYear(), month: today.getMonth() }); setSelectedDay(s.view === "calendar" ? todayIso : null); }}
                className="ml-1 cursor-pointer rounded-full bg-white px-3 py-1.5 text-xs font-bold text-brand-700 shadow-soft hover:bg-accent-50"
              >
                {t("site.ev.today")}
              </button>
            </div>
            <label className="relative ml-auto min-w-[14rem] flex-1 sm:max-w-sm">
              <span className="sr-only">{t("site.ev.search")}</span>
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true">⌕</span>
              <input
                type="search"
                value={s.q}
                onChange={(e) => set({ q: e.target.value })}
                placeholder={t("site.ev.searchPlaceholder")}
                className="h-10 w-full rounded-2xl bg-white pl-9 pr-3 text-sm text-ink-900 placeholder:text-ink-400 focus:outline-none focus:ring-2 focus:ring-accent-300"
              />
            </label>
          </div>
          <div className="glass-card flex flex-wrap items-center gap-2 rounded-2xl px-3 py-2">
            <FilterSelect label={t("site.filter.kind")} value={s.kind} onChange={(v) => set({ kind: v })}
              options={KINDS.map((k) => [k, t.dyn(`site.kind.${k}`, k)])} all={t("site.filter.all")} />
            <FilterSelect label={t("site.ev.level")} value={s.level} onChange={(v) => set({ level: v })}
              options={LEVELS.map((l) => [l, t.dyn(`club.level.${l}`, l)])} all={t("site.ev.allLevels")} />
            <FilterSelect label={t("site.filter.club")} value={s.club} onChange={(v) => set({ club: v })}
              options={[["rede", `🌍 ${t("site.event.network")}`], ...clubs.map((c) => [c.slug, c.name] as [string, string])]} all={t("site.filter.allClubs")} />
            <FilterSelect label={t("site.ev.ageGroup")} value={s.age} onChange={(v) => set({ age: v })}
              options={AGES.map((a) => [a, t.dyn(`site.ev.age.${a}`, a)])} all={t("site.ev.allAges")} />
            <button
              type="button"
              onClick={() => set({ open: !s.open })}
              aria-pressed={s.open}
              className={cn("cursor-pointer rounded-full px-3 py-1.5 text-xs font-semibold ring-1 transition-colors", s.open ? "bg-emerald-500 text-white ring-emerald-500" : "bg-white text-ink-700 ring-ink-200 hover:ring-emerald-300")}
            >
              ✓ {t("site.ev.openOnly")}
            </button>
            <span className="ml-auto flex items-center gap-2 text-xs font-semibold text-ink-500">
              {isFetching && <span className="h-3 w-3 animate-spin rounded-full border-2 border-brand-300 border-t-transparent" aria-hidden="true" />}
              {t("site.ev.count", { n: events.length })}
              {filtersOn && (
                <button type="button" onClick={() => set({ q: "", kind: "", level: "", club: "", age: "", open: false })} className="cursor-pointer text-brand-600 hover:underline">
                  {t("site.ev.reset")}
                </button>
              )}
            </span>
          </div>
          <Legend t={t} />
        </div>

        {isError && <p className="rounded-2xl bg-rose-50 p-4 text-sm text-rose-700">{t("site.ev.loadError")}</p>}

        <AnimatePresence mode="wait">
          <motion.div key={`${s.view}-${s.year}-${s.view === "calendar" ? s.month : ""}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25 }}>
            {s.view === "list" && <ListView events={events} todayIso={todayIso} page={s.page ?? 1} onPage={(page) => setS((prev) => ({ ...prev, page }))} />}
            {s.view === "calendar" && (
              <CalendarView events={events} year={s.year} month={s.month} todayIso={todayIso}
                selected={selectedDay} onSelect={setSelectedDay} />
            )}
            {s.view === "year" && (
              <YearView events={events} year={s.year} todayIso={todayIso}
                onMonth={(m) => { set({ view: "calendar", month: m }); setSelectedDay(null); }} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </MotionConfig>
    </OpenEvent.Provider>
  );
}

function FilterSelect({ label, value, onChange, options, all }: {
  label: string; value: string; onChange: (v: string) => void; options: [string, string][]; all: string;
}) {
  return (
    <label className={cn("flex items-center gap-1.5 rounded-full py-1 pl-3 pr-1 text-xs ring-1", value ? "bg-brand-50 ring-brand-300" : "bg-white ring-ink-200")}>
      <span className="font-semibold text-ink-500">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="cursor-pointer rounded-full bg-transparent py-0.5 pr-1 text-xs font-semibold text-ink-900 focus:outline-none">
        <option value="">{all}</option>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}

function Legend({ t }: { t: ReturnType<typeof useI18n>["t"] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 px-1 text-xs text-ink-500" aria-hidden="true">
      {KINDS.map((k) => (
        <span key={k} className="inline-flex items-center gap-1.5"><span className={cn("h-2.5 w-2.5 rounded-full", style(k).dot)} />{t.dyn(`site.kind.${k}`, k)}</span>
      ))}
    </div>
  );
}

function Deadline({ e, todayIso }: { e: PublicEvent; todayIso: string }) {
  const { t, fmt } = useI18n();
  if (e.ends_on < todayIso) return <span className="rounded-full bg-ink-100 px-2 py-0.5 text-[11px] font-semibold text-ink-600">{t("site.ev.done")}</span>;
  if (e.status === "OPEN" && e.registration_deadline >= todayIso) {
    return <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200">{t("site.ev.openUntil", { date: fmt.date(day(e.registration_deadline), { day: "numeric", month: "short" }) })}</span>;
  }
  return <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700 ring-1 ring-amber-200">{t("site.ev.closed")}</span>;
}

/** Una riga della lista: tutto ciò che serve per decidere, senza aprire. */
function EventRow({ e, todayIso, index }: { e: PublicEvent; todayIso: string; index: number }) {
  const open = useContext(OpenEvent);
  const { t, fmt } = useI18n();
  const start = day(e.starts_on);
  const end = day(e.ends_on);
  const multi = e.ends_on !== e.starts_on;
  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.4, delay: Math.min(index, 6) * 0.04 }}
      className={cn("glass-card group relative flex gap-4 rounded-3xl p-4 transition-all hover:-translate-y-0.5 hover:shadow-lift", e.ends_on < todayIso && "opacity-80")}
    >
      <div className={cn("flex w-20 shrink-0 flex-col items-center justify-center rounded-2xl bg-gradient-to-br py-2 text-white shadow-soft", style(e.kind).tile)}>
        <span className="text-[11px] font-bold uppercase tracking-widest opacity-90">{fmt.date(start, { weekday: "short" })}</span>
        <span className="font-display text-3xl leading-none">{start.getDate()}</span>
        <span className="text-[11px] font-bold uppercase tracking-widest opacity-90">{fmt.date(start, { month: "short" })}</span>
        {multi && <span className="mt-1 rounded-full bg-white/20 px-2 text-[10px] font-semibold">→ {end.getDate()} {end.getMonth() !== start.getMonth() ? fmt.date(end, { month: "short" }) : ""}</span>}
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-1.5">
          <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-bold", style(e.kind).chip)}>{t.dyn(`site.kind.${e.kind}`, e.kind)}</span>
          {e.kind === "COMPETITION" && e.level !== "CLUB" && <span className="rounded-full bg-ink-100 px-2 py-0.5 text-[11px] font-semibold text-ink-700">{t.dyn(`club.level.${e.level}`, e.level)}</span>}
          <Deadline e={e} todayIso={todayIso} />
        </div>
        <h3 className="text-base leading-snug text-ink-900 sm:text-lg">
          <Link href={`/eventos/${e.id}${open?.query ?? ""}`} onClick={open?.onOpen} className="after:absolute after:inset-0 hover:text-brand-700">{e.name}</Link>
        </h3>
        <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm text-ink-500">
          {e.location && <span>📍 {e.location}</span>}
          {e.starts_at_time && <span>🕘 {e.starts_at_time.slice(0, 5)}</span>}
          {e.organizer && <span className="hidden sm:inline">🏛️ {e.organizer}</span>}
        </p>
        <div className="relative z-10 mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span className="font-semibold text-ink-500">{e.club ? e.club.name : `🌍 ${t("site.event.network")}`}</span>
          {e.entries_count > 0 && <span className="rounded-full bg-brand-50 px-2 py-0.5 font-semibold text-brand-700">👥 {t("site.ev.entries", { n: e.entries_count })}</span>}
          {e.price_cents > 0 && <span className="rounded-full bg-ink-50 px-2 py-0.5 font-semibold text-ink-700">{fmt.euro(e.price_cents)}</span>}
          {(e.age_groups ?? []).slice(0, 4).map((a) => <span key={a} className="rounded-full bg-accent-50 px-2 py-0.5 font-semibold text-accent-800">{t.dyn(`site.ev.age.${a}`, a)}</span>)}
          {e.circular_url && <a href={e.circular_url} target="_blank" rel="noopener" className="rounded-full bg-white px-2 py-0.5 font-semibold text-brand-700 ring-1 ring-brand-200 hover:bg-brand-50">📄 {t("site.ev.circular")}</a>}
        </div>
        {/* Quanto manca: alla chiusura delle iscrizioni se aperte, se no alla gara. */}
        {e.ends_on >= todayIso && (
          <div className="relative z-10 mt-2 flex flex-wrap gap-2">
            {e.status === "OPEN" && e.registration_deadline >= todayIso
              ? <Countdown target={moment(e.registration_deadline, e.registration_deadline_time, "endOfDay")} label={t("countdown.registrations")} />
              : <Countdown target={moment(e.starts_on, e.starts_at_time, "morning")} label={t("countdown.starts")} tone="brand" />}
          </div>
        )}
      </div>
    </motion.article>
  );
}

/** La lista: in cima i **prossimi eventi** (dal più vicino), poi quelli già
 *  fatti (dal più recente), a pagine da 12, con il mese come titolo. */
const PAGE_SIZE = 12;

function ListView({ events, todayIso, page, onPage }: { events: PublicEvent[]; todayIso: string; page: number; onPage: (page: number) => void }) {
  const { t, fmt } = useI18n();
  const ordered = useMemo(() => {
    const next = events.filter((e) => e.ends_on >= todayIso).sort((a, b) => a.starts_on.localeCompare(b.starts_on));
    const past = events.filter((e) => e.ends_on < todayIso).sort((a, b) => b.starts_on.localeCompare(a.starts_on));
    return [...next.map((e) => ({ e, past: false })), ...past.map((e) => ({ e, past: true }))];
  }, [events, todayIso]);
  // La pagina sta nello stato del calendario (si ritrova tornando da un evento).
  const pages = Math.max(1, Math.ceil(ordered.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const paged = { page: current, pages, items: ordered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE) };
  const top = useRef<HTMLDivElement>(null);
  if (events.length === 0) return <Empty text={t("site.ev.none")} />;
  const upcoming = ordered.filter((x) => !x.past).length;

  // Dentro la pagina: un blocco per sezione (prossimi / già fatti) e mese.
  const groups: { key: string; past: boolean; label: string; items: PublicEvent[] }[] = [];
  for (const { e, past } of paged.items) {
    const d = day(e.starts_on);
    const key = `${past ? "p" : "n"}-${d.getFullYear()}-${d.getMonth()}`;
    let g = groups[groups.length - 1];
    if (!g || g.key !== key) {
      g = { key, past, label: fmt.date(new Date(d.getFullYear(), d.getMonth(), 1), { month: "long", year: "numeric" }), items: [] };
      groups.push(g);
    }
    g.items.push(e);
  }
  return (
    <div ref={top} className="scroll-mt-48 space-y-8">
      <p className="flex flex-wrap gap-2 text-sm">
        <span className="rounded-full bg-emerald-50 px-3 py-1 font-semibold text-emerald-800 ring-1 ring-emerald-200">⏭ {t("site.ev.upcomingCount", { n: upcoming })}</span>
        <span className="rounded-full bg-ink-50 px-3 py-1 font-semibold text-ink-600 ring-1 ring-ink-200">✓ {t("site.ev.pastCount", { n: ordered.length - upcoming })}</span>
      </p>
      {groups.map((g, i) => (
        <section key={g.key}>
          {(i === 0 || groups[i - 1]!.past !== g.past) && (
            <p className={cn("mb-3 text-xs font-bold uppercase tracking-[0.2em]", g.past ? "text-ink-400" : "text-emerald-700")}>
              {g.past ? t("site.ev.pastTitle") : t("site.ev.upcomingTitle")}
            </p>
          )}
          <h2 className="mb-3 flex items-baseline gap-3 font-display text-2xl capitalize text-ink-900">
            {g.label}
            <span className="text-sm font-semibold normal-case text-ink-400">{t("site.ev.count", { n: g.items.length })}</span>
          </h2>
          <div className="grid gap-3 lg:grid-cols-2">
            {g.items.map((e, j) => <EventRow key={e.id} e={e} todayIso={todayIso} index={j} />)}
          </div>
        </section>
      ))}
      <Pagination page={paged.page} pages={paged.pages} onChange={(p) => { onPage(p); top.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }} />
    </div>
  );
}

function covering(events: PublicEvent[], iso: string): PublicEvent[] {
  return events.filter((e) => e.starts_on <= iso && e.ends_on >= iso);
}

function CalendarView({ events, year, month, todayIso, selected, onSelect }: {
  events: PublicEvent[]; year: number; month: number; todayIso: string; selected: string | null; onSelect: (d: string | null) => void;
}) {
  const { t, fmt } = useI18n();
  const days = monthGrid(year, month);
  // Sul telefono «segunda, terça…» non ci stanno: l'iniziale.
  const weekdays = days.slice(0, 7).map((d) => ({ short: fmt.date(d, { weekday: "short" }), narrow: fmt.date(d, { weekday: "narrow" }) }));
  const picked = selected ? covering(events, selected) : null;
  // Sotto xl l'elenco sta sotto il calendario, fuori schermo sul telefono:
  // toccando un giorno ci si arriva.
  const listRef = useRef<HTMLElement>(null);
  function pick(iso: string) {
    const next = selected === iso ? null : iso;
    onSelect(next);
    if (next && window.matchMedia("(max-width: 1279px)").matches) {
      requestAnimationFrame(() => listRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  }
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
      <div className="glass-card overflow-hidden rounded-3xl">
        <div className="grid grid-cols-7 bg-ink-900 text-center text-[11px] font-bold uppercase tracking-widest text-white/80">
          {weekdays.map((w) => (
            <div key={w.short} className="py-2">
              <span className="sm:hidden" aria-hidden="true">{w.narrow}</span>
              <span className="hidden sm:inline">{w.short}</span>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {days.map((d) => {
            const iso = isoOf(d);
            const inMonth = d.getMonth() === month;
            const list = covering(events, iso);
            const isToday = iso === todayIso;
            return (
              <button
                key={iso}
                type="button"
                onClick={() => pick(iso)}
                className={cn(
                  "group relative min-h-[4.5rem] cursor-pointer border-b border-r border-ink-900/5 p-1.5 text-left align-top transition-colors sm:min-h-[6.5rem]",
                  inMonth ? "bg-white hover:bg-brand-50/50" : "bg-ink-50/60 text-ink-400",
                  selected === iso && "bg-accent-50 ring-2 ring-inset ring-accent-400",
                )}
                aria-label={`${fmt.date(d, { day: "numeric", month: "long" })}: ${t("site.ev.count", { n: list.length })}`}
              >
                {/* Sul telefono non c'è posto per i nomi: il giorno con eventi
                    si colora (come nella vista anno) e dice quanti sono. */}
                <span className={cn("inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold",
                  isToday ? "bg-brand-500 text-white" : inMonth ? "text-ink-700" : "",
                  !isToday && list.length > 0 && cn("text-white sm:bg-transparent sm:text-ink-700", style(list[0]!.kind).dot))}>{d.getDate()}</span>
                <div className="mt-1 hidden space-y-0.5 sm:block">
                  {list.slice(0, 3).map((e) => (
                    <span key={e.id} className={cn("block truncate rounded-md px-1.5 py-0.5 text-[10px] font-semibold leading-tight", style(e.kind).chip, e.starts_on !== iso && "opacity-80")} title={e.name}>
                      {e.starts_on === iso ? "" : "↳ "}{e.name}
                    </span>
                  ))}
                  {list.length > 3 && <span className="block px-1 text-[10px] font-bold text-ink-500">{t("site.ev.more", { n: list.length - 3 })}</span>}
                </div>
                {list.length > 0 && (
                  <div className="mt-1 flex flex-wrap items-center gap-0.5 sm:hidden">
                    {list.slice(0, 3).map((e) => <span key={e.id} className={cn("h-2 w-2 rounded-full", style(e.kind).dot)} />)}
                    {list.length > 1 && <span className="text-[10px] font-bold leading-none text-ink-600">{list.length}</span>}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>
      <aside ref={listRef} className="scroll-mt-24 space-y-3">
        <h3 className="font-display text-xl capitalize text-ink-900">
          {selected ? fmt.date(day(selected), { weekday: "long", day: "numeric", month: "long" }) : t("site.ev.monthEvents")}
        </h3>
        {(picked ?? events.filter((e) => e.ends_on >= isoOf(new Date(year, month, 1)) && e.starts_on <= isoOf(new Date(year, month + 1, 0))))
          .sort((a, b) => a.starts_on.localeCompare(b.starts_on))
          .map((e, i) => <EventRow key={e.id} e={e} todayIso={todayIso} index={i} />)}
        {picked && picked.length === 0 && <Empty text={t("site.ev.noneDay")} />}
      </aside>
    </div>
  );
}

function YearView({ events, year, todayIso, onMonth }: {
  events: PublicEvent[]; year: number; todayIso: string; onMonth: (m: number) => void;
}) {
  const { t, fmt } = useI18n();
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 12 }, (_, m) => {
        const first = isoOf(new Date(year, m, 1));
        const last = isoOf(new Date(year, m + 1, 0));
        const inMonth = events.filter((e) => e.ends_on >= first && e.starts_on <= last);
        const days = monthGrid(year, m);
        return (
          <motion.button
            key={m}
            type="button"
            onClick={() => onMonth(m)}
            whileHover={{ y: -3 }}
            className="glass-card cursor-pointer rounded-3xl p-4 text-left hover:shadow-lift"
          >
            <div className="mb-2 flex items-baseline justify-between">
              <span className="font-display text-lg capitalize text-ink-900">{fmt.date(new Date(year, m, 1), { month: "long" })}</span>
              <span className={cn("rounded-full px-2 py-0.5 text-xs font-bold", inMonth.length ? "bg-brand-500 text-white" : "bg-ink-100 text-ink-400")}>{inMonth.length}</span>
            </div>
            <div className="grid grid-cols-7 gap-0.5">
              {days.map((d) => {
                const iso = isoOf(d);
                const list = d.getMonth() === m ? covering(events, iso) : [];
                return (
                  <span key={iso} className={cn(
                    "flex aspect-square items-center justify-center rounded text-[9px]",
                    d.getMonth() !== m ? "text-transparent" : list.length ? cn("font-bold text-white", style(list[0]!.kind).dot) : "text-ink-400",
                    iso === todayIso && "ring-2 ring-accent-400",
                  )}>
                    {d.getDate()}
                  </span>
                );
              })}
            </div>
            {inMonth.length > 0 && (
              <p className="mt-2 truncate text-xs text-ink-500">{inMonth.slice(0, 2).map((e) => e.name).join(" · ")}{inMonth.length > 2 ? " …" : ""}</p>
            )}
            {inMonth.length === 0 && <p className="mt-2 text-xs text-ink-400">{t("site.ev.noneMonth")}</p>}
          </motion.button>
        );
      })}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="glass-card flex flex-col items-center gap-2 rounded-3xl p-10 text-center">
      <span className="text-4xl" aria-hidden="true">🥋</span>
      <p className="text-sm text-ink-600">{text}</p>
    </div>
  );
}

