import { cn } from "@/lib/cn";

// L'immagine di un evento accanto al suo nome negli elenchi delle prove: la
// foto o la locandina caricata dalla segreteria, o l'icona del tipo su un
// colore suo, così gara, stage e arbitragem si riconoscono a colpo d'occhio.

export const EVENT_KIND_STYLE: Record<string, { icon: string; bg: string }> = {
  COMPETITION: { icon: "🏆", bg: "from-brand-500 to-brand-800" },
  STAGE: { icon: "🥋", bg: "from-sky-500 to-sky-800" },
  REFEREEING: { icon: "🧑‍⚖️", bg: "from-violet-500 to-violet-800" },
  EDUCATION: { icon: "🎓", bg: "from-emerald-500 to-emerald-800" },
  MEETING: { icon: "🤝", bg: "from-amber-500 to-amber-700" },
  OTHER: { icon: "📌", bg: "from-ink-500 to-ink-800" },
};

export function EventIcon({ kind, imageUrl, size = "lg", className }: {
  kind?: string | null; imageUrl?: string | null; size?: "md" | "lg" | "xl"; className?: string;
}) {
  const style = EVENT_KIND_STYLE[kind ?? "COMPETITION"] ?? EVENT_KIND_STYLE.OTHER!;
  const box = { md: "h-14 w-14 text-2xl rounded-2xl", lg: "h-20 w-20 text-4xl rounded-3xl", xl: "h-28 w-28 text-5xl rounded-3xl" }[size];
  return imageUrl ? (
    // eslint-disable-next-line @next/next/no-img-element -- immagine caricata dalla segreteria
    <img src={imageUrl} alt="" loading="lazy" className={cn("shrink-0 object-cover shadow-soft ring-2 ring-white", box, className)} />
  ) : (
    <span className={cn("flex shrink-0 items-center justify-center bg-gradient-to-br text-white shadow-soft ring-2 ring-white", style.bg, box, className)} aria-hidden="true">
      {style.icon}
    </span>
  );
}
