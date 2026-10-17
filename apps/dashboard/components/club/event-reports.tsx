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
import { Tabs } from "@/components/ui/tabs";
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

/** La scheda «Provas» dell'area del treinador: i risultati da scrivere e i
 *  suoi relatórios, in un posto solo. */
export function CoachEventsPanel() {
  const { t } = useI18n();
  const [view, setView] = useState("results");
  return (
    <div className="space-y-4">
      <Tabs value={view} onChange={setView} items={[{ key: "results", label: t("evrep.admin.results") }, { key: "reports", label: t("evrep.admin.reports") }]} />
      {view === "results" ? <CoachResultsPanel /> : <EventReportsPanel />}
    </div>
  );
}

export function EventReportsPanel({ admin = false }: { admin?: boolean }) {
  const { t } = useI18n();
  const { data, isLoading, error } = useQuery({ queryKey: KEY, queryFn: () => clubGet<EventReport[]>("/staff/event-reports") });
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<EventReport | null>(null);
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data ?? []).filter((r) => !needle || `${r.title} ${r.competition_name} ${r.author_name} ${r.location ?? ""}`.toLowerCase().includes(needle));
  }, [data, q]);
  const paged = usePaged(filtered, 12);
  const top = useRef<HTMLDivElement>(null);

  return (
    <MotionConfig reducedMotion="user">
      <div ref={top} className="scroll-mt-24 space-y-5">
        {admin && <ExportBar />}
        <div className="flex flex-wrap items-center gap-2">
          <Input value={q} onChange={(e) => { setQ(e.target.value); paged.setPage(1); }} placeholder={t("evrep.list.search")} className="h-11 min-w-0 flex-1 sm:max-w-sm" aria-label={t("evrep.list.search")} />
          <Button onClick={() => setCreating(true)} icon={<span>＋</span>}>{t("evrep.list.new")}</Button>
        </div>
        {isLoading ? <Skeleton className="h-64" /> : error ? <EmptyState title={t("evrep.loadError")} text={(error as Error).message} /> : filtered.length === 0 ? (
          <EmptyState icon={<span className="text-3xl">📝</span>} title={q ? t("evrep.list.noMatch") : t("evrep.list.empty")} text={q ? undefined : t("evrep.list.emptyText")}
            action={q ? undefined : <Button onClick={() => setCreating(true)}>{t("evrep.list.new")}</Button>} />
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {paged.items.map((r, i) => <ReportCard key={r.id} report={r} index={i} showAuthor={admin} onOpen={() => setEditing(r)} />)}
          </ul>
        )}
        <Pagination page={paged.page} pages={paged.pages} onChange={(p) => { paged.setPage(p); top.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }} />
        {creating && <NewReportModal onClose={() => setCreating(false)} onCreated={(r) => { setCreating(false); setEditing(r); }} existing={data ?? []} />}
        {editing && <ReportEditor key={editing.id} report={editing} onClose={() => setEditing(null)} />}
      </div>
    </MotionConfig>
  );
}

function medalCount(r: EventReport, p: number) {
  return r.results.filter((x) => x.placement === p).length;
}

function ReportCard({ report: r, index, showAuthor, onOpen }: { report: EventReport; index: number; showAuthor: boolean; onOpen: () => void }) {
  const { t, fmt } = useI18n();
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
    </motion.li>
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
  const { data, isLoading } = useStaffEvents(when);
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
        <div className="flex w-fit gap-1 rounded-full bg-ink-50 p-1">
          {(["past", "upcoming"] as const).map((w) => (
            <button key={w} type="button" onClick={() => setWhen(w)}
              className={cn("h-9 cursor-pointer rounded-full px-4 text-sm font-semibold", when === w ? "bg-ink-900 text-white" : "text-ink-600 hover:bg-white")}>
              {w === "past" ? t("evrep.results.past") : t("evrep.results.upcoming")}
            </button>
          ))}
        </div>
        {isLoading ? <Skeleton className="h-48" /> : !data?.length ? <p className="text-sm text-ink-500">{t("evrep.results.empty")}</p> : (
          <ul className="max-h-[55vh] space-y-2 overflow-y-auto pr-1">
            {data.map((e) => (
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
  const [busy, setBusy] = useState<"save" | "photo" | "delete" | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const editable = report.can_edit;
  const cents = COST_KINDS.map((k) => toCents(costs[k].amount));
  const invalid = cents.some((c) => c === null);
  const total = cents.reduce<number>((s, c) => s + (c ?? 0), 0);

  function refresh(r: EventReport) {
    setCurrent(r);
    queryClient.setQueryData<EventReport[]>(KEY, (old) => old?.map((x) => (x.id === r.id ? r : x)));
  }

  async function save() {
    if (invalid || title.trim().length < 3) return;
    setBusy("save");
    try {
      const r = await clubSend<EventReport>(`/staff/event-reports/${report.id}`, "PATCH", {
        title: title.trim(), description, narrative,
        costs: COST_KINDS.map((k, i) => ({ kind: k, amount_cents: cents[i] ?? 0, note: costs[k].note.trim() || null })),
      });
      refresh(r);
      toast({ tone: "success", title: t("evrep.editor.saved") });
      onClose();
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
