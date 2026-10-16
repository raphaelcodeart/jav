import Link from "next/link";
import { cn } from "@/lib/cn";
import type { Sponsor } from "@/lib/public-site";

// La barra degli sponsor della home: i loghi scorrono (solo CSS, si fermano
// sotto il mouse e con «riduci movimento»), ognuno porta alla pagina dello
// sponsor (/patrocinadores/<slug>). Senza logo, il nome scritto con le
// iniziali nel colore dello sponsor. Server component: niente JavaScript.

function initials(name: string) {
  const words = name.replace(/^(câmara|camara) municipal (de|do|da) /i, "").split(/\s+/).filter(Boolean);
  return words.map((w) => w[0]).join("").slice(0, 3).toUpperCase();
}

export function SponsorTile({ sponsor, className }: { sponsor: Sponsor; className?: string }) {
  const color = sponsor.color ?? "#E13F22";
  return (
    <span className={cn("flex h-20 items-center gap-3 rounded-2xl bg-white px-5 shadow-soft ring-1 ring-ink-900/5", className)}>
      {sponsor.logo_url ? (
        // eslint-disable-next-line @next/next/no-img-element -- logo caricato dalla piattaforma
        <img src={sponsor.logo_url} alt={sponsor.name} className="h-14 w-auto max-w-[11rem] object-contain" loading="lazy" />
      ) : (
        <>
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl font-display text-lg text-white shadow-sm" style={{ backgroundColor: color }} aria-hidden="true">
            {initials(sponsor.name)}
          </span>
          <span className="min-w-0 text-left leading-tight">
            <span className="block max-w-[12rem] truncate font-semibold text-ink-900">{sponsor.name}</span>
            {sponsor.tagline && <span className="block max-w-[12rem] truncate text-xs text-ink-500">{sponsor.tagline}</span>}
          </span>
        </>
      )}
    </span>
  );
}

export function SponsorMarquee({ sponsors, eyebrow, title, cta }: { sponsors: Sponsor[]; eyebrow: string; title: string; cta: { href: string; label: string } }) {
  if (sponsors.length === 0) return null;
  // Abbastanza copie da riempire lo schermo, poi raddoppiate: l'animazione
  // va da 0 a -50% e ricomincia senza salto.
  const copies = Math.max(1, Math.ceil(8 / sponsors.length));
  const row = Array.from({ length: copies }, () => sponsors).flat();
  return (
    <section aria-label={title} className="relative overflow-hidden border-y border-ink-900/5 bg-gradient-to-r from-accent-50 via-white to-brand-50 py-8">
      <div className="mx-auto mb-5 flex max-w-7xl flex-wrap items-end justify-between gap-3 px-4 sm:px-6">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-brand-600">★ {eyebrow}</p>
          <h2 className="text-xl text-ink-900 sm:text-2xl">{title}</h2>
        </div>
        <Link href={cta.href} className="text-sm font-semibold text-brand-700 hover:underline">{cta.label} →</Link>
      </div>
      <div className="relative [mask-image:linear-gradient(to_right,transparent,black_6%,black_94%,transparent)]">
        <ul className="flex w-max gap-4 animate-sponsor-marquee">
          {[...row, ...row].map((s, i) => (
            <li key={`${s.id}-${i}`} aria-hidden={i >= row.length ? true : undefined}>
              <Link href={`/patrocinadores/${s.slug}`} tabIndex={i >= row.length ? -1 : undefined}
                className="block transition hover:-translate-y-1 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-300 rounded-2xl"
                title={s.name}>
                <SponsorTile sponsor={s} />
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
