"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { celebrate } from "@/lib/motion";
import { LEVEL_LABELS, PLACEMENT_LABELS, clubGet, clubSend, daysUntil, type FamilyCompetition } from "@/lib/club";
import type { MessageKey } from "@/lib/i18n/messages/it";
import { EventIcon } from "@/components/club/event-icon";
import { JavCalendar } from "@/components/club/jav-calendar";
import { AreaEvents } from "@/components/club/area-events";
import { Pagination, usePaged } from "@/components/ui/pagination";
import { useI18n } from "@/lib/i18n/provider";

const LEVEL_TONES: Record<string, string> = {
  CLUB: "from-ink-600 to-ink-800",
  REGIONAL: "from-sky-500 to-sky-700",
  ZONAL: "from-sky-600 to-sky-800",
  OPENS: "from-emerald-500 to-emerald-700",
  NATIONAL: "from-brand-500 to-brand-700",
  INTERNATIONAL: "from-accent-400 to-accent-600 text-ink-900",
  EUROPEAN_CUP: "from-accent-400 to-accent-600 text-ink-900",
  EUROPEAN_CHAMPIONSHIP: "from-accent-400 to-accent-600 text-ink-900",
  WORLD_CHAMPIONSHIP: "from-accent-500 to-accent-700 text-ink-900",
  OLYMPIC_GAMES: "from-accent-500 to-accent-700 text-ink-900",
};

/** The competition calendar, per family: for every competition, each child
 *  with a one-tap "Iscrivi" -- or the reason they can't (age, certificate). */
export function CompetitionsPanel() {
  const [when, setWhen] = useState<"events" | "next" | "past" | "calendar">("events");
  const { t } = useI18n();
  const { data, isLoading, error } = useQuery({
    queryKey: ["club", "competitions", when === "past" ? "past" : "next"],
    queryFn: () => clubGet<FamilyCompetition[]>(`/competitions${when === "past" ? "?include_past=true" : ""}`),
  });
  const list = (data ?? []).filter((c) => (when === "past" ? c.status === "DONE" || daysUntil(c.ends_on) < 0 : c.status !== "DONE" && daysUntil(c.ends_on) >= 0))
    .sort((a, b) => when === "past" ? b.starts_on.localeCompare(a.starts_on) : a.starts_on.localeCompare(b.starts_on));
  const paged = usePaged(list, 8);

  return (
    <div>
      <PageHeader eyebrow={t("comp.eyebrow")} title={t("nav.club-competitions")} subtitle={t("comp.subtitle")} actions={<Tabs value={when} onChange={(k) => setWhen(k as "events" | "next" | "past" | "calendar")} items={[{ key: "events", label: `🗓️ ${t("comp.eventsTab")}` }, { key: "next", label: t("comp.upcoming") }, { key: "past", label: t("comp.past") }, { key: "calendar", label: `📅 ${t("jcal.tabEvents")}` }]} />} />
      {when === "events" ? <AreaEvents /> : when === "calendar" ? <JavCalendar mode="member" /> : (
        <>
          {isLoading && <div className="space-y-4"><Skeleton className="h-40" /><Skeleton className="h-40" /></div>}
          {error && <EmptyState title={t("comp.unavailable")} text={(error as Error).message} />}
          {!isLoading && !error && list.length === 0 && (
            <EmptyState icon={<span className="text-3xl">🏟️</span>} title={when === "next" ? t("comp.noneUpcoming") : t("comp.nonePast")} text={t("comp.emptyText")} />
          )}
          <div className="space-y-5">
            {paged.items.map((c, i) => (
              <CompetitionCard key={c.id} competition={c} delay={i * 0.05} />
            ))}
          </div>
          <Pagination className="mt-6" page={paged.page} pages={paged.pages} onChange={(p) => { paged.setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
        </>
      )}
    </div>
  );
}

const EVENT_KIND_KEYS: Record<string, MessageKey> = {
  STAGE: "event.stage", REFEREEING: "event.referee", EDUCATION: "event.education", MEETING: "event.meeting",
  OTHER: "event.other",
};

function CompetitionCard({ competition: c, delay }: { competition: FamilyCompetition; delay: number }) {
  const { t, fmt } = useI18n();
  const start = new Date(`${c.starts_on}T00:00:00`);
  const toDeadline = daysUntil(c.registration_deadline);
  // Solo una gara ha un livello di ranking: per gli altri eventi si dice che cosa sono.
  const level = c.kind === "COMPETITION" || !c.kind
    ? t.dyn(`club.level.${c.level}`, LEVEL_LABELS[c.level] ?? c.level)
    : t(EVENT_KIND_KEYS[c.kind] ?? "event.other");
  return (
    <motion.article initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }} className="glass-card rounded-3xl overflow-hidden">
      <div className="flex flex-col sm:flex-row">
        <div className={`sm:w-36 shrink-0 bg-gradient-to-br ${LEVEL_TONES[c.level] ?? LEVEL_TONES.CLUB} text-white p-5 flex sm:flex-col items-center sm:justify-center gap-3 sm:gap-0 text-center`}>
          <EventIcon kind={c.kind} imageUrl={c.image_url} size="md" className="sm:mb-3" />
          <p className="font-display text-4xl leading-none">{start.getDate()}</p>
          <p className="text-sm font-bold uppercase tracking-widest">{fmt.date(start, { month: "short" })}</p>
          <p className="text-xs opacity-80 sm:mt-1">{start.getFullYear()}</p>
        </div>
        <div className="flex-1 p-5 space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap gap-1.5 mb-1.5">
                <Badge tone="neutral">{level}</Badge>
                {c.requires_agonistic_certificate && <Badge tone="info">{t("comp.needsCertificate")}</Badge>}
                {c.fee_cents > 0 ? <Badge tone="brand">{t("comp.entryFee", { amount: fmt.euro(c.fee_cents) })}</Badge> : <Badge tone="success">{t("comp.free")}</Badge>}
              </div>
              <h3 className="text-lg text-ink-900">{c.name}</h3>
              <p className="text-sm text-ink-500">
                {[c.location, c.organizer].filter(Boolean).join(" · ") || t("comp.placeTbd")}
              </p>
              {c.categories && <p className="text-xs text-ink-500 mt-1">{t("comp.categories", { categories: c.categories })}</p>}
            </div>
            {c.registrations_open ? (
              <div className="rounded-2xl bg-accent-100 text-accent-900 px-3 py-2 text-center">
                <p className="font-display text-xl leading-none">{Math.max(0, toDeadline)}</p>
                <p className="text-[10px] font-bold uppercase tracking-wide">{toDeadline === 1 ? t("comp.dayLeft") : t("comp.daysLeft")}</p>
              </div>
            ) : (
              <Badge tone="neutral">{t("comp.closed")}</Badge>
            )}
          </div>
          <div className="space-y-2">
            {c.athletes.map((a) => (
              <AthleteEntryRow key={a.athlete_id} competition={c} athlete={a} />
            ))}
          </div>
        </div>
      </div>
    </motion.article>
  );
}

