"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import type { Belt, CareerState, HeroColor, LogLine, Result } from "./engine";
import type { CareerKey, CareerT } from "./i18n";

// Mattoncini visivi condivisi dal gioco: colori, barre, figure, tatami, coriandoli.

export const BELT_HEX: Record<Belt, string> = {
  WHITE: "#f8fafc", YELLOW: "#facc15", ORANGE: "#fb923c", GREEN: "#22c55e",
  BLUE: "#2563eb", BROWN: "#92400e", BLACK: "#0a0a0a",
};

export const COLOR_HEX: Record<HeroColor, string> = {
  red: "#e43f21", blue: "#2563eb", green: "#16a34a", purple: "#9333ea", orange: "#f97316", teal: "#0d9488",
};

export const COLOR_GRAD: Record<HeroColor, string> = {
  red: "from-brand-400 to-brand-700",
  blue: "from-sky-400 to-blue-700",
  green: "from-emerald-400 to-green-700",
  purple: "from-fuchsia-400 to-purple-700",
  orange: "from-amber-300 to-orange-600",
  teal: "from-teal-300 to-teal-700",
};

/** Traduce una riga del registro, anche i codici dentro (cintura, medaglia, livello). */
export function logText(t: CareerT, line: LogLine): string {
  const vars: Record<string, string | number> = { ...(line.vars ?? {}) };
  if (typeof vars.belt === "string") vars.belt = t(`belt_${vars.belt}` as CareerKey);
  if (typeof vars.medal === "string") vars.medal = t(`medal_${vars.medal}` as CareerKey);
  if (typeof vars.level === "string") vars.level = t(`level_${vars.level}` as CareerKey);
  return t(line.key, vars);
}

export function BeltBadge({ belt, t, small }: { belt: Belt; t: CareerT; small?: boolean }) {
  const dark = belt === "BLUE" || belt === "BROWN" || belt === "BLACK" || belt === "GREEN";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-bold ring-1 ring-black/10 shadow-sm",
        small ? "px-2 py-0.5 text-[11px]" : "px-3 py-1 text-xs",
        dark ? "text-white" : "text-ink-900",
      )}
      style={{ background: BELT_HEX[belt] }}
    >
      <span className="h-1.5 w-4 rounded-full bg-current opacity-40" aria-hidden="true" />
      {t(`belt_${belt}` as CareerKey)}
    </span>
  );
}

export function Bar({ value, max = 100, tone, label, right }: { value: number; max?: number; tone: string; label?: ReactNode; right?: ReactNode }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="min-w-0">
      {(label || right) && (
        <div className="mb-1 flex items-center justify-between gap-2 text-[11px] font-semibold">
          <span className="truncate">{label}</span>
          <span className="tabular-nums opacity-80">{right}</span>
        </div>
      )}
      <div className="h-2 overflow-hidden rounded-full bg-black/15" role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={max}>
        <motion.div className={cn("h-full rounded-full", tone)} initial={false} animate={{ width: `${pct}%` }} transition={{ type: "spring", stiffness: 120, damping: 20 }} />
      </div>
    </div>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-3xl bg-white/80 p-4 shadow-soft ring-1 ring-ink-100 backdrop-blur-md sm:p-5", className)}>
      {children}
    </div>
  );
}

export function SectionTitle({ children, icon }: { children: ReactNode; icon?: string }) {
  return (
    <h3 className="mb-3 flex items-center gap-2 font-display text-lg text-ink-900">
      {icon && <span aria-hidden="true">{icon}</span>}
      {children}
    </h3>
  );
}

export type Pose = "idle" | "attack" | "thrown" | "grip" | "win" | "block";

