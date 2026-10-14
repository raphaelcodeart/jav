"use client";

import { motion } from "motion/react";
import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { CountUp } from "@/components/ui/count-up";
import { TiltCard } from "@/components/ui/tilt-card";
import { useI18n } from "@/lib/i18n/provider";

/** An achievement medal: locked ones are grey and flat, unlocked ones shine. */
export function AchievementBadge({ icon, label, unlocked, hint }: { icon: ReactNode; label: string; unlocked: boolean; hint?: string }) {
  return (
    <motion.div
      whileHover={unlocked ? { y: -4, rotate: -2 } : undefined}
      className="flex flex-col items-center gap-2 w-24 text-center"
      title={hint}
    >
      <div
        className={cn(
          "relative h-16 w-16 rounded-full flex items-center justify-center text-2xl",
          unlocked
            ? "bg-gradient-to-br from-accent-200 via-accent-400 to-accent-600 shadow-accent ring-4 ring-white"
            : "bg-ink-100 text-ink-300 ring-4 ring-white grayscale",
        )}
      >
        {unlocked && <span className="absolute inset-0 rounded-full shine-sweep" aria-hidden="true" />}
        <span className="relative">{icon}</span>
      </div>
      <span className={cn("text-xs font-semibold leading-tight", unlocked ? "text-ink-800" : "text-ink-400")}>{label}</span>
    </motion.div>
  );
}

export interface PodiumEntry {
  name: string;
  points: number;
  photoUrl?: string | null;
  /** La pagina del judoca, quando ne ha una (il sito pubblico). */
  href?: string;
}

/** The ranking podium: 2nd, 1st, 3rd, rising from the floor one after the
 *  other, with the points rolling up. */
export function Podium({ entries }: { entries: PodiumEntry[] }) {
  const order = [entries[1], entries[0], entries[2]];
  const heights = ["h-24", "h-32", "h-20"];
  const medals = ["from-ink-200 to-ink-400", "from-accent-300 to-accent-500", "from-amber-600 to-amber-800"];
  const places = [2, 1, 3];
  return (
    <div className="flex items-end justify-center gap-3 sm:gap-5 pt-6">
      {order.map((e, i) =>
        e ? (
          <motion.div
            key={places[i]}
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: [0.25, 0.05, 0.45][i], type: "spring", stiffness: 160, damping: 16 }}
            className="flex flex-col items-center w-24 sm:w-32"
          >
            <div className={cn("relative h-14 w-14 sm:h-16 sm:w-16 rounded-full ring-4 ring-white shadow-lift bg-gradient-to-br overflow-hidden mb-2", medals[i])}>
              {e.photoUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={e.photoUrl} alt="" className="h-full w-full object-cover" />
              ) : (
                <span className="h-full w-full flex items-center justify-center font-display text-lg text-white">{e.name.slice(0, 1)}</span>
              )}
            </div>
            <p className="text-xs sm:text-sm font-semibold text-ink-900 text-center truncate w-full">
              {e.href ? <Link href={e.href} className="hover:text-brand-700">{e.name}</Link> : e.name}
            </p>
            <p className="font-display text-brand-600 text-sm"><CountUp value={e.points} /> pt</p>
            <div className={cn("mt-2 w-full rounded-t-2xl bg-gradient-to-b flex items-start justify-center pt-2 shadow-soft", heights[i], medals[i])}>
              <span className="font-display text-2xl text-white drop-shadow">{places[i]}</span>
            </div>
          </motion.div>
        ) : null,
      )}
    </div>
  );
}

/** The big home-screen actions for parents ("Carica un pagamento"). */
export function ActionButton({ icon, title, text, onClick, tone = "brand" }: { icon: ReactNode; title: string; text?: string; onClick?: () => void; tone?: "brand" | "accent" | "ink" }) {
  const tones = {
    brand: "from-brand-500 to-brand-600 text-white shadow-brand",
    accent: "from-accent-300 to-accent-400 text-ink-900 shadow-accent",
    ink: "from-ink-700 to-ink-900 text-white shadow-lift",
  }[tone];
  return (
    <motion.button
      whileHover={{ y: -4, scale: 1.01 }}
      whileTap={{ scale: 0.97 }}
      transition={{ type: "spring", stiffness: 420, damping: 24 }}
      onClick={onClick}
      className={cn("relative overflow-hidden w-full text-left rounded-3xl p-5 bg-gradient-to-br cursor-pointer", tones)}
    >
      <span className="absolute -right-6 -bottom-8 h-28 w-28 rounded-full bg-white/15" aria-hidden="true" />
      <span className="relative flex items-center gap-4">
        <span className="h-14 w-14 shrink-0 rounded-2xl bg-white/20 backdrop-blur flex items-center justify-center text-2xl ring-1 ring-inset ring-white/30">
          {icon}
        </span>
        <span className="min-w-0">
          <span className="block font-display text-lg leading-tight">{title}</span>
          {text && <span className="block text-sm opacity-85 mt-1">{text}</span>}
        </span>
      </span>
    </motion.button>
  );
}

