"use client";

import { motion } from "motion/react";
import type { CareerState } from "./engine";
import type { CareerT } from "./i18n";
import { COLOR_HEX, Judoka, Tatami, type Pose } from "./ui";

// Il dojo "3D" della scheda principale: parete di legno, kamiza con il nome,
// tatami in prospettiva, il protagonista al centro e gli allievi intorno.

export function DojoScene({ state, pose, t }: { state: CareerState; pose: Pose; t: CareerT }) {
  const club = state.club;
  const color = COLOR_HEX[club?.color ?? state.hero.color];
  const kids = (club?.athletes ?? []).slice(0, 6);
  const title = club?.name ?? `道場 · ${state.hero.city}`;

  return (
    <div className="relative overflow-hidden rounded-[2rem] shadow-lift ring-1 ring-black/10">
      {/* parete */}
      <div className="absolute inset-0 bg-gradient-to-b from-[#7c4a24] via-[#a8693a] to-[#d9a066]" aria-hidden="true" />
      <div
        className="absolute inset-x-0 top-0 h-1/2 opacity-30"
        style={{ backgroundImage: "repeating-linear-gradient(90deg, rgba(0,0,0,0.35) 0 2px, transparent 2px 60px)" }}
        aria-hidden="true"
      />
      {/* finestre con luce */}
      <div className="absolute left-[8%] top-6 h-16 w-12 rounded-md bg-gradient-to-b from-sky-200 to-sky-50 opacity-70 shadow-inner" aria-hidden="true" />
      <div className="absolute right-[8%] top-6 h-16 w-12 rounded-md bg-gradient-to-b from-sky-200 to-sky-50 opacity-70 shadow-inner" aria-hidden="true" />
      {/* kamiza */}
      <div className="relative flex justify-center pt-4">
        <motion.div
          initial={{ y: -8, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="max-w-[70%] truncate rounded-xl px-4 py-1.5 font-display text-sm text-white shadow-lift ring-2 ring-white/30 sm:text-base"
          style={{ background: color }}
        >
          {title}
        </motion.div>
      </div>

      <Tatami className="relative mt-2 h-52 sm:h-64">
        <div className="absolute inset-x-0 bottom-5 flex items-end justify-center">
          {kids.slice(0, 3).map((a, i) => (
            <div key={a.id} className="-mx-2 opacity-90" style={{ marginBottom: 18 + i * 4 }}>
              <Judoka belt={a.belt} size={44} pose={a.lesao > 0 ? "block" : "idle"} skin={i % 2 ? "#c68642" : "#f1c27d"} />
            </div>
          ))}
          <div className="z-10 mx-2">
            <Judoka belt={state.hero.belt} pose={pose} size={92} />
          </div>
          {kids.slice(3).map((a, i) => (
            <div key={a.id} className="-mx-2 opacity-90" style={{ marginBottom: 26 - i * 4 }}>
              <Judoka belt={a.belt} size={44} pose="idle" flip skin={i % 2 ? "#f1c27d" : "#8d5524"} />
            </div>
          ))}
        </div>
      </Tatami>

      <div className="absolute bottom-3 left-3 rounded-full bg-black/45 px-3 py-1 text-[11px] font-bold text-white backdrop-blur">
        {t(`phase_${state.phase}`)}
      </div>
    </div>
  );
}
