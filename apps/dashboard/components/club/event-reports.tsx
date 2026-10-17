"use client";

import { MotionConfig, motion } from "motion/react";
import { useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Pagination, usePaged } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { EVENT_KIND_STYLE, EventIcon } from "@/components/club/event-icon";
import { EventNameButton, ResultChip } from "@/components/club/competition-detail-modal";
import { CoachResultsPanel, useStaffEvents } from "@/components/club/coach-results";
import { clubGet, clubSend } from "@/lib/club";
import { cn } from "@/lib/cn";
import { COST_ICONS, COST_KINDS, MEDALS, type CostKind, type EventReport } from "@/lib/competition-staff";
import { useI18n } from "@/lib/i18n/provider";

// I relatórios degli eventi (apps/api/app/domains/club/event_reports.py):
// dopo una gara il treinador racconta com'è andata, mette le spese voce per
// voce e le foto; i risultati degli atleti arrivano da soli dalle
// iscrizioni. La segreteria (`admin`) li vede tutti e ne scarica un PDF
// unico per un mese, un anno o un periodo scelto.

const KEY = ["club", "event-reports"];

export type ProvasView = "events" | "results" | "reports" | "articles";

const VIEW_ICONS: Record<ProvasView, string> = { events: "🗓️", results: "🏅", reports: "📝", articles: "📰" };

/** La barra delle prove: le schermate come pulsanti grandi con la pillola
 *  che scorre (come la barra degli eventi del sito, site/events-explorer),
 *  e la ricerca sempre a portata di pollice. */
export function ProvasBar({ views, value, onChange, q, onQ }: {
  views: ProvasView[]; value: ProvasView; onChange: (v: ProvasView) => void; q?: string; onQ?: (q: string) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-2.5 rounded-3xl bg-gradient-to-r from-brand-600 via-brand-500 to-accent-500 p-2.5 text-white shadow-lift lg:flex-row lg:items-center">
      <div className="grid grid-cols-2 gap-1 rounded-2xl bg-white/15 p-1 ring-1 ring-white/25 sm:flex" role="tablist" aria-label={t("evrep.bar.label")}>
        {views.map((v) => (
          <button key={v} type="button" role="tab" aria-selected={value === v} onClick={() => onChange(v)}
            className={cn("relative flex min-h-14 cursor-pointer items-center gap-2.5 rounded-xl px-3.5 py-2 text-left transition-colors sm:min-w-[9.5rem]",
              value === v ? "text-ink-900" : "text-white hover:bg-white/10")}>
            {value === v && <motion.span layoutId="provas-view" className="absolute inset-0 rounded-xl bg-white shadow-soft" transition={{ type: "spring", bounce: 0.2, duration: 0.4 }} />}
            <span className="relative text-2xl leading-none" aria-hidden="true">{VIEW_ICONS[v]}</span>
            <span className="relative min-w-0">
              <span className="block text-sm font-bold leading-tight">{t(`evrep.view.${v}` as "evrep.view.events")}</span>
              <span className={cn("block truncate text-[11px] leading-tight", value === v ? "text-ink-500" : "text-white/75")}>
                {t(`evrep.view.${v}Sub` as "evrep.view.eventsSub")}
              </span>
            </span>
          </button>
        ))}
      </div>
      {onQ && (
        <label className="relative min-w-0 flex-1 lg:ml-auto lg:max-w-sm">
          <span className="sr-only">{t("evrep.bar.search")}</span>
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true">⌕</span>
          <input type="search" value={q ?? ""} onChange={(e) => onQ(e.target.value)} placeholder={t("evrep.bar.search")}
            className="h-11 w-full rounded-2xl bg-white pl-9 pr-3 text-sm text-ink-900 placeholder:text-ink-400 focus:outline-none focus:ring-2 focus:ring-accent-300" />
        </label>
      )}
    </div>
  );
}

/** La scheda «Provas» dell'area del treinador: i risultati da scrivere, i
 *  suoi relatórios e i relatórios finali, in un posto solo. */
export function CoachEventsPanel() {
  const [view, setView] = useState<ProvasView>("results");
  const [q, setQ] = useState("");
  return (
    <MotionConfig reducedMotion="user">
      <div className="space-y-4">
        <ProvasBar views={["results", "reports", "articles"]} value={view} onChange={setView} q={q} onQ={setQ} />
        <ProvasContent view={view} q={q} />
      </div>
    </MotionConfig>
  );
}

/** Il contenuto di una schermata della barra (anche per la segreteria, che
 *  ha in più gli eventi: club-admin-panel.tsx). */
export function ProvasContent({ view, q, admin = false }: { view: ProvasView; q: string; admin?: boolean }) {
  if (view === "results") return <CoachResultsPanel q={q} />;
  if (view === "reports") return <EventReportsPanel admin={admin} q={q} />;
  if (view === "articles") return <ArticlesPanel q={q} />;
  return null;
}

function matches(r: EventReport, needle: string) {
  if (!needle) return true;
  const text = `${r.title} ${r.competition_name} ${r.author_name} ${r.location ?? ""} ${r.article_title ?? ""} ${r.results.map((x) => x.athlete_name).join(" ")}`;
  return text.toLowerCase().includes(needle);
}

