// La Loja del club (apps/api/app/domains/club/loja.py): judogi ed
// equipaggiamento per un atleta, il carrello unico, gli ordini.
// Come per i judogi, il browser manda solo scelte (modello, variante,
// quantità, permuta): ogni importo che si vede l'ha calcolato il server.

import type { CatalogBrand, JudogiAthlete, JudogiColor, JudogiQuote, KimonoType, OrderStatus, TradeInChoice } from "@/lib/judogi";

/** Perché un articolo si vede ma non si compra (il server lo ricontrolla all'ordine). */
export type LojaLock = "HIGH_COMPETITION" | "GIRLS_ONLY" | "SEX";

export interface LojaAthlete extends JudogiAthlete {
  high_competition: boolean;
}

/** Il listino per tipo → colore → modello, con le foto dei modelli. */
export interface LojaCatalogBrand extends CatalogBrand {
  model_id: string | null;
  image_url: string | null;
  images: string[];
  description: string | null;
}
export interface LojaCatalogColor { code: JudogiColor; label: string; brands: LojaCatalogBrand[] }
export interface LojaCatalogType { code: KimonoType; label: string; colors: LojaCatalogColor[]; min_price_cents: number }

export interface LojaJudogi {
  kimono_type: KimonoType;
  type_label: string;
  color: JudogiColor;
  color_label: string;
  brand: string;
  model_id: string | null;
  image_url: string | null;
  images: string[];
  description: string | null;
  min_price_cents: number;
  suggested_size_cm: number | null;
  suggested_price_cents: number | null;
  lock: LojaLock | null;
}

export interface LojaVariant {
  id: string;
  label: string;
  price_cents: number;
  max_height_cm: number | null;
  image_url: string | null;
  in_stock: boolean;
}

export interface LojaProduct {
  id: string;
  name: string;
  description: string | null;
  image_url: string | null;
  images: string[];
  audience_sex: "ALL" | "F" | "M";
  high_competition_only: boolean;
  club_kit: boolean;
  needs_name: boolean;
  variants: LojaVariant[];
  suggested_variant_id: string | null;
  min_price_cents: number;
  lock: LojaLock | null;
}

export interface KitItem {
  code: "WHITE_JUDOGI" | "PRODUCT";
  product_id: string | null;
  name: string | null;
  state: "HAS" | "ORDERED" | "MISSING";
}

/** Un judogi dell'«armadio» dell'atleta: quelli consegnati si possono restituire. */
export interface OwnedJudogi {
  id: string;
  kimono_type: KimonoType | null;
  type_label: string | null;
  color: JudogiColor | null;
  color_label: string | null;
  brand: string | null;
  size_cm: number | null;
  kimono_name: string | null;
  status: OrderStatus;
  origin: string | null;
  delivered_on: string | null;
  small: boolean;
}

export interface LojaShop {
  athlete: LojaAthlete;
  settings: { customization_cents: number; trade_in_percent: number };
  judogi_types: LojaCatalogType[];
  judogis: LojaJudogi[];
  products: LojaProduct[];
  kit: KitItem[];
  wardrobe: OwnedJudogi[];
}

/** La permuta come la manda il wizard: un judogi dell'armadio o descritto a mano. */
export type TradeInWrite = { owned_order_id: string } | TradeInChoice;

export interface JudogiLineWrite {
  kimono_type: KimonoType;
  color: JudogiColor;
  brand: string;
  size_cm?: number | null;
  height_cm?: number | null;
  kimono_name: string;
  notes?: string | null;
  trade_in?: TradeInWrite | null;
  wish_id?: string | null;
}

/** Il corpo di POST /club/loja/cart e di /club/loja/buy-now. */
export interface LineWrite {
  athlete_id: string;
  kind: "JUDOGI" | "PRODUCT";
  judogi?: JudogiLineWrite;
  variant_id?: string;
  quantity?: number;
  name?: string | null;
}

export interface CartLine {
  id: string;
  kind: "JUDOGI" | "PRODUCT";
  athlete_id: string;
  athlete_name: string | null;
  quantity: number;
  config: { kimono_name?: string | null; name?: string | null; [key: string]: unknown } | null;
  product_id: string | null;
  variant_id: string | null;
  title: string | null;
  variant_label?: string | null;
  image_url?: string | null;
  price_cents: number;
  unit_price_cents?: number;
  quote?: JudogiQuote;
  lock?: LojaLock | null;
  /** Perché la riga non si può ordinare adesso (testo del server). */
  problem: string | null;
}

export interface Cart {
  items: CartLine[];
  count: number;
  total_cents: number;
  can_checkout: boolean;
}

/** Un ordine della Loja (judogi o prodotto del club): ognuno con la sua quota. */
export interface LojaOrder {
  id: string;
  kind: "JUDOGI" | "PRODUCT";
  origin: string | null;
  title: string;
  athlete_id: string;
  athlete_name: string | null;
  kimono_name: string | null;
  kimono_type: KimonoType | null;
  type_label: string | null;
  color: JudogiColor | null;
  color_label: string | null;
  brand: string | null;
  size_cm: number | null;
  price_cents: number | null;
  status: OrderStatus;
  fee_id: string | null;
  fee_status: "DUE" | "PAID" | "WAIVED" | null;
  created_at: string;
  product_name: string | null;
  variant_label: string | null;
  quantity: number | null;
}

export interface CheckoutResult {
  orders: LojaOrder[];
  fee_ids: string[];
  total_cents: number;
}

export const LOJA_KEYS = {
  shop: (athleteId: string) => ["club", "loja", "shop", athleteId] as const,
  cart: ["club", "loja", "cart"] as const,
};
