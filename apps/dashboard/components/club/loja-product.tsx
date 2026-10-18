"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { LockBadge, LockIcon, LojaPhoto, useLojaRefresh } from "@/components/club/loja-common";
import { clubSend } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import type { CheckoutResult, LojaAthlete, LojaProduct } from "@/lib/loja";

// L'equipaggiamento del club nella Loja: la scheda nella griglia e il
// prodotto aperto (foto, taglie con quella consigliata già scelta, quantità,
// nome da stampare se serve). Chi compra lo mette nel carrello o lo compra
// subito; il minorenne (modo WISH) lo mette nella lista dei desideri.

function audienceTag(p: LojaProduct): { key: "loja.tag.hc" | "loja.tag.F" | "loja.tag.M" | "loja.tag.ALL"; hc: boolean } {
  if (p.high_competition_only) return { key: "loja.tag.hc", hc: true };
  return { key: `loja.tag.${p.audience_sex}` as "loja.tag.ALL", hc: false };
}

export function ProductCard({ product, onOpen, index = 0 }: { product: LojaProduct; onOpen: () => void; index?: number }) {
  const { t, fmt } = useI18n();
  const tag = audienceTag(product);
  const suggested = product.variants.find((v) => v.id === product.suggested_variant_id);
  const single = product.variants.length === 1 ? product.variants[0] : null;
  return (
    <motion.li initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(index, 8) * 0.03 }}
      className="overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/5">
      <button type="button" onClick={onOpen} className="group flex h-full w-full cursor-pointer flex-col text-left">
        <span className={cn("relative block h-32 overflow-hidden sm:h-40", tag.hc ? "bg-accent-100" : "bg-ink-100")}>
          <LojaPhoto src={product.image_url} className="h-full w-full transition duration-300 group-hover:scale-105 motion-reduce:transition-none motion-reduce:group-hover:scale-100" />
          <span className={cn("absolute left-2 top-2 rounded-full px-2 py-0.5 text-[11px] font-bold", tag.hc ? "bg-accent-500 text-ink-900" : "bg-white text-ink-700")}>
            {t(tag.key)}
          </span>
        </span>
        <span className="flex flex-1 flex-col gap-1.5 p-3">
          <span className="line-clamp-2 text-sm font-bold leading-snug text-ink-900">{product.name}</span>
          <span className="text-xs text-ink-500">
            {product.lock ? t(`loja.lock.${product.lock}` as "loja.lock.HIGH_COMPETITION")
              : suggested ? t("loja.product.suggested", { size: suggested.label })
              : product.variants.length > 1 ? t("loja.product.sizes", { n: product.variants.length }) : " "}
          </span>
          <span className="mt-auto flex items-center justify-between gap-2">
            <span className="text-[15px] font-extrabold text-ink-900">
              {single ? fmt.euro(single.price_cents) : t("judo.from", { amount: fmt.euro(product.min_price_cents) })}
            </span>
            {product.lock ? (
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-ink-100 text-ink-500"><LockIcon className="h-[18px] w-[18px]" /></span>
            ) : (
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-500 text-white shadow-brand" aria-hidden="true">
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
              </span>
            )}
          </span>
        </span>
      </button>
    </motion.li>
  );
}

