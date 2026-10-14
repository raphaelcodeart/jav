"use client";

import { motion } from "motion/react";
import { type ApiBelt, beltFor, fromApiBelt, nextBelt } from "@/lib/belts";
import { cn } from "@/lib/cn";
import { ProgressBar } from "@/components/ui/progress";
import { useI18n } from "@/lib/i18n/provider";
import type { Translator } from "@/lib/i18n/translate";

/** The belt's name in the reader's language; the API label (Italian) for a
 *  code the dictionaries do not know. */
export function beltLabel(t: Translator, code: string, fallback: string): string {
  if (code.startsWith("BLACK_")) return t("belt.BLACK", { n: code.split("_")[1] ?? "" });
  return t.dyn(`belt.${code}`, fallback);
}

/** A belt drawn as a belt: the band with its knot, in the grade's colors. */
export function BeltBadge({ code, belt: apiBelt, size = "md", showLabel = true, className }: { code?: string | null; belt?: ApiBelt | null; size?: "sm" | "md" | "lg"; showLabel?: boolean; className?: string }) {
  const { t } = useI18n();
  const belt = apiBelt ? fromApiBelt(apiBelt) : beltFor(code);
  const [a, b] = belt.colors;
  const dims = { sm: "h-3 w-14", md: "h-4 w-20", lg: "h-6 w-32" }[size];
  const dan = belt.code.startsWith("BLACK_") ? Number(belt.code.split("_")[1]) : 0;
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span
        className={cn("relative inline-block rounded-[3px] shadow-sm ring-1 ring-ink-900/15", dims)}
        style={{ background: b ? `linear-gradient(90deg, ${a} 50%, ${b} 50%)` : a }}
        aria-hidden="true"
      >
        <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-[140%] w-[18%] rounded-[2px] ring-1 ring-ink-900/20" style={{ background: a }} />
        {dan > 0 && (
          <span className="absolute right-1 top-1/2 -translate-y-1/2 flex gap-[2px]">
            {Array.from({ length: Math.min(dan, 5) }).map((_, i) => (
              <span key={i} className="h-[60%] min-h-1.5 w-[3px] bg-accent-400 rounded-[1px]" />
            ))}
          </span>
        )}
      </span>
      {showLabel && <span className="text-sm font-semibold text-ink-800">{beltLabel(t, belt.code, belt.label)}</span>}
    </span>
  );
}

/** Progress toward the next belt, like an XP bar. `value`/`max` come from
 *  the API (presences, months at the grade...), never invented here. */
export function BeltProgress({ code, value, max }: { code: string | null | undefined; value: number; max: number }) {
  const { t } = useI18n();
  const next = nextBelt(code);
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <BeltBadge code={code} size="sm" />
        {next ? (
          <motion.span initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} className="flex items-center gap-2 text-xs text-ink-500">
            {t("belt.next")} <BeltBadge code={next.code} size="sm" showLabel={false} />
          </motion.span>
        ) : (
          <span className="text-xs font-semibold text-accent-700">{t("belt.maxGrade")}</span>
        )}
      </div>
      {next && <ProgressBar value={value} max={max} label={t("belt.progressTo", { belt: beltLabel(t, next.code, next.label) })} />}
    </div>
  );
}
