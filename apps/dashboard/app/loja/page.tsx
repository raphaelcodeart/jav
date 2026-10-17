import type { Metadata } from "next";
import Link from "next/link";
import { Container, EmptyNote } from "@/components/site/blocks";
import { HeroStat, PageHero } from "@/components/site/page-hero";
import { siteI18n } from "@/components/site/i18n";
import { linkButton } from "@/components/site/link-button";
import { PartnerBanner } from "@/components/site/partner-banner";
import { ChipScroller } from "@/components/ui/chip-scroller";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { cn } from "@/lib/cn";
import { isUuid, publicSite } from "@/lib/public-site";

type Search = { searchParams: Promise<Record<string, string | undefined>> };
const PAGE = 24;

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return { title: `${t("site.nav.shop")} · Judo Arte e Vida`, description: t("site.shop.text") };
}

/** Lo Shop JAV sul sito pubblico (jav_market/public_router.py): si guarda
 *  senza account, si compra da soci di un club della rete. «Comprar» porta a
 *  /loja/comprar, che lo spiega e mostra i club. Ricerca, categoria e pagina
 *  stanno nell'URL: la pagina si prepara sul server. */
export default async function ShopPage({ searchParams }: Search) {
  const params = await searchParams;
  const q = (params.q ?? "").slice(0, 80);
  const category = isUuid(params.cat ?? "") ? params.cat : undefined;
  const page = Math.max(1, Math.min(200, Number(params.page) || 1));
  const [{ t, fmt }, shop, photos] = await Promise.all([
    siteI18n(),
    publicSite.shop({ q: q || undefined, category_id: category, offset: String((page - 1) * PAGE), limit: String(PAGE) }),
    publicSite.photos(),
  ]);
  const items = shop?.items ?? [];
  const href = (over: Record<string, string | undefined>) => {
    const s = new URLSearchParams();
    const all = { q: q || undefined, cat: category, ...over };
    for (const [k, v] of Object.entries(all)) if (v) s.set(k, v);
    const str = s.toString();
    return str ? `/loja?${str}` : "/loja";
  };

  return (
    <SiteShell>
      <PageHero theme="ranking" icon="🛍️" photos={photos ?? []} eyebrow={t("site.shop.eyebrow")} title={t("site.shop.title")} text={t("site.shop.text")}>
        {shop && shop.shop_total > 0 && <HeroStat value={shop.shop_total} label={t("site.shop.heroProducts")} />}
      </PageHero>
      <Container className="py-8">
        <PartnerBanner className="mb-6" title={t("site.shop.partnersTitle")} text={t("site.shop.partnersText")} label={t("site.shop.partnerLabel")} />
        {!shop || shop.shop_total === 0 ? (
          <EmptyNote>{t("site.shop.closed")}</EmptyNote>
        ) : (
          <>
            <form action="/loja" className="flex flex-col gap-2 sm:flex-row">
              {category && <input type="hidden" name="cat" value={category} />}
              <input name="q" defaultValue={q} placeholder={t("site.shop.search")} aria-label={t("site.shop.search")}
                className="h-12 flex-1 rounded-2xl border border-ink-200 bg-white px-4 text-ink-900 shadow-soft focus:outline-none focus:ring-2 focus:ring-brand-500" />
              <button type="submit" className={linkButton({})}>🔎 {t("site.shop.searchButton")}</button>
            </form>
            {shop.categories.length > 0 && (
              <ChipScroller label={t("site.shop.categories")} className="mt-3">
                <Link href={href({ cat: undefined })} aria-current={!category ? "page" : undefined} className={chip(!category)}>{t("site.shop.all")}</Link>
                {shop.categories.map((c) => (
                  <Link key={c.id} href={href({ cat: c.id })} aria-current={category === c.id ? "page" : undefined} className={chip(category === c.id)}>
                    {c.name} <span className="opacity-60">{c.count}</span>
                  </Link>
                ))}
              </ChipScroller>
            )}
            {items.length === 0 ? (
              <div className="mt-8"><EmptyNote>{t("site.shop.none")}</EmptyNote></div>
            ) : (
              <ul className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
                {items.map((p, i) => (
                  <li key={p.id}>
                    <Reveal delay={i * 0.02} className="h-full">
                      <article className="glass-card group flex h-full flex-col overflow-hidden rounded-3xl">
                        <div className="relative aspect-square overflow-hidden bg-white">
                          {p.image_url ? (
                            // eslint-disable-next-line @next/next/no-img-element -- foto del prodotto nel bucket dei media
                            <img src={p.image_url} alt="" loading="lazy" className="h-full w-full object-contain p-3 transition-transform duration-500 group-hover:scale-105" />
                          ) : <div className="flex h-full items-center justify-center text-5xl">🛍️</div>}
                          {!p.in_stock && <span className="absolute left-2 top-2 rounded-full bg-ink-900/80 px-2 py-0.5 text-[11px] font-bold text-white">{t("site.shop.outOfStock")}</span>}
                        </div>
                        <div className="flex flex-1 flex-col p-4">
                          <h2 className="line-clamp-2 text-sm font-semibold text-ink-900">{p.name}</h2>
                          {p.description && <p className="mt-1 line-clamp-2 text-xs text-ink-500">{p.description.split("\n")[0]}</p>}
                          <p className="mt-auto pt-3 font-display text-xl text-brand-700">
                            {p.max_price_cents > p.price_cents ? t("site.shop.from", { price: fmt.euro(p.price_cents) }) : fmt.euro(p.price_cents)}
                          </p>
                          <Link href={`/loja/comprar?p=${p.id}`} className={cn(linkButton({ size: "sm" }), "mt-3 justify-center")}>🛒 {t("site.shop.buy")}</Link>
                        </div>
                      </article>
                    </Reveal>
                  </li>
                ))}
              </ul>
            )}
            <PageLinks page={page} pages={Math.max(1, Math.ceil(shop.total / PAGE))} href={(n) => href({ page: n > 1 ? String(n) : undefined })} />
            <p className="mt-6 text-center text-xs text-ink-500">{t("site.shop.vatNote")}</p>
          </>
        )}
      </Container>
    </SiteShell>
  );
}

