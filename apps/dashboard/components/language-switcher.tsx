"use client";

import { useEffect, useId, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { cn } from "@/lib/cn";
import { LOCALES, LOCALE_NAMES, type Locale } from "@/lib/i18n/config";
import { useI18n } from "@/lib/i18n/provider";

/** Flags drawn in SVG, not emoji: Windows has no flag emoji and would show
 *  the letters "PT" in a box. */
function Flag({ locale, className }: { locale: Locale; className?: string }) {
  const id = useId();
  const box = cn("block overflow-hidden rounded-[4px] ring-1 ring-ink-900/15 shadow-sm", className);
  if (locale === "pt") {
    return (
      <svg viewBox="0 0 30 20" className={box} aria-hidden="true">
        <rect width="12" height="20" fill="#006600" />
        <rect x="12" width="18" height="20" fill="#ff0000" />
        <circle cx="12" cy="10" r="4.6" fill="none" stroke="#ffcc00" strokeWidth="1.6" />
        <path d="M10.1 7.6h3.8v3.3a1.9 1.9 0 0 1-3.8 0z" fill="#fff" stroke="#ff0000" strokeWidth="0.7" />
      </svg>
    );
  }
  if (locale === "it") {
    return (
      <svg viewBox="0 0 3 2" className={box} aria-hidden="true">
        <rect width="1" height="2" fill="#009246" />
        <rect x="1" width="1" height="2" fill="#fff" />
        <rect x="2" width="1" height="2" fill="#ce2b37" />
      </svg>
    );
  }
  // Union Jack. useId: two flags on one page must not share a clipPath id.
  return (
    <svg viewBox="0 0 60 30" preserveAspectRatio="xMidYMid slice" className={box} aria-hidden="true">
      <clipPath id={`${id}-t`}>
        <path d="M30,15 h30 v15 z v15 h-30 z h-30 v-15 z v-15 h30 z" />
      </clipPath>
      <rect width="60" height="30" fill="#012169" />
      <path d="M0,0 L60,30 M60,0 L0,30" stroke="#fff" strokeWidth="6" />
      <path d="M0,0 L60,30 M60,0 L0,30" clipPath={`url(#${id}-t)`} stroke="#c8102e" strokeWidth="4" />
      <path d="M30,0 v30 M0,15 h60" stroke="#fff" strokeWidth="10" />
      <path d="M30,0 v30 M0,15 h60" stroke="#c8102e" strokeWidth="6" />
    </svg>
  );
}

/** The flag in the top bar: the current language, and the other two one tap
 *  away. Portuguese first, as in LOCALES. */
export function LanguageSwitcher({ className }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  return (
    <div className={cn("relative", className)} ref={ref}>
      <motion.button
        whileHover={{ scale: 1.06 }}
        whileTap={{ scale: 0.92 }}
        onClick={() => setOpen((v) => !v)}
        className="flex h-10 items-center gap-1.5 rounded-2xl bg-white px-2.5 ring-1 ring-ink-200 shadow-soft cursor-pointer hover:ring-brand-300"
        aria-label={t("lang.choose")}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Flag locale={locale} className="h-[18px] w-[27px]" />
        <span className="text-xs font-bold uppercase text-ink-700">{locale}</span>
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 460, damping: 32 }}
            className="absolute right-0 top-12 z-50 w-48 rounded-2xl bg-white shadow-lift ring-1 ring-ink-200 overflow-hidden origin-top-right py-1"
            role="menu"
          >
            {LOCALES.map((l) => (
              <button
                key={l}
                role="menuitemradio"
                aria-checked={l === locale}
                lang={l}
                onClick={() => {
                  setOpen(false);
                  if (l !== locale) setLocale(l);
                }}
                className={cn(
                  "w-full flex items-center gap-3 px-4 py-2.5 text-sm cursor-pointer hover:bg-ink-50",
                  l === locale ? "font-semibold text-ink-900" : "text-ink-700",
                )}
              >
                <Flag locale={l} className="h-4 w-6" />
                <span className="flex-1 text-left">{LOCALE_NAMES[l]}</span>
                {l === locale && <span className="text-brand-600">✓</span>}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
