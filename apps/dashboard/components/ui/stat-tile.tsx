"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { CountUp } from "@/components/ui/count-up";

type Accent = "brand" | "accent" | "ink" | "success";

const ACCENTS: Record<Accent, { icon: string; glow: string }> = {
  brand: { icon: "from-brand-400 to-brand-600 text-white", glow: "bg-brand-500/15" },
  accent: { icon: "from-accent-200 to-accent-400 text-ink-900", glow: "bg-accent-400/25" },
  ink: { icon: "from-ink-600 to-ink-900 text-white", glow: "bg-ink-500/10" },
  success: { icon: "from-emerald-400 to-emerald-600 text-white", glow: "bg-emerald-500/15" },
};

/** A KPI tile: big animated number in the display font, a glossy icon chip,
 *  and a soft glow that follows the accent. */
export function StatTile({
  label, value, format, icon, accent = "brand", hint, onClick,
}: {
  label: ReactNode;
  value: number;
  format?: (n: number) => string;
  icon?: ReactNode;
  accent?: Accent;
  hint?: ReactNode;
  onClick?: () => void;
}) {
  const a = ACCENTS[accent];
  return (
    <motion.div
      whileHover={{ y: -4 }}
      whileTap={onClick ? { scale: 0.98 } : undefined}
      transition={{ type: "spring", stiffness: 400, damping: 26 }}
      onClick={onClick}
      className={cn("glass-card relative overflow-hidden rounded-2xl p-5", onClick && "cursor-pointer")}
    >
      <div className={cn("absolute -right-8 -top-10 h-32 w-32 rounded-full blur-2xl", a.glow)} aria-hidden="true" />
      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">{label}</p>
          <p className="font-display text-3xl text-ink-900 mt-2 tabular-nums">
            <CountUp value={value} format={format} />
          </p>
          {hint && <p className="text-xs text-ink-500 mt-1.5">{hint}</p>}
        </div>
        {icon && (
          <div className={cn("h-11 w-11 shrink-0 rounded-2xl bg-gradient-to-br flex items-center justify-center shadow-soft ring-1 ring-inset ring-white/30", a.icon)}>
            {icon}
          </div>
        )}
      </div>
    </motion.div>
  );
}
