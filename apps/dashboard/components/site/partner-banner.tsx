import Image from "next/image";

/** La fascia dei partner sopra lo Shop (sito e area): nera come il sito di
 *  Suplementos24, con il loro logo, come un banner. */
export function PartnerBanner({ title, text, label, className }: { title: string; text: string; label: string; className?: string }) {
  return (
    <div className={`${className ?? ""} relative overflow-hidden rounded-3xl bg-ink-950 p-5 text-white shadow-lift ring-1 ring-white/10 sm:p-6`}>
      <div className="pointer-events-none absolute -right-10 -top-16 h-48 w-48 rounded-full bg-[#ff5a1f]/35 blur-3xl" aria-hidden="true" />
      <div className="pointer-events-none absolute -bottom-20 left-1/3 h-40 w-40 rounded-full bg-brand-600/30 blur-3xl" aria-hidden="true" />
      <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
        <a href="https://www.suplementos24.com" target="_blank" rel="noopener noreferrer sponsored"
          className="flex shrink-0 flex-col items-start gap-1.5 rounded-2xl bg-white/5 px-4 py-3 ring-1 ring-white/10 transition hover:bg-white/10">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#ff7a3d]">{label}</span>
          <Image src="/partners/suplementos24.png" alt="Suplementos24" width={229} height={40} className="h-8 w-auto" />
        </a>
        <div className="min-w-0">
          <p className="font-display text-lg sm:text-xl">🤝 {title}</p>
          <p className="mt-1 text-sm text-white/75">{text}</p>
        </div>
      </div>
    </div>
  );
}
