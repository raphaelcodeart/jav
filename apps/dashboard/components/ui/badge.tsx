"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

export type Tone = "neutral" | "brand" | "accent" | "success" | "warning" | "danger" | "info";

const TONES: Record<Tone, string> = {
  neutral: "bg-ink-100 text-ink-700 ring-ink-200",
  brand: "bg-brand-50 text-brand-700 ring-brand-200",
  accent: "bg-accent-100 text-accent-800 ring-accent-300",
  success: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  warning: "bg-amber-50 text-amber-800 ring-amber-200",
  danger: "bg-rose-50 text-rose-700 ring-rose-200",
  info: "bg-sky-50 text-sky-700 ring-sky-200",
};

const DOTS: Record<Tone, string> = {
  neutral: "bg-ink-400",
  brand: "bg-brand-500",
  accent: "bg-accent-500",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-rose-500",
  info: "bg-sky-500",
};

export function Badge({ tone = "neutral", dot = false, className, children }: { tone?: Tone; dot?: boolean; className?: string; children: ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset", TONES[tone], className)}>
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full", DOTS[tone])} />}
      {children}
    </span>
  );
}

/** Fee states of the club portal, worded for a parent. */
export const FEE_STATUS: Record<string, { label: string; tone: Tone }> = {
  DUE: { label: "Da pagare", tone: "warning" },
  OVERDUE: { label: "Scaduta", tone: "danger" },
  PAID: { label: "Pagata", tone: "success" },
  WAIVED: { label: "Condonata", tone: "neutral" },
};

export function FeeStatusPill({ status, overdue = false }: { status: string; overdue?: boolean }) {
  const { t } = useI18n();
  const code = overdue && status === "DUE" ? "OVERDUE" : status;
  const s = FEE_STATUS[code] ?? { label: status, tone: "neutral" as Tone };
  return <Badge tone={s.tone} dot>{t.dyn(`club.feeStatus.${code}`, s.label)}</Badge>;
}