/** Le pagine 1 2 3 come link (la pagina si prepara sul server). */
function PageLinks({ page, pages, href }: { page: number; pages: number; href: (n: number) => string }) {
  if (pages <= 1) return null;
  const list: (number | "…")[] = [];
  for (let p = 1; p <= pages; p++) {
    if (p === 1 || p === pages || Math.abs(p - page) <= 1) list.push(p);
    else if (list[list.length - 1] !== "…") list.push("…");
  }
  const cls = (active: boolean) => cn("inline-flex h-10 min-w-10 items-center justify-center rounded-xl px-3 text-sm font-semibold",
    active ? "bg-brand-600 text-white shadow-soft" : "bg-white text-ink-700 ring-1 ring-ink-200 hover:bg-ink-50");
  return (
    <nav aria-label="Páginas" className="mt-8 flex flex-wrap items-center justify-center gap-1.5">
      {page > 1 && <Link href={href(page - 1)} className={cls(false)} aria-label="‹">‹</Link>}
      {list.map((p, i) => p === "…" ? <span key={`g${i}`} className="px-1 text-ink-400">…</span> : (
        <Link key={p} href={href(p)} aria-current={p === page ? "page" : undefined} className={cls(p === page)}>{p}</Link>
      ))}
      {page < pages && <Link href={href(page + 1)} className={cls(false)} aria-label="›">›</Link>}
    </nav>
  );
}

function chip(active: boolean) {
  return cn(
    "shrink-0 whitespace-nowrap rounded-full px-4 py-2 text-sm font-semibold ring-1 transition",
    active ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-ink-700 ring-ink-200 hover:bg-ink-50",
  );
}
