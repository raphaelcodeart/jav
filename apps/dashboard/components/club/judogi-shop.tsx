"use client";

import { MotionConfig, motion } from "motion/react";
import { useEffect, useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Pagination } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { JavMarketProductModal } from "@/components/jav-market-product-modal";
import { JudogiCalculator, useJudogiAthletes } from "@/components/club/judogi-calculator";
import { clubGet, clubSend } from "@/lib/club";
import { cn } from "@/lib/cn";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";
import { JUDOGI_KEYS, STATUS_TONE, type JudogiAthlete, type JudogiOrder, type Wish } from "@/lib/judogi";
import type { JavMarketProductRead } from "@/lib/types";

// La Loja delle aree del club (apps/api/app/domains/club/judogi.py):
// - l'atleta vede lo Shop e il calcolatore dei judogi; se è maggiorenne
//   compra, se è minorenne mette i prodotti nella lista dei desideri e il
//   titolare riceve la notifica;
// - la famiglia trova i desideri dei figli (e li trasforma in un ordine, o
//   li rifiuta), il calcolatore e gli ordini dei judogi.

const PAGE = 12;

function useWishes() {
  return useQuery({ queryKey: JUDOGI_KEYS.wishes, queryFn: () => clubGet<Wish[]>("/wishlist"), retry: false });
}

function useJudogiOrders() {
  return useQuery({ queryKey: JUDOGI_KEYS.orders, queryFn: () => clubGet<JudogiOrder[]>("/judogi/orders"), retry: false });
}

/** La sezione «Loja» dell'area dell'atleta. */
export function AthleteShop({ athleteId }: { athleteId: string }) {
  const { data: athletes, isLoading } = useJudogiAthletes();
  const me = athletes?.find((a) => a.id === athleteId) ?? null;
  const [calc, setCalc] = useState(false);
  const wishMode = me?.mode === "WISH";
  if (isLoading) return <Skeleton className="h-96" />;
  return (
    <MotionConfig reducedMotion="user">
      <div className="space-y-6">
        <ShopHero mode={me?.mode ?? "WISH"} onCalculator={() => setCalc(true)} />
        {wishMode && <WishList athleteId={athleteId} />}
        <ProductGrid athleteId={athleteId} wishMode={wishMode || !me} />
        <JudogiOrders athleteId={athleteId} />
        {calc && athletes && <JudogiCalculator athletes={athletes} initialAthleteId={athleteId} onClose={() => setCalc(false)} />}
      </div>
    </MotionConfig>
  );
}

/** Sopra lo Shop della famiglia: desideri dei figli, calcolatore, ordini. */
export function FamilyJudogiSection() {
  const { data: athletes } = useJudogiAthletes();
  const [calc, setCalc] = useState(false);
  if (!athletes || athletes.length === 0) return null;
  return (
    <MotionConfig reducedMotion="user">
      <div className="space-y-6">
        <ShopHero mode="BUY" family onCalculator={() => setCalc(true)} />
        <WishList athletes={athletes} />
        <JudogiOrders />
        {calc && <JudogiCalculator athletes={athletes.filter((a) => a.mode === "BUY")} onClose={() => setCalc(false)} />}
      </div>
    </MotionConfig>
  );
}

function ShopHero({ mode, family = false, onCalculator }: { mode: "BUY" | "WISH"; family?: boolean; onCalculator: () => void }) {
  const { t } = useI18n();
  return (
    <section className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-brand-600 via-brand-500 to-accent-500 p-6 text-white shadow-lift sm:p-8">
      <div className="pointer-events-none absolute -right-10 -top-16 h-56 w-56 rounded-full bg-white/20 blur-3xl" aria-hidden="true" />
      <div className="relative grid items-center gap-5 sm:grid-cols-[1fr_auto]">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-white/75">🛍️ {t("judo.shop.eyebrow")}</p>
          <h2 className="font-display text-3xl leading-tight">{family ? t("judo.shop.familyTitle") : t("judo.shop.title")}</h2>
          <p className="mt-1 max-w-xl text-sm text-white/85">
            {family ? t("judo.shop.familyText") : mode === "WISH" ? t("judo.shop.wishText") : t("judo.shop.buyText")}
          </p>
        </div>
        <motion.button type="button" whileTap={{ scale: 0.97 }} onClick={onCalculator}
          className="flex cursor-pointer items-center gap-3 rounded-3xl bg-white/95 px-5 py-4 text-left text-ink-900 shadow-soft ring-1 ring-white/60 transition hover:bg-white">
          <span className="text-4xl" aria-hidden="true">🥋</span>
          <span>
            <span className="block font-display text-lg leading-tight">{t("judo.shop.calcTitle")}</span>
            <span className="block text-xs text-ink-600">{t("judo.shop.calcText")}</span>
          </span>
        </motion.button>
      </div>
    </section>
  );
}

