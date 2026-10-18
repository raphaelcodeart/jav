"use client";

import { motion } from "motion/react";
import { AthleteCard } from "@/components/ui/gamification";
import { Badge } from "@/components/ui/badge";
import { BeltBadge } from "@/components/ui/belt";
import { ProgressBar } from "@/components/ui/progress";
import { CERTIFICATE_LABELS, type AthleteCard as AthleteCardData } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";
import { useClubFeatures } from "@/components/club/jav-courses";

/** One athlete of the family as a trading card: belt, level and XP, and the
 *  three things a parent must not miss -- what is due, the medical
 *  certificate, the next competition. */
export function AthleteTile({ athlete, onOpen }: { athlete: AthleteCardData; onOpen: () => void }) {
  const { t, fmt } = useI18n();
  const { euro, shortDate } = fmt;
  // Nei corsi JAV niente cinture né medaglie (club/kinds.py).
  const features = useClubFeatures();
  const certCode = CERTIFICATE_LABELS[athlete.certificate.status] ? athlete.certificate.status : "MISSING";
  const cert = CERTIFICATE_LABELS[certCode]!;
  const xpInLevel = athlete.xp - athlete.level_xp_floor;
  const xpForLevel = Math.max(1, athlete.next_level_xp - athlete.level_xp_floor);
  return (
    <motion.div layout initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
      <button onClick={onOpen} className="block w-full text-left cursor-pointer" aria-label={t("athlete.openCard", { name: athlete.first_name })}>
        <AthleteCard
          name={`${athlete.first_name} ${athlete.last_name}`}
          photoUrl={athlete.photo_url}
          level={features.achievements ? athlete.level : undefined}
          points={features.ranking ? athlete.ranking_points : undefined}
          subtitle={`${t("club.yearsOld", { n: athlete.age })} · ${athlete.plan?.name ?? t("club.noPlan")}`}
          belt={features.belts ? <BeltBadge belt={athlete.belt} /> : undefined}
          footer={
            <div className="space-y-3">
              {features.achievements && <div>
                <div className="flex items-center justify-between text-[11px] font-semibold text-ink-500 mb-1.5">
                  <span>{t("club.level", { n: athlete.level })}</span>
                  <span className="tabular-nums">
                    {xpInLevel}/{xpForLevel} XP
                  </span>
                </div>
                <ProgressBar value={xpInLevel} max={xpForLevel} tone="accent" label={t("athlete.xpToNext")} />
              </div>}
              <div className="flex flex-wrap justify-center gap-1.5">
                {features.certificates && (
                  <Badge tone={cert.tone} dot>
                    {t.dyn(`club.cert.${certCode}`, cert.label)}
                  </Badge>
                )}
                {athlete.due_cents > 0 ? (
                  <Badge tone={athlete.overdue_count > 0 ? "danger" : "warning"} dot>
                    {athlete.overdue_count > 0 ? t("athlete.overdueFees") : t("family.statDue")} {euro(athlete.due_cents)}
                  </Badge>
                ) : (
                  <Badge tone="success" dot>
                    {t("athlete.upToDate")}
                  </Badge>
                )}
              </div>
              <div className={`grid ${features.courses ? "grid-cols-1" : features.competitions ? "grid-cols-3" : "grid-cols-2"} gap-2 text-center`}>
                <Stat label={t("athlete.attendances")} value={athlete.attendances} />
                {features.competitions && <Stat label={t("athlete.medals")} value={athlete.medals.gold + athlete.medals.silver + athlete.medals.bronze} />}
                {features.achievements && <Stat label={t("athlete.achievements")} value={athlete.achievements_earned} />}
              </div>
              {athlete.next_competition && (
                <p className="rounded-xl bg-brand-50 px-3 py-2 text-xs text-brand-800 text-center">
                  🏟️ <strong>{athlete.next_competition.name}</strong> · {shortDate(athlete.next_competition.starts_on)}
                </p>
              )}
            </div>
          }
        />
      </button>
    </motion.div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl bg-white ring-1 ring-ink-100 py-2">
      <p className="font-display text-lg text-ink-900 tabular-nums">{value}</p>
      <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-500">{label}</p>
    </div>
  );
}
