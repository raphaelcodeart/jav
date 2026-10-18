"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { LockBadge, LojaPhoto, useLojaRefresh, useLojaShop } from "@/components/club/loja-common";
import { clubGet, clubSend } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import { COLOR_SWATCH, type JudogiAthlete, type JudogiColor, type JudogiQuote, type KimonoType } from "@/lib/judogi";
import type { CheckoutResult, JudogiLineWrite, LojaCatalogType, LojaJudogi, TradeInWrite } from "@/lib/loja";

// Il judogi passo a passo (docs/club-portal.md, "La Loja del club"), pensato
// per un genitore dal telefono: per chi, tipo, colore e modello, nome da
// ricamare, judogi usato da restituire, riepilogo. Il listino, i lucchetti
// (FIJ solo per l'alta competizione, il rosa solo per le ragazze) e ogni
// importo li dà il server: il totale che corre in basso è POST /judogi/quote.
// Alla fine, come un prodotto: nel carrello o «Comprar já»; il minorenne
// (modo WISH) lo mette nella lista dei desideri.

const STEPS = ["athlete", "type", "model", "name", "trade", "summary"] as const;
type Step = (typeof STEPS)[number];

/** Il judogi usato: nessuno, uno dell'armadio, o descritto a mano. */
type Trade =
  | { mode: "NONE" }
  | { mode: "OWNED"; id: string }
  | { mode: "MANUAL"; kimono_type: KimonoType | null; color: JudogiColor | null; brand: string; size_cm: number | null };

export interface WizardStart { kimono_type: KimonoType; color: JudogiColor; brand: string }

