// I colori del club e il loro contrasto: la stessa regola di
// apps/api/app/domains/club/brand.py, rifatta qui solo per l'anteprima dal
// vivo dell'editor della pagina (club-site-editor.tsx). La pagina pubblica
// usa il tema calcolato dall'API, non questo: se le due versioni divergono,
// vince l'API, e questo file va riallineato.

export const JAV_PRIMARY = "#E13F22";
export const JAV_SECONDARY = "#F3E017";
export const JAV_ACCENT = "#F3E017";
const WHITE = "#FFFFFF";
const INK = "#0A0A0A";
const AA_TEXT = 4.5;
const DISTINCT = 1.6;

export interface BrandTheme {
  primary: string;
  secondary: string;
  accent: string;
  on_primary: string;
  on_accent: string;
  primary_text: string;
  accent_on_dark: string;
  cover_from: string;
  cover_to: string;
  custom: boolean;
  warnings: string[];
}

/** "#e32" → "#EE3322"; vuoto → null; un valore che non è un colore → undefined. */
export function normalizeHex(value: string | null | undefined): string | null | undefined {
  const v = (value ?? "").trim();
  if (!v) return null;
  const m = /^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec(v);
  if (!m) return undefined;
  const digits = m[1]!.length === 3 ? m[1]!.split("").map((c) => c + c).join("") : m[1]!;
  return `#${digits.toUpperCase()}`;
}

function rgb(hex: string): [number, number, number] {
  return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
}

function toHex(c: number[]): string {
  return `#${c.map((x) => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, "0")).join("").toUpperCase()}`;
}

function luminance(hex: string): number {
  const ch = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const [r, g, b] = rgb(hex);
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

function mix(a: string, b: string, weight: number): string {
  const ra = rgb(a);
  const rb = rgb(b);
  return toHex(ra.map((x, i) => x + (rb[i]! - x) * weight));
}

export function readableOn(background: string): string {
  return contrast(background, WHITE) >= contrast(background, INK) ? WHITE : INK;
}

function toward(color: string, target: string, against: string, minimum: number): string {
  if (contrast(color, against) >= minimum) return color;
  for (let step = 1; step <= 20; step++) {
    const candidate = mix(color, target, step / 20);
    if (contrast(candidate, against) >= minimum) return candidate;
  }
  return target;
}

export function brandTheme(primary: string | null, secondary: string | null, accent: string | null): BrandTheme {
  const p = primary ?? JAV_PRIMARY;
  const s = secondary ?? accent ?? (primary === null ? JAV_SECONDARY : p);
  const a = accent ?? secondary ?? (primary === null ? JAV_ACCENT : readableOn(p));
  const coverFrom = toward(p, INK, WHITE, 3.0);
  const warnings: string[] = [];
  if (contrast(p, WHITE) < AA_TEXT) warnings.push("PRIMARY_DARKENED");
  if (contrast(a, coverFrom) < DISTINCT) warnings.push("ACCENT_LIKE_PRIMARY");
  return {
    primary: p,
    secondary: s,
    accent: a,
    on_primary: readableOn(p),
    on_accent: readableOn(a),
    primary_text: toward(p, INK, WHITE, AA_TEXT),
    accent_on_dark: toward(a, WHITE, INK, AA_TEXT),
    cover_from: coverFrom,
    cover_to: mix(coverFrom, INK, 0.65),
    custom: primary !== null,
    warnings,
  };
}

/** Le variabili CSS che accendono i token `club-*` di globals.css. */
export function themeStyle(theme: BrandTheme): Record<string, string> {
  return {
    "--club-primary": theme.primary,
    "--club-on-primary": theme.on_primary,
    "--club-primary-text": theme.primary_text,
    "--club-secondary": theme.secondary,
    "--club-accent": theme.accent,
    "--club-on-accent": theme.on_accent,
    "--club-accent-on-dark": theme.accent_on_dark,
    "--club-cover-from": theme.cover_from,
    "--club-cover-to": theme.cover_to,
  };
}

/** Le sfumature 50…950 di un colore, come le scale di Tailwind: verso il
 *  bianco le chiare, verso il nero le scure. Il 500 è il colore scelto, ma
 *  scurito quanto basta perché un testo bianco sopra si legga (i bottoni). */
const SHADES: [number, number][] = [
  [50, 0.92], [100, 0.84], [200, 0.68], [300, 0.48], [400, 0.24], [500, 0],
  [600, -0.14], [700, -0.28], [800, -0.42], [900, -0.54], [950, -0.72],
];

export function shadeScale(color: string, readableBase = true): Record<number, string> {
  const base = readableBase ? toward(color, INK, WHITE, 3.0) : color;
  const out: Record<number, string> = {};
  for (const [step, w] of SHADES) out[step] = w >= 0 ? mix(base, WHITE, w) : mix(base, INK, -w);
  return out;
}

/** Le variabili CSS che ridipingono `brand-*` e `accent-*` di globals.css con
 *  i colori del club: le aree riservate (segreteria, treinador, famiglia,
 *  atleta) prendono il tema del loro club. Senza colori scelti: nessuna
 *  variabile, resta JAV. */
export function paletteVars(primary: string | null, secondary: string | null, accent: string | null): Record<string, string> {
  if (!primary) return {};
  const theme = brandTheme(primary, secondary, accent);
  const vars: Record<string, string> = {};
  for (const [step, value] of Object.entries(shadeScale(theme.primary))) vars[`--color-brand-${step}`] = value;
  for (const [step, value] of Object.entries(shadeScale(theme.accent, false))) vars[`--color-accent-${step}`] = value;
  return vars;
}