/** "Scatta o scegli una foto": opens the camera directly on phones
 *  (`capture="environment"`), the file picker on a computer. */
export function CameraUploadButton({ onFile, label, accept = "image/*,application/pdf", disabled }: { onFile: (file: File) => void; label?: string; accept?: string; disabled?: boolean }) {
  const { t } = useI18n();
  return (
    <label
      className={cn(
        "group relative flex flex-col items-center justify-center gap-3 w-full rounded-3xl border-2 border-dashed border-brand-300 bg-brand-50/50 px-6 py-8 text-center cursor-pointer transition-colors hover:bg-brand-50 hover:border-brand-500",
        disabled && "opacity-50 pointer-events-none",
      )}
    >
      <span className="h-16 w-16 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-600 text-white shadow-brand flex items-center justify-center transition-transform group-hover:scale-105 group-active:scale-95">
        <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 8.5A2.5 2.5 0 0 1 5.5 6h1.6a1 1 0 0 0 .86-.49l.98-1.62A1 1 0 0 1 9.8 3.4h4.4a1 1 0 0 1 .86.49l.98 1.62a1 1 0 0 0 .86.49h1.6A2.5 2.5 0 0 1 21 8.5v9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5v-9Z" />
          <circle cx="12" cy="13" r="3.5" />
        </svg>
      </span>
      <span className="font-display text-ink-900">{label ?? t("camera.label")}</span>
      <span className="text-xs text-ink-500">{t("camera.hint")}</span>
      <input
        type="file"
        accept={accept}
        capture="environment"
        className="sr-only"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
    </label>
  );
}

/** The athlete "trading card": photo, name, belt, points and level, tilting
 *  in 3D with a holographic sheen. */
export function AthleteCard({
  name, photoUrl, belt, points, level, subtitle, footer,
}: {
  name: string;
  photoUrl?: string | null;
  belt?: ReactNode;
  points?: number;
  level?: number;
  subtitle?: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <TiltCard className="rounded-[28px]">
      <div className="relative overflow-hidden rounded-[28px] bg-gradient-to-b from-white to-ink-50 ring-1 ring-ink-200 shadow-lift">
        <div className="relative h-36 bg-gradient-to-br from-brand-500 via-brand-600 to-ink-900 overflow-hidden">
          <div className="absolute inset-0 opacity-25 bg-[radial-gradient(circle_at_20%_20%,#f9e40f,transparent_45%)]" aria-hidden="true" />
          <div className="absolute -bottom-10 -right-6 font-display text-[7rem] leading-none text-white/10 select-none" aria-hidden="true">柔</div>
          {level !== undefined && (
            <div className="absolute top-3 left-3 rounded-full bg-white/90 px-3 py-1 text-xs font-bold text-ink-900 shadow-soft">
              LV <span className="font-display">{level}</span>
            </div>
          )}
          {points !== undefined && (
            <div className="absolute top-3 right-3 rounded-full bg-accent-400 px-3 py-1 text-xs font-bold text-ink-900 shadow-accent">
              <span className="font-display"><CountUp value={points} /></span> pt
            </div>
          )}
        </div>
        <div className="relative -mt-12 flex flex-col items-center px-5 pb-5">
          <div className="h-24 w-24 rounded-full ring-4 ring-white shadow-lift overflow-hidden bg-gradient-to-br from-ink-200 to-ink-400">
            {photoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={photoUrl} alt="" className="h-full w-full object-cover" />
            ) : (
              <span className="h-full w-full flex items-center justify-center font-display text-3xl text-white">{name.slice(0, 1)}</span>
            )}
          </div>
          <h3 className="mt-3 text-lg text-ink-900 text-center">{name}</h3>
          {subtitle && <p className="text-xs text-ink-500 mt-0.5">{subtitle}</p>}
          {belt && <div className="mt-3">{belt}</div>}
          {footer && <div className="mt-4 w-full">{footer}</div>}
        </div>
      </div>
    </TiltCard>
  );
}

/** A wallet balance as a spinning gold coin and a rolling number. */
export function CoinCounter({ cents, label = "JavCash" }: { cents: number; label?: string }) {
  return (
    <div className="flex items-center gap-3">
      <motion.div
        animate={{ rotateY: [0, 360] }}
        transition={{ duration: 2.4, repeat: Infinity, repeatDelay: 3, ease: "easeInOut" }}
        className="h-12 w-12 rounded-full bg-gradient-to-br from-accent-200 via-accent-400 to-accent-600 shadow-accent ring-2 ring-white flex items-center justify-center font-display text-ink-900"
        style={{ transformStyle: "preserve-3d" }}
        aria-hidden="true"
      >
        J
      </motion.div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">{label}</p>
        <p className="font-display text-2xl text-ink-900 tabular-nums">
          <CountUp value={cents / 100} format={(n) => n.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} />
        </p>
      </div>
    </div>
  );
}
