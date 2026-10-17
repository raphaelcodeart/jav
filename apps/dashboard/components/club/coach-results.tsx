"use client";

import { MotionConfig, motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { EventIcon } from "@/components/club/event-icon";
import { AthleteAvatar, CompetitionDetailModal, ResultChip, useEventDetail } from "@/components/club/competition-detail-modal";
import { clubGet, clubSend } from "@/lib/club";
import { cn } from "@/lib/cn";
import type { EventDetail, EventEntry, StaffEvent } from "@/lib/competition-staff";
import { useI18n } from "@/lib/i18n/provider";

// I risultati scritti dal treinador, dal telefono, a bordo tatami: alla
// pesata il peso e la categoria, a gara finita la medaglia (o il
// piazzamento) e una nota. Ogni campo si salva da solo appena lo si lascia,
// ogni medaglia appena la si tocca. Il piazzamento passa dalla stessa
// funzione della segreteria: conta nel Jav Ranking allo stesso modo.

const PLACEMENTS: { value: number; icon: string }[] = [
  { value: 1, icon: "🥇" }, { value: 2, icon: "🥈" }, { value: 3, icon: "🥉" },
  { value: 5, icon: "5º" }, { value: 7, icon: "7º" }, { value: 0, icon: "🎽" },
];

export function CoachResultsPanel() {
  const { t } = useI18n();
  const [when, setWhen] = useState<"upcoming" | "past">("upcoming");
  const [open, setOpen] = useState<string | null>(null);
  if (open) return <ResultsEditor competitionId={open} onBack={() => setOpen(null)} />;
  return (
    <div className="space-y-4">
      <Tabs value={when} onChange={(k) => setWhen(k as "upcoming" | "past")}
        items={[{ key: "upcoming", label: t("evrep.results.upcoming") }, { key: "past", label: t("evrep.results.past") }]} />
      <EventPicker when={when} onPick={setOpen} />
    </div>
  );
}

export function useStaffEvents(when: "upcoming" | "past") {
  return useQuery({
    queryKey: ["club", "staff-competitions", when],
    queryFn: () => clubGet<StaffEvent[]>(`/staff/competitions?when=${when}`),
  });
}

function EventPicker({ when, onPick }: { when: "upcoming" | "past"; onPick: (id: string) => void }) {
  const { t, fmt } = useI18n();
  const { data, isLoading, error } = useStaffEvents(when);
  if (isLoading) return <Skeleton className="h-48" />;
  if (error) return <EmptyState title={t("evrep.loadError")} text={(error as Error).message} />;
  if (!data?.length) return <EmptyState icon={<span className="text-3xl">🏟️</span>} title={t("evrep.results.empty")} />;
  return (
    <MotionConfig reducedMotion="user">
      <ul className="space-y-2">
        {data.map((e, i) => {
          const pct = e.entries_count ? Math.round((e.results_count / e.entries_count) * 100) : 0;
          return (
            <motion.li key={e.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }}>
              <button type="button" onClick={() => onPick(e.id)}
                className="flex w-full cursor-pointer items-center gap-3 rounded-3xl bg-white p-3 text-left shadow-soft ring-1 ring-ink-900/5 hover:ring-brand-300">
                <EventIcon kind={e.kind} imageUrl={e.image_url} size="md" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold text-ink-900">{e.name}</span>
                  <span className="block text-xs text-ink-500">{fmt.shortDate(e.starts_on)} · {e.location ?? "—"}</span>
                  <span className="mt-1.5 flex items-center gap-2">
                    <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-100">
                      <span className="block h-full rounded-full bg-gradient-to-r from-accent-400 to-brand-500" style={{ width: `${pct}%` }} />
                    </span>
                    <span className="shrink-0 text-[11px] font-semibold text-ink-600">
                      {t("evrep.results.progress", { done: e.results_count, n: e.entries_count })}
                    </span>
                  </span>
                </span>
                <span className="text-xl text-ink-300" aria-hidden="true">›</span>
              </button>
            </motion.li>
          );
        })}
      </ul>
    </MotionConfig>
  );
}

