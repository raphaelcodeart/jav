"use client";

import { motion } from "motion/react";
import { useDeferredValue, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Spinner } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/field";
import { ImageCropDialog } from "@/components/ui/image-cropper";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { friendlyApiError } from "@/lib/api-error";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// Chi allena dove (apps/api/app/domains/club/staff_clubs.py): per ogni
// treinador i club in cui entra con lo stesso account. Un chip per ogni club
// attivo: toccandolo si assegna o si toglie; un chip "pedido" è la richiesta
// di una segreteria, e toccandolo si approva. Il club di origine non si tocca
// da qui: è quello dell'account.

interface CoachRow {
  user_id: string;
  email: string;
  name: string;
  home_club_id: string | null;
  photo_url: string | null;
  clubs: { club_id: string; name: string; status: "ACTIVE" | "REQUESTED" | string }[];
}

interface ClubBrief { id: string; name: string; status: string; kind?: string }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/proxy/clubs${path}`, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";

export function CoachesPanel() {
  const { t } = useI18n();
  const coaches = useQuery({ queryKey: ["clubs", "coaches"], queryFn: () => call<CoachRow[]>("/coaches") });
  const clubs = useQuery({ queryKey: ["clubs"], queryFn: () => call<ClubBrief[]>("") });
  const [search, setSearch] = useState("");
  const needle = useDeferredValue(search).trim().toLowerCase();

  if (coaches.isLoading || clubs.isLoading) return <div className="space-y-3"><Skeleton className="h-28" /><Skeleton className="h-28" /></div>;
  if (coaches.error) return <EmptyState title={t("staffClubs.failed")} text={(coaches.error as Error).message} />;
  const active = (clubs.data ?? []).filter((c) => c.status === "ACTIVE");
  const names = new Map((clubs.data ?? []).map((c) => [c.id, c.name]));
  const rows = (coaches.data ?? []).filter((c) => !needle || `${c.name} ${c.email}`.toLowerCase().includes(needle));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-500">{t("staffClubs.chipsHint")}</p>
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("staffClubs.search")} className="w-full sm:w-72" aria-label={t("staffClubs.search")} />
      </div>
      {rows.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🧑‍🏫</span>} title={t("staffClubs.empty")} />
      ) : (
        <ul className="grid gap-3 xl:grid-cols-2">
          {rows.map((c) => <CoachCard key={c.user_id} coach={c} clubs={active} homeName={c.home_club_id ? names.get(c.home_club_id) ?? null : null} />)}
        </ul>
      )}
    </div>
  );
}

function CoachCard({ coach, clubs, homeName }: { coach: CoachRow; clubs: ClubBrief[]; homeName: string | null }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<File | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const status = new Map(coach.clubs.map((m) => [m.club_id, m.status]));

  async function toggle(club: ClubBrief) {
    const current = status.get(club.id);
    if (current === "ACTIVE" && !window.confirm(t("staffClubs.removeFromClubConfirm", { name: coach.name, club: club.name }))) return;
    setBusy(club.id);
    try {
      // Spento o chiesto dalla segreteria: lo si assegna (approva); acceso: lo si toglie.
      if (current === "ACTIVE") await call(`/${club.id}/coaches/${coach.user_id}`, { method: "DELETE" });
      else await call(`/${club.id}/coaches`, {
        method: "POST", body: JSON.stringify({ user_id: coach.user_id }), headers: { "Content-Type": "application/json" },
      });
      await queryClient.invalidateQueries({ queryKey: ["clubs"] });
      toast({ tone: "success", title: current === "ACTIVE" ? t("staffClubs.removed") : current === "REQUESTED" ? t("staffClubs.approved") : t("staffClubs.assigned") });
    } catch (e) {
      toast({ tone: "error", title: t("staffClubs.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function upload(file: File) {
    setBusy("photo");
    try {
      const form = new FormData();
      form.append("file", file);
      await call(`/coaches/${coach.user_id}/photo`, { method: "PUT", body: form });
      await queryClient.invalidateQueries({ queryKey: ["clubs", "coaches"] });
      toast({ tone: "success", title: t("staffClubs.photoSaved") });
    } catch (e) {
      toast({ tone: "error", title: t("staffClubs.photoFailed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <motion.li initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
      <div className="flex items-center gap-4">
        <button type="button" onClick={() => input.current?.click()} disabled={busy === "photo"}
          className="group relative flex h-16 w-16 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-brand-500 to-brand-700 shadow-soft ring-4 ring-white ring-offset-2 ring-offset-ink-100"
          aria-label={t("staffClubs.photoOf", { name: coach.name })} title={t("staffClubs.photoOf", { name: coach.name })}>
          {coach.photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- foto del treinador
            <img src={coach.photo_url} alt="" className="h-full w-full object-cover" />
          ) : <span className="font-display text-lg text-white">{initials(coach.name)}</span>}
          <span className="absolute inset-x-0 bottom-0 flex h-1/3 items-center justify-center bg-ink-950/45 text-xs text-white opacity-80 group-hover:opacity-100" aria-hidden="true">
            {busy === "photo" ? <Spinner /> : "📷"}
          </span>
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-ink-900">{coach.name}</p>
          <p className="truncate text-xs text-ink-500">{coach.email}</p>
          <p className="mt-0.5 truncate text-xs text-ink-500">🏠 {t("staffClubs.homeClub")}: <span className="font-semibold text-ink-700">{homeName ?? "—"}</span></p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {clubs.map((club) => {
          const isHome = club.id === coach.home_club_id;
          const st = status.get(club.id);
          const on = isHome || st === "ACTIVE";
          return (
            <button key={club.id} type="button" disabled={isHome || busy !== null} onClick={() => toggle(club)} aria-pressed={on}
              className={cn("inline-flex cursor-pointer items-center gap-1 rounded-full px-3 py-1.5 text-xs font-semibold ring-1 transition disabled:cursor-default",
                isHome ? "bg-brand-500 text-white ring-brand-500"
                  : st === "ACTIVE" ? "bg-emerald-500 text-white ring-emerald-500 hover:bg-emerald-600"
                    : st === "REQUESTED" ? "bg-amber-50 text-amber-800 ring-amber-300 hover:bg-amber-100"
                      : "bg-white text-ink-600 ring-ink-200 hover:ring-brand-300 hover:text-ink-900")}>
              {busy === club.id ? <Spinner /> : <span aria-hidden="true">{isHome ? "🏠" : st === "ACTIVE" ? "✓" : st === "REQUESTED" ? "⏳" : "+"}</span>}
              {club.name}
              {st === "REQUESTED" && <span className="font-normal">· {t("staffClubs.pending")}</span>}
            </button>
          );
        })}
      </div>
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) setPicked(f); }} />
      <ImageCropDialog file={picked} onCancel={() => setPicked(null)} onConfirm={async (f) => { setPicked(null); await upload(f); }} />
    </motion.li>
  );
}