/** Un judoka in SVG: judogi bianco o blu, cintura colorata. */
export function Judoka({ gi = "#ffffff", belt, pose = "idle", flip, size = 96, skin = "#f1c27d" }: {
  gi?: string; belt: Belt; pose?: Pose; flip?: boolean; size?: number; skin?: string;
}) {
  const variants = {
    idle: { x: 0, y: [0, -3, 0], rotate: 0, transition: { y: { repeat: Infinity, duration: 1.6 } } },
    grip: { x: 10, y: 0, rotate: 4 },
    attack: { x: 28, y: -4, rotate: 10 },
    block: { x: -6, y: 0, rotate: -6 },
    thrown: { x: -20, y: 30, rotate: -95 },
    win: { x: 0, y: [0, -14, 0], rotate: 0, transition: { y: { repeat: Infinity, duration: 0.7 } } },
  };
  const outline = gi === "#ffffff" ? "#cbd5e1" : "#1e3a8a";
  return (
    <div style={{ transform: flip ? "scaleX(-1)" : undefined, width: size, height: size * 1.25 }}>
      <motion.svg
        viewBox="0 0 80 100"
        width={size}
        height={size * 1.25}
        animate={pose}
        variants={variants}
        transition={{ type: "spring", stiffness: 260, damping: 16 }}
        style={{ originX: 0.5, originY: 0.9 }}
        aria-hidden="true"
      >
        {/* ombra */}
        <ellipse cx="40" cy="97" rx="22" ry="3" fill="rgba(0,0,0,0.25)" />
        {/* gambe */}
        <path d="M30 62 L26 94 L35 94 L40 70 L45 94 L54 94 L50 62 Z" fill={gi} stroke={outline} strokeWidth="1.5" />
        {/* busto */}
        <path d="M24 30 Q40 24 56 30 L54 64 L26 64 Z" fill={gi} stroke={outline} strokeWidth="1.5" />
        {/* risvolto */}
        <path d="M34 28 L40 44 L46 28" fill="none" stroke={outline} strokeWidth="2" />
        {/* braccia */}
        <motion.path
          d={pose === "attack" || pose === "grip" ? "M54 32 Q70 34 76 30" : pose === "win" ? "M54 32 Q64 18 66 6" : "M54 32 Q62 46 60 58"}
          stroke={gi} strokeWidth="9" strokeLinecap="round" fill="none"
        />
        <path d={pose === "win" ? "M26 32 Q16 18 14 6" : "M26 32 Q18 46 20 58"} stroke={gi} strokeWidth="9" strokeLinecap="round" fill="none" />
        {/* cintura */}
        <rect x="25" y="56" width="30" height="5" rx="1.5" fill={BELT_HEX[belt]} stroke="rgba(0,0,0,0.25)" strokeWidth="0.8" />
        <path d="M40 60 L36 70 M40 60 L45 69" stroke={BELT_HEX[belt]} strokeWidth="3" strokeLinecap="round" />
        {/* testa */}
        <circle cx="40" cy="16" r="10" fill={skin} />
        <path d="M30 14 Q40 2 50 14 Q46 8 40 8 Q34 8 30 14 Z" fill="#3f2a1d" />
        <circle cx="44" cy="16" r="1.3" fill="#1f2937" />
      </motion.svg>
    </div>
  );
}

/** Il tatami in prospettiva: la "3D" è tutta CSS. */
export function Tatami({ children, className, tone = "green" }: { children?: ReactNode; className?: string; tone?: "green" | "blue" }) {
  const area = tone === "blue" ? "#2563eb" : "#16a34a";
  const safety = tone === "blue" ? "#facc15" : "#fde047";
  return (
    <div className={cn("relative [perspective:900px]", className)}>
      <div
        className="absolute inset-x-[4%] bottom-0 top-[18%] rounded-[28px] shadow-[0_40px_60px_-20px_rgba(0,0,0,0.55),0_8px_0_0_rgba(0,0,0,0.25)] [transform:rotateX(58deg)] [transform-origin:50%_100%]"
        style={{
          background: `linear-gradient(${safety}, ${safety})`,
          padding: "7%",
        }}
        aria-hidden="true"
      >
        <div
          className="h-full w-full rounded-[18px]"
          style={{
            backgroundColor: area,
            backgroundImage:
              "repeating-linear-gradient(90deg, rgba(255,255,255,0.10) 0 2px, transparent 2px 12.5%), repeating-linear-gradient(0deg, rgba(0,0,0,0.10) 0 2px, transparent 2px 25%), radial-gradient(circle at 50% 40%, rgba(255,255,255,0.25), transparent 60%)",
          }}
        />
      </div>
      <div className="relative h-full">{children}</div>
    </div>
  );
}

const BURST_COLORS = ["#e43f21", "#f9e40f", "#22c55e", "#2563eb", "#f97316", "#a855f7", "#ffffff"];

/** Coriandoli che esplodono dal centro: per medaglie e nuove cinture. */
export function Burst({ big }: { big?: boolean }) {
  const n = big ? 42 : 28;
  return (
    <div className="pointer-events-none fixed inset-0 z-[150] flex items-center justify-center" aria-hidden="true">
      {Array.from({ length: n }, (_, i) => {
        const angle = (i / n) * Math.PI * 2 + (i % 3) * 0.2;
        const dist = 140 + ((i * 37) % 160);
        const color = BURST_COLORS[i % BURST_COLORS.length];
        return (
          <motion.span
            key={i}
            className={cn("absolute block", i % 2 ? "h-3 w-2 rounded-sm" : "h-2.5 w-2.5 rounded-full")}
            style={{ background: color }}
            initial={{ x: 0, y: 0, opacity: 1, scale: 0.4, rotate: 0 }}
            animate={{ x: Math.cos(angle) * dist, y: Math.sin(angle) * dist + 120, opacity: 0, scale: 1.2, rotate: (i % 2 ? 1 : -1) * 360 }}
            transition={{ duration: 1.6, ease: [0.16, 1, 0.3, 1] }}
          />
        );
      })}
    </div>
  );
}

export const MEDAL_EMOJI = { GOLD: "🥇", SILVER: "🥈", BRONZE: "🥉" } as const;

/** Quello che ogni scheda riceve dal componente principale. */
export interface PanelProps {
  state: CareerState;
  t: CareerT;
  locale: string;
  examsPassed: string[];
  /** Applica il risultato di un'azione immediata: errore → avviso, altrimenti salva. */
  apply: (r: Result) => void;
}
