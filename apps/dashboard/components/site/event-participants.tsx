"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useMemo, useRef, useState } from "react";
import { BeltBadge } from "@/components/ui/belt";
import { Pagination, usePaged } from "@/components/ui/pagination";
import { JudokaModal } from "@/components/site/judoka-modal";
import { ClubLogo, Place, initials } from "@/components/site/ranking-explorer";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import type { EventDetail } from "@/lib/public-site";

type Participant = EventDetail["participants"][number];

function fold(s: string) {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** Gli iscritti di un evento con le righe del ranking (ranking-explorer.tsx):
 *  foto o iniziali con il logo del club, medaglia, punti. Chi ha la scheda
 *  pubblica si apre nel popup del judoca; gli altri sono solo «Nome I.». */
export function EventParticipants({ participants, withResults }: { participants: Participant[]; withResults: boolean }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const shown = useMemo(() => {
    const needle = fold(q.trim());
    return needle ? participants.filter((p) => fold(`${p.display_name} ${p.club?.name ?? ""} ${p.category ?? ""}`).includes(needle)) : participants;
  }, [participants, q]);
  const paged = usePaged(shown, 20);
  const list = useRef<HTMLOListElement>(null);
  const max = Math.max(1, ...participants.map((p) => p.points));

  return (
    <MotionConfig reducedMotion="user">
      {participants.length > 8 && (
        <div className="relative mb-5">
          <span className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-xl" aria-hidden="true">🔎</span>
          <input
            type="search" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder={t("site.event.searchJudoka")} aria-label={t("site.event.searchJudoka")}
            className="h-14 w-full rounded-2xl bg-white pl-14 pr-4 text-base sm:pr-28 text-ink-900 shadow-soft ring-1 ring-ink-900/10 placeholder:text-ink-400 focus:outline-none focus:ring-4 focus:ring-accent-300/60"
          />
          <span className="pointer-events-none absolute right-5 top-1/2 hidden -translate-y-1/2 text-xs font-semibold uppercase tracking-wider text-ink-400 sm:block">
            {t("site.rankx.found", { n: shown.length })}
          </span>
        </div>
      )}
      {shown.length === 0 ? (
        <p className="rounded-2xl bg-ink-50 p-8 text-center text-ink-500">{t("site.rankx.noMatch", { q })}</p>
      ) : (
        <ol ref={list} className="scroll-mt-28 space-y-2">
          <AnimatePresence initial={false}>
            {paged.items.map((p, i) => {
              const medal = p.placement !== null && p.placement >= 1 && p.placement <= 3;
              const body = (
                <>
                  {withResults && p.points > 0 && (
                    <span aria-hidden="true" className="absolute inset-y-0 left-0 bg-gradient-to-r from-accent-100/70 to-transparent transition-all group-hover:from-accent-200/70"
                      style={{ width: `${Math.max(8, (p.points / max) * 100)}%` }} />
                  )}
                  <span className="relative flex w-full items-center gap-3 sm:gap-4">
                    {withResults && (medal
                      ? <Place position={p.placement as number} />
                      : <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ink-100 text-sm text-ink-400" aria-hidden="true">🥋</span>)}
                    <span className="relative shrink-0">
                      {p.photo_url ? (
                        // eslint-disable-next-line @next/next/no-img-element -- foto pubblicata con il consenso
                        <img src={p.photo_url} alt="" className="h-14 w-14 rounded-2xl object-cover shadow ring-2 ring-white sm:h-16 sm:w-16" loading="lazy" />
                      ) : (
                        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-ink-700 to-ink-900 font-display text-lg text-white shadow ring-2 ring-white sm:h-16 sm:w-16">{initials(p.display_name)}</span>
                      )}
                      {p.club && <span className="absolute -bottom-1.5 -right-1.5"><ClubLogo club={p.club} /></span>}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className={cn("block truncate text-lg font-semibold text-ink-900", p.has_page && "group-hover:text-brand-700")}>{p.display_name}</span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-500">
                        {p.club && <span className="font-semibold text-ink-700">{p.club.name}</span>}
                        <span>{t.dyn(`club.ageBand.${p.age_band}`, p.age_band)}</span>
                        {p.category && <span>⚖️ {p.category}</span>}
                        {p.belt && <span className="hidden sm:inline"><BeltBadge code={p.belt} size="sm" /></span>}
                      </span>
                    </span>
                    {withResults && p.placement !== null && (
                      <span className="shrink-0 text-right">
                        <span className="block font-display text-2xl leading-none text-brand-600 sm:text-3xl">{p.points}</span>
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">
                          {t.dyn(`club.placement.${p.placement}`, String(p.placement))}
                        </span>
                      </span>
                    )}
                    {p.has_page && !withResults && <span className="shrink-0 text-xl text-ink-300 transition group-hover:translate-x-0.5 group-hover:text-brand-600" aria-hidden="true">›</span>}
                  </span>
                </>
              );
              const box = cn(
                "group relative flex w-full items-center gap-3 overflow-hidden rounded-2xl bg-white p-3 text-left shadow-soft ring-1 ring-ink-900/5 sm:gap-4 sm:p-4",
                medal && withResults && "ring-2 ring-accent-200",
                p.has_page && "cursor-pointer transition hover:-translate-y-0.5 hover:shadow-lift hover:ring-accent-300",
              );
              return (
                <motion.li key={p.athlete_id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                  transition={{ delay: q ? 0 : Math.min(i, 12) * 0.025 }}>
                  {p.has_page
                    ? <button type="button" onClick={() => setOpen(p.athlete_id)} className={box}>{body}</button>
                    : <div className={box}>{body}</div>}
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ol>
      )}
      <Pagination className="mt-6" page={paged.page} pages={paged.pages} onChange={(n) => { paged.setPage(n); list.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }} />
      <JudokaModal id={open} onClose={() => setOpen(null)} />
    </MotionConfig>
  );
}
