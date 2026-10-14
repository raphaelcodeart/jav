import type { ReactNode } from "react";
import { Container } from "@/components/site/blocks";
import { Reveal } from "@/components/site/reveal";

/** I mattoni delle pagine che raccontano il progetto (chi siamo, visione,
 *  progetto, sponsor): stessa voce visiva della home -- foto a tutta
 *  larghezza velata, schede chiare, fasce scure -- così il sito sembra uno. */

export function StoryHero({ image, eyebrow, title, text, children }: {
  image: string; eyebrow: string; title: string; text: string; children?: ReactNode;
}) {
  return (
    <section className="relative isolate overflow-hidden bg-ink-950 text-white">
      {/* eslint-disable-next-line @next/next/no-img-element -- foto decorativa statica */}
      <img src={image} alt="" className="absolute inset-0 -z-20 h-full w-full object-cover opacity-60" aria-hidden="true" />
      <div className="absolute inset-0 -z-10 bg-gradient-to-r from-ink-950 via-ink-950/80 to-ink-950/30" aria-hidden="true" />
      <div className="pointer-events-none absolute -left-32 -top-32 -z-10 h-[28rem] w-[28rem] rounded-full bg-brand-600/40 blur-[110px] animate-aurora" aria-hidden="true" />
      <Container className="py-24 sm:py-32">
        <Reveal>
          <p className="text-xs font-bold uppercase tracking-[0.25em] text-accent-300">{eyebrow}</p>
          <h1 className="mt-4 max-w-4xl font-display text-4xl leading-tight sm:text-6xl">{title}</h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-white/80 sm:text-xl">{text}</p>
          {children && <div className="mt-10">{children}</div>}
        </Reveal>
      </Container>
    </section>
  );
}

export function SectionTitle({ eyebrow, title, text }: { eyebrow?: string; title: string; text?: string }) {
  return (
    <div className="mb-10 max-w-3xl">
      {eyebrow && <p className="text-xs font-bold uppercase tracking-[0.22em] text-brand-600">{eyebrow}</p>}
      <h2 className="mt-2 font-display text-3xl text-ink-900 sm:text-4xl">{title}</h2>
      {text && <p className="mt-4 text-lg leading-relaxed text-ink-600">{text}</p>}
    </div>
  );
}

export function FeatureGrid({ items, columns = 3 }: { items: { icon: string; title: string; text: string }[]; columns?: 2 | 3 }) {
  return (
    <div className={`grid gap-5 sm:grid-cols-2 ${columns === 3 ? "lg:grid-cols-3" : ""}`}>
      {items.map((item, i) => (
        <Reveal key={item.title} delay={i * 0.05}>
          <div className="group h-full rounded-3xl bg-white p-6 shadow-soft ring-1 ring-ink-900/5 transition hover:-translate-y-1 hover:shadow-lift">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-2xl transition group-hover:scale-110" aria-hidden="true">{item.icon}</span>
            <h3 className="mt-4 text-lg text-ink-900">{item.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-ink-600">{item.text}</p>
          </div>
        </Reveal>
      ))}
    </div>
  );
}

export function Timeline({ items }: { items: { year: string; title: string; text: string }[] }) {
  return (
    <ol className="relative ml-3 space-y-8 border-l-2 border-brand-200">
      {items.map((item, i) => (
        <Reveal key={item.year} delay={i * 0.06}>
          <li className="relative pl-8">
            <span className="absolute -left-[11px] top-1 h-5 w-5 rounded-full bg-brand-500 ring-4 ring-white" aria-hidden="true" />
            <p className="font-display text-2xl text-brand-600">{item.year}</p>
            <h3 className="text-lg text-ink-900">{item.title}</h3>
            <p className="mt-1 text-ink-600">{item.text}</p>
          </li>
        </Reveal>
      ))}
    </ol>
  );
}

export function DarkBand({ children }: { children: ReactNode }) {
  return (
    <section className="relative overflow-hidden bg-ink-950 text-white">
      <div className="pointer-events-none absolute right-[-10rem] top-[-8rem] h-[26rem] w-[26rem] rounded-full bg-accent-400/20 blur-[110px]" aria-hidden="true" />
      <Container className="relative py-20">{children}</Container>
    </section>
  );
}
