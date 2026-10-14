import { cn } from "@/lib/cn";

// Gli stessi bottoni di components/ui/button.tsx, ma per i link: il sito
// pubblico naviga con <Link> (pagine indicizzabili, prefetch, tasto destro
// "apri in una nuova scheda"), e un <button> dentro un <a> non è HTML valido.

type Variant = "primary" | "secondary" | "accent" | "dark" | "ghost" | "light";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary: "text-white bg-gradient-to-b from-brand-500 to-brand-600 shadow-brand hover:from-brand-400 hover:to-brand-600 ring-1 ring-inset ring-white/20",
  secondary: "text-ink-900 bg-white border border-ink-200 shadow-soft hover:border-brand-300 hover:text-brand-700",
  accent: "text-ink-900 bg-gradient-to-b from-accent-300 to-accent-400 shadow-accent hover:from-accent-200",
  dark: "text-white bg-ink-900 hover:bg-ink-800 shadow-soft",
  ghost: "text-ink-700 hover:bg-ink-100 hover:text-ink-900",
  // Sopra una foto scura (la copertina di un club).
  light: "text-white bg-white/15 ring-1 ring-inset ring-white/40 backdrop-blur hover:bg-white/25",
};

const SIZES: Record<Size, string> = {
  sm: "h-9 px-3.5 text-sm gap-1.5 rounded-xl",
  md: "h-11 px-5 text-sm gap-2 rounded-xl",
  lg: "h-12 px-6 text-base gap-2 rounded-2xl",
};

export function linkButton({ variant = "primary", size = "md", className }: { variant?: Variant; size?: Size; className?: string } = {}): string {
  return cn(
    "inline-flex items-center justify-center font-semibold select-none transition-all hover:-translate-y-px active:translate-y-0",
    "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-500/25",
    VARIANTS[variant],
    SIZES[size],
    className,
  );
}