function useReports() {
  return useQuery({ queryKey: KEY, queryFn: () => clubGet<EventReport[]>("/staff/event-reports") });
}

function useArticleAi() {
  const { data } = useQuery({
    queryKey: [...KEY, "ai"], staleTime: 5 * 60_000,
    queryFn: () => clubGet<{ available: boolean }>("/staff/event-reports/ai"),
  });
  return data?.available ?? false;
}

/** Scrive il relatório final dal server (modello o IA) e aggiorna la lista. */
function useGenerateArticle() {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  async function generate(report: EventReport, source: "TEMPLATE" | "AI"): Promise<EventReport | null> {
    setBusy(`${report.id}:${source}`);
    try {
      const r = await clubSend<EventReport>(`/staff/event-reports/${report.id}/article`, "POST", { source });
      queryClient.setQueryData<EventReport[]>(KEY, (old) => old?.map((x) => (x.id === r.id ? r : x)));
      toast({ tone: "success", title: t("evrep.article.generated") });
      return r;
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
      return null;
    } finally {
      setBusy(null);
    }
  }
  return { generate, busy };
}

export function EventReportsPanel({ admin = false, q = "" }: { admin?: boolean; q?: string }) {
  const { t } = useI18n();
  const { data, isLoading, error } = useReports();
  const [article, setArticle] = useState<"" | "with" | "without">("");
  const [author, setAuthor] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<EventReport | null>(null);
  const [reading, setReading] = useState<EventReport | null>(null);
  const authors = useMemo(() => [...new Map((data ?? []).map((r) => [r.author_user_id, r.author_name])).entries()], [data]);
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data ?? []).filter((r) => matches(r, needle)
      && (!article || (article === "with") === !!r.article)
      && (!author || r.author_user_id === author));
  }, [data, q, article, author]);
  const paged = usePaged(filtered, 12);
  const top = useRef<HTMLDivElement>(null);
  const filtersOn = !!(article || author);

  return (
    <MotionConfig reducedMotion="user">
      <div ref={top} className="scroll-mt-24 space-y-4">
        {admin && <ExportBar />}
        <div className="glass-card flex flex-wrap items-center gap-2 rounded-2xl px-3 py-2">
          <FilterSelect label={t("evrep.article.badge")} value={article} onChange={(v) => { setArticle(v as typeof article); paged.setPage(1); }} all={t("evrep.filter.all")}
            options={[["with", t("evrep.filter.withArticle")], ["without", t("evrep.filter.withoutArticle")]]} />
          {admin && authors.length > 1 && (
            <FilterSelect label={t("evrep.filter.author")} value={author} onChange={(v) => { setAuthor(v); paged.setPage(1); }} all={t("evrep.filter.allAuthors")} options={authors} />
          )}
          <span className="flex items-center gap-2 text-xs font-semibold text-ink-500">
            {t("evrep.count", { n: filtered.length })}
            {filtersOn && <button type="button" onClick={() => { setArticle(""); setAuthor(""); }} className="cursor-pointer text-brand-600 hover:underline">{t("evrep.filter.reset")}</button>}
          </span>
          <Button className="ml-auto" size="sm" onClick={() => setCreating(true)} icon={<span>＋</span>}>{t("evrep.list.new")}</Button>
        </div>
        {isLoading ? <Skeleton className="h-64" /> : error ? <EmptyState title={t("evrep.loadError")} text={(error as Error).message} /> : filtered.length === 0 ? (
          <EmptyState icon={<span className="text-3xl">📝</span>} title={q || filtersOn ? t("evrep.list.noMatch") : t("evrep.list.empty")} text={q || filtersOn ? undefined : t("evrep.list.emptyText")}
            action={q || filtersOn ? undefined : <Button onClick={() => setCreating(true)}>{t("evrep.list.new")}</Button>} />
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {paged.items.map((r, i) => <ReportCard key={r.id} report={r} index={i} showAuthor={admin} onOpen={() => setEditing(r)} onRead={() => setReading(r)} />)}
          </ul>
        )}
        <Pagination page={paged.page} pages={paged.pages} onChange={(p) => { paged.setPage(p); top.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }} />
        {creating && <NewReportModal onClose={() => setCreating(false)} onCreated={(r) => { setCreating(false); setEditing(r); }} existing={data ?? []} />}
        {editing && <ReportEditor key={editing.id} report={editing} onClose={() => setEditing(null)} />}
        {reading && <ArticleReader report={(data ?? []).find((x) => x.id === reading.id) ?? reading} onClose={() => setReading(null)}
          onEdit={() => { setEditing(reading); setReading(null); }} />}
      </div>
    </MotionConfig>
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

function medalCount(r: EventReport, p: number) {
  return r.results.filter((x) => x.placement === p).length;
}

function ReportCard({ report: r, index, showAuthor, onOpen, onRead }: {
  report: EventReport; index: number; showAuthor: boolean; onOpen: () => void; onRead: () => void;
}) {
  const { t, fmt } = useI18n();
  const ai = useArticleAi();
  const { generate, busy } = useGenerateArticle();
  const style = EVENT_KIND_STYLE[r.competition_kind] ?? EVENT_KIND_STYLE.OTHER!;
  const medals = [1, 2, 3].map((p) => [p, medalCount(r, p)] as const).filter(([, n]) => n > 0);
  return (
    <motion.li initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(index, 8) * 0.03 }}
      className="flex flex-col overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/5">
      <div className={cn("flex items-center gap-3 bg-gradient-to-br p-4 text-white", style.bg)}>
        <span className="text-3xl" aria-hidden="true">{style.icon}</span>
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wider text-white/80">{fmt.shortDate(r.starts_on)} · {r.location ?? "—"}</p>
          <EventNameButton id={r.competition_id} name={r.competition_name} mode="staff" className="block truncate font-semibold text-white hover:text-white" />
        </div>
      </div>
      <button type="button" onClick={onOpen} className="flex flex-1 cursor-pointer flex-col gap-2 p-4 text-left hover:bg-ink-50/60">
        <h3 className="font-semibold leading-snug text-ink-900">{r.title}</h3>
        {showAuthor && <p className="text-xs text-ink-500">✍️ {r.author_name}</p>}
        {r.narrative && <p className="line-clamp-2 text-sm text-ink-600">{r.narrative}</p>}
        <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-1">
          {medals.map(([p, n]) => <Badge key={p} tone="accent">{MEDALS[p]} {n}</Badge>)}
          <Badge tone="neutral">👥 {r.results.length}</Badge>
          {r.photos.length > 0 && <Badge tone="info">📷 {r.photos.length}</Badge>}
          <span className="ml-auto text-sm font-bold text-ink-900">{fmt.euro(r.total_cents)}</span>
        </div>
      </button>
      <div className="flex flex-wrap items-center gap-2 border-t border-ink-100 bg-ink-50/50 px-4 py-3">
        {r.article ? (
          <>
            <Badge tone="success">📰 {t("evrep.article.badge")}</Badge>
            <Button size="sm" variant="secondary" className="ml-auto" onClick={onRead}>{t("evrep.article.read")}</Button>
          </>
        ) : r.can_edit ? (
          <>
            <Button size="sm" variant="dark" loading={busy === `${r.id}:TEMPLATE`} disabled={!!busy} onClick={() => void generate(r, "TEMPLATE")}>
              📰 {t("evrep.article.generate")}
            </Button>
            <Button size="sm" variant="accent" loading={busy === `${r.id}:AI`} disabled={!ai || !!busy} title={ai ? undefined : t("evrep.article.aiOff")}
              onClick={() => void generate(r, "AI")}>✨ {t("evrep.article.generateAi")}</Button>
          </>
        ) : <span className="text-xs text-ink-400">—</span>}
      </div>
    </motion.li>
  );
}

