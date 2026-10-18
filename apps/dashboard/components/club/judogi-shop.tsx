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
import { ProgressBar } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { JavMarketProductModal } from "@/components/jav-market-product-modal";
import { JudogiWizard, type WizardStart } from "@/components/club/judogi-wizard";
import { CartButton, CartModal } from "@/components/club/loja-cart";
import {
  LockBadge, LojaPhoto, useJudogiAthletes, useLojaCart, useLojaPay, useLojaRefresh, useLojaShop, type LojaPayer,
} from "@/components/club/loja-common";
import { ProductCard, ProductModal } from "@/components/club/loja-product";
import { PayModal } from "@/components/club/pay-modal";
import { clubGet, clubSend, type Family } from "@/lib/club";
import { cn } from "@/lib/cn";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";
import { COLOR_SWATCH, JUDOGI_KEYS, KIMONO_TYPES, STATUS_TONE, type JudogiAthlete, type Wish } from "@/lib/judogi";
import { LOJA_KEYS, type KitItem, type LojaJudogi, type LojaOrder, type LojaProduct, type LojaShop } from "@/lib/loja";
import type { JavMarketProductRead } from "@/lib/types";

// La Loja del club (apps/api/app/domains/club/loja.py), una «loja guiada»:
// ogni atleta vede ciò che è per lui. Il server toglie i capi dell'altro
// sesso e mette il lucchetto a ciò che si vede ma non si compra (alta
// competizione, judogi rosa per i ragazzi); qui si mostra e si spiega.
// - la famiglia sceglie l'atleta, vede il suo kit, il judogi passo a passo,
//   l'equipaggiamento, e ordina tutto da un carrello unico (un ordine e una
//   quota per riga), pagando subito o più tardi dalla home;
// - l'atleta con il suo accesso vede la sua Loja: dai 18 anni compra, da
//   minorenne mette tutto nella lista dei desideri e il titolare lo vede.

const PAGE = 12;

function useWishes() {
  return useQuery({ queryKey: JUDOGI_KEYS.wishes, queryFn: () => clubGet<Wish[]>("/wishlist"), retry: false });
}

function useLojaOrders() {
  return useQuery({ queryKey: JUDOGI_KEYS.orders, queryFn: () => clubGet<LojaOrder[]>("/judogi/orders"), retry: false });
}

/** La sezione «Loja» dell'area dell'atleta. */
export function AthleteShop({ athleteId }: { athleteId: string }) {
  // Chi guarda: l'atleta con il suo accesso paga dalla sua area, il titolare
  // dalla famiglia (la stessa query dell'area, già in cache).
  const { data: area } = useQuery({
    queryKey: ["club", "athlete-area", athleteId],
    queryFn: () => clubGet<{ viewer_is_athlete: boolean }>(`/athlete-area/${athleteId}`),
  });
  const { data: shop, isLoading, error } = useLojaShop(athleteId);
  if (isLoading) return <Skeleton className="h-96" />;
  if (!shop) return error ? <p className="rounded-2xl bg-rose-50 p-4 text-sm text-rose-700 ring-1 ring-rose-200">{(error as Error).message}</p> : null;
  const payer: LojaPayer = area?.viewer_is_athlete ? { kind: "athlete", athleteId } : { kind: "family" };
  return (
    <MotionConfig reducedMotion="user">
      <div className="space-y-6">
        <Loja athletes={[shop.athlete]} payer={payer} self />
        {/* Lo Shop della piattaforma resta qui sotto, come prima della Loja. */}
        <ProductGrid athleteId={athleteId} wishMode={shop.athlete.mode === "WISH"} />
      </div>
    </MotionConfig>
  );
}

/** La Loja nella pagina della famiglia, sopra lo Shop della piattaforma. */
export function FamilyJudogiSection() {
  const { data: athletes } = useJudogiAthletes();
  if (!athletes || athletes.length === 0) return null;
  return (
    <MotionConfig reducedMotion="user">
      <Loja athletes={athletes} payer={{ kind: "family" }} />
    </MotionConfig>
  );
}

