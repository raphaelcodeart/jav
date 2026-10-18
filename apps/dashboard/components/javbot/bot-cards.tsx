"use client";

import { useState } from "react";
import { EVENT_KIND_STYLE } from "@/components/club/event-icon";
import { openRegulation, type RegulationArea } from "@/components/club/regulation-link";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import type { BotAction, BotCard, BotEventCard, BotSourceCard } from "@/lib/javbot";

// Le schede sotto un messaggio di JAVBOT (BotMessageRead.cards): le gare
// proposte, con i bottoni che rimandano una frase alla chat («Inscrever
// Marco»), e le fonti dei documenti da cui viene la risposta. Il
// regolamento si apre solo dove c'è un'area con i permessi per chiederlo
// (`regulationArea`): sul sito pubblico no.

const isEvent = (c: BotCard): c is BotEventCard => c.type === "event" && "title" in c;
const isSource = (c: BotCard): c is BotSourceCard => c.type === "source" && "n" in c;

const chip = "inline-flex min-h-10 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-semibold transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 disabled:cursor-not-allowed disabled:opacity-50";

export function BotCards({ cards, regulationArea, busy, onSay }: {
  cards: BotCard[]; regulationArea?: RegulationArea; busy: boolean; onSay: (text: string) => void;
}) {
  const { t } = useI18n();
  const events = cards.filter(isEvent);
  const sources = cards.filter(isSource);
  const [error, setError] = useState<string | null>(null);

  async function regulation(id: string) {
    if (!regulationArea) return;
    setError(null);
    try {
      await openRegulation(id, regulationArea);
    } catch (e) {
      setError((e as Error).message || t("jbx.reg.openError"));
    }
  }

  return (
    <div className="flex w-full max-w-[92%] flex-col gap-2">
      {events.map((c, i) => (
        <EventCard key={`${c.competition_id ?? c.title}-${i}`} card={c} busy={busy} onSay={onSay}
          onRegulation={regulationArea && c.has_regulation && c.competition_id ? () => void regulation(c.competition_id!) : undefined} />
      ))}
      {sources.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 px-1">
          <span className="mr-0.5 text-[11px] font-bold uppercase tracking-wide text-ink-400">{t("jbx.sources")}</span>
          {sources.map((s) => {
            const canOpen = Boolean(regulationArea && s.source === "EVENT" && s.competition_id);
            const label = (
              <>
                <span className="font-bold text-brand-700">[{s.n}]</span>
                {s.source === "DATA" && <span aria-hidden="true">🗂️</span>}
                {s.source === "EVENT" && <span aria-hidden="true">📄</span>}
                <span className="max-w-[12rem] truncate">{s.title}</span>
                {s.page != null && <span className="text-ink-400">· {t("jbx.page", { page: s.page })}</span>}
              </>
            );
            const title = s.source === "DATA" ? t("jbx.chip.DATA") : s.source === "EVENT" ? t("jbx.chip.EVENT") : t("jbx.chip.UPLOAD");
            return canOpen ? (
              <button key={s.n} type="button" title={`${title} · ${t("jbx.reg.download")}`} onClick={() => void regulation(s.competition_id!)}
                className="inline-flex min-h-8 cursor-pointer items-center gap-1 rounded-full bg-white px-2.5 text-[11px] font-medium text-ink-700 ring-1 ring-brand-200 hover:bg-brand-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400">
                {label}
              </button>
            ) : (
              <span key={s.n} title={title} className="inline-flex min-h-8 items-center gap-1 rounded-full bg-white px-2.5 text-[11px] font-medium text-ink-700 ring-1 ring-ink-200">
                {label}
              </span>
            );
          })}
        </div>
      )}
      {error && <p role="alert" className="px-1 text-xs text-rose-700">{error}</p>}
    </div>
  );
}

function EventCard({ card: c, busy, onSay, onRegulation }: {
  card: BotEventCard; busy: boolean; onSay: (text: string) => void; onRegulation?: () => void;
}) {
  const { t, fmt } = useI18n();
  const style = EVENT_KIND_STYLE[c.kind ?? "COMPETITION"] ?? EVENT_KIND_STYLE.OTHER!;
  // Mezzogiorno: una data senza ora non deve scivolare al giorno prima col fuso.
  const day = (iso: string) => fmt.date(new Date(`${iso.slice(0, 10)}T12:00:00`), { weekday: "short", day: "numeric", month: "short" });
  const dates = c.end_date && c.end_date.slice(0, 10) !== c.date.slice(0, 10) ? `${day(c.date)} – ${day(c.end_date)}` : day(c.date);
  const says = (c.actions ?? []).filter((a: BotAction) => a.type === "say" && a.value);
  return (
    <article className="overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-100">
      <div className="flex gap-3 p-3.5">
        <span aria-hidden="true" className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br text-2xl text-white shadow-soft", style.bg)}>
          {style.icon}
        </span>
        <div className="min-w-0 flex-1">
          <h4 className="text-[15px] font-semibold leading-snug text-ink-900">{c.title}</h4>
          <p className="mt-0.5 text-[13px] text-ink-600">📅 {dates}</p>
          {c.location && <p className="text-[13px] text-ink-600">📍 {c.location}</p>}
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {c.deadline && (
              <span className="rounded-full bg-accent-100 px-2.5 py-0.5 text-[11px] font-semibold text-accent-900">
                ⏳ {t("jbx.card.deadline", { date: day(c.deadline) })}
              </span>
            )}
            <span className={cn("rounded-full px-2.5 py-0.5 text-[11px] font-semibold", c.fee_cents ? "bg-brand-50 text-brand-700" : "bg-emerald-50 text-emerald-700")}>
              {c.fee_cents ? fmt.euro(c.fee_cents) : t("jbx.card.free")}
            </span>
          </div>
        </div>
      </div>
      {(says.length > 0 || onRegulation) && (
        <div className="flex flex-wrap gap-2 border-t border-ink-100 bg-ink-50/60 px-3.5 py-2.5">
          {says.map((a, i) => (
            <button key={`${a.value}-${i}`} type="button" disabled={busy} onClick={() => onSay(a.value!)}
              className={cn(chip, "bg-gradient-to-b from-brand-500 to-brand-600 text-white shadow-brand hover:from-brand-400")}>
              {a.label}
            </button>
          ))}
          {onRegulation && (
            <button type="button" onClick={onRegulation} className={cn(chip, "bg-white text-ink-800 ring-1 ring-ink-200 hover:text-brand-700 hover:ring-brand-300")}>
              <span aria-hidden="true">📄</span> {t("jbx.reg.short")}
            </button>
          )}
        </div>
      )}
    </article>
  );
}