// --- I relatórios finali ----------------------------------------------------------------------

function ArticlesPanel({ q }: { q: string }) {
  const { t } = useI18n();
  const toast = useToast();
  const { data, isLoading, error } = useReports();
  const [reading, setReading] = useState<string | null>(null);
  const [editing, setEditing] = useState<EventReport | null>(null);
  const [busy, setBusy] = useState(false);
  const needle = q.trim().toLowerCase();
  const articles = useMemo(() => (data ?? []).filter((r) => r.article && (!needle || `${matchText(r)}`.includes(needle))), [data, needle]);
  const paged = usePaged(articles, 9);
  const open = (data ?? []).find((r) => r.id === reading);

  async function download() {
    setBusy(true);
    try {
      const res = await fetch(`/api/proxy/club/staff/event-reports/articles/pdf${needle ? `?q=${encodeURIComponent(q.trim())}` : ""}`);
      if (!res.ok) throw new Error(t("evrep.export.error"));
      const count = Number(res.headers.get("X-Report-Count") ?? "0");
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `relatorios-finais.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast({ tone: "success", title: t("evrep.articles.downloadDone", { n: count }) });
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="glass-card flex flex-wrap items-center gap-2 rounded-2xl px-3 py-2">
        <span className="text-xs font-semibold text-ink-500">{t("evrep.articles.count", { n: articles.length })}</span>
        <Button className="ml-auto" size="sm" variant="dark" loading={busy} disabled={!articles.length} onClick={download}>⬇ {t("evrep.articles.download")}</Button>
      </div>
      {isLoading ? <Skeleton className="h-64" /> : error ? <EmptyState title={t("evrep.loadError")} text={(error as Error).message} /> : articles.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">📰</span>} title={needle ? t("evrep.list.noMatch") : t("evrep.articles.empty")} text={needle ? undefined : t("evrep.articles.emptyText")} />
      ) : (
        <ul className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
          {paged.items.map((r, i) => <ArticleCard key={r.id} report={r} index={i} onOpen={() => setReading(r.id)} />)}
        </ul>
      )}
      <Pagination page={paged.page} pages={paged.pages} onChange={paged.setPage} />
      {open && <ArticleReader report={open} onClose={() => setReading(null)} onEdit={() => { setEditing(open); setReading(null); }} />}
      {editing && <ReportEditor key={editing.id} report={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function matchText(r: EventReport) {
  return `${r.article_title ?? ""} ${r.article ?? ""} ${r.competition_name} ${r.author_name} ${r.location ?? ""}`.toLowerCase();
}

function ArticleCard({ report: r, index, onOpen }: { report: EventReport; index: number; onOpen: () => void }) {
  const { t, fmt } = useI18n();
  const style = EVENT_KIND_STYLE[r.competition_kind] ?? EVENT_KIND_STYLE.OTHER!;
  const cover = r.photos[0]?.url;
  const medals = [1, 2, 3].map((p) => [p, medalCount(r, p)] as const).filter(([, n]) => n > 0);
  return (
    <motion.li initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(index, 8) * 0.03 }}>
      <button type="button" onClick={onOpen} className="group flex h-full w-full cursor-pointer flex-col overflow-hidden rounded-3xl bg-white text-left shadow-soft ring-1 ring-ink-900/5 transition-shadow hover:shadow-lift">
        <div className={cn("relative aspect-[16/9] w-full overflow-hidden bg-gradient-to-br", style.bg)}>
          {cover ? (
            // eslint-disable-next-line @next/next/no-img-element -- URL presigned del bucket privato
            <img src={cover} alt="" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03] motion-reduce:transition-none" loading="lazy" />
          ) : <span className="flex h-full items-center justify-center text-6xl opacity-80" aria-hidden="true">{style.icon}</span>}
          <span className="absolute left-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-ink-800 shadow-soft">
            {fmt.shortDate(r.starts_on)}{r.location ? ` · ${r.location}` : ""}
          </span>
        </div>
        <div className="flex flex-1 flex-col gap-2 p-4">
          <p className="text-[11px] font-bold uppercase tracking-wider text-brand-600">{r.competition_name}</p>
          <h3 className="font-serif text-xl font-bold leading-snug text-ink-950">{r.article_title || r.title}</h3>
          <p className="line-clamp-3 font-serif text-sm leading-relaxed text-ink-600">{r.article}</p>
          <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-2">
            {medals.map(([p, n]) => <Badge key={p} tone="accent">{MEDALS[p]} {n}</Badge>)}
            <span className="ml-auto text-xs text-ink-500">{t("evrep.article.by", { name: r.author_name })}</span>
          </div>
        </div>
      </button>
    </motion.li>
  );
}

/** Il relatório final da leggere, impaginato come una pagina di giornale. */
function ArticleReader({ report: r, onClose, onEdit }: { report: EventReport; onClose: () => void; onEdit: () => void }) {
  const { t, fmt } = useI18n();
  const ai = useArticleAi();
  const { generate, busy } = useGenerateArticle();
  const paragraphs = (r.article ?? "").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  const medals = [1, 2, 3].map((p) => [p, r.results.filter((x) => x.placement === p).map((x) => x.athlete_name)] as const).filter(([, n]) => n.length);
  async function rewrite(source: "TEMPLATE" | "AI") {
    if (r.article_source === "MANUAL" && !window.confirm(t("evrep.article.regenerateConfirm"))) return;
    await generate(r, source);
  }
  return (
    <Modal open onClose={onClose} size="xl" title={r.competition_name}
      subtitle={`${fmt.shortDate(r.starts_on)} · ${r.location ?? "—"}`}
      footer={<>
        {r.can_edit && (
          <>
            <Button variant="ghost" className="mr-auto" loading={busy?.endsWith("TEMPLATE")} disabled={!!busy} onClick={() => void rewrite("TEMPLATE")}>↻ {t("evrep.article.regenerate")}</Button>
            {ai && <Button variant="ghost" loading={busy?.endsWith("AI")} disabled={!!busy} onClick={() => void rewrite("AI")}>✨ {t("evrep.article.generateAi")}</Button>}
            <Button variant="secondary" onClick={onEdit}>✏️ {t("evrep.article.edit")}</Button>
          </>
        )}
        <Button onClick={onClose}>{t("common.close")}</Button>
      </>}>
      <article className="mx-auto max-w-2xl">
        <div className="border-y-2 border-ink-900 py-1 text-center text-[11px] font-bold uppercase tracking-[0.25em] text-ink-700">{t("evrep.article.badge")}</div>
        <h2 className="mt-4 font-serif text-3xl font-bold leading-tight text-ink-950 sm:text-4xl">{r.article_title || r.title}</h2>
        <p className="mt-2 font-serif text-sm italic text-ink-500">
          {t("evrep.article.by", { name: r.author_name })}
          {r.article_source && <> · {t(`evrep.article.source.${r.article_source}` as "evrep.article.source.AI")}</>}
        </p>
        {r.photos[0]?.url && (
          // eslint-disable-next-line @next/next/no-img-element -- URL presigned del bucket privato
          <img src={r.photos[0].url} alt="" className="mt-4 max-h-[22rem] w-full rounded-2xl object-cover" />
        )}
        <div className="mt-5 space-y-4 font-serif text-[1.05rem] leading-relaxed text-ink-800">
          {paragraphs.map((p, i) => <p key={i} className={cn("whitespace-pre-line", i === 0 && "font-semibold text-ink-950")}>{p}</p>)}
        </div>
        {(medals.length > 0 || r.total_cents > 0) && (
          <aside className="mt-6 rounded-2xl border-l-4 border-brand-500 bg-ink-50 p-4 text-sm">
            <p className="mb-1 text-[11px] font-bold uppercase tracking-wider text-brand-600">{t("evrep.editor.results")}</p>
            <p className="text-ink-700">👥 {t("evrep.results.athletes", { n: r.results.length })}</p>
            {medals.map(([p, names]) => <p key={p} className="text-ink-800">{MEDALS[p]} {names.join(", ")}</p>)}
            {r.total_cents > 0 && <p className="mt-1 font-semibold text-ink-900">💶 {fmt.euro(r.total_cents)}</p>}
          </aside>
        )}
        {r.photos.length > 1 && (
          <div className="mt-6">
            <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-ink-500">{t("evrep.article.photos")}</p>
            <div className="grid grid-cols-3 gap-2">
              {r.photos.slice(1).map((p) => p.url && (
                <a key={p.id} href={p.url} target="_blank" rel="noopener noreferrer" className="block aspect-square overflow-hidden rounded-xl bg-ink-100">
                  {/* eslint-disable-next-line @next/next/no-img-element -- URL presigned del bucket privato */}
                  <img src={p.url} alt="" className="h-full w-full object-cover" loading="lazy" />
                </a>
              ))}
            </div>
          </div>
        )}
      </article>
    </Modal>
  );
}

// --- Il PDF della segreteria -------------------------------------------------------------------

function pad(n: number) {
  return String(n).padStart(2, "0");
}

function ExportBar() {
  const { t } = useI18n();
  const toast = useToast();
  const now = new Date();
  const [mode, setMode] = useState<"month" | "year" | "range">("month");
  const [month, setMonth] = useState(`${now.getFullYear()}-${pad(now.getMonth() + 1)}`);
  const [year, setYear] = useState(String(now.getFullYear()));
  const [from, setFrom] = useState(`${now.getFullYear()}-01-01`);
  const [to, setTo] = useState(`${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`);
  const [busy, setBusy] = useState(false);

  function period(): [string, string] | null {
    if (mode === "month") {
      const [y, m] = month.split("-").map(Number);
      if (!y || !m) return null;
      return [`${y}-${pad(m)}-01`, `${y}-${pad(m)}-${pad(new Date(y, m, 0).getDate())}`];
    }
    if (mode === "year") return /^\d{4}$/.test(year) ? [`${year}-01-01`, `${year}-12-31`] : null;
    return from && to && from <= to ? [from, to] : null;
  }

  async function download() {
    const p = period();
    if (!p) return;
    setBusy(true);
    try {
      const res = await fetch(`/api/proxy/club/admin/event-reports/pdf?from=${p[0]}&to=${p[1]}`);
      if (!res.ok) throw new Error(t("evrep.export.error"));
      const count = Number(res.headers.get("X-Report-Count") ?? "0");
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `relatorios-${p[0]}-${p[1]}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast({ tone: count ? "success" : "info", title: count ? t("evrep.export.done", { n: count }) : t("evrep.export.none") });
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-accent-300 via-accent-400 to-amber-600 p-5 text-ink-950 shadow-lift">
      <div className="pointer-events-none absolute -right-10 -top-14 h-48 w-48 rounded-full bg-white/30 blur-3xl" aria-hidden="true" />
      <div className="relative">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-ink-900/70">📄 {t("evrep.export.eyebrow")}</p>
        <h2 className="font-display text-2xl">{t("evrep.export.title")}</h2>
        <p className="mt-1 text-sm text-ink-900/75">{t("evrep.export.text")}</p>
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <div className="flex gap-1 rounded-full bg-white/40 p-1">
            {(["month", "year", "range"] as const).map((m) => (
              <button key={m} type="button" onClick={() => setMode(m)}
                className={cn("h-9 cursor-pointer rounded-full px-4 text-sm font-semibold", mode === m ? "bg-ink-900 text-white" : "text-ink-900 hover:bg-white/60")}>
                {t(`evrep.export.mode.${m}` as "evrep.export.mode.month")}
              </button>
            ))}
          </div>
          {mode === "month" && <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="h-11 w-44 bg-white" aria-label={t("evrep.export.mode.month")} />}
          {mode === "year" && <Input inputMode="numeric" value={year} maxLength={4} onChange={(e) => setYear(e.target.value.replace(/\D/g, ""))} className="h-11 w-28 bg-white" aria-label={t("evrep.export.mode.year")} />}
          {mode === "range" && (
            <>
              <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-11 w-40 bg-white" aria-label={t("evrep.export.from")} />
              <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-11 w-40 bg-white" aria-label={t("evrep.export.to")} />
            </>
          )}
          <Button variant="dark" onClick={download} loading={busy} disabled={!period()}>⬇ {t("evrep.export.download")}</Button>
        </div>
      </div>
    </div>
  );
}

// --- Nuovo relatório ---------------------------------------------------------------------------

function NewReportModal({ onClose, onCreated, existing }: { onClose: () => void; onCreated: (r: EventReport) => void; existing: EventReport[] }) {
  const { t, fmt } = useI18n();
  const [when, setWhen] = useState<"past" | "upcoming">("past");
  const [q, setQ] = useState("");
  const [onlyDone, setOnlyDone] = useState(true);
  const { data, isLoading } = useStaffEvents(when);
  const today = new Date().toISOString().slice(0, 10);
  const needle = q.trim().toLowerCase();
  const events = (data ?? []).filter((e) => (!needle || `${e.name} ${e.location ?? ""}`.toLowerCase().includes(needle))
    && (!onlyDone || (e.entries_count > 0 && e.ends_on < today)));
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();
  const queryClient = useQueryClient();
  const mine = new Set(existing.map((r) => r.competition_id));

  async function create(competitionId: string) {
    setBusy(competitionId);
    try {
      const report = await clubSend<EventReport>("/staff/event-reports", "POST", { competition_id: competitionId });
      await queryClient.invalidateQueries({ queryKey: KEY });
      onCreated(report);
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal open onClose={onClose} size="lg" title={t("evrep.new.title")} subtitle={t("evrep.new.subtitle")}
      footer={<Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>}>
      <div className="space-y-3">
        <label className="relative block">
          <span className="sr-only">{t("evrep.new.search")}</span>
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true">⌕</span>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("evrep.new.search")} autoFocus
            className="h-11 w-full rounded-2xl bg-white pl-9 pr-3 text-sm text-ink-900 ring-1 ring-ink-200 placeholder:text-ink-400 focus:outline-none focus:ring-2 focus:ring-brand-300" />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex w-fit gap-1 rounded-full bg-ink-50 p-1">
            {(["past", "upcoming"] as const).map((w) => (
              <button key={w} type="button" onClick={() => { setWhen(w); if (w === "upcoming") setOnlyDone(false); }}
                className={cn("h-9 cursor-pointer rounded-full px-4 text-sm font-semibold", when === w ? "bg-ink-900 text-white" : "text-ink-600 hover:bg-white")}>
                {w === "past" ? t("evrep.results.past") : t("evrep.results.upcoming")}
              </button>
            ))}
          </div>
          <button type="button" onClick={() => setOnlyDone((v) => !v)} aria-pressed={onlyDone}
            className={cn("h-9 cursor-pointer rounded-full px-3.5 text-xs font-semibold ring-1 transition-colors", onlyDone ? "bg-emerald-500 text-white ring-emerald-500" : "bg-white text-ink-700 ring-ink-200 hover:ring-emerald-300")}>
            ✓ {t("evrep.new.onlyDone")}
          </button>
        </div>
        {isLoading ? <Skeleton className="h-48" /> : !events.length ? <p className="py-6 text-center text-sm text-ink-500">{data?.length ? t("evrep.new.noMatch") : t("evrep.results.empty")}</p> : (
          <ul className="max-h-[55vh] space-y-2 overflow-y-auto pr-1">
            {events.map((e) => (
              <li key={e.id}>
                <button type="button" disabled={!!busy} onClick={() => void create(e.id)}
                  className="flex w-full cursor-pointer items-center gap-3 rounded-2xl bg-white p-3 text-left ring-1 ring-ink-100 hover:ring-brand-300 disabled:opacity-60">
                  <EventIcon kind={e.kind} imageUrl={e.image_url} size="md" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold text-ink-900">{e.name}</span>
                    <span className="block text-xs text-ink-500">{fmt.shortDate(e.starts_on)} · {t("evrep.results.athletes", { n: e.entries_count })}</span>
                  </span>
                  {mine.has(e.id) ? <Badge tone="success">✓ {t("evrep.new.hasReport")}</Badge> : busy === e.id ? <span className="text-xs text-ink-400">…</span> : <span className="text-xl text-ink-300" aria-hidden="true">＋</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  );
}

// --- L'editor ----------------------------------------------------------------------------------

type CostDraft = Record<CostKind, { amount: string; note: string }>;

function toDraft(r: EventReport): CostDraft {
  const out = {} as CostDraft;
  for (const k of COST_KINDS) {
    const c = r.costs.find((x) => x.kind === k);
    out[k] = { amount: c && c.amount_cents ? (c.amount_cents / 100).toFixed(2).replace(".", ",") : "", note: c?.note ?? "" };
  }
  return out;
}

/** "12,50" o "12.5" → 1250 centesimi; null se non è un importo. */
function toCents(s: string): number | null {
  const clean = s.trim().replace(/\s/g, "").replace(",", ".");
  if (!clean) return 0;
  if (!/^\d+(\.\d{0,2})?$/.test(clean)) return null;
  return Math.round(Number(clean) * 100);
}

function ReportEditor({ report, onClose }: { report: EventReport; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [current, setCurrent] = useState(report);
  const [title, setTitle] = useState(report.title);
  const [description, setDescription] = useState(report.description ?? "");
  const [narrative, setNarrative] = useState(report.narrative ?? "");
  const [costs, setCosts] = useState<CostDraft>(() => toDraft(report));
  const [articleTitle, setArticleTitle] = useState(report.article_title ?? "");
  const [article, setArticle] = useState(report.article ?? "");
  const [busy, setBusy] = useState<"save" | "photo" | "delete" | "TEMPLATE" | "AI" | null>(null);
  const ai = useArticleAi();
  const fileRef = useRef<HTMLInputElement>(null);
  const editable = report.can_edit;
  const cents = COST_KINDS.map((k) => toCents(costs[k].amount));
  const invalid = cents.some((c) => c === null);
  const total = cents.reduce<number>((s, c) => s + (c ?? 0), 0);

  function refresh(r: EventReport) {
    setCurrent(r);
    queryClient.setQueryData<EventReport[]>(KEY, (old) => old?.map((x) => (x.id === r.id ? r : x)));
  }

  function persist() {
    return clubSend<EventReport>(`/staff/event-reports/${report.id}`, "PATCH", {
      title: title.trim(), description, narrative, article_title: articleTitle, article,
      costs: COST_KINDS.map((k, i) => ({ kind: k, amount_cents: cents[i] ?? 0, note: costs[k].note.trim() || null })),
    });
  }

  async function save() {
    if (invalid || title.trim().length < 3) return;
    setBusy("save");
    try {
      refresh(await persist());
      toast({ tone: "success", title: t("evrep.editor.saved") });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  /** Il relatório final si scrive dai dati salvati: prima si salva quello
   *  che c'è sullo schermo, poi lo si fa scrivere al server. */
  async function writeArticle(source: "TEMPLATE" | "AI") {
    if (invalid || title.trim().length < 3) return;
    if (current.article_source === "MANUAL" && !window.confirm(t("evrep.article.regenerateConfirm"))) return;
    setBusy(source);
    try {
      await persist();
      const r = await clubSend<EventReport>(`/staff/event-reports/${report.id}/article`, "POST", { source });
      refresh(r);
      setArticleTitle(r.article_title ?? "");
      setArticle(r.article ?? "");
      toast({ tone: "success", title: t("evrep.article.generated") });
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy("photo");
    try {
      for (const file of Array.from(files)) {
        const body = new FormData();
        body.append("file", file);
        refresh(await clubSend<EventReport>(`/staff/event-reports/${report.id}/photos`, "POST", body));
      }
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function removePhoto(id: string) {
    try {
      refresh(await clubSend<EventReport>(`/staff/event-reports/${report.id}/photos/${id}`, "DELETE"));
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    }
  }

  async function remove() {
    if (!window.confirm(t("evrep.editor.deleteConfirm"))) return;
    setBusy("delete");
    try {
      await clubSend(`/staff/event-reports/${report.id}`, "DELETE");
      await queryClient.invalidateQueries({ queryKey: KEY });
      toast({ tone: "success", title: t("evrep.editor.deleted") });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
      setBusy(null);
    }
  }

  return (
    <Modal open onClose={onClose} size="xl" title={current.competition_name}
      subtitle={`${fmt.shortDate(current.starts_on)} · ${current.location ?? "—"} · ✍️ ${current.author_name}`}
      footer={<>
        {editable && <Button variant="ghost" className="mr-auto text-rose-700" loading={busy === "delete"} onClick={remove}>🗑 {t("evrep.editor.delete")}</Button>}
        <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
        {editable && <Button loading={busy === "save"} disabled={invalid || title.trim().length < 3} onClick={save}>{t("common.save")}</Button>}
      </>}>
      <div className="space-y-6">
        <section className="space-y-3">
          <Field label={t("evrep.editor.reportTitle")} htmlFor="er-title">
            <Input id="er-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} disabled={!editable} />
          </Field>
          <Field label={t("evrep.editor.description")} hint={t("evrep.editor.descriptionHint")} htmlFor="er-desc">
            <Textarea id="er-desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={3} maxLength={4000} disabled={!editable} />
          </Field>
        </section>

        <section>
          <SectionTitle icon="🏅" title={t("evrep.editor.results")} hint={t("evrep.editor.resultsHint")} />
          {current.results.length === 0 ? <p className="text-sm text-ink-500">{t("evrep.detail.noAthletes")}</p> : (
            <ul className="divide-y divide-ink-100 rounded-2xl bg-white ring-1 ring-ink-100">
              {current.results.map((x) => (
                <li key={x.athlete_id} className="flex flex-wrap items-center gap-2 px-3 py-2.5">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-ink-900">{x.athlete_name}</span>
                    <span className="block text-xs text-ink-500">{[x.category, x.weight_kg ? `${Number(x.weight_kg)} kg` : null, x.result_notes].filter(Boolean).join(" · ") || "—"}</span>
                  </span>
                  {x.placement == null ? <span className="text-xs text-ink-400">{t("evrep.editor.noResult")}</span> : <ResultChip placement={x.placement} rank={x.rank} />}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <SectionTitle icon="💶" title={t("evrep.editor.costs")} hint={t("evrep.editor.costsHint")} />
          <div className="space-y-2">
            {COST_KINDS.map((k, i) => (
              <div key={k} className="grid grid-cols-[1fr_7.5rem] items-center gap-2 rounded-2xl bg-white p-2.5 ring-1 ring-ink-100 sm:grid-cols-[11rem_7.5rem_1fr]">
                <span className="text-sm font-semibold text-ink-900"><span aria-hidden="true">{COST_ICONS[k]}</span> {t(`evrep.cost.${k}` as "evrep.cost.HOTEL")}</span>
                <div className="relative">
                  <Input inputMode="decimal" value={costs[k].amount} placeholder="0,00" disabled={!editable} aria-label={t("evrep.editor.amount")}
                    onChange={(e) => setCosts((c) => ({ ...c, [k]: { ...c[k], amount: e.target.value } }))}
                    className={cn("h-10 pr-7 text-right", cents[i] === null && "ring-2 ring-rose-400")} />
                  <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-sm text-ink-400">€</span>
                </div>
                <Input value={costs[k].note} maxLength={300} placeholder={t("evrep.editor.notePh")} disabled={!editable} aria-label={t("evrep.editor.note")}
                  onChange={(e) => setCosts((c) => ({ ...c, [k]: { ...c[k], note: e.target.value } }))} className="col-span-2 h-10 sm:col-span-1" />
              </div>
            ))}
            <div className="flex items-center justify-between rounded-2xl bg-accent-100 px-4 py-3 ring-1 ring-accent-300">
              <span className="text-sm font-bold uppercase tracking-wide text-ink-800">{t("evrep.editor.total")}</span>
              <span className="font-display text-xl text-ink-950">{fmt.euro(total)}</span>
            </div>
            {invalid && <p className="text-xs text-rose-700">{t("evrep.editor.badAmount")}</p>}
          </div>
        </section>

        <section>
          <SectionTitle icon="💬" title={t("evrep.editor.narrative")} hint={t("evrep.editor.narrativeHint")} />
          <Textarea value={narrative} onChange={(e) => setNarrative(e.target.value)} rows={8} maxLength={20000} disabled={!editable}
            placeholder={t("evrep.editor.narrativePh")} className="leading-relaxed" aria-label={t("evrep.editor.narrative")} />
        </section>

        <section>
          <SectionTitle icon="📷" title={t("evrep.editor.photos")} hint={t("evrep.editor.photosHint")} />
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {current.photos.map((p) => (
              <div key={p.id} className="group relative aspect-square overflow-hidden rounded-2xl bg-ink-100 ring-1 ring-ink-100">
                {p.url && (
                  <a href={p.url} target="_blank" rel="noopener noreferrer">
                    {/* eslint-disable-next-line @next/next/no-img-element -- URL presigned del bucket privato */}
                    <img src={p.url} alt="" className="h-full w-full object-cover" loading="lazy" />
                  </a>
                )}
                {editable && (
                  <button type="button" onClick={() => void removePhoto(p.id)} aria-label={t("evrep.editor.removePhoto")}
                    className="absolute right-1.5 top-1.5 flex h-8 w-8 cursor-pointer items-center justify-center rounded-full bg-black/60 text-sm text-white hover:bg-rose-600">✕</button>
                )}
              </div>
            ))}
            {editable && current.photos.length < 12 && (
              <button type="button" onClick={() => fileRef.current?.click()} disabled={busy === "photo"}
                className="flex aspect-square cursor-pointer flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-ink-200 text-ink-500 hover:border-brand-300 hover:text-brand-700 disabled:opacity-60">
                <span className="text-2xl" aria-hidden="true">{busy === "photo" ? "⏳" : "＋"}</span>
                <span className="text-xs font-semibold">{busy === "photo" ? t("evrep.editor.uploading") : t("evrep.editor.addPhoto")}</span>
              </button>
            )}
          </div>
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={(e) => void upload(e.target.files)} />
        </section>

        <section className="rounded-3xl bg-gradient-to-br from-ink-50 to-white p-4 ring-1 ring-ink-100">
          <SectionTitle icon="📰" title={t("evrep.article.section")} hint={t("evrep.article.sectionHint")} />
          {editable && (
            <div className="mb-3 flex flex-wrap gap-2">
              <Button size="sm" variant="dark" loading={busy === "TEMPLATE"} disabled={!!busy || invalid} onClick={() => void writeArticle("TEMPLATE")}>
                📰 {current.article ? t("evrep.article.regenerate") : t("evrep.article.generate")}
              </Button>
              <Button size="sm" variant="accent" loading={busy === "AI"} disabled={!ai || !!busy || invalid} title={ai ? undefined : t("evrep.article.aiOff")}
                onClick={() => void writeArticle("AI")}>✨ {t("evrep.article.generateAi")}</Button>
              {current.article_source && <Badge tone="neutral" className="self-center">{t(`evrep.article.source.${current.article_source}` as "evrep.article.source.AI")}</Badge>}
            </div>
          )}
          {!ai && editable && <p className="mb-3 text-xs text-ink-500">ℹ️ {t("evrep.article.aiOff")}</p>}
          {(article || editable) && (
            <div className="space-y-2">
              <Input value={articleTitle} onChange={(e) => setArticleTitle(e.target.value)} maxLength={200} disabled={!editable}
                placeholder={t("evrep.article.titleLabel")} aria-label={t("evrep.article.titleLabel")} className="font-serif text-lg font-bold" />
              <Textarea value={article} onChange={(e) => setArticle(e.target.value)} rows={10} maxLength={20000} disabled={!editable}
                aria-label={t("evrep.article.text")} className="font-serif leading-relaxed" />
            </div>
          )}
        </section>
      </div>
    </Modal>
  );
}

function SectionTitle({ icon, title, hint }: { icon: string; title: string; hint?: string }) {
  return (
    <div className="mb-2">
      <h3 className="text-sm font-bold uppercase tracking-wide text-ink-700"><span aria-hidden="true">{icon}</span> {title}</h3>
      {hint && <p className="text-xs text-ink-500">{hint}</p>}
    </div>
  );
}
