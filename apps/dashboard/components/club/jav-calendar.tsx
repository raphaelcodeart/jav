"use client";

import { MotionConfig, motion } from "motion/react";
import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input } from "@/components/ui/field";
import { Pagination, usePaged } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { EVENT_KIND_STYLE, EventIcon } from "@/components/club/event-icon";
import { EventNameButton } from "@/components/club/competition-detail-modal";
import { clubGet } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// Il Calendário JudoArteVida (apps/api/app/domains/club/calendar.py): le
// prove del club e della rete in un periodo scelto, in tre viste (schede,
// lista dettagliata divisa per mesi, tabella) e il PDF da stampare, una
// tabella divisa per mesi senza interruzioni. Per lo staff (`staff`) e per
// atleti e famiglie (`member`).

interface CalEvent {
  id: string; name: string; kind: string; level: string; status: string; starts_on: string; ends_on: string;
  location: string | null; organizer: string | null; age_groups: string[]; description: string | null; image_url: string | null;
  registration_deadline: string; fee_cents: number; club_name: string | null; network: boolean; circular_url: string | null;
}

type View = "cards" | "list" | "table";

function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function presets(): { key: string; from: string; to: string }[] {
  const now = new Date();
  const y = now.getFullYear();
  // La stagione sportiva va da settembre ad agosto.
  const seasonStart = now.getMonth() >= 8 ? y : y - 1;
  return [
    { key: "next3", from: iso(now), to: iso(new Date(y, now.getMonth() + 3, now.getDate())) },
    { key: "season", from: `${seasonStart}-09-01`, to: `${seasonStart + 1}-08-31` },
    { key: "year", from: `${y}-01-01`, to: `${y}-12-31` },
  ];
}

const STATUS_TONE: Record<string, string> = {
  OPEN: "bg-emerald-50 text-emerald-700 ring-emerald-200", CLOSED: "bg-amber-50 text-amber-800 ring-amber-200", DONE: "bg-ink-50 text-ink-600 ring-ink-200",
};

