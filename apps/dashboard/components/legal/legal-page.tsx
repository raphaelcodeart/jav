import Link from "next/link";
import type { ReactNode } from "react";
import { Container } from "@/components/site/blocks";
import { SiteShell } from "@/components/site/site-shell";
import { LEGAL } from "@/lib/legal";

/** La veste delle pagine legali: titolo, versione, indice e i paragrafi. I
 *  testi sono in portoghese (la lingua che fa fede, in Portogallo). */
export function LegalPage({ title, intro, sections }: {
  title: string; intro: ReactNode; sections: { id: string; title: string; body: ReactNode }[];
}) {
  return (
    <SiteShell>
      <Container className="py-12">
        <article className="mx-auto max-w-3xl">
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-brand-600">Informação legal</p>
          <h1 className="mt-2 font-display text-4xl text-ink-900">{title}</h1>
          <p className="mt-2 text-sm text-ink-500">Versão de {LEGAL.version.split("-").reverse().join("/")} · em vigor desde esta data</p>
          <div className="mt-6 space-y-3 text-ink-700">{intro}</div>
          <nav aria-label="Índice" className="mt-8 rounded-3xl bg-ink-50 p-5 ring-1 ring-ink-900/5">
            <p className="mb-2 text-sm font-semibold text-ink-900">Índice</p>
            <ol className="grid gap-1 text-sm sm:grid-cols-2">
              {sections.map((s, i) => <li key={s.id}><a href={`#${s.id}`} className="text-brand-700 hover:underline">{i + 1}. {s.title}</a></li>)}
            </ol>
          </nav>
          <div className="mt-10 space-y-10">
            {sections.map((s, i) => (
              <section key={s.id} id={s.id} className="scroll-mt-32">
                <h2 className="mb-3 text-xl text-ink-900">{i + 1}. {s.title}</h2>
                <div className="legal-body space-y-3 text-[15px] leading-relaxed text-ink-700">{s.body}</div>
              </section>
            ))}
          </div>
          <p className="mt-12 border-t border-ink-100 pt-6 text-sm text-ink-500">
            Ver também: <Link href="/privacidade" className="text-brand-700 underline">Política de Privacidade</Link> ·{" "}
            <Link href="/cookies" className="text-brand-700 underline">Política de Cookies</Link> ·{" "}
            <Link href="/termos" className="text-brand-700 underline">Termos e Condições</Link>
          </p>
        </article>
      </Container>
    </SiteShell>
  );
}

export function Controller() {
  const c = LEGAL.controller;
  return (
    <div className="rounded-2xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
      <p className="font-semibold text-ink-900">{c.name}</p>
      {c.nipc && <p>NIPC: {c.nipc}</p>}
      <p>{c.address}</p>
      <p>Email: <a href={`mailto:${c.email}`} className="text-brand-700 underline">{c.email}</a> · Telefone: {c.phone}</p>
    </div>
  );
}