export function JudogiWizard({ athletes, initialAthleteId, initial, onClose, onOpenCart, onPay }: {
  /** Per chi si può scegliere: gli atleti BUY della famiglia, o l'atleta stesso. */
  athletes: JudogiAthlete[];
  initialAthleteId?: string | null;
  /** Aperto da un modello della vetrina: tipo, colore e marca già scelti. */
  initial?: WizardStart | null;
  onClose: () => void;
  onOpenCart?: () => void;
  /** «Comprar já e pagar»: apre il pagamento con le quote nuove. */
  onPay?: (feeIds: string[]) => void;
}) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const refresh = useLojaRefresh();
  const first = athletes.find((a) => a.id === initialAthleteId) ?? (athletes.length === 1 ? athletes[0] : undefined);
  const [athleteId, setAthleteId] = useState<string | null>(first?.id ?? null);
  const [heightEdit, setHeightEdit] = useState<string | null>(null);
  const [type, setType] = useState<KimonoType | null>(initial?.kimono_type ?? null);
  const [color, setColor] = useState<JudogiColor | null>(initial?.color ?? null);
  const [brand, setBrand] = useState<string | null>(initial?.brand ?? null);
  const [size, setSize] = useState<number | null>(null);
  const [showSizes, setShowSizes] = useState(false);
  const [name, setName] = useState<string | null>(null);
  const [trade, setTrade] = useState<Trade>({ mode: "NONE" });
  const [notes, setNotes] = useState("");
  const [step, setStep] = useState<Step>(initial && first ? "model" : "athlete");
  const [busy, setBusy] = useState<"CART" | "BUY" | "WISH" | null>(null);
  const [done, setDone] = useState<"CART" | "WISH" | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  // A ogni passo il fuoco va sulla domanda: chi usa il lettore di schermo
  // sente subito che cosa gli si chiede.
  useEffect(() => { heading.current?.focus(); }, [step]);

  const { data: shop, isLoading: shopLoading, error: shopError } = useLojaShop(athleteId);
  const athlete = shop?.athlete ?? athletes.find((a) => a.id === athleteId) ?? null;
  const wishMode = athlete?.mode === "WISH";
  const heightText = heightEdit ?? (athlete?.height_cm ? String(athlete.height_cm) : "");
  const heightCm = /^\d{2,3}$/.test(heightText) ? Number(heightText) : null;
  const heightChanged = heightCm != null && heightCm !== (athlete?.height_cm ?? null);
  // Un'altezza corretta qui: il listino con le taglie consigliate per quella.
  const { data: catalog } = useQuery({
    queryKey: ["club", "judogi", "catalog", heightCm ?? 0],
    queryFn: () => clubGet<{ customization_cents: number; trade_in_percent: number; types: LojaCatalogType[] }>(`/judogi/catalog?height_cm=${heightCm}`),
    enabled: heightChanged,
    placeholderData: keepPreviousData,
  });
  const types = (heightChanged ? catalog?.types : undefined) ?? shop?.judogi_types ?? [];
  const settings = shop?.settings ?? null;

  // I lucchetti vengono dal server, modello per modello: un tipo (o un
  // colore) è chiuso se lo sono tutti i suoi modelli.
  const judogis = shop?.judogis ?? [];
  const groupLock = (list: LojaJudogi[]) => (list.length > 0 && list.every((j) => j.lock) ? list[0]!.lock : null);
  const typeLock = (k: KimonoType) => groupLock(judogis.filter((j) => j.kimono_type === k));
  const colorLock = (k: KimonoType, c: JudogiColor) => groupLock(judogis.filter((j) => j.kimono_type === k && j.color === c));
  const modelLock = (k: KimonoType, c: JudogiColor, b: string) => judogis.find((j) => j.kimono_type === k && j.color === c && j.brand === b)?.lock ?? null;

  const typeRow = types.find((x) => x.code === type) ?? null;
  const colorCode = color ?? typeRow?.colors.find((c) => !colorLock(typeRow.code, c.code))?.code ?? null;
  const colorRow = typeRow?.colors.find((c) => c.code === colorCode) ?? null;
  const brandName = brand ?? (typeRow && colorRow ? colorRow.brands.find((b) => !modelLock(typeRow.code, colorRow.code, b.name))?.name : null) ?? null;
  const brandRow = colorRow?.brands.find((b) => b.name === brandName) ?? null;
  const chosenSize = size ?? brandRow?.suggested_size_cm ?? null;
  const pickedLock = type && colorCode && brandName ? modelLock(type, colorCode, brandName) : null;

  const tradeable = (shop?.wardrobe ?? []).filter((w) => w.status === "DELIVERED" && w.kimono_type && w.color && w.brand && w.size_cm);
  const owned = trade.mode === "OWNED" ? tradeable.find((w) => w.id === trade.id) ?? null : null;
  const manualReady = trade.mode === "MANUAL" && !!(trade.kimono_type && trade.color && trade.brand && trade.size_cm);
  const tradeOk = trade.mode === "NONE" || (trade.mode === "OWNED" && !!owned) || manualReady;
  let tradeWrite: TradeInWrite | null = null;
  if (trade.mode === "OWNED" && owned) {
    // La lista dei desideri calcola il conto senza l'atleta, e non sa leggere
    // l'armadio: lì il judogi usato si descrive (tipo, colore, marca, taglia).
    tradeWrite = wishMode
      ? { kimono_type: owned.kimono_type!, color: owned.color!, brand: owned.brand!, size_cm: owned.size_cm }
      : { owned_order_id: owned.id };
  } else if (trade.mode === "MANUAL" && manualReady) {
    tradeWrite = { kimono_type: trade.kimono_type!, color: trade.color!, brand: trade.brand, size_cm: trade.size_cm };
  }

  const index = STEPS.indexOf(step);
  const choice = athlete && type && colorCode && brandName && chosenSize
    ? { kimono_type: type, color: colorCode, brand: brandName, size_cm: chosenSize, height_cm: heightChanged ? heightCm : null, trade_in: tradeWrite }
    : null;
  const { data: quote, error: quoteError, isFetching: quoting } = useQuery({
    queryKey: ["club", "judogi", "quote", athleteId, choice],
    queryFn: () => clubSend<JudogiQuote>("/judogi/quote", "POST", { ...choice, athlete_id: athleteId }),
    enabled: !!choice && index >= 2 && !pickedLock,
    placeholderData: keepPreviousData,
    retry: false,
  });

  const kimonoName = name ?? athlete?.kimono_name ?? "";
  const nameWords = kimonoName.trim().split(/\s+/).filter(Boolean).length;
  const nameError = athlete?.single_name_only && nameWords > 1 ? t("judo.calc.nameSingle") : null;
  const nameOk = kimonoName.trim().length >= 2 && !nameError;

  function canLeave(s: Step): boolean {
    if (s === "athlete") return !!athlete && !!shop;
    if (s === "type") return !!type && !typeLock(type);
    if (s === "model") return !!(colorCode && brandName && chosenSize) && !pickedLock;
    if (s === "name") return nameOk;
    if (s === "trade") return tradeOk;
    return true;
  }

  function pickAthlete(a: JudogiAthlete) {
    setAthleteId(a.id);
    setHeightEdit(null);
    setSize(null);
    setName(null);
    setTrade({ mode: "NONE" });
  }

  function pickType(k: KimonoType) {
    setType(k);
    setColor(null);
    setBrand(null);
    setSize(null);
    setShowSizes(false);
  }

  function line(): JudogiLineWrite {
    return {
      kimono_type: choice!.kimono_type, color: choice!.color, brand: choice!.brand, size_cm: choice!.size_cm,
      height_cm: choice!.height_cm, kimono_name: kimonoName.trim(), notes: notes.trim() || null, trade_in: tradeWrite,
    };
  }

  async function submit(what: "CART" | "BUY" | "WISH") {
    if (!athlete || !choice) return;
    setBusy(what);
    try {
      if (what === "WISH") {
        // Le note del desiderio vanno nel desiderio, non nel judogi.
        await clubSend("/wishlist", "POST", { athlete_id: athlete.id, kind: "JUDOGI", judogi: { ...line(), notes: undefined }, note: notes.trim().slice(0, 300) || null });
        await refresh();
        setDone("WISH");
      } else if (what === "CART") {
        await clubSend("/loja/cart", "POST", { athlete_id: athlete.id, kind: "JUDOGI", judogi: line() });
        await refresh();
        setDone("CART");
      } else {
        const res = await clubSend<CheckoutResult>("/loja/buy-now", "POST", { athlete_id: athlete.id, kind: "JUDOGI", judogi: line() });
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

  const modelTitle = brandName ?? "";

  if (done) {
    return (
      <Modal open onClose={onClose} size="md"
        footer={done === "CART" ? (
          <div className="flex w-full flex-col gap-2 sm:flex-row">
            <Button variant="secondary" size="lg" className="flex-1" onClick={onClose}>{t("loja.wiz.keepShopping")}</Button>
            {onOpenCart && <Button size="lg" className="flex-1" onClick={() => { onClose(); onOpenCart(); }}>🛒 {t("loja.cart.open")}</Button>}
          </div>
        ) : <Button size="lg" className="w-full" onClick={onClose}>{t("common.close")}</Button>}>
        <div className="flex flex-col items-center gap-3 pt-6 text-center">
          <motion.span initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
            className={cn("flex h-20 w-20 items-center justify-center rounded-full text-4xl", done === "CART" ? "bg-emerald-50 text-emerald-600" : "bg-pink-50")} aria-hidden="true">
            {done === "CART" ? "✓" : "💝"}
          </motion.span>
          <h2 className="font-display text-2xl text-ink-900">{done === "CART" ? t("loja.wiz.inCart") : t("judo.done.wishTitle")}</h2>
          <p className="max-w-sm text-sm text-ink-600">
            {done === "CART"
              ? t("loja.wiz.inCartText", { model: modelTitle, name: athlete?.first_name ?? "", amount: fmt.euro(quote?.total_cents ?? 0) })
              : t("judo.done.wishText")}
          </p>
        </div>
      </Modal>
    );
  }

  const showTotal = index >= 2 && !!quote && !pickedLock;
  return (
    <MotionConfig reducedMotion="user">
      <Modal open onClose={onClose} size="lg"
        title={t(`loja.wiz.title.${step}` as "loja.wiz.title.athlete")}
        subtitle={t("loja.wiz.stepOf", { n: index + 1, total: STEPS.length })}
        footer={
          <div className="flex w-full flex-col gap-2">
            {showTotal && (
              <div className={cn("flex items-baseline justify-between transition-opacity", quoting && "opacity-60")} aria-live="polite">
                <span className="text-sm font-semibold text-ink-600">{step === "summary" ? t("loja.wiz.totalToPay") : t("loja.wiz.soFar")}</span>
                <span className="font-display text-2xl text-ink-900">{fmt.euro(quote.total_cents)}</span>
              </div>
            )}
            {step !== "summary" ? (
              <div className="flex gap-2">
                {index > 0 && <BackButton onClick={() => setStep(STEPS[index - 1]!)} />}
                <Button size="lg" className="flex-1" disabled={!canLeave(step)} onClick={() => setStep(STEPS[index + 1]!)}>{t("loja.wiz.next")}</Button>
              </div>
            ) : wishMode ? (
              <div className="flex gap-2">
                <BackButton onClick={() => setStep(STEPS[index - 1]!)} />
                <Button size="lg" variant="accent" className="flex-1" loading={busy === "WISH"} disabled={!quote || !!busy} onClick={() => void submit("WISH")}>
                  ♡ {t("loja.wish.addJudogi")}
                </Button>
              </div>
            ) : (
              <>
                <Button size="lg" className="w-full" loading={busy === "CART"} disabled={!quote || !!busy} onClick={() => void submit("CART")}>
                  🛒 {t("loja.addToCart")}
                </Button>
                <div className="flex gap-2">
                  <BackButton onClick={() => setStep(STEPS[index - 1]!)} />
                  <Button size="lg" variant="secondary" className="flex-1" loading={busy === "BUY"} disabled={!quote || !!busy} onClick={() => void submit("BUY")}>
                    {t("loja.buyNowPay")}
                  </Button>
                </div>
              </>
            )}
          </div>
        }>
        {/* --- La barra dei passi --- */}
        <div className="mb-5 grid grid-cols-6 gap-1.5" aria-hidden="true">
          {STEPS.map((s, i) => <span key={s} className={cn("h-1.5 rounded-full transition-colors", i <= index ? "bg-brand-500" : "bg-ink-100")} />)}
        </div>

        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={step} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.18 }} className="space-y-4">
            <h3 ref={heading} tabIndex={-1} className="text-base font-semibold text-ink-700 outline-none">
              {step === "model" && chosenSize
                ? t("loja.wiz.ask.modelSize", { cm: chosenSize })
                : step === "trade"
                  ? t("loja.wiz.ask.trade", { pct: settings?.trade_in_percent ?? 50 })
                  : t(`loja.wiz.ask.${step}` as "loja.wiz.ask.athlete")}
            </h3>

            {step !== "athlete" && (shopLoading || !shop) ? (
              shopError ? <ErrorBox text={(shopError as Error).message} /> : <Skeleton className="h-64" />
            ) : null}

            {/* --- 1. Per chi --- */}
            {step === "athlete" && (
              <div className="space-y-3">
                <ul className="space-y-2">
                  {athletes.map((a) => (
                    <li key={a.id}>
                      <OptionButton active={a.id === athleteId} onClick={() => pickAthlete(a)}>
                        <Avatar athlete={a} active={a.id === athleteId} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-bold text-ink-900">{a.name}</span>
                          <span className="block text-xs text-ink-500">
                            {t("judo.athlete.age", { n: a.age })}{a.height_cm ? ` · ${a.height_cm} cm` : ""}
                          </span>
                        </span>
                        {a.mode === "WISH" && <Badge tone="accent">{t("judo.athlete.wish")}</Badge>}
                      </OptionButton>
                    </li>
                  ))}
                </ul>
                {athlete && (
                  <div className="rounded-2xl bg-ink-50 p-4">
                    <Field label={t("loja.wiz.heightLabel")} htmlFor="wiz-height"
                      hint={athlete.height_cm ? t("loja.wiz.heightHint") : t("loja.wiz.heightMissing")}>
                      <div className="flex items-center gap-2">
                        <Input id="wiz-height" inputMode="numeric" maxLength={3} value={heightText} className="w-28 bg-white text-center text-lg font-bold"
                          onChange={(e) => { setHeightEdit(e.target.value.replace(/\D/g, "")); setSize(null); }} />
                        <span className="text-sm text-ink-600">cm</span>
                      </div>
                    </Field>
                  </div>
                )}
                {shopError && <ErrorBox text={(shopError as Error).message} />}
              </div>
            )}

            {/* --- 2. Tipo --- */}
            {step === "type" && shop && (
              types.length === 0 ? <p className="rounded-2xl bg-ink-50 p-6 text-center text-sm text-ink-600">{t("judo.calc.noCatalog")}</p> : (
                <ul className="space-y-2">
                  {types.map((x) => {
                    const lock = typeLock(x.code);
                    const fij = x.code === "FIJ_APPROVED";
                    return (
                      <li key={x.code}>
                        <OptionButton active={type === x.code} disabled={!!lock} onClick={() => pickType(x.code)}>
                          <span className="min-w-0 flex-1">
                            <span className="block font-bold text-ink-900">{t(`judo.type.${x.code}` as "judo.type.TRAINING")}</span>
                            <span className="block text-xs leading-snug text-ink-500">{t(`judo.typeText.${x.code}` as "judo.typeText.TRAINING")}</span>
                            {fij && <span className="mt-1 block text-xs font-medium text-accent-800">{t("loja.wiz.fijNote")}</span>}
                          </span>
                          <span className="flex shrink-0 flex-col items-end gap-1">
                            <span className="text-sm font-bold text-brand-700">{t("judo.from", { amount: fmt.euro(x.min_price_cents) })}</span>
                            {fij && <Badge tone="accent">{t("loja.highCompetition")}</Badge>}
                          </span>
                        </OptionButton>
                        {lock && <p className="mt-1 px-2 text-xs text-ink-500">🔒 {t(`loja.lockText.${lock}` as "loja.lockText.HIGH_COMPETITION")}</p>}
                      </li>
                    );
                  })}
                </ul>
              )
            )}

            {/* --- 3. Colore e modello --- */}
            {step === "model" && shop && typeRow && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="group" aria-label={t("judo.color.title")}>
                  {typeRow.colors.map((c) => {
                    const lock = colorLock(typeRow.code, c.code);
                    return (
                      <button key={c.code} type="button" disabled={!!lock} aria-pressed={colorCode === c.code}
                        onClick={() => { setColor(c.code); setBrand(null); setSize(null); setShowSizes(false); }}
                        className={cn("flex min-h-12 cursor-pointer items-center justify-center gap-2 rounded-2xl border-2 bg-white px-3 text-sm font-bold text-ink-900 transition disabled:cursor-not-allowed disabled:opacity-50",
                          colorCode === c.code ? "border-brand-500" : "border-ink-100 hover:border-brand-200")}>
                        <span className={cn("h-4 w-4 shrink-0 rounded-full ring-1", COLOR_SWATCH[c.code])} aria-hidden="true" />
                        <span className="text-left leading-tight">
                          {t(`judo.color.${c.code}` as "judo.color.WHITE")}
                          {lock && <span className="block text-[11px] font-medium text-ink-500">{t(`loja.lock.${lock}` as "loja.lock.GIRLS_ONLY")}</span>}
                        </span>
                      </button>
                    );
                  })}
                </div>
                {colorRow && (
                  <ul className="space-y-2">
                    {colorRow.brands.map((b) => {
                      const lock = modelLock(typeRow.code, colorRow.code, b.name);
                      const active = brandName === b.name;
                      return (
                        <li key={b.name}>
                          <OptionButton active={active} disabled={!!lock} onClick={() => { setBrand(b.name); setSize(null); setShowSizes(false); }}>
                            <LojaPhoto src={b.image_url} judogi color={colorRow.code} className="h-[72px] w-[72px] shrink-0 overflow-hidden rounded-2xl" size={48} />
                            <span className="min-w-0 flex-1">
                              <span className="block font-bold text-ink-900">{b.name}</span>
                              <span className="line-clamp-2 block text-xs text-ink-500">
                                {b.description || (b.suggested_size_cm ? t("judo.brand.suggested", { cm: b.suggested_size_cm }) : t("judo.brand.sizes", { n: b.sizes.length }))}
                              </span>
                              {lock && <LockBadge lock={lock} className="mt-1" />}
                            </span>
                            <span className="shrink-0 text-base font-extrabold text-brand-700">{fmt.euro(b.suggested_price_cents ?? b.min_price_cents)}</span>
                          </OptionButton>
                        </li>
                      );
                    })}
                  </ul>
                )}
                {brandRow && !pickedLock && (brandRow.sizes.length > 1 || !chosenSize) && (
                  <div className="rounded-2xl bg-ink-50 p-4">
                    <button type="button" onClick={() => setShowSizes((v) => !v)} aria-expanded={showSizes}
                      className="flex w-full cursor-pointer items-center justify-between text-left text-sm font-semibold text-ink-800">
                      <span>{t("loja.wiz.sizeLine", { cm: chosenSize ?? "—" })}</span>
                      <span className="text-brand-700">{showSizes ? t("loja.wiz.sizeClose") : t("loja.wiz.sizeChange")}</span>
                    </button>
                    {/* Senza altezza non c'è una taglia consigliata: le taglie si vedono subito. */}
                    {(showSizes || !chosenSize) && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {brandRow.sizes.map((s) => (
                          <button key={s.size_cm} type="button" aria-pressed={chosenSize === s.size_cm} onClick={() => setSize(s.size_cm)}
                            className={cn("flex min-h-12 cursor-pointer flex-col items-center justify-center rounded-xl px-3 py-1 text-sm ring-1 transition",
                              chosenSize === s.size_cm ? "bg-brand-500 text-white ring-brand-500" : "bg-white text-ink-800 ring-ink-200 hover:ring-brand-300")}>
                            <span className="font-bold">{s.size_cm}</span>
                            <span className={cn("text-[11px]", chosenSize === s.size_cm ? "text-white/85" : "text-ink-500")}>{fmt.euro(s.price_cents)}</span>
                            {brandRow.suggested_size_cm === s.size_cm && <span className={cn("text-[10px] font-semibold", chosenSize === s.size_cm ? "text-white" : "text-emerald-600")}>{t("judo.size.suggested")}</span>}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                {quoteError && !pickedLock && <ErrorBox text={(quoteError as Error).message} />}
              </div>
            )}

            {/* --- 4. Il nome da ricamare --- */}
            {step === "name" && shop && (
              <div className="space-y-4">
                <Field label={t("judo.summary.name")} htmlFor="wiz-name" error={nameError}
                  hint={athlete?.single_name_only ? t("judo.calc.nameSingle") : t("judo.summary.nameHint")}>
                  <Input id="wiz-name" value={kimonoName} maxLength={100} onChange={(e) => setName(e.target.value)} className="text-lg font-semibold" />
                </Field>
                {/* L'anteprima del ricamo: il nome come comparirà sul judogi. */}
                <div className="flex min-h-24 items-center justify-center rounded-2xl bg-ink-900 p-4" aria-hidden="true">
                  <span className="rounded-lg border-2 border-dashed border-accent-300/70 px-4 py-2 font-display text-xl uppercase tracking-[0.18em] text-accent-200">
                    {kimonoName.trim() || "—"}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-2xl bg-ink-50 px-4 py-3 text-sm">
                  <span className="text-ink-700">{t("judo.receipt.custom")}</span>
                  <b className="text-ink-900">+ {fmt.euro(quote?.customization_cents ?? settings?.customization_cents ?? 0)}</b>
                </div>
              </div>
            )}

            {/* --- 5. Il judogi usato --- */}
            {step === "trade" && shop && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2">
                  <PillButton active={trade.mode !== "NONE"} onClick={() => trade.mode === "NONE" && setTrade(tradeable[0] ? { mode: "OWNED", id: tradeable[0].id } : { mode: "MANUAL", kimono_type: null, color: null, brand: "", size_cm: null })}>
                    {t("loja.wiz.tradeYes")}
                  </PillButton>
                  <PillButton active={trade.mode === "NONE"} onClick={() => setTrade({ mode: "NONE" })}>{t("judo.trade.no")}</PillButton>
                </div>
                {trade.mode !== "NONE" && (
                  <div className="space-y-3">
                    {tradeable.length > 0 && (
                      <fieldset className="space-y-2">
                        <legend className="mb-2 text-sm font-semibold text-ink-800">{t("loja.wiz.tradeWardrobe")}</legend>
                        {tradeable.map((w) => (
                          <OptionButton key={w.id} active={trade.mode === "OWNED" && trade.id === w.id} onClick={() => setTrade({ mode: "OWNED", id: w.id })}>
                            <span className={cn("h-5 w-5 shrink-0 rounded-full ring-1", COLOR_SWATCH[w.color!])} aria-hidden="true" />
                            <span className="min-w-0 flex-1">
                              <span className="block font-bold text-ink-900">{t(`judo.type.${w.kimono_type}` as "judo.type.TRAINING")} · {w.brand}</span>
                              <span className="block text-xs text-ink-500">
                                {t(`judo.color.${w.color}` as "judo.color.WHITE")} · {w.size_cm} cm{w.delivered_on ? ` · ${t("loja.wiz.deliveredOn", { date: fmt.shortDate(w.delivered_on) })}` : ""}
                              </span>
                            </span>
                          </OptionButton>
                        ))}
                        <OptionButton active={trade.mode === "MANUAL"} onClick={() => trade.mode !== "MANUAL" && setTrade({ mode: "MANUAL", kimono_type: null, color: null, brand: "", size_cm: null })}>
                          <span className="text-xl" aria-hidden="true">✍️</span>
                          <span className="flex-1 font-bold text-ink-900">{t("loja.wiz.tradeOther")}</span>
                        </OptionButton>
                      </fieldset>
                    )}
                    {trade.mode === "MANUAL" && <ManualTrade types={shop.judogi_types} trade={trade} onChange={setTrade} />}
                    {quote?.trade_in && tradeWrite && (
                      <div className="flex items-center justify-between rounded-2xl bg-emerald-50 px-4 py-3 ring-1 ring-emerald-200">
                        <span className="text-sm font-semibold text-emerald-800">{t("loja.wiz.tradeWorth")}</span>
                        <span className="font-display text-xl text-emerald-700">− {fmt.euro(quote.trade_in_discount_cents)}</span>
                      </div>
                    )}
                    {quoteError && <ErrorBox text={(quoteError as Error).message} />}
                    <p className="text-xs leading-relaxed text-ink-500">{t("loja.wiz.tradeBring")}</p>
                  </div>
                )}
              </div>
            )}

            {/* --- 6. Il riepilogo --- */}
            {step === "summary" && shop && (
              <div className="space-y-4">
                <div className="flex items-center gap-4 rounded-3xl bg-white p-3 ring-1 ring-ink-100">
                  <LojaPhoto src={brandRow?.image_url} judogi color={colorCode} className="h-24 w-24 shrink-0 overflow-hidden rounded-2xl" size={56} />
                  <div className="min-w-0">
                    <p className="font-display text-lg leading-tight text-ink-900">{brandName}</p>
                    <p className="text-sm text-ink-600">
                      {type && t(`judo.type.${type}` as "judo.type.TRAINING")} · {colorCode && t(`judo.color.${colorCode}` as "judo.color.WHITE")} · {quote?.size_cm ?? chosenSize} cm
                    </p>
                    <p className="mt-1 text-sm text-ink-500">{t("loja.wiz.forWhom", { name: athlete?.first_name ?? "", kimono: kimonoName.trim() })}</p>
                  </div>
                </div>
                {quoteError ? <ErrorBox text={(quoteError as Error).message} /> : !quote ? <Skeleton className="h-36" /> : (
                  <dl className={cn("space-y-2 rounded-3xl bg-ink-50 p-4 text-sm transition-opacity", quoting && "opacity-60")}>
                    <SumRow label={t("judo.receipt.base")} value={fmt.euro(quote.base_price_cents)} />
                    <SumRow label={t("judo.receipt.custom")} value={fmt.euro(quote.customization_cents)} />
                    {quote.trade_in && <SumRow label={t("loja.wiz.tradeLine")} value={`− ${fmt.euro(quote.trade_in_discount_cents)}`} accent />}
                    <div className="border-t border-ink-200 pt-2">
                      <SumRow label={t("judo.receipt.total")} value={fmt.euro(quote.total_cents)} strong />
                    </div>
                  </dl>
                )}
                <Field label={t("judo.summary.notes")} htmlFor="wiz-notes">
                  <Textarea id="wiz-notes" value={notes} rows={2} maxLength={wishMode ? 300 : 2000} placeholder={t("judo.summary.notesPh")} onChange={(e) => setNotes(e.target.value)} />
                </Field>
                <p className="text-xs leading-relaxed text-ink-500">{wishMode ? t("judo.summary.wishText") : t("loja.wiz.summaryText")}</p>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </Modal>
    </MotionConfig>
  );
}

function ManualTrade({ types, trade, onChange }: {
  types: LojaCatalogType[];
  trade: Extract<Trade, { mode: "MANUAL" }>;
  onChange: (t: Trade) => void;
}) {
  const { t } = useI18n();
  const typeRow = types.find((x) => x.code === trade.kimono_type);
  const colorRow = typeRow?.colors.find((c) => c.code === trade.color);
  const brandRow = colorRow?.brands.find((b) => b.name === trade.brand);
  return (
    <div className="grid gap-3 rounded-2xl bg-ink-50 p-4 sm:grid-cols-2">
      <Field label={t("judo.trade.type")} htmlFor="wiz-tt">
        <Select id="wiz-tt" value={trade.kimono_type ?? ""} className="bg-white"
          onChange={(e) => onChange({ mode: "MANUAL", kimono_type: (e.target.value || null) as KimonoType | null, color: null, brand: "", size_cm: null })}>
          <option value="">{t("judo.trade.pick")}</option>
          {types.map((x) => <option key={x.code} value={x.code}>{t(`judo.type.${x.code}` as "judo.type.TRAINING")}</option>)}
        </Select>
      </Field>
      <Field label={t("judo.trade.color")} htmlFor="wiz-tc">
        <Select id="wiz-tc" value={trade.color ?? ""} disabled={!typeRow} className="bg-white"
          onChange={(e) => onChange({ ...trade, color: (e.target.value || null) as JudogiColor | null, brand: "", size_cm: null })}>
          <option value="">{t("judo.trade.pick")}</option>
          {(typeRow?.colors ?? []).map((c) => <option key={c.code} value={c.code}>{t(`judo.color.${c.code}` as "judo.color.WHITE")}</option>)}
        </Select>
      </Field>
      <Field label={t("judo.trade.brand")} htmlFor="wiz-tb">
        <Select id="wiz-tb" value={trade.brand} disabled={!colorRow} className="bg-white"
          onChange={(e) => onChange({ ...trade, brand: e.target.value, size_cm: null })}>
          <option value="">{t("judo.trade.pick")}</option>
          {(colorRow?.brands ?? []).map((b) => <option key={b.name} value={b.name}>{b.name}</option>)}
        </Select>
      </Field>
      <Field label={t("judo.trade.size")} htmlFor="wiz-ts">
        <Select id="wiz-ts" value={trade.size_cm ?? ""} disabled={!brandRow} className="bg-white"
          onChange={(e) => onChange({ ...trade, size_cm: Number(e.target.value) || null })}>
          <option value="">{t("judo.trade.pick")}</option>
          {(brandRow?.sizes ?? []).map((s) => <option key={s.size_cm} value={s.size_cm}>{s.size_cm} cm</option>)}
        </Select>
      </Field>
    </div>
  );
}

/** Una scelta grande, da pollice: bordo rosso quando è quella presa. */
function OptionButton({ active, disabled = false, onClick, children }: { active: boolean; disabled?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-pressed={active}
      className={cn("flex min-h-16 w-full cursor-pointer items-center gap-3 rounded-2xl border-2 bg-white p-3 text-left transition",
        "disabled:cursor-not-allowed disabled:opacity-55",
        active ? "border-brand-500 shadow-soft" : "border-ink-100 hover:border-brand-200")}>
      {children}
    </button>
  );
}

function PillButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={active}
      className={cn("min-h-12 cursor-pointer rounded-2xl border-2 px-3 text-[15px] font-bold transition",
        active ? "border-brand-500 bg-brand-500 text-white" : "border-ink-100 bg-white text-ink-900 hover:border-brand-200")}>
      {children}
    </button>
  );
}

function BackButton({ onClick }: { onClick: () => void }) {
  const { t } = useI18n();
  return (
    <Button size="lg" variant="secondary" onClick={onClick} aria-label={t("judo.calc.back")} className="px-4">
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>
    </Button>
  );
}

function Avatar({ athlete, active }: { athlete: JudogiAthlete; active: boolean }) {
  return (
    <span className={cn("flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full text-base font-extrabold",
      active ? "bg-brand-500 text-white" : "bg-ink-100 text-ink-700")}>
      {/* eslint-disable-next-line @next/next/no-img-element -- foto profilo nel bucket pubblico */}
      {athlete.photo_url ? <img src={athlete.photo_url} alt="" className="h-full w-full object-cover" /> : athlete.first_name.slice(0, 1).toUpperCase()}
    </span>
  );
}

function SumRow({ label, value, accent = false, strong = false }: { label: string; value: string; accent?: boolean; strong?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className={cn(strong ? "font-bold text-ink-900" : "text-ink-600")}>{label}</dt>
      <dd className={cn("font-semibold", accent && "text-emerald-700", strong && "font-display text-xl text-ink-900")}>{value}</dd>
    </div>
  );
}

function ErrorBox({ text }: { text: string }) {
  return <p className="rounded-2xl bg-rose-50 p-4 text-sm text-rose-700 ring-1 ring-rose-200" role="alert">{text}</p>;
}
