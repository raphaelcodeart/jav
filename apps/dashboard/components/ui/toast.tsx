"use client";

import { AnimatePresence, motion } from "motion/react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";

type ToastTone = "success" | "error" | "info";
interface ToastItem { id: number; tone: ToastTone; title: string; text?: string }

const ToastContext = createContext<((t: Omit<ToastItem, "id">) => void) | null>(null);

const TONE: Record<ToastTone, { ring: string; icon: ReactNode }> = {
  success: {
    ring: "ring-emerald-200",
    icon: <span className="h-8 w-8 rounded-full bg-emerald-500 text-white flex items-center justify-center">✓</span>,
  },
  error: {
    ring: "ring-rose-200",
    icon: <span className="h-8 w-8 rounded-full bg-rose-500 text-white flex items-center justify-center">!</span>,
  },
  info: {
    ring: "ring-ink-200",
    icon: <span className="h-8 w-8 rounded-full bg-ink-900 text-white flex items-center justify-center">i</span>,
  },
};

/** Small confirmations that slide in at the top and leave on their own. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((t: Omit<ToastItem, "id">) => {
    const id = Date.now() + Math.random();
    setItems((list) => [...list, { ...t, id }]);
    setTimeout(() => setItems((list) => list.filter((x) => x.id !== id)), 4200);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="fixed top-4 inset-x-0 z-[200] flex flex-col items-center gap-2 pointer-events-none px-4" aria-live="polite">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: -24, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -16, scale: 0.95 }}
              transition={{ type: "spring", stiffness: 420, damping: 30 }}
              className={cn("pointer-events-auto w-full max-w-sm rounded-2xl bg-white shadow-lift ring-1 px-4 py-3 flex items-center gap-3", TONE[t.tone].ring)}
            >
              {TONE[t.tone].icon}
              <div className="min-w-0">
                <p className="text-sm font-semibold text-ink-900">{t.title}</p>
                {t.text && <p className="text-xs text-ink-500 mt-0.5">{t.text}</p>}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const push = useContext(ToastContext);
  if (!push) throw new Error("useToast must be used within ToastProvider");
  return push;
}
