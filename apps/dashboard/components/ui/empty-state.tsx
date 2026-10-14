"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

export function EmptyState({ icon, title, text, action }: { icon?: ReactNode; title: ReactNode; text?: ReactNode; action?: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      className="glass-card rounded-3xl px-6 py-12 text-center flex flex-col items-center"
    >
      <div className="relative mb-5">
        <div className="absolute inset-0 rounded-full bg-accent-300/40 blur-xl" aria-hidden="true" />
        <div className="relative h-16 w-16 rounded-2xl bg-gradient-to-br from-white to-ink-50 ring-1 ring-ink-100 shadow-soft flex items-center justify-center text-brand-500 animate-float">
          {icon ?? (
            <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M20 13V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v6m16 0v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4m16 0h-3.6a1 1 0 0 0-.9.55l-.9 1.9a1 1 0 0 1-.9.55h-3.4a1 1 0 0 1-.9-.55l-.9-1.9a1 1 0 0 0-.9-.55H4" />
            </svg>
          )}
        </div>
      </div>
      <h3 className="text-lg text-ink-900">{title}</h3>
      {text && <p className="text-sm text-ink-500 mt-1.5 max-w-sm">{text}</p>}
      {action && <div className="mt-5">{action}</div>}
    </motion.div>
  );
}
