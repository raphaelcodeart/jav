"use client";

import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { EVENT_KIND_STYLE } from "@/components/club/event-icon";
import { clubGet } from "@/lib/club";
import { cn } from "@/lib/cn";
import { MEDALS, whatsappNumber, type EventDetail, type EventEntry } from "@/lib/competition-staff";
import { useI18n } from "@/lib/i18n/provider";

// La scheda di un evento: si apre toccando il nome di una prova nel
// calendário, negli elenchi della segreteria e nei risultati del
// treinador. Lo staff (`staff`) vede gli iscritti del club con i contatti
// (l'encarregado per un minorenne) da chiamare, scrivere o mandare su
// WhatsApp con un tocco; atleti e famiglie (`member`) la stessa scheda,
// senza contatti.

type Mode = "staff" | "member";

export function useEventDetail(id: string, mode: Mode) {
  return useQuery({
    queryKey: ["club", "event-detail", mode, id],
    queryFn: () => clubGet<EventDetail>(mode === "staff" ? `/staff/competitions/${id}` : `/calendar/events/${id}`),
  });
}

/** Il nome di una prova come bottone che apre la sua scheda. */
export function EventNameButton({ id, name, mode, className }: { id: string; name: string; mode: Mode; className?: string }) {
  const [open, setOpen] = useState(false);
  const { t } = useI18n();
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} title={t("evrep.detail.open")}
        className={cn("cursor-pointer text-left underline-offset-4 decoration-brand-300 hover:text-brand-700 hover:underline", className)}>
        {name}
      </button>
      {open && <CompetitionDetailModal competitionId={id} mode={mode} onClose={() => setOpen(false)} />}
    </>
  );
}

export function CompetitionDetailModal({ competitionId, mode, onClose }: { competitionId: string; mode: Mode; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const { data: e, isLoading, error } = useEventDetail(competitionId, mode);
  const day = (iso: string) => fmt.date(new Date(`${iso}T12:00:00`), { weekday: "short", day: "numeric", month: "long", year: "numeric" });
  const time = (hhmm: string | null) => (hhmm ? hhmm.slice(0, 5) : null);

  if (isLoading || !e) {
    return (
      <Modal open onClose={onClose} size="lg" title={t("evrep.detail.title")}>
        {error ? <p className="text-sm text-rose-700">{(error as Error).message}</p> : <Skeleton className="h-72" />}
      </Modal>
    );
  }
  const style = EVENT_KIND_STYLE[e.kind] ?? EVENT_KIND_STYLE.OTHER!;
  const kindLabel = e.kind === "COMPETITION" ? t.dyn(`club.level.${e.level}`, e.level) : t.dyn(`jcal.kind.${e.kind}`, e.kind);
  const dates = e.starts_on === e.ends_on ? day(e.starts_on) : `${day(e.starts_on)} – ${day(e.ends_on)}`;
  const hours = [time(e.starts_at_time), time(e.ends_at_time)].filter(Boolean).join(" – ");
  const ages = [
    e.age_groups.length ? e.age_groups.map((a) => t.dyn(`site.ev.age.${a}`, a)).join(" · ") : null,
    e.min_age != null || e.max_age != null ? t("evrep.detail.ageRange", { min: e.min_age ?? "—", max: e.max_age ?? "—" }) : null,
  ].filter(Boolean).join(" · ") || t("jcal.allAges");
  const medals = e.entries.filter((x) => x.placement != null && MEDALS[x.placement]).length;

  return (
    <Modal open onClose={onClose} size="lg" title={e.name} subtitle={`${kindLabel} · ${e.network ? t("jcal.network") : e.club_name ?? ""}`}
      footer={<Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>}>
      <div className="space-y-5">
        <div className={cn("relative h-36 overflow-hidden rounded-3xl bg-gradient-to-br sm:h-44", style.bg)}>
          {e.image_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- locandina caricata dal club
            <img src={e.image_url} alt="" className="absolute inset-0 h-full w-full object-cover" />
          ) : (
            <span className="absolute inset-0 flex items-center justify-center text-7xl opacity-80" aria-hidden="true">{style.icon}</span>
          )}
          <div className="absolute inset-x-0 bottom-0 flex flex-wrap gap-1.5 bg-gradient-to-t from-black/60 to-transparent p-3">
            <Badge tone={e.status === "OPEN" ? "success" : e.status === "DONE" ? "info" : "warning"}>{t.dyn(`jcal.status.${e.status}`, e.status)}</Badge>
            {e.requires_agonistic_certificate && <Badge tone="neutral">🩺 {t("evrep.detail.certificate")}</Badge>}
            {medals > 0 && <Badge tone="accent">🏅 {t("evrep.detail.medals", { n: medals })}</Badge>}
          </div>
        </div>

        <dl className="grid gap-2 sm:grid-cols-2">
          <Info icon="📅" label={t("evrep.detail.when")}>{dates}{hours ? ` · ${hours}` : ""}</Info>
          <Info icon="📍" label={t("evrep.detail.where")}>{e.location ?? "—"}</Info>
          <Info icon="⏳" label={t("evrep.detail.deadline")}>{day(e.registration_deadline)}{e.registration_deadline_time ? ` · ${time(e.registration_deadline_time)}` : ""}</Info>
          <Info icon="🏷️" label={t("evrep.detail.level")}>{kindLabel}</Info>
          <Info icon="👥" label={t("evrep.detail.ages")}>{ages}</Info>
          <Info icon="💶" label={t("evrep.detail.fee")}>{e.fee_cents ? fmt.euro(e.fee_cents) : t("evrep.detail.free")}</Info>
          {e.organizer && <Info icon="🏛️" label={t("jcal.organizer")}>{e.organizer}</Info>}
          {e.transport_info && <Info icon="🚌" label={t("event.transport")}>{e.transport_info}</Info>}
        </dl>

        {e.description && <p className="whitespace-pre-line rounded-2xl bg-ink-50 p-4 text-sm leading-relaxed text-ink-700">{e.description}</p>}
        {e.categories && (
          <div>
            <p className="mb-1 text-xs font-bold uppercase tracking-wide text-ink-500">{t("evrep.detail.categories")}</p>
            <p className="whitespace-pre-line text-sm text-ink-700">{e.categories}</p>
          </div>
        )}
        {e.circular_url && (
          <a href={e.circular_url} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-3 rounded-2xl bg-white p-3 ring-1 ring-ink-200 hover:ring-brand-300">
            <span className="text-2xl" aria-hidden="true">📄</span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold text-ink-900">{t("jcal.circular")}</span>
              <span className="block truncate text-xs text-ink-500">{e.circular_filename ?? e.circular_url}</span>
            </span>
            <span className="text-sm font-semibold text-brand-700">{t("evrep.detail.openCircular")} ↗</span>
          </a>
        )}

        <section>
          <h3 className="mb-2 flex items-center justify-between text-sm font-bold uppercase tracking-wide text-ink-500">
            <span>{t("evrep.detail.athletes")}</span>
            <span className="rounded-full bg-ink-100 px-2.5 py-0.5 text-xs text-ink-700">{e.entries.length}</span>
          </h3>
          {e.entries.length === 0 ? <p className="text-sm text-ink-500">{t("evrep.detail.noAthletes")}</p> : (
            <ul className="space-y-2">
              {e.entries.map((x) => <AthleteRow key={x.entry_id} entry={x} staff={mode === "staff"} />)}
            </ul>
          )}
        </section>
      </div>
    </Modal>
  );
}