export function JavCalendar({ mode }: { mode: "staff" | "member" }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const initial = presets()[0]!;
  const [from, setFrom] = useState(initial.from);
  const [to, setTo] = useState(initial.to);
  const [view, setView] = useState<View>("list");
  const [downloading, setDownloading] = useState(false);
  // Il flyer è di un mese: quello dell'inizio del periodo, cambiabile.
  const [flyerMonth, setFlyerMonth] = useState(initial.from.slice(0, 7));
  const [flyering, setFlyering] = useState(false);
  const base = mode === "staff" ? "/staff/calendar" : "/calendar";
  const valid = from && to && from <= to;
  const { data, isLoading, error } = useQuery({
    queryKey: ["club", "jav-calendar", mode, from, to],
    queryFn: () => clubGet<CalEvent[]>(`${base}?from=${from}&to=${to}`),
    enabled: !!valid,
  });
  // Le prove a pagine (12 schede, 25 righe), poi divise per mese: le righe
  // dei mesi restano dentro la pagina, con il totale del mese intero.
  const paged = usePaged(data ?? [], view === "cards" ? 12 : 25);
  const top = useRef<HTMLDivElement>(null);
  const monthTotals = useMemo(() => {
    const out: Record<string, number> = {};
    for (const e of data ?? []) out[e.starts_on.slice(0, 7)] = (out[e.starts_on.slice(0, 7)] ?? 0) + 1;
    return out;
  }, [data]);
  const months = useMemo(() => {
    const out: { key: string; label: string; events: CalEvent[] }[] = [];
    for (const e of paged.items) {
      const key = e.starts_on.slice(0, 7);
      let m = out.find((x) => x.key === key);
      if (!m) {
        m = { key, label: fmt.date(new Date(`${key}-15T12:00:00`), { month: "long", year: "numeric" }), events: [] };
        out.push(m);
      }
      m.events.push(e);
    }
    return out;
  }, [paged.items, fmt]);

  async function downloadPdf() {
    setDownloading(true);
    try {
      const res = await fetch(`/api/proxy/club${base}/pdf?from=${from}&to=${to}`);
      if (!res.ok) throw new Error(t("jcal.pdfError"));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `calendario-judoartevida-${from}-${to}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    } finally {
      setDownloading(false);
    }
  }

  async function downloadFlyer() {
    const [y, m] = flyerMonth.split("-");
    if (!y || !m) return;
    setFlyering(true);
    try {
      const res = await fetch(`/api/proxy/club${base}/flyer?year=${Number(y)}&month=${Number(m)}`);
      if (!res.ok) throw new Error(t("jcal.pdfError"));
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `flyer-judoartevida-${flyerMonth}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    } finally {
      setFlyering(false);
    }
  }

  const dates = (e: CalEvent) => e.starts_on === e.ends_on
    ? fmt.date(new Date(`${e.starts_on}T12:00:00`), { weekday: "short", day: "numeric", month: "short" })
    : `${fmt.date(new Date(`${e.starts_on}T12:00:00`), { day: "numeric", month: "short" })} – ${fmt.date(new Date(`${e.ends_on}T12:00:00`), { day: "numeric", month: "short" })}`;
  const ages = (e: CalEvent) => e.age_groups.length ? e.age_groups.map((a) => t.dyn(`site.ev.age.${a}`, a)).join(" · ") : t("jcal.allAges");
  const kindLabel = (e: CalEvent) => e.kind === "COMPETITION" ? t.dyn(`club.level.${e.level}`, e.level) : t.dyn(`jcal.kind.${e.kind}`, e.kind);
  const status = (e: CalEvent) => t.dyn(`jcal.status.${e.status}`, e.status);

  return (
    <MotionConfig reducedMotion="user">
      <div className="space-y-5">
        <div className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-brand-600 via-brand-700 to-ink-950 p-5 text-white shadow-lift sm:p-6">
          <div className="pointer-events-none absolute -right-10 -top-16 h-64 w-64 rounded-full bg-accent-400/30 blur-3xl" aria-hidden="true" />
          <div className="relative flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-accent-200">📅 {t("jcal.eyebrow")}</p>
              <h2 className="font-display text-3xl">{t("clubNav.calendar")} <span className="text-accent-300">JudoArteVida</span></h2>
              <p className="mt-1 text-sm text-white/80">{t("jcal.count", { n: data?.length ?? 0 })}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={downloadPdf} loading={downloading} disabled={!valid} className="bg-white text-ink-900 hover:bg-accent-50">⬇ {t("jcal.download")}</Button>
              <div className="flex items-center gap-1 rounded-2xl bg-white/10 p-1 ring-1 ring-white/25">
                <input type="month" value={flyerMonth} onChange={(e) => setFlyerMonth(e.target.value)} aria-label={t("jcal.flyerMonth")}
                  className="h-10 rounded-xl bg-white px-2 text-sm text-ink-900" />
                <Button onClick={downloadFlyer} loading={flyering} disabled={!flyerMonth} className="bg-accent-400 text-ink-900 hover:bg-accent-300">🎨 {t("jcal.flyer")}</Button>
              </div>
            </div>
          </div>
          <div className="relative mt-5 flex flex-wrap items-end gap-3">
            <Field label={t("jcal.from")}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-44 bg-white text-ink-900" /></Field>
            <Field label={t("jcal.to")}><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-44 bg-white text-ink-900" /></Field>
            <div className="flex flex-wrap gap-2 pb-0.5">
              {presets().map((p) => (
                <button key={p.key} type="button" onClick={() => { setFrom(p.from); setTo(p.to); }}
                  className={cn("h-10 cursor-pointer rounded-full px-4 text-sm font-semibold ring-1", from === p.from && to === p.to ? "bg-accent-400 text-ink-900 ring-accent-300" : "bg-white/10 ring-white/25 hover:bg-white/20")}>
                  {t(`jcal.preset.${p.key}` as "jcal.preset.next3")}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex gap-1.5 rounded-full bg-ink-50 p-1 w-fit">
          {([["cards", "🗂️", t("jcal.viewCards")], ["list", "📋", t("jcal.viewList")], ["table", "🧾", t("jcal.viewTable")]] as const).map(([key, icon, label]) => (
            <button key={key} type="button" onClick={() => setView(key)}
              className={cn("h-10 cursor-pointer rounded-full px-4 text-sm font-semibold", view === key ? "bg-ink-900 text-white shadow" : "text-ink-600 hover:bg-white")}>{icon} {label}</button>
          ))}
        </div>

        {!valid ? <EmptyState title={t("jcal.badRange")} /> : isLoading ? <Skeleton className="h-64" /> : error ? (
          <EmptyState title={t("jcal.loadError")} text={(error as Error).message} />
        ) : months.length === 0 ? <EmptyState icon={<span className="text-3xl">📅</span>} title={t("jcal.empty")} /> : (
          <div ref={top} className="scroll-mt-24 space-y-6">
            {months.map((m) => (
              <section key={m.key}>
                {/* La riga del mese: il calendario continua, mese dopo mese. */}
                <div className="sticky top-0 z-10 mb-3 flex items-center justify-between rounded-2xl bg-gradient-to-r from-brand-600 to-brand-700 px-5 py-2.5 text-white shadow-soft">
                  <h3 className="font-display text-lg uppercase tracking-wide">{m.label}</h3>
                  <span className="rounded-full bg-white/20 px-3 py-0.5 text-xs font-semibold">{t("jcal.count", { n: monthTotals[m.key] ?? m.events.length })}</span>
                </div>
                {view === "cards" && (
                  <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {m.events.map((e, i) => (
                      <motion.li key={e.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }}
                        className="flex flex-col overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/5">
                        <div className={cn("relative h-28 bg-gradient-to-br", EVENT_KIND_STYLE[e.kind]?.bg ?? "from-ink-500 to-ink-800")}>
                          {e.image_url && (
                            // eslint-disable-next-line @next/next/no-img-element -- locandina caricata dal club
                            <img src={e.image_url} alt="" className="absolute inset-0 h-full w-full object-cover" loading="lazy" />
                          )}
                          {!e.image_url && <span className="absolute inset-0 flex items-center justify-center text-6xl opacity-80">{EVENT_KIND_STYLE[e.kind]?.icon}</span>}
                          <span className="absolute left-3 top-3 rounded-xl bg-white/95 px-3 py-1 text-sm font-bold text-ink-900 shadow">{dates(e)}</span>
                        </div>
                        <div className="flex flex-1 flex-col gap-2 p-4">
                          <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">{kindLabel(e)} · {e.network ? t("jcal.network") : e.club_name}</p>
                          <h4 className="font-semibold leading-snug text-ink-900"><EventNameButton id={e.id} name={e.name} mode={mode} /></h4>
                          <p className="text-sm text-ink-500">📍 {e.location ?? "—"}</p>
                          <p className="text-xs text-ink-500">👥 {ages(e)}</p>
                          <span className={cn("mt-auto w-fit rounded-full px-3 py-1 text-xs font-semibold ring-1", STATUS_TONE[e.status])}>{status(e)}</span>
                        </div>
                      </motion.li>
                    ))}
                  </ul>
                )}
                {view === "list" && (
                  <ul className="space-y-2">
                    {m.events.map((e) => (
                      <li key={e.id} className="flex gap-4 rounded-2xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
                        <EventIcon kind={e.kind} imageUrl={e.image_url} size="md" />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-baseline justify-between gap-2">
                            <p className="font-semibold text-ink-900"><EventNameButton id={e.id} name={e.name} mode={mode} /></p>
                            <span className="text-sm font-bold text-brand-700">{dates(e)}</span>
                          </div>
                          <p className="text-sm text-ink-600">📍 {e.location ?? "—"} · {kindLabel(e)} · {e.network ? t("jcal.network") : e.club_name}</p>
                          <p className="text-xs text-ink-500">👥 {ages(e)}{e.organizer ? ` · ${t("jcal.organizer")}: ${e.organizer}` : ""}{e.fee_cents ? ` · ${fmt.euro(e.fee_cents)}` : ""}</p>
                          {e.description && <p className="mt-1 line-clamp-2 text-xs text-ink-500">{e.description}</p>}
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <span className={cn("rounded-full px-3 py-0.5 text-xs font-semibold ring-1", STATUS_TONE[e.status])}>{status(e)}</span>
                            {e.status === "OPEN" && <span className="text-xs text-ink-500">{t("jcal.until", { date: fmt.shortDate(e.registration_deadline) })}</span>}
                            {e.circular_url && <a href={e.circular_url} target="_blank" rel="noopener noreferrer" className="text-xs font-semibold text-brand-700 hover:underline">📄 {t("jcal.circular")}</a>}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
                {view === "table" && (
                  <div className="overflow-x-auto rounded-2xl bg-white shadow-soft ring-1 ring-ink-900/5">
                    <table className="w-full min-w-[720px] text-sm">
                      <thead className="bg-ink-900 text-left text-xs uppercase tracking-wider text-white">
                        <tr>{[t("jcal.colDate"), t("jcal.colEvent"), t("jcal.colPlace"), t("jcal.colStatus"), t("jcal.colAges"), t("jcal.colNotes")].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
                      </thead>
                      <tbody className="divide-y divide-ink-100">
                        {m.events.map((e, i) => (
                          <tr key={e.id} className={i % 2 ? "bg-ink-50/60" : ""}>
                            <td className="whitespace-nowrap px-3 py-2 font-semibold text-ink-900">{dates(e)}</td>
                            <td className="px-3 py-2"><EventNameButton id={e.id} name={e.name} mode={mode} className="font-semibold text-ink-900" /><span className="block text-xs text-ink-500">{EVENT_KIND_STYLE[e.kind]?.icon} {kindLabel(e)}</span></td>
                            <td className="px-3 py-2 text-ink-700">{e.location ?? "—"}</td>
                            <td className="px-3 py-2 text-xs">{status(e)}</td>
                            <td className="px-3 py-2 text-xs text-ink-600">{ages(e)}</td>
                            <td className="px-3 py-2 text-xs text-ink-500">{[e.organizer, e.fee_cents ? fmt.euro(e.fee_cents) : null].filter(Boolean).join(" · ") || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            ))}
            <Pagination page={paged.page} pages={paged.pages} onChange={(p) => { paged.setPage(p); top.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }} />
          </div>
        )}
      </div>
    </MotionConfig>
  );
}
