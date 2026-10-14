"use client";

import { motion, type HTMLMotionProps } from "motion/react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface CardProps extends HTMLMotionProps<"div"> {
  /** Lifts on hover and presses on tap -- for cards that are a button. */
  interactive?: boolean;
  padded?: boolean;
  children?: ReactNode;
}

export function Card({ interactive = false, padded = true, className, children, ...rest }: CardProps) {
  return (
    <motion.div
      whileHover={interactive ? { y: -3 } : undefined}
      whileTap={interactive ? { scale: 0.985 } : undefined}
      transition={{ type: "spring", stiffness: 400, damping: 28 }}
      className={cn(
        "glass-card rounded-2xl",
        padded && "p-5",
        interactive && "cursor-pointer",
        className,
      )}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

export function CardHeader({ title, subtitle, action, icon }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 mb-4">
      <div className="flex items-center gap-3 min-w-0">
        {icon && (
          <div className="h-10 w-10 shrink-0 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center">{icon}</div>
        )}
        <div className="min-w-0">
          <h3 className="text-base text-ink-900 truncate">{title}</h3>
          {subtitle && <p className="text-sm text-ink-500 mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}
