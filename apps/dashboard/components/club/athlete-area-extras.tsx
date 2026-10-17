"use client";

import { Countdown, moment } from "@/components/site/countdown";
import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { EventIcon } from "@/components/club/event-icon";
import { ParticipateButton } from "@/components/club/participate-button";
import { clubGet, clubSend, type AthleteDetail, type Competition } from "@/lib/club";
import type { MessageKey } from "@/lib/i18n/messages/it";
import { useI18n } from "@/lib/i18n/provider";

export interface AthleteMoney {
  wallet_balance_cents: number;
  support_total_cents: number;
  support_by_category: Record<string, number>;
  invested_cents: number;
  supports: { id: string; category: string; amount_cents: number; note: string | null; paid_on: string }[];
}

export const SUPPORT_CATEGORIES = ["TRANSPORT", "MATERIAL", "COMPETITION", "EXAM", "TRAINING_CAMP", "OTHER"] as const;
export const SUPPORT_ICONS: Record<string, string> = {
  TRANSPORT: "🚐", MATERIAL: "🥋", COMPETITION: "🏆", EXAM: "🎓", TRAINING_CAMP: "⛺", OTHER: "✨",
};

/** Il riquadro dei soldi nella scheda dell'atleta (club/support.py): il saldo
 *  del wallet della famiglia, quanto il club ha pagato per lui (trasporto,
 *  materiale, gare, esami, stage) e quanto ha investito. Senza aiuti e senza
 *  saldo non c'è niente da dire, e il riquadro non appare. */
export function AthleteMoneyCard({ athleteId, path }: { athleteId: string; path?: string }) {
  const { t, fmt } = useI18n();
  const { data } = useQuery({
    queryKey: ["club", "athlete-money", athleteId],
    queryFn: () => clubGet<AthleteMoney>(path ?? `/athlete-area/${athleteId}/money`),
    retry: false,
  });
  if (!data) return null;
  if (!data.wallet_balance_cents && !data.support_total_cents && !data.invested_cents) return null;
  const cats = Object.entries(data.support_by_category).sort((a, b) => b[1] - a[1]);
  return (
    <section className="overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/5">
      <div className="grid gap-px bg-ink-100 sm:grid-cols-3">
        <div className="bg-gradient-to-br from-brand-600 to-brand-800 p-4 text-white">
          <p className="text-[11px] font-bold uppercase tracking-wider text-white/75">👛 {t("money.wallet")}</p>
          <p className="mt-1 font-display text-3xl leading-none">{fmt.euro(data.wallet_balance_cents)}</p>
        </div>
        <div className="bg-white p-4">
          <p className="text-[11px] font-bold uppercase tracking-wider text-emerald-700">💚 {t("money.support")}</p>
          <p className="mt-1 font-display text-3xl leading-none text-ink-900">{fmt.euro(data.support_total_cents)}</p>
          <p className="mt-1 text-xs text-ink-500">{t("money.supportHint")}</p>
        </div>
        <div className="bg-white p-4">
          <p className="text-[11px] font-bold uppercase tracking-wider text-accent-700">📈 {t("money.invested")}</p>
          <p className="mt-1 font-display text-3xl leading-none text-ink-900">{fmt.euro(data.invested_cents)}</p>
        </div>
      </div>
      {cats.length > 0 && (
        <div className="flex flex-wrap gap-2 border-t border-ink-100 px-4 py-3">
          {cats.map(([cat, cents]) => (
            <span key={cat} className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-200">
              {SUPPORT_ICONS[cat] ?? "✨"} {t(`support.cat.${cat}` as MessageKey)} · {fmt.euro(cents)}
            </span>
          ))}
        </div>
      )}
      {data.supports.length > 0 && (
        <ul className="divide-y divide-ink-100 border-t border-ink-100 text-sm">
          {data.supports.slice(0, 5).map((s) => (
            <li key={s.id} className="flex items-center gap-3 px-4 py-2">
              <span aria-hidden="true">{SUPPORT_ICONS[s.category] ?? "✨"}</span>
              <span className="min-w-0 flex-1 truncate text-ink-700">
                {t(`support.cat.${s.category}` as MessageKey)}{s.note ? ` — ${s.note}` : ""}
              </span>
              <span className="text-xs text-ink-400">{fmt.shortDate(s.paid_on)}</span>
              <span className="font-semibold text-ink-900">{fmt.euro(s.amount_cents)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

interface AreaCompetition extends Competition {
  registrations_open: boolean;
  entry_status: string | null;
  viewer_is_holder: boolean;
}

/** Le prove in arrivo nell'area dell'atleta. L'atleta non si iscrive da solo
 *  (spesso è minorenne): «Voglio partecipare» avvisa il titolare del conto per
 *  email e notifica, una volta per prova; il titolare iscrive da qui. Con
 *  delle quote scadute si paga prima (participate-button.tsx). */
export function AreaCompetitions({ athlete }: { athlete: AthleteDetail }) {
  const { t, fmt } = useI18n();
  const { data, isLoading } = useQuery({
    queryKey: ["club", "area-competitions", athlete.id],
    queryFn: () => clubGet<AreaCompetition[]>(`/athlete-area/${athlete.id}/competitions`),
  });

  return (
    <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
      <h2 className="text-xl text-ink-900">🏆 {t("area.nav.competitions")}</h2>
      <p className="mt-1 text-sm text-ink-500">{t("area.compIntro")}</p>
      {isLoading && <div className="mt-4 space-y-3"><Skeleton className="h-20" /><Skeleton className="h-20" /></div>}
      {data && data.length === 0 && <p className="mt-4 rounded-2xl bg-ink-50 p-4 text-sm text-ink-500">{t("area.compNone")}</p>}
      <ul className="mt-4 space-y-3">
        {data?.map((c, i) => (
          <motion.li key={c.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
            className="flex flex-col gap-3 rounded-2xl bg-ink-50/70 p-4 ring-1 ring-ink-900/5 sm:flex-row sm:items-center">
            <EventIcon kind={c.kind} imageUrl={c.image_url ?? null} size="md" />
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-ink-900">{c.name}</p>
              <p className="text-xs text-ink-500">
                📅 {fmt.shortDate(c.starts_on)}{c.location ? ` · 📍 ${c.location}` : ""}
                {c.registrations_open && ` · ⏳ ${t("area.compDeadline", { date: fmt.shortDate(c.registration_deadline) })}`}
              </p>
              {c.registrations_open && !c.entry_status && (
                <Countdown className="mt-1.5" target={moment(c.registration_deadline, null, "endOfDay")} label={t("countdown.registrations")} />
              )}
            </div>
            {c.entry_status ? (
              <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-800">✓ {t("area.compEntered")}</span>
            ) : !c.registrations_open ? (
              <span className="rounded-full bg-ink-100 px-3 py-1 text-xs font-semibold text-ink-500">{t("area.compClosed")}</span>
            ) : (
              // Lo stesso «Quero participar» del sito: controlla i debiti, poi
              // iscrive (titolare) o avvisa chi iscrive (atleta).
              <ParticipateButton competitionId={c.id} clubSlug={null} open />
            )}
          </motion.li>
        ))}
      </ul>
    </section>
  );
}
