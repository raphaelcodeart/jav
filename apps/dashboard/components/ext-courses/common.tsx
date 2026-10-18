"use client";

import { cn } from "@/lib/cn";
import type { ExtCourse, ExtGroup } from "@/lib/ext-courses";
import { useI18n } from "@/lib/i18n/provider";

/** Il nome del giorno nella lingua di chi legge: il 1° gennaio 2024 era
 *  lunedì, e 0 è lunedì anche per l'API. */
export function useWeekdayName() {
  const { fmt } = useI18n();
  return (d: number) => fmt.date(new Date(2024, 0, 1 + d), { weekday: "long" });
}

/** "Segunda · 15:30–16:00 · até 6 anos". */
export function useGroupLine() {
  const { t } = useI18n();
  const weekday = useWeekdayName();
  return (g: ExtGroup) => [weekday(g.weekday), `${g.starts_at}–${g.ends_at}`, agesLabel(t, g)].filter(Boolean).join(" · ");
}

export function agesLabel(t: ReturnType<typeof useI18n>["t"], g: Pick<ExtGroup, "min_age" | "max_age">): string | null {
  if (g.min_age == null && g.max_age == null) return null;
  if (g.max_age == null) return t("site.agesFrom", { min: g.min_age ?? 0 });
  if (g.min_age == null) return t("site.agesUpTo", { max: g.max_age });
  return t("site.agesRange", { min: g.min_age, max: g.max_age });
}

/** Il logo della scuola in un riquadro bianco, intero; senza logo l'iniziale. */
export function SchoolBadge({ course, className }: { course: Pick<ExtCourse, "school_name" | "school_logo_url">; className?: string }) {
  return (
    <span className={cn("flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-white p-1 ring-1 ring-ink-100", className)}>
      {course.school_logo_url ? (
        // eslint-disable-next-line @next/next/no-img-element -- logo caricato dal superadmin
        <img src={course.school_logo_url} alt="" className="h-full w-full object-contain" />
      ) : (
        <span className="font-display text-lg text-brand-600" aria-hidden="true">{course.school_name.charAt(0).toUpperCase() || "🏫"}</span>
      )}
    </span>
  );
}

/** "Outubro 2026" da "2026-10". */
export function usePeriodLabel() {
  const { fmt } = useI18n();
  return (period: string) => {
    const [y, m] = period.split("-").map(Number);
    return y && m ? fmt.date(new Date(y, m - 1, 1), { month: "long", year: "numeric" }) : period;
  };
}

export function useMethodLabel() {
  const { t } = useI18n();
  return (method: string | null) => (method ? t.dyn(`ext.method.${method}`, method) : "—");
}
