"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import {
  COLOR_SWATCH, JUDOGI_KEYS, TYPE_ICON,
  type CatalogBrand, type JudogiAthlete, type JudogiCatalog, type JudogiChoice, type JudogiColor, type JudogiQuote,
  type KimonoType, type TradeInChoice,
} from "@/lib/judogi";

// Il calcolatore dei judogi (apps/api/app/domains/club/judogi.py), sei passi
// come quello del sito vecchio: atleta, tipo, colore, marca e taglia,
// judogi restituito, riepilogo. I prezzi li dà il server (listino e conto);
// alla fine il titolare (o l'atleta maggiorenne) ordina, il minorenne mette
// il judogi nella lista dei desideri e lo vede il titolare.

const STEPS = ["athlete", "type", "color", "brand", "trade", "summary"] as const;
type Step = (typeof STEPS)[number];

export function useJudogiAthletes(enabled = true) {
  return useQuery({ queryKey: JUDOGI_KEYS.athletes, queryFn: () => clubGet<JudogiAthlete[]>("/judogi/athletes"), enabled, retry: false });
}

export function JudogiCalculator({ athletes, initialAthleteId, initialChoice, initialName, wishId, onClose }: {
  athletes: JudogiAthlete[];
  initialAthleteId?: string | null;
  initialChoice?: JudogiChoice | null;
  initialName?: string | null;
  /** Il desiderio da cui nasce l'ordine (il titolare che lo esaudisce). */
  wishId?: string | null;
  onClose: () => void;
}) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const first = athletes.find((a) => a.id === initialAthleteId) ?? (athletes.length === 1 ? athletes[0] : undefined);
  const [athleteId, setAthleteId] = useState<string | null>(first?.id ?? null);
  const [height, setHeight] = useState<string>(first?.height_cm ? String(first.height_cm) : "");
  const [type, setType] = useState<KimonoType | null>(initialChoice?.kimono_type ?? null);
  const [color, setColor] = useState<JudogiColor | null>(initialChoice?.color ?? null);
  const [brand, setBrand] = useState<string | null>(initialChoice?.brand ?? null);
  const [size, setSize] = useState<number | null>(initialChoice?.size_cm ?? null);
  const [trade, setTrade] = useState<TradeInChoice | null>(initialChoice?.trade_in ?? null);
  const [name, setName] = useState(initialName ?? first?.kimono_name ?? "");
  const [notes, setNotes] = useState("");
  const [step, setStep] = useState<Step>(initialChoice ? "summary" : first ? "type" : "athlete");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<"ORDER" | "WISH" | null>(null);

  const athlete = athletes.find((a) => a.id === athleteId) ?? null;
  const heightCm = /^\d{2,3}$/.test(height) ? Number(height) : null;
  const { data: catalog, isLoading } = useQuery({
    queryKey: JUDOGI_KEYS.catalog(heightCm),
    queryFn: () => clubGet<JudogiCatalog>(`/judogi/catalog${heightCm ? `?height_cm=${heightCm}` : ""}`),
    placeholderData: keepPreviousData,
  });
  const typeRow = catalog?.types.find((x) => x.code === type) ?? null;
  const colorRow = typeRow?.colors.find((c) => c.code === color) ?? null;
  const brandRow = colorRow?.brands.find((b) => b.name === brand) ?? null;
  const chosenSize = size ?? brandRow?.suggested_size_cm ?? null;
  const ready = !!(athlete && type && color && brand && chosenSize);
  const choice: JudogiChoice | null = ready ? { kimono_type: type!, color: color!, brand: brand!, size_cm: chosenSize, trade_in: trade } : null;
  const tradeOk = !trade || !!(trade.brand && trade.size_cm);

  const { data: quote, error: quoteError, isFetching: quoting } = useQuery({
    queryKey: ["club", "judogi", "quote", choice],
    queryFn: () => clubSend<JudogiQuote>("/judogi/quote", "POST", { ...choice, athlete_id: athleteId }),
    enabled: !!choice && tradeOk && (step === "summary" || step === "trade"),
    retry: false,
  });

  const wishMode = athlete?.mode === "WISH";
  const index = STEPS.indexOf(step);
  const canGo = (s: Step) => {
    const i = STEPS.indexOf(s);
    if (i <= 0) return true;
    if (!athlete) return false;
    if (i >= 2 && !type) return false;
    if (i >= 3 && !color) return false;
    if (i >= 4 && !(brand && chosenSize)) return false;
    if (i >= 5 && !tradeOk) return false;
    return true;
  };

  function pickAthlete(a: JudogiAthlete) {
    setAthleteId(a.id);
    setHeight(a.height_cm ? String(a.height_cm) : "");
    setName(a.kimono_name);
    setSize(null);
    setStep("type");
  }

  async function submit() {
    if (!athlete || !choice) return;
    setBusy(true);
    try {
      if (wishMode) {
        await clubSend("/wishlist", "POST", { athlete_id: athlete.id, kind: "JUDOGI", judogi: { ...choice, kimono_name: name.trim() || null }, note: notes.trim() || null });
        await queryClient.invalidateQueries({ queryKey: JUDOGI_KEYS.wishes });
        setDone("WISH");
      } else {
        await clubSend("/judogi/orders", "POST", { ...choice, athlete_id: athlete.id, kimono_name: name.trim(), notes: notes.trim() || null, wish_id: wishId ?? null });
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: JUDOGI_KEYS.orders }),
          queryClient.invalidateQueries({ queryKey: JUDOGI_KEYS.wishes }),
          queryClient.invalidateQueries({ queryKey: ["club"] }),
        ]);
        setDone("ORDER");
      }
    } catch (e) {
      toast({ tone: "error", title: t("judo.calc.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const nameWords = name.trim().split(/\s+/).filter(Boolean).length;
  const nameError = athlete?.single_name_only && nameWords > 1 ? t("judo.calc.nameSingle") : null;

  if (done) {
    return (
      <Modal open onClose={onClose} size="md" title={done === "WISH" ? t("judo.done.wishTitle") : t("judo.done.orderTitle")}
        footer={<Button onClick={onClose}>{t("common.close")}</Button>}>
        <div className="space-y-3 text-center">
          <motion.div initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="text-6xl" aria-hidden="true">{done === "WISH" ? "💝" : "🥋"}</motion.div>
          <p className="text-sm text-ink-600">{done === "WISH" ? t("judo.done.wishText") : t("judo.done.orderText", { amount: fmt.euro(quote?.total_cents ?? 0) })}</p>
        </div>
      </Modal>
    );
  }

  return (
    <MotionConfig reducedMotion="user">
      <Modal open onClose={onClose} size="xl" title={wishId ? t("judo.calc.titleWish") : t("judo.calc.title")} subtitle={t("judo.calc.subtitle")}
        footer={<>
          {index > 0 && <Button variant="ghost" className="mr-auto" onClick={() => setStep(STEPS[index - 1]!)}>← {t("judo.calc.back")}</Button>}
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          {step !== "summary" ? (
            <Button disabled={!canGo(STEPS[index + 1]!)} onClick={() => setStep(STEPS[index + 1]!)}>{t("judo.calc.next")} →</Button>
          ) : (
            <Button loading={busy} disabled={!quote || !!nameError || (!wishMode && name.trim().length < 2)} onClick={submit}>
              {wishMode ? `💝 ${t("judo.calc.addWish")}` : `🥋 ${t("judo.calc.order")}`}
            </Button>
          )}
        </>}>
        {/* --- I passi --- */}
        <ol className="-mx-1 mb-5 flex gap-1 overflow-x-auto pb-1">
          {STEPS.map((s, i) => (
            <li key={s} className="shrink-0">
              <button type="button" disabled={!canGo(s)} onClick={() => setStep(s)}
                className={cn("flex h-9 cursor-pointer items-center gap-2 rounded-full px-3 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-40",
                  s === step ? "bg-ink-900 text-white" : i < index ? "bg-brand-50 text-brand-700 ring-1 ring-brand-200" : "bg-ink-50 text-ink-600")}>
                <span className={cn("flex h-5 w-5 items-center justify-center rounded-full text-[11px]", s === step ? "bg-white/20" : "bg-white")}>{i < index ? "✓" : i + 1}</span>
                {t(`judo.step.${s}` as "judo.step.athlete")}
              </button>
            </li>
          ))}
        </ol>

        {isLoading || !catalog ? <Skeleton className="h-64" /> : catalog.types.length === 0 ? (
          <p className="rounded-2xl bg-ink-50 p-6 text-center text-sm text-ink-600">{t("judo.calc.noCatalog")}</p>
        ) : (
          <AnimatePresence mode="wait">
            <motion.div key={step} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} transition={{ duration: 0.18 }}>
              {step === "athlete" && (
                <div className="space-y-4">
                  <StepTitle title={t("judo.athlete.title")} text={t("judo.athlete.text")} />
                  <ul className="grid gap-2 sm:grid-cols-2">
                    {athletes.map((a) => (
                      <li key={a.id}>
                        <button type="button" onClick={() => pickAthlete(a)}
                          className={cn("flex w-full cursor-pointer items-center gap-3 rounded-2xl bg-white p-3 text-left ring-1 transition hover:ring-brand-300",
                            a.id === athleteId ? "ring-2 ring-brand-500" : "ring-ink-100")}>
                          <span className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full bg-ink-100 text-lg">
                            {/* eslint-disable-next-line @next/next/no-img-element -- foto profilo nel bucket pubblico */}
                            {a.photo_url ? <img src={a.photo_url} alt="" className="h-full w-full object-cover" /> : "🥋"}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate font-semibold text-ink-900">{a.name}</span>
                            <span className="block text-xs text-ink-500">{t("judo.athlete.age", { n: a.age })}{a.height_cm ? ` · ${a.height_cm} cm` : ""}</span>
                          </span>
                          <Badge tone={a.mode === "BUY" ? "success" : "accent"}>{a.mode === "BUY" ? t("judo.athlete.buy") : t("judo.athlete.wish")}</Badge>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {step === "type" && (
                <div className="space-y-4">
                  <StepTitle title={t("judo.type.title")} text={t("judo.type.text", { fee: fmt.euro(catalog.customization_cents) })} />
                  <HeightField value={height} onChange={(v) => { setHeight(v); setSize(null); }} />
                  <ul className="grid gap-3 sm:grid-cols-2">
                    {catalog.types.map((x) => (
                      <li key={x.code}>
                        <OptionCard active={type === x.code} onClick={() => { setType(x.code); setColor(null); setBrand(null); setSize(null); setStep("color"); }}
                          icon={TYPE_ICON[x.code]} title={t(`judo.type.${x.code}` as "judo.type.TRAINING")}
                          text={t(`judo.typeText.${x.code}` as "judo.typeText.TRAINING")}
                          aside={t("judo.from", { amount: fmt.euro(x.min_price_cents) })} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {step === "color" && typeRow && (
                <div className="space-y-4">
                  <StepTitle title={t("judo.color.title")} text={t("judo.color.text")} />
                  <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {typeRow.colors.map((c) => (
                      <li key={c.code}>
                        <button type="button" onClick={() => { setColor(c.code); setBrand(null); setSize(null); setStep("brand"); }}
                          className={cn("flex w-full cursor-pointer flex-col items-center gap-2 rounded-2xl bg-white p-4 ring-1 transition hover:-translate-y-0.5 hover:ring-brand-300",
                            color === c.code ? "ring-2 ring-brand-500" : "ring-ink-100")}>
                          <span className={cn("h-12 w-12 rounded-full ring-2", COLOR_SWATCH[c.code])} aria-hidden="true" />
                          <span className="text-sm font-semibold text-ink-900">{t(`judo.color.${c.code}` as "judo.color.WHITE")}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {step === "brand" && colorRow && (
                <div className="space-y-4">
                  <StepTitle title={t("judo.brand.title")} text={heightCm ? t("judo.brand.textHeight", { cm: heightCm }) : t("judo.brand.text")} />
                  <HeightField value={height} onChange={(v) => { setHeight(v); setSize(null); }} />
                  <ul className="grid gap-3 sm:grid-cols-2">
                    {colorRow.brands.map((b) => (
                      <li key={b.name}>
                        <OptionCard active={brand === b.name} onClick={() => { setBrand(b.name); setSize(null); }}
                          icon="🏷️" title={b.name}
                          text={b.suggested_size_cm ? t("judo.brand.suggested", { cm: b.suggested_size_cm }) : t("judo.brand.sizes", { n: b.sizes.length })}
                          aside={fmt.euro(b.suggested_price_cents ?? b.min_price_cents)} />
                      </li>
                    ))}
                  </ul>
                  {brandRow && <SizePicker brand={brandRow} value={chosenSize} onChange={setSize} />}
                </div>
              )}

              {step === "trade" && (
                <TradeStep catalog={catalog} trade={trade} onChange={setTrade} quote={quote ?? null} />
              )}

              {step === "summary" && (
                <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
                  <div className="space-y-4">
                    <StepTitle title={t("judo.summary.title")} text={wishMode ? t("judo.summary.wishText") : t("judo.summary.orderText")} />
                    <Field label={t("judo.summary.name")} hint={athlete?.single_name_only ? t("judo.calc.nameSingle") : t("judo.summary.nameHint")} error={nameError} htmlFor="jg-name">
                      <Input id="jg-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
                    </Field>
                    <Field label={t("judo.summary.notes")} htmlFor="jg-notes">
                      <Textarea id="jg-notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} maxLength={wishMode ? 300 : 2000} placeholder={t("judo.summary.notesPh")} />
                    </Field>
                  </div>
                  <Receipt quote={quote ?? null} loading={quoting} error={quoteError ? (quoteError as Error).message : null} athleteName={athlete?.name ?? ""} />
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        )}
      </Modal>
    </MotionConfig>
  );
}

function StepTitle({ title, text }: { title: string; text?: string }) {
  return (
    <div>
      <h3 className="font-display text-xl text-ink-900">{title}</h3>
      {text && <p className="text-sm text-ink-500">{text}</p>}
    </div>
  );
}

function HeightField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useI18n();
  return (
    <label className="flex w-fit items-center gap-2 rounded-2xl bg-ink-50 px-3 py-2 text-sm text-ink-700">
      📏 {t("judo.height")}
      <Input inputMode="numeric" value={value} maxLength={3} onChange={(e) => onChange(e.target.value.replace(/\D/g, ""))} className="h-9 w-20 bg-white text-center" aria-label={t("judo.height")} />
      cm
    </label>
  );
}

function OptionCard({ active, onClick, icon, title, text, aside }: { active: boolean; onClick: () => void; icon: string; title: string; text?: string; aside?: string }) {
  return (
    <button type="button" onClick={onClick}
      className={cn("flex h-full w-full cursor-pointer items-center gap-3 rounded-2xl bg-white p-4 text-left ring-1 transition hover:-translate-y-0.5 hover:ring-brand-300",
        active ? "ring-2 ring-brand-500 shadow-soft" : "ring-ink-100")}>
      <span className="text-2xl" aria-hidden="true">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold text-ink-900">{title}</span>
        {text && <span className="block text-xs text-ink-500">{text}</span>}
      </span>
      {aside && <span className="shrink-0 text-sm font-bold text-brand-700">{aside}</span>}
    </button>
  );
}

function SizePicker({ brand, value, onChange }: { brand: CatalogBrand; value: number | null; onChange: (s: number) => void }) {
  const { t, fmt } = useI18n();
  return (
    <div className="rounded-2xl bg-ink-50 p-4">
      <p className="mb-2 text-sm font-semibold text-ink-800">{t("judo.size.title", { brand: brand.name })}</p>
      <div className="flex flex-wrap gap-2">
        {brand.sizes.map((s) => (
          <button key={s.size_cm} type="button" onClick={() => onChange(s.size_cm)}
            className={cn("flex cursor-pointer flex-col items-center rounded-xl px-3 py-1.5 text-sm ring-1 transition",
              value === s.size_cm ? "bg-brand-500 text-white ring-brand-500" : "bg-white text-ink-800 ring-ink-200 hover:ring-brand-300")}>
            <span className="font-bold">{s.size_cm}</span>
            <span className={cn("text-[11px]", value === s.size_cm ? "text-white/85" : "text-ink-500")}>{fmt.euro(s.price_cents)}</span>
            {brand.suggested_size_cm === s.size_cm && <span className={cn("text-[10px] font-semibold", value === s.size_cm ? "text-white" : "text-emerald-600")}>{t("judo.size.suggested")}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

function TradeStep({ catalog, trade, onChange, quote }: { catalog: JudogiCatalog; trade: TradeInChoice | null; onChange: (t: TradeInChoice | null) => void; quote: JudogiQuote | null }) {
  const { t, fmt } = useI18n();
  const typeRow = catalog.types.find((x) => x.code === trade?.kimono_type);
  const colorRow = typeRow?.colors.find((c) => c.code === trade?.color);
  const brandRow = colorRow?.brands.find((b) => b.name === trade?.brand);
  const select = "h-11 w-full rounded-xl border border-ink-200 bg-white px-3 text-sm text-ink-900";
  return (
    <div className="space-y-4">
      <StepTitle title={t("judo.trade.title")} text={t("judo.trade.text", { pct: catalog.trade_in_percent })} />
      <div className="flex w-fit gap-1 rounded-full bg-ink-50 p-1">
        {[false, true].map((yes) => (
          <button key={String(yes)} type="button" onClick={() => onChange(yes ? { kimono_type: "TRAINING", color: "WHITE", brand: "", size_cm: null } : null)}
            className={cn("h-9 cursor-pointer rounded-full px-5 text-sm font-semibold", (!!trade) === yes ? "bg-ink-900 text-white" : "text-ink-600 hover:bg-white")}>
            {yes ? t("judo.trade.yes") : t("judo.trade.no")}
          </button>
        ))}
      </div>
      {trade && (
        <div className="grid gap-3 rounded-2xl bg-ink-50 p-4 sm:grid-cols-2">
          <Field label={t("judo.trade.type")}>
            <select className={select} value={trade.kimono_type} onChange={(e) => onChange({ kimono_type: e.target.value as KimonoType, color: "WHITE", brand: "", size_cm: null })}>
              {catalog.types.map((x) => <option key={x.code} value={x.code}>{t(`judo.type.${x.code}` as "judo.type.TRAINING")}</option>)}
            </select>
          </Field>
          <Field label={t("judo.trade.color")}>
            <select className={select} value={trade.color} onChange={(e) => onChange({ ...trade, color: e.target.value as JudogiColor, brand: "", size_cm: null })}>
              {(typeRow?.colors ?? []).map((c) => <option key={c.code} value={c.code}>{t(`judo.color.${c.code}` as "judo.color.WHITE")}</option>)}
            </select>
          </Field>
          <Field label={t("judo.trade.brand")}>
            <select className={select} value={trade.brand} onChange={(e) => onChange({ ...trade, brand: e.target.value, size_cm: null })}>
              <option value="">{t("judo.trade.pick")}</option>
              {(colorRow?.brands ?? []).map((b) => <option key={b.name} value={b.name}>{b.name}</option>)}
            </select>
          </Field>
          <Field label={t("judo.trade.size")}>
            <select className={select} value={trade.size_cm ?? ""} disabled={!brandRow} onChange={(e) => onChange({ ...trade, size_cm: Number(e.target.value) || null })}>
              <option value="">{t("judo.trade.pick")}</option>
              {(brandRow?.sizes ?? []).map((s) => <option key={s.size_cm} value={s.size_cm}>{s.size_cm} cm</option>)}
            </select>
          </Field>
          {quote?.trade_in && (
            <p className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800 ring-1 ring-emerald-200 sm:col-span-2">
              {t("judo.trade.value", { value: fmt.euro(quote.trade_in.value_cents), discount: fmt.euro(quote.trade_in.discount_cents) })}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function Receipt({ quote, loading, error, athleteName }: { quote: JudogiQuote | null; loading?: boolean; error?: string | null; athleteName?: string }) {
  const { t, fmt } = useI18n();
  if (error) return <p className="rounded-2xl bg-rose-50 p-4 text-sm text-rose-700 ring-1 ring-rose-200">{error}</p>;
  if (!quote) return <Skeleton className="h-64" />;
  return (
    <div className={cn("relative overflow-hidden rounded-3xl bg-gradient-to-br from-ink-900 to-ink-800 p-5 text-white shadow-lift", loading && "opacity-70")}>
      <div className="pointer-events-none absolute -right-8 -top-10 h-36 w-36 rounded-full bg-brand-500/30 blur-3xl" aria-hidden="true" />
      <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-white/60">{t("judo.receipt.eyebrow")}</p>
      {athleteName && <p className="text-sm text-white/80">{athleteName}</p>}
      <p className="mt-1 font-display text-lg leading-tight">{t(`judo.type.${quote.kimono_type}` as "judo.type.TRAINING")}</p>
      <p className="text-sm text-white/75">{quote.brand} · {t(`judo.color.${quote.color}` as "judo.color.WHITE")} · {quote.size_cm} cm</p>
      <dl className="mt-4 space-y-1.5 text-sm">
        <Row label={t("judo.receipt.base")} value={fmt.euro(quote.base_price_cents)} />
        <Row label={t("judo.receipt.custom")} value={`+ ${fmt.euro(quote.customization_cents)}`} />
        {quote.trade_in && <Row label={t("judo.receipt.trade", { pct: quote.trade_in.percent })} value={`− ${fmt.euro(quote.trade_in_discount_cents)}`} accent />}
      </dl>
      <div className="mt-4 flex items-end justify-between border-t border-white/15 pt-3">
        <span className="text-xs font-bold uppercase tracking-wider text-white/70">{t("judo.receipt.total")}</span>
        <span className="font-display text-3xl text-accent-300">{fmt.euro(quote.total_cents)}</span>
      </div>
    </div>
  );
}

function Row({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-white/75">{label}</dt>
      <dd className={cn("font-semibold", accent && "text-emerald-300")}>{value}</dd>
    </div>
  );
}
