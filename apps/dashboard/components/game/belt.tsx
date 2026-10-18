"use client";

import { BELT_COLORS } from "@/components/game/i18n";
import { cn } from "@/lib/cn";

// La cintura disegnata per un grado della Dojo Academy: una tinta per le
// cinture piene, due metà per le mezze cinture della FPJ, la nera con le
// barrette dei dan, bianca e rossa a pannelli dal 6° all'8°, rossa al 9° e 10°.

const RED = "#dc2626";
const color = (code: string | undefined) => BELT_COLORS[code ?? ""] ?? "#f8fafc";

function dan(grade: string): number {
  if (grade === "BLACK") return 1;
  const m = /^DAN(\d+)$/.exec(grade);
  return m ? Number(m[1]) : 0;
}

export function beltBackground(grade: string): string {
  const d = dan(grade);
  if (d >= 9) return RED;
  if (d >= 6) return `repeating-linear-gradient(90deg, ${RED} 0 14%, #f8fafc 14% 28%)`;
  if (d >= 1) return color("BLACK");
  const [a, b] = grade.split("_");
  if (b) return `linear-gradient(90deg, ${color(a)} 0 50%, ${color(b)} 50% 100%)`;
  return color(grade);
}

/** La cintura annodata, con le barrette dorate del dan (fino al 5°). */
export function BeltSwatch({ grade, className }: { grade: string; className?: string }) {
  const d = dan(grade);
  return (
    <span className={cn("relative inline-flex h-4 w-14 shrink-0 items-center justify-end overflow-hidden rounded-md ring-1 ring-black/15 shadow-inner", className)}
      style={{ background: beltBackground(grade) }} aria-hidden="true">
      {d > 0 && d <= 5 && (
        <span className="mr-[12%] flex h-full gap-[2px]">
          {Array.from({ length: d }, (_, i) => <span key={i} className="h-full w-[3px] bg-amber-400" />)}
        </span>
      )}
      <span className="absolute left-1/2 top-0 h-full w-[18%] -translate-x-1/2 bg-black/15" />
    </span>
  );
}
