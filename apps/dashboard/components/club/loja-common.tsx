"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { AthletePayModal } from "@/components/club/athlete-pay-modal";
import { PayModal } from "@/components/club/pay-modal";
import { clubGet, type Family, type Fee } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import { JUDOGI_KEYS, type JudogiAthlete, type JudogiColor } from "@/lib/judogi";
import { LOJA_KEYS, type Cart, type LojaLock, type LojaShop } from "@/lib/loja";

// I pezzi comuni della Loja (judogi-shop, judogi-wizard, loja-cart,
// loja-product): le query, il pagamento dopo l'ordine, le illustrazioni
// che stanno al posto di una foto che la segreteria non ha ancora caricato.

export function useJudogiAthletes(enabled = true) {
  return useQuery({ queryKey: JUDOGI_KEYS.athletes, queryFn: () => clubGet<JudogiAthlete[]>("/judogi/athletes"), enabled, retry: false });
}

export function useLojaShop(athleteId: string | null) {
  return useQuery({
    queryKey: LOJA_KEYS.shop(athleteId ?? ""),
    queryFn: () => clubGet<LojaShop>(`/loja/athletes/${athleteId}`),
    enabled: !!athleteId,
    retry: false,
  });
}

export function useLojaCart(enabled = true) {
  return useQuery({ queryKey: LOJA_KEYS.cart, queryFn: () => clubGet<Cart>("/loja/cart"), enabled, retry: false });
}

/** Dopo un ordine, un articolo nel carrello o un desiderio: il kit, il
 *  carrello, gli ordini, i desideri e le quote della home cambiano insieme. */
export function useLojaRefresh() {
  const queryClient = useQueryClient();
  return () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["club", "loja"] }),
    queryClient.invalidateQueries({ queryKey: JUDOGI_KEYS.orders }),
    queryClient.invalidateQueries({ queryKey: JUDOGI_KEYS.wishes }),
    queryClient.invalidateQueries({ queryKey: ["club", "family"] }),
    queryClient.invalidateQueries({ queryKey: ["club", "athlete-area"] }),
  ]);
}

/** Chi paga le quote dei nuovi ordini: il titolare dalla famiglia
 *  (/club/family è suo), l'atleta maggiorenne con il suo accesso dalla sua area. */
export type LojaPayer = { kind: "family" } | { kind: "athlete"; athleteId: string };

/** «Pagar já»: le quote appena create, già scelte nel pagamento di sempre.
 *  Le quote si rileggono dal server, mai ricostruite dalla risposta dell'ordine. */
export function useLojaPay(payer: LojaPayer) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<{ fees: Fee[]; preselect: string[] } | null>(null);

  async function pay(feeIds: string[]) {
    if (payer.kind === "family") {
      const family = await queryClient.fetchQuery({ queryKey: ["club", "family"], queryFn: () => clubGet<Family>("/family"), staleTime: 0 });
      setState({ fees: family.due_fees, preselect: feeIds });
    } else {
      const area = await queryClient.fetchQuery({
        queryKey: ["club", "athlete-area", payer.athleteId],
        queryFn: () => clubGet<{ fees: Fee[] }>(`/athlete-area/${payer.athleteId}`),
        staleTime: 0,
      });
      setState({ fees: area.fees.filter((f) => f.status === "DUE" && feeIds.includes(f.id)), preselect: feeIds });
    }
  }

  const close = () => setState(null);
  const modal = !state ? null : payer.kind === "family"
    ? <PayModal open onClose={close} fees={state.fees} preselect={state.preselect} />
    : <AthletePayModal athleteId={payer.athleteId} fees={state.fees} onClose={close} />;
  return { pay, modal };
}

// --- Illustrazioni e badge --------------------------------------------------------------------

const JUDOGI_FILL: Record<JudogiColor, { bg: string; stroke: string }> = {
  WHITE: { bg: "bg-ink-100", stroke: "text-ink-700" },
  BLUE: { bg: "bg-blue-700", stroke: "text-white" },
  PINK: { bg: "bg-pink-100", stroke: "text-pink-700" },
  WHITE_PINK_STRIPES: { bg: "bg-[repeating-linear-gradient(45deg,#fff_0_10px,#fbcfe8_10px_16px)]", stroke: "text-pink-700" },
};

/** Il judogi disegnato, del suo colore: al posto della foto che manca. */
export function JudogiArt({ color, className, size = 64 }: { color: JudogiColor | null; className?: string; size?: number }) {
  const fill = JUDOGI_FILL[color ?? "WHITE"];
  return (
    <span className={cn("flex items-center justify-center", fill.bg, className)} aria-hidden="true">
      <svg width={size} height={size} viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth={2} strokeLinejoin="round" className={fill.stroke}>
        <path d="M22 6l10 8 10-8 14 8-6 12-6-3v35H20V23l-6 3-6-12z" />
        <path d="M32 14l-6 20M32 14l6 20M20 38h24" />
      </svg>
    </span>
  );
}

/** Un capo del club senza foto: una sagoma neutra. */
export function ProductArt({ className, size = 56 }: { className?: string; size?: number }) {
  return (
    <span className={cn("flex items-center justify-center bg-ink-100", className)} aria-hidden="true">
      <svg width={size} height={size} viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth={2} strokeLinejoin="round" className="text-ink-500">
        <path d="M22 8c2 4 6 6 10 6s8-2 10-6l14 8-6 11-6-3v32H20V24l-6 3-6-11z" />
      </svg>
    </span>
  );
}

/** La foto se c'è, altrimenti l'illustrazione. */
export function LojaPhoto({ src, color, judogi = false, className, size }: { src: string | null | undefined; color?: JudogiColor | null; judogi?: boolean; className?: string; size?: number }) {
  if (src) {
    // eslint-disable-next-line @next/next/no-img-element -- foto della Loja nel bucket pubblico
    return <img src={src} alt="" className={cn("bg-white object-contain", className)} loading="lazy" />;
  }
  return judogi ? <JudogiArt color={color ?? null} className={className} size={size} /> : <ProductArt className={className} size={size} />;
}

export function LockIcon({ className }: { className?: string }) {
  return (
    <svg className={cn("h-3.5 w-3.5", className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  );
}

/** Il lucchetto con il perché, corto: «Só alta competição», «Só raparigas». */
export function LockBadge({ lock, className }: { lock: LojaLock; className?: string }) {
  const { t } = useI18n();
  return (
    <Badge tone={lock === "HIGH_COMPETITION" ? "accent" : "neutral"} className={className}>
      <LockIcon />
      {t(`loja.lock.${lock}` as "loja.lock.HIGH_COMPETITION")}
    </Badge>
  );
}
