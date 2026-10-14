"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

/** A centered dialog on desktop that becomes a bottom sheet on phones --
 *  thumbs reach the bottom of the screen, not the middle. Rendered in a
 *  portal on <body>, so no ancestor transform can ever offset it. */
export function Modal({
  open, onClose, title, subtitle, children, footer, size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  const { t } = useI18n();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (typeof document === "undefined") return null;
  const width = { sm: "sm:max-w-md", md: "sm:max-w-lg", lg: "sm:max-w-2xl", xl: "sm:max-w-4xl" }[size];

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center sm:p-6" role="dialog" aria-modal="true">
          <motion.div
            className="absolute inset-0 bg-ink-900/35 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            initial={{ y: 60, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 40, opacity: 0, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 380, damping: 32 }}
            className={cn(
              "relative w-full bg-white shadow-lift rounded-t-3xl sm:rounded-3xl max-h-[92vh] flex flex-col",
              width,
            )}
          >
            <div className="sm:hidden mx-auto mt-2.5 h-1.5 w-10 rounded-full bg-ink-200" aria-hidden="true" />
            {(title || subtitle) && (
              <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-3">
                <div>
                  {title && <h2 className="text-lg text-ink-900">{title}</h2>}
                  {subtitle && <p className="text-sm text-ink-500 mt-1">{subtitle}</p>}
                </div>
                <button
                  onClick={onClose}
                  aria-label={t("common.close")}
                  className="h-9 w-9 shrink-0 rounded-full flex items-center justify-center text-ink-500 hover:bg-ink-100 hover:text-ink-900 cursor-pointer"
                >
                  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" d="M6 6l12 12M18 6 6 18" />
                  </svg>
                </button>
              </div>
            )}
            <div className="px-6 pb-6 overflow-y-auto">{children}</div>
            {footer && <div className="px-6 py-4 border-t border-ink-100 flex justify-end gap-2">{footer}</div>}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
