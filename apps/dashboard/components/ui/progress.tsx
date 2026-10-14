"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/cn";

/** A progress bar that fills with a spring when it appears, with a moving
 *  sheen on the filled part -- the XP bar of the club portal. */
export function ProgressBar({ value, max = 100, className, tone = "brand", label }: { value: number; max?: number; className?: string; tone?: "brand" | "accent" | "success"; label?: string }) {
  const pct = Math.max(0, Math.min(100, (value / Math.max(1, max)) * 100));
  const fill = {
    brand: "from-brand-400 via-brand-500 to-brand-600",
    accent: "from-accent-300 to-accent-500",
    success: "from-emerald-400 to-emerald-600",
  }[tone];
  return (
    <div className={cn("h-3 w-full rounded-full bg-ink-100 overflow-hidden ring-1 ring-inset ring-ink-200/60", className)} role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-label={label}>
      <motion.div
        initial={{ width: 0 }}
        whileInView={{ width: `${pct}%` }}
        viewport={{ once: true }}
        transition={{ type: "spring", stiffness: 60, damping: 16 }}
        className={cn("h-full rounded-full bg-gradient-to-r relative overflow-hidden", fill)}
      >
        <span className="absolute inset-0 shine-sweep" aria-hidden="true" />
      </motion.div>
    </div>
  );
}