function AthleteEntryRow({ competition: c, athlete: a }: { competition: FamilyCompetition; athlete: FamilyCompetition["athletes"][number] }) {
  const [asking, setAsking] = useState(false);
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const queryClient = useQueryClient();
  const toast = useToast();
  const { t } = useI18n();
  const registered = a.entry_status === "REGISTERED";

  async function register() {
    setBusy(true);
    try {
      await clubSend(`/competitions/${c.id}/entries`, "POST", { athlete_id: a.athlete_id, category: category.trim() || null });
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      void celebrate({ x: 0.5, y: 0.4 });
      toast({ tone: "success", title: t("comp.registeredToast", { name: a.first_name }), text: c.fee_cents > 0 ? t("comp.feeAdded") : undefined });
      setAsking(false);
    } catch (e) {
      toast({ tone: "error", title: t("comp.registerFailed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function openLetter() {
    // La finestra si apre nel clic: dopo l'await il browser la bloccherebbe.
    const tab = window.open("", "_blank");
    if (tab) tab.opener = null;
    try {
      const { url } = await clubGet<{ url: string }>(`/competitions/${c.id}/entries/${a.athlete_id}/school-letter/url`);
      if (tab) tab.location.href = url;
      else window.location.href = url;
    } catch (e) {
      tab?.close();
      toast({ tone: "error", title: t("letter.downloadFailed"), text: (e as Error).message });
    }
  }

  async function withdraw() {
    if (!window.confirm(t("comp.withdrawConfirm", { name: a.first_name, competition: c.name }))) return;
    setBusy(true);
    try {
      await clubSend(`/competitions/${c.id}/entries/${a.athlete_id}`, "DELETE");
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "info", title: t("comp.withdrawn") });
    } catch (e) {
      toast({ tone: "error", title: t("comp.withdrawFailed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl bg-white ring-1 ring-ink-100 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink-900">{a.first_name}</p>
          {a.placement != null ? (
            <p className="text-xs font-bold text-brand-600">{a.placement === 1 ? "🥇" : a.placement === 2 ? "🥈" : a.placement === 3 ? "🥉" : "🎖️"} {t.dyn(`club.placement.${a.placement}`, PLACEMENT_LABELS[a.placement] ?? `${a.placement}°`)}</p>
          ) : registered ? (
            <p className="text-xs text-emerald-700 font-semibold">{t("comp.entered")}{a.category ? ` · ${a.category}` : ""}</p>
          ) : !a.eligible ? (
            <p className="text-xs text-ink-500">{a.reason ?? t("comp.notEligible")}</p>
          ) : (
            <p className="text-xs text-ink-500">{t("comp.eligible")}</p>
          )}
        </div>
        {registered && a.school_letter_ready && (
          <Button variant="secondary" size="sm" onClick={openLetter}>🏫 {t("letter.download")} ↗</Button>
        )}
        {c.registrations_open &&
          (registered ? (
            <Button variant="ghost" size="sm" onClick={withdraw} loading={busy}>{t("comp.withdraw")}</Button>
          ) : a.eligible && !asking ? (
            <Button size="sm" onClick={() => setAsking(true)}>{t("comp.enter")}</Button>
          ) : null)}
      </div>
      {asking && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="flex flex-col sm:flex-row gap-2 mt-3">
          <Input placeholder={t("comp.categoryPlaceholder")} value={category} onChange={(e) => setCategory(e.target.value)} />
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setAsking(false)}>{t("common.cancel")}</Button>
            <Button onClick={register} loading={busy}>{t("common.confirm")}</Button>
          </div>
        </motion.div>
      )}
    </div>
  );
}
