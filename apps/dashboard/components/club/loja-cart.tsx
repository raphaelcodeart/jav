"use client";

import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { LojaPhoto, useLojaCart, useLojaRefresh } from "@/components/club/loja-common";
import { Stepper } from "@/components/club/loja-product";
import { clubSend } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import { STATUS_TONE } from "@/lib/judogi";
import { LOJA_KEYS, type Cart, type CartLine, type CheckoutResult } from "@/lib/loja";

// Il carrello della Loja (club/loja.py): judogi e prodotti, per uno o più
// atleti. All'ordine ogni riga diventa un ordine a sé con la sua quota; la
// famiglia paga subito (il pagamento di sempre, con le quote nuove già
// scelte) o più tardi, dalla home. Prezzi e totale li ricalcola il server a
// ogni lettura: qui non si somma niente.

/** Il bottone del carrello che resta in vista mentre si scorre la Loja. */
export function CartButton({ count, onClick }: { count: number; onClick: () => void }) {
  const { t } = useI18n();
  return (
    <AnimatePresence>
      {count > 0 && (
        <motion.div initial={{ y: 24, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 24, opacity: 0 }}
          className="pointer-events-none sticky bottom-[calc(max(env(safe-area-inset-bottom),12px)+88px)] z-30 flex justify-center lg:bottom-6">
          <button type="button" onClick={onClick}
            className="pointer-events-auto flex min-h-14 cursor-pointer items-center gap-3 rounded-full bg-ink-900 py-2 pl-5 pr-2 text-white shadow-lift ring-1 ring-white/10 transition hover:bg-ink-800">
            <span className="text-[15px] font-bold">🛒 {t("loja.cart.open")}</span>
            <span className="flex h-10 min-w-10 items-center justify-center rounded-full bg-brand-500 px-2 text-sm font-extrabold">{count}</span>
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function CartModal({ onClose, onPay }: { onClose: () => void; onPay?: (feeIds: string[]) => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const refresh = useLojaRefresh();
  const { data: cart, isLoading } = useLojaCart();
  const [busyLine, setBusyLine] = useState<string | null>(null);
  const [busy, setBusy] = useState<"NOW" | "LATER" | null>(null);
  const [done, setDone] = useState<CheckoutResult | null>(null);

  async function change(line: CartLine, quantity: number | null) {
    setBusyLine(line.id);
    try {
      const next = quantity == null
        ? await clubSend<Cart>(`/loja/cart/${line.id}`, "DELETE")
        : await clubSend<Cart>(`/loja/cart/${line.id}`, "PATCH", { quantity });
      queryClient.setQueryData(LOJA_KEYS.cart, next);
    } catch (e) {
      toast({ tone: "error", title: t("judo.calc.failed"), text: (e as Error).message });
    } finally {
      setBusyLine(null);
    }
  }

  async function checkout(now: boolean) {
    setBusy(now ? "NOW" : "LATER");
    try {
      const res = await clubSend<CheckoutResult>("/loja/checkout", "POST", {});
      await refresh();
      setDone(res);
      if (now) onPay?.(res.fee_ids);
    } catch (e) {
      toast({ tone: "error", title: t("judo.calc.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  if (done) {
    return (
      <Modal open onClose={onClose} size="md"
        footer={
          <div className="flex w-full flex-col gap-2">
            {onPay && done.fee_ids.length > 0 && (
              <Button size="lg" className="w-full" onClick={() => onPay(done.fee_ids)}>{t("loja.cart.payAmount", { amount: fmt.euro(done.total_cents) })}</Button>
            )}
            <Button size="lg" variant="secondary" className="w-full" onClick={onClose}>{t("loja.cart.backToShop")}</Button>
          </div>
        }>
        <div className="flex flex-col items-center gap-2 pt-6 text-center">
          <motion.span initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
            className="flex h-20 w-20 items-center justify-center rounded-full bg-emerald-50 text-4xl text-emerald-600" aria-hidden="true">✓</motion.span>
          <h2 className="font-display text-2xl text-ink-900">
            {done.orders.length === 1 ? t("loja.cart.doneOne") : t("loja.cart.doneMany", { n: done.orders.length })}
          </h2>
          <p className="max-w-sm text-sm text-ink-600">{t("loja.cart.doneText")}</p>
        </div>
        <ul className="mt-5 divide-y divide-ink-100 rounded-2xl bg-ink-50 px-4">
          {done.orders.map((o) => (
            <li key={o.id} className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink-900">{o.title}</p>
                {o.athlete_name && <p className="text-xs text-ink-500">{o.athlete_name}</p>}
              </div>
              {o.price_cents != null && <span className="text-sm font-bold text-ink-900">{fmt.euro(o.price_cents)}</span>}
              <Badge tone={STATUS_TONE[o.status]}>{t(`judo.status.${o.status}` as "judo.status.PENDING")}</Badge>
            </li>
          ))}
        </ul>
      </Modal>
    );
  }

  // Le righe per atleta: la famiglia che compra per due figli li ritrova divisi.
  const groups: { id: string; name: string; lines: CartLine[] }[] = [];
  for (const line of cart?.items ?? []) {
    let group = groups.find((g) => g.id === line.athlete_id);
    if (!group) {
      group = { id: line.athlete_id, name: line.athlete_name ?? "", lines: [] };
      groups.push(group);
    }
    group.lines.push(line);
  }
  const problems = (cart?.items ?? []).some((l) => l.problem);

  return (
    <Modal open onClose={onClose} size="lg" title={t("loja.cart.title")}
      subtitle={cart ? (cart.count === 1 ? t("loja.cart.countOne") : t("loja.cart.count", { n: cart.count })) : undefined}
      footer={cart && cart.count > 0 ? (
        <div className="flex w-full flex-col gap-2">
          <div className="flex items-baseline justify-between">
            <span className="text-sm font-semibold text-ink-600">{t("judo.receipt.total")}</span>
            <span className="font-display text-2xl text-ink-900">{fmt.euro(cart.total_cents)}</span>
          </div>
          {problems && <p className="text-xs font-medium text-rose-700">{t("loja.cart.fixProblems")}</p>}
          <Button size="lg" className="w-full" disabled={!cart.can_checkout || !!busy} loading={busy === "NOW"} onClick={() => void checkout(true)}>
            {t("loja.cart.orderPayNow")}
          </Button>
          <Button size="lg" variant="secondary" className="w-full" disabled={!cart.can_checkout || !!busy} loading={busy === "LATER"} onClick={() => void checkout(false)}>
            {t("loja.cart.orderPayLater")}
          </Button>
        </div>
      ) : undefined}>
      {isLoading ? <Skeleton className="h-48" /> : !cart || cart.count === 0 ? (
        <div className="flex flex-col items-center gap-2 py-10 text-center">
          <span className="text-5xl" aria-hidden="true">🛒</span>
          <p className="font-semibold text-ink-900">{t("loja.cart.empty")}</p>
          <p className="text-sm text-ink-500">{t("loja.cart.emptyText")}</p>
        </div>
      ) : (
        <div className="space-y-5">
          {groups.map((g) => (
            <section key={g.id} className="space-y-2">
              {groups.length > 1 && <h3 className="text-xs font-bold uppercase tracking-wider text-brand-600">{g.name}</h3>}
              <ul className="space-y-2">
                {g.lines.map((l) => <CartRow key={l.id} line={l} busy={busyLine === l.id} onChange={(q) => void change(l, q)} showAthlete={groups.length === 1} />)}
              </ul>
            </section>
          ))}
          <p className="flex gap-2 rounded-2xl bg-ink-50 p-3 text-xs leading-relaxed text-ink-600">
            <span aria-hidden="true">📦</span>
            <span>{t("loja.cart.separateHint")}</span>
          </p>
        </div>
      )}
    </Modal>
  );
}

function CartRow({ line, busy, onChange, showAthlete }: { line: CartLine; busy: boolean; onChange: (q: number | null) => void; showAthlete: boolean }) {
  const { t, fmt } = useI18n();
  const q = line.quote;
  const name = line.kind === "JUDOGI" ? line.config?.kimono_name : line.config?.name;
  const bits: string[] = [];
  if (showAthlete && line.athlete_name) bits.push(line.athlete_name.split(" ")[0]!);
  if (q) bits.push(t(`judo.color.${q.color}` as "judo.color.WHITE"), `${q.size_cm} cm`);
  if (line.variant_label && line.variant_label !== "Unica") bits.push(line.variant_label);
  if (name) bits.push(`«${name}»`);
  return (
    <li className={cn("flex gap-3 rounded-2xl bg-white p-3 ring-1 transition-opacity", line.problem ? "ring-rose-200" : "ring-ink-100", busy && "opacity-60")}>
      <LojaPhoto src={line.image_url} judogi={line.kind === "JUDOGI"} color={q?.color ?? null} className="h-16 w-16 shrink-0 overflow-hidden rounded-xl" size={40} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-bold leading-snug text-ink-900">
          {line.title ? (line.kind === "JUDOGI" && q ? `${t(`judo.type.${q.kimono_type}` as "judo.type.TRAINING")} · ${q.brand}` : line.title) : t("loja.cart.unavailable")}
        </p>
        {bits.length > 0 && <p className="text-xs text-ink-500">{bits.join(" · ")}</p>}
        {q?.trade_in && <p className="text-xs font-semibold text-emerald-700">{t("loja.cart.tradeLine", { amount: fmt.euro(q.trade_in_discount_cents) })}</p>}
        {line.problem && <p className="mt-1 rounded-lg bg-rose-50 px-2 py-1 text-xs text-rose-700" role="alert">{line.problem}</p>}
        {line.kind === "PRODUCT" && !line.problem && (
          <div className="mt-2"><Stepper value={line.quantity} disabled={busy} onChange={(n) => onChange(n)} /></div>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end justify-between gap-2">
        {!line.problem && <span className="text-[15px] font-extrabold text-ink-900">{fmt.euro(line.price_cents)}</span>}
        <button type="button" onClick={() => onChange(null)} disabled={busy} aria-label={t("loja.cart.remove", { name: line.title ?? "" })}
          className="flex h-11 w-11 cursor-pointer items-center justify-center rounded-xl text-ink-500 transition hover:bg-rose-50 hover:text-rose-700 disabled:opacity-40">
          <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />
          </svg>
        </button>
      </div>
    </li>
  );
}