// --- La vetrina dello Shop -------------------------------------------------------------------

interface Page { items: JavMarketProductRead[]; total: number }

function ProductGrid({ athleteId, wishMode }: { athleteId: string; wishMode: boolean }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<JavMarketProductRead | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    const timer = setTimeout(() => { setQ(search.trim()); setPage(1); }, 350);
    return () => clearTimeout(timer);
  }, [search]);
  const { data, isLoading } = useQuery({
    queryKey: ["club", "loja", q, page],
    queryFn: async (): Promise<Page> => {
      const params = new URLSearchParams({ offset: String((page - 1) * PAGE), limit: String(PAGE) });
      if (q) params.set("q", q);
      const res = await fetch(`/api/proxy/jav-market/products/mine/page?${params}`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
    placeholderData: keepPreviousData,
  });
  const { data: wishes } = useWishes();
  const wished = new Set((wishes ?? []).filter((w) => w.status === "OPEN" && w.athlete_id === athleteId && w.product).map((w) => w.product!.id));

  async function wish(p: JavMarketProductRead) {
    setBusy(p.id);
    try {
      await clubSend("/wishlist", "POST", { athlete_id: athleteId, kind: "PRODUCT", product_id: p.id, variant_id: p.variants[0]?.id ?? null });
      await queryClient.invalidateQueries({ queryKey: JUDOGI_KEYS.wishes });
      toast({ tone: "success", title: t("judo.wish.added"), text: t("judo.wish.addedText") });
    } catch (e) {
      toast({ tone: "error", title: t("judo.calc.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-2xl text-ink-900">{t("judo.shop.products")}</h2>
        <div className="relative w-full sm:w-72">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true">⌕</span>
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("judo.shop.search")} className="h-11 pl-9" aria-label={t("judo.shop.search")} />
        </div>
      </div>
      {isLoading ? <Skeleton className="h-64" /> : !data?.items.length ? (
        <EmptyState icon={<span className="text-3xl">🛍️</span>} title={q ? t("judo.shop.noMatch") : t("judo.shop.empty")} />
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3 xl:grid-cols-4">
          {data.items.map((p, i) => (
            <motion.li key={p.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }}
              className="flex flex-col overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/5">
              <button type="button" onClick={() => setOpen(p)} className="group block cursor-pointer text-left">
                <div className="aspect-square overflow-hidden bg-ink-50">
                  {/* eslint-disable-next-line @next/next/no-img-element -- immagini dello Shop nel bucket pubblico */}
                  {p.image_url ? <img src={p.image_url} alt="" className="h-full w-full object-cover transition group-hover:scale-105" loading="lazy" /> : <div className="flex h-full items-center justify-center text-5xl">🥋</div>}
                </div>
                <div className="p-3">
                  <p className="line-clamp-2 text-sm font-semibold leading-snug text-ink-900">{p.name}</p>
                  <p className="mt-1 text-sm font-bold text-brand-700">
                    {p.min_price_cents === p.max_price_cents ? fmt.euro(p.min_price_cents) : t("judo.from", { amount: fmt.euro(p.min_price_cents) })}
                  </p>
                  {p.seller?.name && <p className="text-[11px] text-ink-500">{p.seller.name}</p>}
                </div>
              </button>
              <div className="mt-auto px-3 pb-3">
                {wishMode ? (
                  <Button size="sm" variant={wished.has(p.id) ? "secondary" : "accent"} className="w-full" disabled={wished.has(p.id)} loading={busy === p.id} onClick={() => void wish(p)}>
                    {wished.has(p.id) ? `💝 ${t("judo.wish.inList")}` : `♡ ${t("judo.wish.add")}`}
                  </Button>
                ) : (
                  <Button size="sm" className="w-full" disabled={p.purchasable === false || !p.in_stock} onClick={() => setOpen(p)}>{t("judo.shop.buy")}</Button>
                )}
              </div>
            </motion.li>
          ))}
        </ul>
      )}
      <Pagination page={page} pages={Math.max(1, Math.ceil((data?.total ?? 0) / PAGE))} onChange={setPage} />
      {open && !wishMode && <JavMarketProductModal product={open} initialAthleteId={athleteId} onClose={() => setOpen(null)} />}
      {open && wishMode && <ProductPeek product={open} wished={wished.has(open.id)} busy={busy === open.id} onWish={() => void wish(open)} onClose={() => setOpen(null)} />}
    </section>
  );
}

/** Il prodotto visto da chi può solo desiderarlo: foto, descrizione, ♡. */
function ProductPeek({ product, wished, busy, onWish, onClose }: { product: JavMarketProductRead; wished: boolean; busy: boolean; onWish: () => void; onClose: () => void }) {
  const { t, fmt } = useI18n();
  return (
    <Modal open onClose={onClose} size="lg" title={product.name} subtitle={product.seller?.name}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
        <Button variant="accent" disabled={wished} loading={busy} onClick={onWish}>{wished ? `💝 ${t("judo.wish.inList")}` : `♡ ${t("judo.wish.add")}`}</Button>
      </>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="aspect-square overflow-hidden rounded-2xl bg-ink-50">
          {/* eslint-disable-next-line @next/next/no-img-element -- immagini dello Shop nel bucket pubblico */}
          {product.image_url ? <img src={product.image_url} alt="" className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center text-6xl">🥋</div>}
        </div>
        <div className="space-y-3">
          <p className="font-display text-2xl text-brand-700">{fmt.euro(product.min_price_cents)}</p>
          {product.variants.length > 1 && <div className="flex flex-wrap gap-1.5">{product.variants.map((v) => <Badge key={v.id} tone="neutral">{v.label}</Badge>)}</div>}
          <p className="whitespace-pre-line text-sm text-ink-600">{product.description}</p>
          <p className="rounded-2xl bg-accent-100 px-3 py-2 text-xs text-ink-800 ring-1 ring-accent-300">{t("judo.wish.peekHint")}</p>
        </div>
      </div>
    </Modal>
  );
}

// --- La lista dei desideri ------------------------------------------------------------------

function WishList({ athleteId, athletes }: { athleteId?: string; athletes?: JudogiAthlete[] }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading } = useWishes();
  const [calcFor, setCalcFor] = useState<Wish | null>(null);
  const [product, setProduct] = useState<{ wish: Wish; card: JavMarketProductRead } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const wishes = (data ?? []).filter((w) => !athleteId || w.athlete_id === athleteId);
  const open = wishes.filter((w) => w.status === "OPEN");
  const past = wishes.filter((w) => w.status !== "OPEN").slice(0, 6);

  async function act(w: Wish, what: "ORDERED" | "DISMISSED" | "REMOVE") {
    setBusy(w.id);
    try {
      if (what === "REMOVE") await clubSend(`/wishlist/${w.id}`, "DELETE");
      else await clubSend(`/wishlist/${w.id}`, "PATCH", { status: what });
      await queryClient.invalidateQueries({ queryKey: JUDOGI_KEYS.wishes });
    } catch (e) {
      toast({ tone: "error", title: t("judo.calc.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function buy(w: Wish) {
    if (w.kind === "JUDOGI") {
      setCalcFor(w);
      return;
    }
    setBusy(w.id);
    try {
      const res = await fetch(`/api/proxy/jav-market/products/mine/${w.product!.id}`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setProduct({ wish: w, card: await res.json() });
    } catch (e) {
      toast({ tone: "error", title: t("judo.calc.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <Skeleton className="h-32" />;
  if (athletes && open.length === 0 && past.length === 0) return null;

  return (
    <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
      <div className="mb-4 flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-pink-50 text-2xl" aria-hidden="true">💝</span>
        <div className="min-w-0">
          <h2 className="font-display text-xl text-ink-900">{athleteId ? t("judo.wish.myTitle") : t("judo.wish.familyTitle")}</h2>
          <p className="text-sm text-ink-500">{athleteId ? t("judo.wish.myText") : t("judo.wish.familyText")}</p>
        </div>
        {open.length > 0 && <Badge tone="accent" className="ml-auto">{open.length}</Badge>}
      </div>
      {open.length === 0 ? <p className="rounded-2xl bg-ink-50 p-4 text-sm text-ink-500">{t("judo.wish.empty")}</p> : (
        <ul className="grid gap-3 md:grid-cols-2">
          {open.map((w) => (
            <motion.li key={w.id} layout className="flex gap-3 rounded-2xl bg-ink-50/70 p-3 ring-1 ring-ink-100">
              <WishThumb wish={w} />
              <div className="min-w-0 flex-1">
                {!athleteId && <p className="text-[11px] font-bold uppercase tracking-wider text-brand-600">{w.athlete_first_name}</p>}
                <p className="truncate font-semibold text-ink-900">{wishTitle(w, t)}</p>
                <p className="text-xs text-ink-500">{wishSub(w, t)}{wishPrice(w) != null ? ` · ${fmt.euro(wishPrice(w)!)}` : ""}</p>
                {w.note && <p className="mt-1 line-clamp-2 text-xs italic text-ink-600">“{w.note}”</p>}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {w.can_decide && <Button size="sm" loading={busy === w.id} onClick={() => void buy(w)}>{w.kind === "JUDOGI" ? `🥋 ${t("judo.wish.order")}` : `🛒 ${t("judo.wish.buy")}`}</Button>}
                  {w.can_decide && <Button size="sm" variant="ghost" disabled={busy === w.id} onClick={() => void act(w, "ORDERED")}>✓ {t("judo.wish.bought")}</Button>}
                  {w.can_decide && <Button size="sm" variant="ghost" className="text-rose-700" disabled={busy === w.id} onClick={() => void act(w, "DISMISSED")}>{t("judo.wish.dismiss")}</Button>}
                  {!w.can_decide && w.can_remove && <Button size="sm" variant="ghost" disabled={busy === w.id} onClick={() => void act(w, "REMOVE")}>✕ {t("judo.wish.remove")}</Button>}
                </div>
              </div>
            </motion.li>
          ))}
        </ul>
      )}
      {past.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-2">
          {past.map((w) => (
            <li key={w.id}><Badge tone={w.status === "ORDERED" ? "success" : "neutral"}>{w.status === "ORDERED" ? "✓" : "✕"} {athleteId ? "" : `${w.athlete_first_name}: `}{wishTitle(w, t)}</Badge></li>
          ))}
        </ul>
      )}
      {calcFor && (athletes ?? []).length > 0 && (
        <JudogiCalculator athletes={(athletes ?? []).filter((a) => a.mode === "BUY")} initialAthleteId={calcFor.athlete_id}
          initialChoice={calcFor.judogi?.choice ?? null} initialName={calcFor.judogi?.kimono_name ?? null} wishId={calcFor.id}
          onClose={() => setCalcFor(null)} />
      )}
      {product && <JavMarketProductModal product={product.card} initialAthleteId={product.wish.athlete_id} onClose={() => setProduct(null)} />}
    </section>
  );
}

type T = ReturnType<typeof useI18n>["t"];

function wishTitle(w: Wish, t: T) {
  if (w.kind === "PRODUCT") return w.product?.name ?? t("judo.wish.gone");
  const q = w.judogi?.quote;
  return q ? `${t(`judo.type.${q.kimono_type}` as "judo.type.TRAINING")} ${q.brand}` : "Judogi";
}

function wishSub(w: Wish, t: T) {
  if (w.kind === "PRODUCT") return w.variant && w.variant.label !== "Unica" ? w.variant.label : t("judo.wish.product");
  const q = w.judogi?.quote;
  return q ? `${t(`judo.color.${q.color}` as "judo.color.WHITE")} · ${q.size_cm} cm` : "";
}

function wishPrice(w: Wish): number | null {
  if (w.kind === "PRODUCT") return w.variant?.price_cents ?? null;
  return w.judogi?.quote.total_cents ?? null;
}

function WishThumb({ wish }: { wish: Wish }) {
  return (
    <span className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-white text-3xl ring-1 ring-ink-100">
      {/* eslint-disable-next-line @next/next/no-img-element -- immagini dello Shop nel bucket pubblico */}
      {wish.product?.image_url ? <img src={wish.product.image_url} alt="" className="h-full w-full object-cover" /> : "🥋"}
    </span>
  );
}

// --- Gli ordini dei judogi ------------------------------------------------------------------

function JudogiOrders({ athleteId }: { athleteId?: string }) {
  const { t, fmt } = useI18n();
  const { data } = useJudogiOrders();
  const orders = (data ?? []).filter((o) => !athleteId || o.athlete_id === athleteId);
  if (orders.length === 0) return null;
  return (
    <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
      <h2 className="mb-3 font-display text-xl text-ink-900">🥋 {t("judo.orders.title")}</h2>
      <ul className="divide-y divide-ink-100">
        {orders.map((o) => (
          <li key={o.id} className="flex flex-wrap items-center gap-3 py-3">
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-ink-900">{t(`judo.type.${o.kimono_type}` as "judo.type.TRAINING")} · {o.brand}</p>
              <p className="text-xs text-ink-500">
                {athleteId ? "" : `${o.athlete_name} · `}{o.color_label} · {o.size_cm} cm · «{o.kimono_name}» · {fmt.shortDate(o.created_at)}
              </p>
            </div>
            {o.price_cents != null && <span className="text-sm font-bold text-ink-900">{fmt.euro(o.price_cents)}</span>}
            {o.fee_status && <Badge tone={o.fee_status === "PAID" ? "success" : "warning"}>{o.fee_status === "PAID" ? t("judo.orders.paid") : t("judo.orders.toPay")}</Badge>}
            <Badge tone={STATUS_TONE[o.status]} className={cn(o.status === "CANCELLED" && "line-through")}>{t(`judo.status.${o.status}` as "judo.status.PENDING")}</Badge>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-ink-500">{t("judo.orders.payHint")}</p>
    </section>
  );
}