function Loja({ athletes, payer, self = false }: { athletes: JudogiAthlete[]; payer: LojaPayer; self?: boolean }) {
  const { t } = useI18n();
  const [picked, setPicked] = useState<string | null>(null);
  const current = athletes.find((a) => a.id === picked) ?? athletes[0]!;
  const { data: shop, isLoading, error } = useLojaShop(current.id);
  const canBuy = athletes.some((a) => a.mode === "BUY");
  const { data: cart } = useLojaCart(canBuy);
  const { data: wishes } = useWishes();
  const { pay, modal: payModal } = useLojaPay(payer);
  const [wizard, setWizard] = useState<{ initial: WizardStart | null } | null>(null);
  const [product, setProduct] = useState<LojaProduct | null>(null);
  const [cartOpen, setCartOpen] = useState(false);
  const wishMode = shop?.athlete.mode === "WISH";
  const payNow = (feeIds: string[]) => void pay(feeIds);
  const wished = new Set((wishes ?? []).filter((w) => w.status === "OPEN" && w.athlete_id === current.id && w.product).map((w) => w.product!.id));
  const wizardAthletes = self ? athletes : athletes.filter((a) => a.mode === "BUY");
  const count = cart?.count ?? 0;

  return (
    <div className="space-y-6">
      {/* --- Il titolo e il carrello --- */}
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-brand-600">{t("loja.eyebrow")}</p>
          <h2 className="font-display text-3xl leading-tight text-ink-900">{t("loja.title")}</h2>
        </div>
        {canBuy && (
          <Button variant="secondary" onClick={() => setCartOpen(true)} aria-label={t("loja.cart.aria", { n: count })}>
            🛒 <span className="hidden sm:inline">{t("loja.cart.open")}</span>
            {count > 0 && <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-500 px-1.5 text-[11px] font-extrabold text-white">{count}</span>}
          </Button>
        )}
      </div>

      {/* --- Per chi --- */}
      <section className="space-y-2">
        {!self && <p className="text-sm font-semibold text-ink-600">{t("loja.forWhom")}</p>}
        <div className="flex gap-2 overflow-x-auto pb-1">
          {athletes.map((a) => {
            const on = a.id === current.id;
            return (
              <button key={a.id} type="button" onClick={() => setPicked(a.id)} aria-pressed={on}
                className={cn("flex min-h-[60px] min-w-[10.5rem] flex-1 cursor-pointer items-center gap-2.5 rounded-2xl border-2 bg-white px-3 py-2 text-left transition sm:flex-none",
                  on ? "border-brand-500 shadow-soft" : "border-ink-100 hover:border-brand-200")}>
                <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full text-sm font-extrabold", on ? "bg-brand-500 text-white" : "bg-ink-100 text-ink-700")}>
                  {/* eslint-disable-next-line @next/next/no-img-element -- foto profilo nel bucket pubblico */}
                  {a.photo_url ? <img src={a.photo_url} alt="" className="h-full w-full object-cover" /> : a.first_name.slice(0, 1).toUpperCase()}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[15px] font-bold text-ink-900">{a.first_name}</span>
                  <span className="block truncate text-xs text-ink-500">
                    {t("judo.athlete.age", { n: a.age })}{a.height_cm ? ` · ${a.height_cm} cm` : ""}
                    {on && shop?.athlete.high_competition ? ` · ${t("loja.highCompetition")}` : ""}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
        {shop && <ProfileHint shop={shop} />}
      </section>

      {isLoading ? <Skeleton className="h-96" /> : error ? (
        <p className="rounded-2xl bg-rose-50 p-4 text-sm text-rose-700 ring-1 ring-rose-200">{(error as Error).message}</p>
      ) : shop && (
        <>
          <KitCard kit={shop.kit} onPick={(k) => {
            if (k.code === "WHITE_JUDOGI") setWizard({ initial: null });
            else setProduct(shop.products.find((p) => p.id === k.product_id) ?? null);
          }} />

          {/* --- Il judogi passo a passo --- */}
          <motion.button type="button" whileTap={{ scale: 0.98 }} onClick={() => setWizard({ initial: null })}
            className="relative flex w-full cursor-pointer flex-col gap-2 overflow-hidden rounded-3xl bg-brand-600 p-5 text-left text-white shadow-brand transition hover:bg-brand-700 sm:p-6">
            <span className="pointer-events-none absolute -right-8 -top-10 h-40 w-40 rounded-full bg-white/10 blur-2xl" aria-hidden="true" />
            <span className="text-xs font-bold uppercase tracking-[0.16em] text-brand-100">Judogi</span>
            <span className="font-display text-2xl leading-tight">{t("loja.cta.title")}</span>
            <span className="max-w-xl text-sm leading-relaxed text-brand-50">{wishMode ? t("loja.cta.textWish") : t("loja.cta.text")}</span>
            <span className="mt-1 self-start rounded-full bg-white px-5 py-3 text-[15px] font-bold text-brand-700">{t("loja.cta.button")}</span>
          </motion.button>

          <JudogiRow judogis={shop.judogis} onPick={(start) => setWizard({ initial: start })} />

          {/* --- L'equipaggiamento --- */}
          <section className="space-y-3">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="text-lg font-extrabold text-ink-900">{t("loja.equipmentFor", { name: shop.athlete.first_name })}</h2>
              <span className="text-sm text-ink-500">{t("loja.itemsCount", { n: shop.products.length })}</span>
            </div>
            {shop.products.length === 0 ? (
              <p className="rounded-2xl bg-white p-6 text-center text-sm text-ink-500 ring-1 ring-ink-100">{t("loja.noProducts")}</p>
            ) : (
              <ul className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3 xl:grid-cols-4">
                {shop.products.map((p, i) => <ProductCard key={p.id} product={p} index={i} onOpen={() => setProduct(p)} />)}
              </ul>
            )}
          </section>
        </>
      )}

      <WishList athleteId={self ? current.id : undefined} athletes={athletes} onPay={payNow} />
      <JudogiOrders athleteId={self ? current.id : undefined} onPay={canBuy ? payNow : undefined} />

      {canBuy && <CartButton count={count} onClick={() => setCartOpen(true)} />}

      {wizard && wizardAthletes.length > 0 && (
        <JudogiWizard athletes={wizardAthletes} initialAthleteId={current.id} initial={wizard.initial}
          onClose={() => setWizard(null)} onOpenCart={canBuy ? () => setCartOpen(true) : undefined} onPay={payNow} />
      )}
      {product && shop && (
        <ProductModal product={product} athlete={shop.athlete} wished={wished.has(product.id)} onClose={() => setProduct(null)} onPay={payNow} />
      )}
      {cartOpen && <CartModal onClose={() => setCartOpen(false)} onPay={payNow} />}
      {payModal}
    </div>
  );
}

/** Una riga che dice che cosa si vede e perché, per questo atleta. */
function ProfileHint({ shop }: { shop: LojaShop }) {
  const { t } = useI18n();
  const a = shop.athlete;
  const models = a.sex === "F" ? t("loja.profile.F") : a.sex === "M" ? t("loja.profile.M") : t("loja.profile.ALL");
  const parts = [
    a.height_cm ? t("loja.profile.base", { name: a.first_name, models, cm: a.height_cm }) : t("loja.profile.noHeight", { name: a.first_name, models }),
    a.high_competition ? t("loja.profile.hc", { name: a.first_name }) : t("loja.profile.notHc"),
  ];
  if (a.mode === "WISH") parts.push(t("loja.profile.wish"));
  return (
    <p className="flex gap-2.5 rounded-2xl bg-accent-50 px-3 py-2.5 text-[13px] leading-relaxed text-accent-900">
      <span aria-hidden="true">ℹ️</span>
      <span>{parts.join(" ")}</span>
    </p>
  );
}

const KIT_STATE: Record<KitItem["state"], { dot: string; tag: string }> = {
  HAS: { dot: "bg-emerald-500", tag: "bg-emerald-50 text-emerald-700" },
  ORDERED: { dot: "bg-accent-500", tag: "bg-accent-100 text-accent-900" },
  MISSING: { dot: "bg-brand-500", tag: "bg-brand-50 text-brand-700" },
};

/** Il kit del club dell'atleta: che cosa ha, che cosa è in arrivo, che cosa
 *  manca (e da qui si apre). */
function KitCard({ kit, onPick }: { kit: KitItem[]; onPick: (k: KitItem) => void }) {
  const { t } = useI18n();
  if (kit.length === 0) return null;
  const has = kit.filter((k) => k.state === "HAS").length;
  return (
    <section className="space-y-3 rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-extrabold text-ink-900">{t("loja.kit.title")}</h2>
        <span className="text-sm font-bold text-brand-600">{t("loja.kit.progress", { n: has, total: kit.length })}</span>
      </div>
      <ProgressBar value={has} max={kit.length} className="h-2" label={t("loja.kit.title")} />
      <ul className="space-y-1">
        {kit.map((k) => {
          const style = KIT_STATE[k.state];
          const label = k.code === "WHITE_JUDOGI" ? t("loja.kit.whiteJudogi") : k.name ?? "";
          const inner = (
            <>
              <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", style.dot)} aria-hidden="true" />
              <span className="flex-1 text-sm text-ink-900">{label}</span>
              <span className={cn("rounded-full px-2.5 py-1 text-xs font-bold", style.tag)}>{t(`loja.kit.${k.state}` as "loja.kit.HAS")}</span>
            </>
          );
          return (
            <li key={`${k.code}-${k.product_id ?? ""}`}>
              {k.state === "MISSING" ? (
                <button type="button" onClick={() => onPick(k)} className="flex min-h-10 w-full cursor-pointer items-center gap-2.5 rounded-xl px-1 text-left transition hover:bg-ink-50">
                  {inner}
                </button>
              ) : <div className="flex min-h-10 items-center gap-2.5 px-1">{inner}</div>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** I modelli di judogi in una fila che scorre: uno per tipo e marca, con i
 *  suoi colori. Si apre il passo a passo con il modello già scelto. */
function JudogiRow({ judogis, onPick }: { judogis: LojaJudogi[]; onPick: (start: WizardStart) => void }) {
  const { t, fmt } = useI18n();
  const groups: { key: string; items: LojaJudogi[] }[] = [];
  for (const type of KIMONO_TYPES) {
    for (const j of judogis.filter((x) => x.kimono_type === type)) {
      const key = `${j.kimono_type}|${j.brand}`;
      const g = groups.find((x) => x.key === key);
      if (g) g.items.push(j);
      else groups.push({ key, items: [j] });
    }
  }
  if (groups.length === 0) return null;
  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-extrabold text-ink-900">{t("loja.judogis")}</h2>
        <span className="text-sm text-ink-500">{t("loja.modelsCount", { n: groups.length })}</span>
      </div>
      <ul className="-mx-1 flex snap-x gap-3 overflow-x-auto px-1 pb-2">
        {groups.map(({ key, items }) => {
          const open = items.filter((j) => !j.lock);
          const lead = open[0] ?? items[0]!;
          const photo = (open.find((j) => j.image_url) ?? items.find((j) => j.image_url))?.image_url ?? null;
          // Il più basso fra i prezzi che il server ha dato per la taglia dell'atleta.
          const from = Math.min(...items.map((j) => j.suggested_price_cents ?? j.min_price_cents));
          const lock = open.length === 0 ? lead.lock : null;
          const body = (
            <>
              <span className="relative block h-32">
                <LojaPhoto src={photo} judogi color={lead.color} className="h-full w-full" size={64} />
                {lead.kimono_type === "FIJ_APPROVED" && (
                  <span className="absolute left-2 top-2 rounded-full bg-accent-500 px-2 py-0.5 text-[11px] font-bold text-ink-900">{t("loja.highCompetition")}</span>
                )}
              </span>
              <span className="flex flex-1 flex-col gap-1 p-3">
                <span className="text-sm font-bold text-ink-900">{lead.brand}</span>
                <span className="text-xs text-ink-500">{t(`judo.type.${lead.kimono_type}` as "judo.type.TRAINING")}</span>
                <span className="flex gap-1">
                  {items.map((j) => <span key={j.color} title={t(`judo.color.${j.color}` as "judo.color.WHITE")} className={cn("h-3.5 w-3.5 rounded-full ring-1", COLOR_SWATCH[j.color])} />)}
                </span>
                <span className="mt-auto pt-1 text-sm font-extrabold text-brand-700">{t("judo.from", { amount: fmt.euro(from) })}</span>
                {lock && <LockBadge lock={lock} className="self-start" />}
              </span>
            </>
          );
          return (
            <li key={key} className="flex w-40 shrink-0 snap-start">
              {lock ? (
                <div className="flex w-full flex-col overflow-hidden rounded-3xl bg-white opacity-80 shadow-soft ring-1 ring-ink-900/5">{body}</div>
              ) : (
                <button type="button" onClick={() => onPick({ kimono_type: lead.kimono_type, color: lead.color, brand: lead.brand })}
                  className="flex w-full cursor-pointer flex-col overflow-hidden rounded-3xl bg-white text-left shadow-soft ring-1 ring-ink-900/5 transition hover:-translate-y-0.5 hover:shadow-lift motion-reduce:transition-none motion-reduce:hover:translate-y-0">
                  {body}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// --- La vetrina dello Shop della piattaforma --------------------------------------------------

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
    queryKey: ["club", "shop-page", q, page],
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
        <h2 className="text-lg font-extrabold text-ink-900">{t("loja.platformShop")}</h2>
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
                  <LojaPhoto src={p.image_url} className="h-full w-full transition group-hover:scale-105 motion-reduce:transition-none motion-reduce:group-hover:scale-100" />
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
          <LojaPhoto src={product.image_url} className="h-full w-full" size={96} />
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

/** I desideri: l'atleta minorenne vede i suoi; il titolare quelli dei figli,
 *  e li mette nel carrello (il prezzo lo ricalcola il server) o risponde. */
function WishList({ athleteId, athletes, onPay }: { athleteId?: string; athletes: JudogiAthlete[]; onPay: (feeIds: string[]) => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const refresh = useLojaRefresh();
  const { data, isLoading } = useWishes();
  const [peek, setPeek] = useState<{ wish: Wish; card: JavMarketProductRead } | null>(null);
  const [clubProduct, setClubProduct] = useState<{ wish: Wish; shop: LojaShop; product: LojaProduct } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const wishes = (data ?? []).filter((w) => !athleteId || w.athlete_id === athleteId);
  const open = wishes.filter((w) => w.status === "OPEN");
  const past = wishes.filter((w) => w.status !== "OPEN").slice(0, 6);
  const selfWish = !!athleteId && athletes.find((a) => a.id === athleteId)?.mode === "WISH";

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

  async function toCart(w: Wish) {
    setBusy(w.id);
    try {
      if (w.kind === "JUDOGI" && w.judogi) {
        // Il desiderio va nel carrello con il suo id: all'ordine si chiude da solo.
        const kimono = w.judogi.kimono_name || athletes.find((a) => a.id === w.athlete_id)?.kimono_name || "";
        await clubSend("/loja/cart", "POST", { athlete_id: w.athlete_id, kind: "JUDOGI", judogi: { ...w.judogi.choice, kimono_name: kimono, wish_id: w.id } });
        await refresh();
        toast({ tone: "success", title: t("loja.cart.added"), text: t("loja.wish.inCartText") });
        return;
      }
      if (!w.product) return;
      // Un prodotto del club passa dal carrello della Loja; uno dello Shop
      // della piattaforma si compra come prima, dalla sua scheda.
      const shop = await queryClient.fetchQuery({ queryKey: LOJA_KEYS.shop(w.athlete_id), queryFn: () => clubGet<LojaShop>(`/loja/athletes/${w.athlete_id}`) });
      const product = shop.products.find((p) => p.id === w.product!.id);
      if (product) {
        if (w.variant && !product.needs_name && !product.lock) {
          await clubSend("/loja/cart", "POST", { athlete_id: w.athlete_id, kind: "PRODUCT", variant_id: w.variant.id, quantity: 1 });
          await refresh();
          toast({ tone: "success", title: t("loja.cart.added"), text: t("loja.cart.addedText", { name: product.name }) });
        } else {
          setClubProduct({ wish: w, shop, product });
        }
        return;
      }
      const res = await fetch(`/api/proxy/jav-market/products/mine/${w.product.id}`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setPeek({ wish: w, card: await res.json() });
    } catch (e) {
      toast({ tone: "error", title: t("judo.calc.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <Skeleton className="h-32" />;
  if (!selfWish && open.length === 0 && past.length === 0) return null;

  return (
    <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
      <div className="mb-4 flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-pink-50 text-2xl" aria-hidden="true">💝</span>
        <div className="min-w-0">
          <h2 className="text-lg font-extrabold text-ink-900">{selfWish ? t("judo.wish.myTitle") : t("judo.wish.familyTitle")}</h2>
          <p className="text-sm text-ink-500">{selfWish ? t("judo.wish.myText") : t("loja.wish.familyText")}</p>
        </div>
        {open.length > 0 && <Badge tone="accent" className="ml-auto">{open.length}</Badge>}
      </div>
      {open.length === 0 ? <p className="rounded-2xl bg-ink-50 p-4 text-sm text-ink-500">{t("judo.wish.empty")}</p> : (
        <ul className="grid gap-3 md:grid-cols-2">
          {open.map((w) => (
            <motion.li key={w.id} layout className="flex gap-3 rounded-2xl bg-ink-50/70 p-3 ring-1 ring-ink-100">
              <LojaPhoto src={w.product?.image_url} judogi={w.kind === "JUDOGI"} color={w.judogi?.quote.color ?? null}
                className="h-16 w-16 shrink-0 overflow-hidden rounded-xl ring-1 ring-ink-100" size={40} />
              <div className="min-w-0 flex-1">
                {!selfWish && <p className="text-[11px] font-bold uppercase tracking-wider text-brand-600">{w.athlete_first_name}</p>}
                <p className="truncate font-semibold text-ink-900">{wishTitle(w, t)}</p>
                <p className="text-xs text-ink-500">{wishSub(w, t)}{wishPrice(w) != null ? ` · ${fmt.euro(wishPrice(w)!)}` : ""}</p>
                {w.note && <p className="mt-1 line-clamp-2 text-xs italic text-ink-600">“{w.note}”</p>}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {w.can_decide && <Button size="sm" loading={busy === w.id} onClick={() => void toCart(w)}>🛒 {t("loja.wish.toCart")}</Button>}
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
            <li key={w.id}><Badge tone={w.status === "ORDERED" ? "success" : "neutral"}>{w.status === "ORDERED" ? "✓" : "✕"} {selfWish ? "" : `${w.athlete_first_name}: `}{wishTitle(w, t)}</Badge></li>
          ))}
        </ul>
      )}
      {clubProduct && (
        <ProductModal product={clubProduct.product} athlete={clubProduct.shop.athlete} initialVariantId={clubProduct.wish.variant?.id ?? null}
          onClose={() => setClubProduct(null)} onPay={onPay} />
      )}
      {peek && <JavMarketProductModal product={peek.card} initialAthleteId={peek.wish.athlete_id} onClose={() => setPeek(null)} />}
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

// --- Gli ordini della Loja ------------------------------------------------------------------

/** Gli ordini della Loja, judogi e prodotti del club, ognuno con la sua
 *  quota. `payable` (area della famiglia, «I miei ordini»): accanto a un
 *  ordine da pagare il bottone apre il pagamento della sua quota, la stessa
 *  che la famiglia trova fra le quote della home. Dentro la Loja il
 *  pagamento lo apre la Loja (`onPay`), per la famiglia o per l'atleta. */
export function JudogiOrders({ athleteId, payable = false, onPay }: { athleteId?: string; payable?: boolean; onPay?: (feeIds: string[]) => void }) {
  const { t, fmt } = useI18n();
  const { data } = useLojaOrders();
  const { data: family } = useQuery({
    queryKey: ["club", "family"], queryFn: () => clubGet<Family>("/family"), enabled: payable && !onPay, retry: false,
  });
  const [payFee, setPayFee] = useState<string | null>(null);
  const dueFees = family?.due_fees ?? [];
  const orders = (data ?? []).filter((o) => !athleteId || o.athlete_id === athleteId);
  if (orders.length === 0) return null;
  return (
    <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
      <h2 className="mb-3 text-lg font-extrabold text-ink-900">📦 {t("loja.orders.title")}</h2>
      <ul className="divide-y divide-ink-100">
        {orders.map((o) => {
          const canPay = o.fee_status === "DUE" && !!o.fee_id && (onPay ? true : payable && dueFees.some((f) => f.id === o.fee_id));
          return (
            <li key={o.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3">
              <div className="min-w-0 flex-1 basis-48">
                <p className="font-semibold text-ink-900">{orderTitle(o, t)}</p>
                <p className="text-xs text-ink-500">{[athleteId ? null : o.athlete_name, ...orderBits(o, t), fmt.shortDate(o.created_at)].filter(Boolean).join(" · ")}</p>
              </div>
              {o.price_cents != null && <span className="text-sm font-bold text-ink-900">{fmt.euro(o.price_cents)}</span>}
              {o.fee_status && <Badge tone={o.fee_status === "PAID" ? "success" : "warning"}>{o.fee_status === "PAID" ? t("judo.orders.paid") : t("judo.orders.toPay")}</Badge>}
              <Badge tone={STATUS_TONE[o.status]} className={cn(o.status === "CANCELLED" && "line-through")}>{t(`judo.status.${o.status}` as "judo.status.PENDING")}</Badge>
              {canPay && <Button size="sm" onClick={() => (onPay ? onPay([o.fee_id!]) : setPayFee(o.fee_id))}>{t("family.payNow")}</Button>}
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-xs text-ink-500">{t("judo.orders.payHint")}</p>
      {payFee && <PayModal open onClose={() => setPayFee(null)} fees={dueFees} preselect={[payFee]} />}
    </section>
  );
}

function orderTitle(o: LojaOrder, t: T) {
  if (o.kind === "PRODUCT") return `${o.quantity && o.quantity > 1 ? `${o.quantity} × ` : ""}${o.product_name ?? o.title}`;
  return o.kimono_type ? `${t(`judo.type.${o.kimono_type}` as "judo.type.TRAINING")} · ${o.brand ?? ""}` : o.title;
}

function orderBits(o: LojaOrder, t: T): (string | null)[] {
  if (o.kind === "PRODUCT") {
    return [o.variant_label && o.variant_label !== "Unica" ? o.variant_label : null, o.kimono_name ? `«${o.kimono_name}»` : null];
  }
  return [
    o.color ? t(`judo.color.${o.color}` as "judo.color.WHITE") : o.color_label,
    o.size_cm ? `${o.size_cm} cm` : null,
    o.kimono_name ? `«${o.kimono_name}»` : null,
  ];
}