function Info({ icon, label, children }: { icon: string; label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 rounded-2xl bg-white p-3 ring-1 ring-ink-100">
      <span className="text-xl" aria-hidden="true">{icon}</span>
      <div className="min-w-0">
        <dt className="text-[11px] font-bold uppercase tracking-wide text-ink-400">{label}</dt>
        <dd className="text-sm font-medium text-ink-900">{children}</dd>
      </div>
    </div>
  );
}

export function AthleteAvatar({ name, photoUrl, className }: { name: string; photoUrl: string | null; className?: string }) {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
  return photoUrl ? (
    // eslint-disable-next-line @next/next/no-img-element -- foto profilo dell'atleta
    <img src={photoUrl} alt="" className={cn("h-11 w-11 shrink-0 rounded-full object-cover ring-2 ring-white shadow-soft", className)} />
  ) : (
    <span className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-sm font-bold text-white shadow-soft", className)} aria-hidden="true">{initials}</span>
  );
}

/** Il risultato in breve: la medaglia, il piazzamento o la posizione vera. */
export function ResultChip({ placement, rank }: { placement: number | null; rank: number | null }) {
  const { t } = useI18n();
  if (placement == null) return null;
  const label = placement === 0 && rank ? t("evrep.result.rank", { n: rank }) : t.dyn(`club.placement.${placement}`, String(placement));
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold ring-1",
      placement === 1 ? "bg-amber-50 text-amber-800 ring-amber-200" : placement === 2 ? "bg-slate-50 text-slate-700 ring-slate-200"
        : placement === 3 ? "bg-orange-50 text-orange-800 ring-orange-200" : "bg-ink-50 text-ink-700 ring-ink-200")}>
      {MEDALS[placement] ?? "🎽"} {label}
    </span>
  );
}

function AthleteRow({ entry: x, staff }: { entry: EventEntry; staff: boolean }) {
  const { t } = useI18n();
  const c = x.contact;
  return (
    <li className="rounded-2xl bg-white p-3 ring-1 ring-ink-100">
      <div className="flex items-center gap-3">
        <AthleteAvatar name={x.athlete_name} photoUrl={x.photo_url} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-ink-900">{x.athlete_name}</p>
          <p className="text-xs text-ink-500">
            {[x.age != null ? t("evrep.detail.age", { n: x.age }) : null, x.category, x.weight_kg ? `${Number(x.weight_kg)} kg` : null].filter(Boolean).join(" · ") || "—"}
          </p>
        </div>
        <ResultChip placement={x.placement} rank={x.rank} />
      </div>
      {staff && c && (c.phone || c.email) && (
        <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-ink-100 pt-2">
          <span className="mr-auto text-xs text-ink-500">
            {c.is_guardian ? t("evrep.detail.guardian", { name: c.name ?? "—" }) : t("evrep.detail.ownContact")}
          </span>
          {c.phone && <ContactLink href={`tel:${c.phone.replace(/\s/g, "")}`} icon="📞" label={c.phone} />}
          {c.phone && <ContactLink href={`https://wa.me/${whatsappNumber(c.phone)}`} icon="💬" label="WhatsApp" external />}
          {c.email && <ContactLink href={`mailto:${c.email}`} icon="✉️" label={t("evrep.detail.email")} title={c.email} />}
        </div>
      )}
      {staff && c && !c.phone && !c.email && <p className="mt-2 text-xs text-ink-400">{t("evrep.detail.noContact")}</p>}
    </li>
  );
}

function ContactLink({ href, icon, label, external, title }: { href: string; icon: string; label: string; external?: boolean; title?: string }) {
  return (
    <a href={href} title={title} {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      className="inline-flex h-9 items-center gap-1.5 rounded-full bg-ink-50 px-3 text-xs font-semibold text-ink-800 ring-1 ring-ink-200 hover:bg-brand-50 hover:text-brand-700 hover:ring-brand-200">
      <span aria-hidden="true">{icon}</span>{label}
    </a>
  );
}