export function ProductModal({ product, athlete, initialVariantId, wished = false, onClose, onPay }: {
  product: LojaProduct;
  athlete: LojaAthlete;
  initialVariantId?: string | null;
  wished?: boolean;
  onClose: () => void;
  onPay?: (feeIds: string[]) => void;
}) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const refresh = useLojaRefresh();
  const firstVariant = product.variants.find((v) => v.id === initialVariantId)
    ?? product.variants.find((v) => v.id === product.suggested_variant_id)
    ?? product.variants.find((v) => v.in_stock) ?? product.variants[0];
  const [variantId, setVariantId] = useState(firstVariant?.id ?? null);
  const [quantity, setQuantity] = useState(1);
  const [name, setName] = useState<string | null>(null);
  const [photo, setPhoto] = useState(0);
  const [busy, setBusy] = useState<"CART" | "BUY" | "WISH" | null>(null);
  const variant = product.variants.find((v) => v.id === variantId) ?? null;
  const wishMode = athlete.mode === "WISH";
  const printName = name ?? athlete.kimono_name;
  const nameOk = !product.needs_name || printName.trim().length >= 2;
  const photos = [...new Set([variant?.image_url, ...product.images, product.image_url].filter((u): u is string => !!u))];
  const shown = photos[Math.min(photo, photos.length - 1)] ?? null;
  const tag = audienceTag(product);
  const canBuy = !product.lock && !!variant?.in_stock && nameOk;

  async function act(what: "CART" | "BUY" | "WISH") {
    if (!variant) return;
    setBusy(what);
    try {
      if (what === "WISH") {
        await clubSend("/wishlist", "POST", { athlete_id: athlete.id, kind: "PRODUCT", product_id: product.id, variant_id: variant.id });
        await refresh();
        toast({ tone: "success", title: t("judo.wish.added"), text: t("judo.wish.addedText") });
        onClose();
        return;
      }
      const body = { athlete_id: athlete.id, kind: "PRODUCT", variant_id: variant.id, quantity, name: product.needs_name ? printName.trim() : null };
      if (what === "CART") {
        await clubSend("/loja/cart", "POST", body);
        await refresh();
        toast({ tone: "success", title: t("loja.cart.added"), text: t("loja.cart.addedText", { name: product.name }) });
        onClose();
      } else {
        const res = await clubSend<CheckoutResult>("/loja/buy-now", "POST", body);
        await refresh();
        toast({ tone: "success", title: t("loja.buy.doneTitle"), text: t("loja.buy.doneText") });
        onClose();
        onPay?.(res.fee_ids);
      }
    } catch (e) {
      toast({ tone: "error", title: t("judo.calc.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal open onClose={onClose} size="lg" title={product.name} subtitle={t("loja.product.for", { name: athlete.first_name })}
      footer={wishMode ? (
        <Button size="lg" variant="accent" className="w-full sm:w-auto" disabled={wished || !!product.lock || !variant} loading={busy === "WISH"} onClick={() => void act("WISH")}>
          {wished ? `💝 ${t("judo.wish.inList")}` : `♡ ${t("loja.wish.want")}`}
        </Button>
      ) : (
        <div className="flex w-full flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button size="lg" variant="secondary" disabled={!canBuy || !!busy} loading={busy === "BUY"} onClick={() => void act("BUY")}>{t("loja.buyNow")}</Button>
          <Button size="lg" disabled={!canBuy || !!busy} loading={busy === "CART"} onClick={() => void act("CART")}>🛒 {t("loja.addToCart")}</Button>
        </div>
      )}>
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-2">
          <div className={cn("relative aspect-square overflow-hidden rounded-3xl", tag.hc ? "bg-accent-100" : "bg-ink-100")}>
            <LojaPhoto src={shown} className="h-full w-full" size={96} />
            <span className={cn("absolute left-3 top-3 rounded-full px-2.5 py-0.5 text-xs font-bold", tag.hc ? "bg-accent-500 text-ink-900" : "bg-white text-ink-700")}>{t(tag.key)}</span>
          </div>
          {photos.length > 1 && (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {photos.map((src, i) => (
                <button key={src} type="button" onClick={() => setPhoto(i)} aria-label={t("loja.product.photo", { n: i + 1 })} aria-pressed={src === shown}
                  className={cn("h-14 w-14 shrink-0 cursor-pointer overflow-hidden rounded-xl ring-2 transition", src === shown ? "ring-brand-500" : "ring-transparent hover:ring-ink-200")}>
                  {/* eslint-disable-next-line @next/next/no-img-element -- foto della Loja nel bucket pubblico */}
                  <img src={src} alt="" className="h-full w-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="space-y-4">
          {variant && <p className="font-display text-3xl text-brand-700">{fmt.euro(variant.price_cents)}</p>}
          {product.lock && (
            <div className="space-y-2 rounded-2xl bg-ink-50 p-3 text-sm text-ink-700 ring-1 ring-ink-100">
              <LockBadge lock={product.lock} />
              <p>{t(`loja.lockText.${product.lock}` as "loja.lockText.HIGH_COMPETITION")}</p>
            </div>
          )}
          {product.variants.length > 1 && (
            <div role="group" aria-label={t("loja.product.size")}>
              <p className="mb-2 text-sm font-semibold text-ink-800">{t("loja.product.size")}</p>
              <div className="flex flex-wrap gap-2">
                {product.variants.map((v) => (
                  <button key={v.id} type="button" disabled={!v.in_stock} aria-pressed={v.id === variantId} onClick={() => { setVariantId(v.id); setPhoto(0); }}
                    className={cn("flex min-h-12 min-w-14 cursor-pointer flex-col items-center justify-center rounded-xl px-3 py-1 text-sm ring-1 transition disabled:cursor-not-allowed disabled:opacity-40",
                      v.id === variantId ? "bg-brand-500 text-white ring-brand-500" : "bg-white text-ink-800 ring-ink-200 hover:ring-brand-300")}>
                    <span className="font-bold">{v.label}</span>
                    {!v.in_stock ? <span className="text-[10px]">{t("loja.product.soldOut")}</span>
                      : v.id === product.suggested_variant_id && <span className={cn("text-[10px] font-semibold", v.id === variantId ? "text-white" : "text-emerald-600")}>{t("judo.size.suggested")}</span>}
                  </button>
                ))}
              </div>
            </div>
          )}
          {variant && !variant.in_stock && <p className="text-sm font-semibold text-rose-700">{t("loja.product.soldOutText")}</p>}
          {!wishMode && !product.lock && (
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-semibold text-ink-800">{t("loja.product.quantity")}</span>
              <Stepper value={quantity} onChange={setQuantity} />
            </div>
          )}
          {!wishMode && product.needs_name && !product.lock && (
            <Field label={t("loja.product.name")} hint={t("loja.product.nameHint")} htmlFor="loja-name">
              <Input id="loja-name" value={printName} maxLength={100} onChange={(e) => setName(e.target.value)} />
            </Field>
          )}
          {product.description && <p className="whitespace-pre-line text-sm leading-relaxed text-ink-600">{product.description}</p>}
          {product.club_kit && <Badge tone="brand">{t("loja.kit.badge")}</Badge>}
          {wishMode && <p className="rounded-2xl bg-accent-100 px-3 py-2 text-xs text-ink-800 ring-1 ring-accent-300">{t("judo.wish.peekHint")}</p>}
        </div>
      </div>
    </Modal>
  );
}

/** − 1 + : la quantità, con bottoni grandi per il pollice. */
export function Stepper({ value, onChange, disabled = false }: { value: number; onChange: (n: number) => void; disabled?: boolean }) {
  const { t } = useI18n();
  const btn = "flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl text-lg font-bold text-ink-800 ring-1 ring-ink-200 transition hover:ring-brand-300 disabled:cursor-not-allowed disabled:opacity-40";
  return (
    <div className="flex items-center gap-2">
      <button type="button" className={btn} disabled={disabled || value <= 1} onClick={() => onChange(value - 1)} aria-label={t("loja.qty.less")}>−</button>
      <span className="w-6 text-center font-bold text-ink-900" aria-live="polite">{value}</span>
      <button type="button" className={btn} disabled={disabled || value >= 20} onClick={() => onChange(value + 1)} aria-label={t("loja.qty.more")}>+</button>
    </div>
  );
}
