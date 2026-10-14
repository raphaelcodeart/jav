"use client";

import { motion } from "motion/react";
import { useId, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface TabItem {
  key: string;
  label: ReactNode;
  count?: number;
}

/** Segmented tabs with a sliding pill under the active one (shared layout
 *  animation). Scrolls horizontally on narrow screens instead of wrapping. */
export function Tabs({ items, value, onChange, className }: { items: TabItem[]; value: string; onChange: (key: string) => void; className?: string }) {
  const id = useId();
  return (
    <div className={cn("inline-flex max-w-full overflow-x-auto rounded-2xl bg-ink-100/80 p-1 gap-1", className)} role="tablist">
      {items.map((item) => {
        const active = item.key === value;
        return (
          <button
            key={item.key}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.key)}
            className={cn(
              "relative shrink-0 rounded-xl px-4 h-9 text-sm font-semibold cursor-pointer transition-colors",
              active ? "text-ink-900" : "text-ink-500 hover:text-ink-800",
            )}
          >
            {active && (
              <motion.span
                layoutId={`tab-pill-${id}`}
                className="absolute inset-0 rounded-xl bg-white shadow-soft"
                transition={{ type: "spring", stiffness: 500, damping: 36 }}
              />
            )}
            <span className="relative flex items-center gap-2">
              {item.label}
              {item.count !== undefined && item.count > 0 && (
                <span className="rounded-full bg-brand-500 text-white text-[10px] font-bold px-1.5 min-w-5 h-5 inline-flex items-center justify-center">
                  {item.count}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}
