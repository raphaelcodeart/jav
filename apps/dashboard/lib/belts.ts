/** The belt ladder, in order -- same codes as the API (club/belts.py). Each
 *  belt has its color(s) so a badge can be drawn, never just named. */
export interface Belt {
  code: string;
  label: string;
  /** One color, or two for the half-and-half belts of the kyu grades. */
  colors: [string] | [string, string];
}

export const BELTS: Belt[] = [
  { code: "WHITE", label: "Bianca", colors: ["#ffffff"] },
  { code: "WHITE_YELLOW", label: "Bianca-gialla", colors: ["#ffffff", "#f9e40f"] },
  { code: "YELLOW", label: "Gialla", colors: ["#f9e40f"] },
  { code: "YELLOW_ORANGE", label: "Gialla-arancio", colors: ["#f9e40f", "#f58220"] },
  { code: "ORANGE", label: "Arancio", colors: ["#f58220"] },
  { code: "ORANGE_GREEN", label: "Arancio-verde", colors: ["#f58220", "#22a04b"] },
  { code: "GREEN", label: "Verde", colors: ["#22a04b"] },
  { code: "BLUE", label: "Blu", colors: ["#1f5fbf"] },
  { code: "BROWN", label: "Marrone", colors: ["#7a4a24"] },
  ...Array.from({ length: 10 }, (_, i) => ({
    code: `BLACK_${i + 1}`,
    label: `Nera ${i + 1}° dan`,
    colors: ["#161515"] as [string],
  })),
];

export const BELT_BY_CODE: Record<string, Belt> = Object.fromEntries(BELTS.map((b) => [b.code, b]));

export function beltFor(code: string | null | undefined): Belt {
  return (code && BELT_BY_CODE[code]) || (BELTS[0] as Belt);
}

export function nextBelt(code: string | null | undefined): Belt | null {
  const i = BELTS.findIndex((b) => b.code === code);
  return i >= 0 && i < BELTS.length - 1 ? (BELTS[i + 1] ?? null) : null;
}

/** The belt as the API sends it (club/belts.py): one color and an optional
 *  stripe for the two-color kyu grades. */
export interface ApiBelt {
  code: string;
  label: string;
  color: string;
  stripe?: string | null;
  rank?: number;
}

export function fromApiBelt(b: ApiBelt): Belt {
  return { code: b.code, label: b.label, colors: b.stripe ? [b.color, b.stripe] : [b.color] };
}
