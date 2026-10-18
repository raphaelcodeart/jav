"use client";

import { useEffect, useRef } from "react";

// JAVBOT: i tipi delle risposte (apps/api/app/domains/javbot/schemas.py) e
// il piccolo "canale" con cui l'assistente apre "Carica un pagamento" nella
// pagina della famiglia senza che le due cose si conoscano.

export interface BotAction {
  /** `say`: il bottone manda `value` come se l'utente l'avesse scritto. */
  type: "navigate" | "open_pay" | "confirm_task" | "cancel_task" | "link" | "copy" | "say";
  label: string;
  target?: string | null;
  kind?: string | null;
  task_id?: string | null;
  /** PENDING / DONE / CANCELLED: una proposta già decisa non si ripropone. */
  task_status?: string | null;
  href?: string | null;
  value?: string | null;
}

export interface BotMessage {
  id: string;
  role: "user" | "bot";
  text: string;
  actions: BotAction[];
  quick_replies: string[];
  /** Le schede sotto il testo (eventi, fonti dei documenti). */
  cards?: BotCard[];
  created_at?: string;
}

/** Una gara o un evento proposto da JAVBOT, con i bottoni `say` («Inscrever X»). */
export interface BotEventCard {
  type: "event";
  competition_id?: string | null;
  title: string;
  kind?: string | null;
  date: string;
  end_date?: string | null;
  location?: string | null;
  deadline?: string | null;
  fee_cents?: number | null;
  has_regulation?: boolean;
  actions?: BotAction[];
}

/** Una fonte della risposta: un PDF caricato, il regolamento di un evento,
 *  o una scheda scritta dal gestionale con i dati del club (DATA). */
export interface BotSourceCard {
  type: "source";
  n: number;
  title: string;
  page?: number | null;
  source: "UPLOAD" | "EVENT" | "DATA" | string;
  competition_id?: string | null;
}

export type BotCard = BotEventCard | BotSourceCard | { type: string };

/** Le sezioni che il backend nomina (`navigate.target`) e le schede che le
 *  mostrano, nell'ordine in cui cercarle: ogni area ha le sue chiavi. */
export const NAV_TARGETS: Record<string, string[]> = {
  club: ["club"],
  shop: ["products", "shop"],
  orders: ["orders"],
  settings: ["settings"],
  competitions: ["club-competitions"],
  wallet: ["wallet", "wallets"],
  accounts: ["club-accounting"],
};

export type PayKind = "fees" | "choose";

let pendingPay: PayKind | null = null;
const payListeners = new Set<(kind: PayKind) => void>();

/** Chiede alla pagina della famiglia di aprire "Carica un pagamento". Se
 *  la pagina non è ancora montata (si sta cambiando scheda) la richiesta
 *  aspetta e la pagina la raccoglie appena compare. */
export function requestJavbotPay(kind: PayKind): void {
  if (payListeners.size === 0) {
    pendingPay = kind;
    return;
  }
  pendingPay = null;
  payListeners.forEach((listener) => listener(kind));
}

/** Il gancio per la pagina che possiede "Carica un pagamento" (family-home):
 *  `useJavbotPayRequest(setPay)`. Riceve le richieste di JAVBOT, anche
 *  quella arrivata un attimo prima che la pagina fosse montata. */
export function useJavbotPayRequest(open: (kind: PayKind) => void): void {
  const latest = useRef(open);
  useEffect(() => {
    latest.current = open;
  });
  useEffect(() => {
    const listener = (kind: PayKind) => latest.current(kind);
    payListeners.add(listener);
    if (pendingPay) {
      const kind = pendingPay;
      pendingPay = null;
      // Una richiesta esterna (dalla chat) da consegnare una volta sola,
      // al montaggio: non è stato derivabile dal render.
      queueMicrotask(() => listener(kind));
    }
    return () => {
      payListeners.delete(listener);
    };
  }, []);
}