function ResultsEditor({ competitionId, onBack }: { competitionId: string; onBack: () => void }) {
  const { t, fmt } = useI18n();
  const { data, isLoading, error } = useEventDetail(competitionId, "staff");
  const [detail, setDetail] = useState(false);
  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={onBack}>← {t("evrep.results.back")}</Button>
      {isLoading ? <Skeleton className="h-64" /> : error || !data ? <EmptyState title={t("evrep.loadError")} text={(error as Error | null)?.message} /> : (
        <>
          <div className="flex items-center gap-3 rounded-3xl bg-gradient-to-br from-brand-600 to-ink-950 p-4 text-white shadow-lift">
            <EventIcon kind={data.kind} imageUrl={data.image_url} size="md" />
            <div className="min-w-0 flex-1">
              <button type="button" onClick={() => setDetail(true)} className="block cursor-pointer truncate text-left font-display text-lg hover:underline">{data.name}</button>
              <p className="text-xs text-white/75">{fmt.shortDate(data.starts_on)} · {data.location ?? "—"} · {t("evrep.results.athletes", { n: data.entries.length })}</p>
            </div>
          </div>
          {data.kind !== "COMPETITION" && <p className="rounded-2xl bg-sky-50 p-3 text-sm text-sky-800">{t("evrep.results.stageNote")}</p>}
          {data.entries.length === 0 ? <EmptyState icon={<span className="text-3xl">🥋</span>} title={t("evrep.detail.noAthletes")} /> : (
            <ul className="space-y-3">
              {data.entries.map((x) => <EntryCard key={x.entry_id} event={data} entry={x} />)}
            </ul>
          )}
          {detail && <CompetitionDetailModal competitionId={competitionId} mode="staff" onClose={() => setDetail(false)} />}
        </>
      )}
    </div>
  );
}

type Field = "weight_kg" | "category" | "placement" | "rank" | "result_notes";

function EntryCard({ event, entry }: { event: EventDetail; entry: EventEntry }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  // I campi partono dal server e poi sono di chi scrive: il salvataggio
  // aggiorna la cache, non riscrive quello che il treinador sta digitando.
  const [weight, setWeight] = useState(entry.weight_kg ? String(Number(entry.weight_kg)) : "");
  const [category, setCategory] = useState(entry.category ?? "");
  const [rank, setRank] = useState(entry.rank ? String(entry.rank) : "");
  const [note, setNote] = useState(entry.result_notes ?? "");
  const [saving, setSaving] = useState<Field | null>(null);
  const [saved, setSaved] = useState(false);
  const canResult = event.kind === "COMPETITION";

  async function save(field: Field, value: string | number | null) {
    setSaving(field);
    setSaved(false);
    try {
      const fresh = await clubSend<EventEntry>(`/staff/competitions/${event.id}/entries/${entry.entry_id}`, "PATCH", { [field]: value });
      queryClient.setQueryData<EventDetail>(["club", "event-detail", "staff", event.id], (old) =>
        old ? { ...old, entries: old.entries.map((e) => (e.entry_id === fresh.entry_id ? fresh : e)) } : old);
      void queryClient.invalidateQueries({ queryKey: ["club", "staff-competitions"] });
      void queryClient.invalidateQueries({ queryKey: ["club", "ranking"] });
      setSaved(true);
    } catch (e) {
      toast({ tone: "error", title: t("evrep.results.saveError"), text: (e as Error).message });
    } finally {
      setSaving(null);
    }
  }

  function blurWeight() {
    const clean = weight.replace(",", ".").trim();
    const current = entry.weight_kg ? String(Number(entry.weight_kg)) : "";
    if (clean === current) return;
    if (clean && (Number.isNaN(Number(clean)) || Number(clean) <= 0)) {
      toast({ tone: "error", title: t("evrep.results.badWeight") });
      return;
    }
    void save("weight_kg", clean || null);
  }

  return (
    <li className={cn("rounded-3xl bg-white p-4 shadow-soft ring-1 transition",
      entry.placement === 1 ? "ring-amber-300" : entry.placement === 2 ? "ring-slate-300" : entry.placement === 3 ? "ring-orange-300" : "ring-ink-900/5")}>
      <div className="flex items-center gap-3">
        <AthleteAvatar name={entry.athlete_name} photoUrl={entry.photo_url} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-ink-900">{entry.athlete_name}</p>
          <p className="text-xs text-ink-500">{entry.age != null ? t("evrep.detail.age", { n: entry.age }) : ""}{entry.points ? ` · ${t("evrep.results.points", { n: entry.points })}` : ""}</p>
        </div>
        <span className="text-xs font-semibold text-ink-400" aria-live="polite">
          {saving ? t("evrep.results.saving") : saved ? `✓ ${t("evrep.results.saved")}` : ""}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <label className="block">
          <span className="text-[11px] font-bold uppercase tracking-wide text-ink-400">⚖️ {t("evrep.results.weight")}</span>
          <Input inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} onBlur={blurWeight} placeholder="kg" className="mt-1 h-11 text-base" />
        </label>
        <label className="block">
          <span className="text-[11px] font-bold uppercase tracking-wide text-ink-400">🏷️ {t("evrep.results.category")}</span>
          <Input value={category} maxLength={120} onChange={(e) => setCategory(e.target.value)} placeholder={t("evrep.results.categoryPh")}
            onBlur={() => category.trim() !== (entry.category ?? "") && void save("category", category.trim() || null)} className="mt-1 h-11 text-base" />
        </label>
      </div>

      {canResult && (
        <div className="mt-3">
          <span className="text-[11px] font-bold uppercase tracking-wide text-ink-400">🏅 {t("evrep.results.result")}</span>
          <div className="mt-1 grid grid-cols-6 gap-1.5" role="radiogroup" aria-label={t("evrep.results.result")}>
            {PLACEMENTS.map((p) => {
              const active = entry.placement === p.value;
              return (
                <motion.button key={p.value} type="button" role="radio" aria-checked={active} whileTap={{ scale: 0.92 }}
                  disabled={saving === "placement"} title={t.dyn(`club.placement.${p.value}`, String(p.value))}
                  onClick={() => void save("placement", active ? null : p.value)}
                  className={cn("flex h-12 cursor-pointer flex-col items-center justify-center rounded-2xl text-xl font-bold ring-1 disabled:opacity-60",
                    active ? "bg-accent-100 ring-2 ring-accent-400" : "bg-ink-50 ring-ink-200 hover:bg-white")}>
                  <span className={p.value === 5 || p.value === 7 ? "text-base text-ink-800" : ""}>{p.icon}</span>
                </motion.button>
              );
            })}
          </div>
          <div className="mt-1.5 flex items-center justify-between gap-2">
            <ResultChip placement={entry.placement} rank={entry.rank} />
            {entry.placement == null && <span className="text-xs text-ink-400">{t("evrep.results.tapMedal")}</span>}
          </div>
          {entry.placement === 0 && (
            <label className="mt-2 block">
              <span className="text-[11px] font-bold uppercase tracking-wide text-ink-400">{t("evrep.results.rank")}</span>
              <Input inputMode="numeric" value={rank} onChange={(e) => setRank(e.target.value.replace(/\D/g, ""))} placeholder="9"
                onBlur={() => rank !== (entry.rank ? String(entry.rank) : "") && void save("rank", rank ? Number(rank) : null)} className="mt-1 h-11 w-28 text-base" />
            </label>
          )}
        </div>
      )}

      <label className="mt-3 block">
        <span className="text-[11px] font-bold uppercase tracking-wide text-ink-400">📝 {t("evrep.results.note")}</span>
        <Input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder={t("evrep.results.notePh")}
          onBlur={() => note.trim() !== (entry.result_notes ?? "") && void save("result_notes", note.trim() || null)} className="mt-1 h-11 text-base" />
      </label>
    </li>
  );
}
