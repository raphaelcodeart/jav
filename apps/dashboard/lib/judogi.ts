// I judogi del club e la lista dei desideri (apps/api/app/domains/club/judogi.py).
// Il browser manda solo le scelte (tipo, colore, marca, taglia, permuta):
// ogni importo lo calcola il server, anche quello che si vede.

export type KimonoType = "FIJ_APPROVED" | "TRAINING" | "SEMI_COMPETITION" | "COMPETITION_NOT_APPROVED";
export type JudogiColor = "WHITE" | "BLUE" | "PINK" | "WHITE_PINK_STRIPES";
export type OrderStatus = "PENDING" | "IN_PREPARATION" | "DELIVERED" | "CANCELLED";

export const KIMONO_TYPES: KimonoType[] = ["TRAINING", "SEMI_COMPETITION", "COMPETITION_NOT_APPROVED", "FIJ_APPROVED"];
export const JUDOGI_COLORS: JudogiColor[] = ["WHITE", "BLUE", "PINK", "WHITE_PINK_STRIPES"];
export const ORDER_STATUSES: OrderStatus[] = ["PENDING", "IN_PREPARATION", "DELIVERED", "CANCELLED"];

/** Il pallino del colore nel calcolatore. */
export const COLOR_SWATCH: Record<JudogiColor, string> = {
  WHITE: "bg-white ring-ink-300",
  BLUE: "bg-blue-700 ring-blue-900",
  PINK: "bg-pink-400 ring-pink-600",
  WHITE_PINK_STRIPES: "bg-[repeating-linear-gradient(45deg,#fff_0_6px,#f472b6_6px_9px)] ring-pink-500",
};

export const TYPE_ICON: Record<KimonoType, string> = {
  TRAINING: "🥋",
  SEMI_COMPETITION: "⚡",
  COMPETITION_NOT_APPROVED: "🏆",
  FIJ_APPROVED: "🌍",
};

export const STATUS_TONE: Record<OrderStatus, "warning" | "info" | "success" | "neutral"> = {
  PENDING: "warning",
  IN_PREPARATION: "info",
  DELIVERED: "success",
  CANCELLED: "neutral",
};

export interface CatalogBrand {
  name: string;
  sizes: { size_cm: number; price_cents: number }[];
  min_price_cents: number;
  suggested_size_cm: number | null;
  suggested_price_cents: number | null;
}
export interface CatalogColor { code: JudogiColor; label: string; brands: CatalogBrand[] }
export interface CatalogType { code: KimonoType; label: string; colors: CatalogColor[]; min_price_cents: number }
export interface JudogiCatalog { customization_cents: number; trade_in_percent: number; types: CatalogType[] }

export interface JudogiAthlete {
  id: string;
  name: string;
  first_name: string;
  photo_url: string | null;
  sex: string;
  age: number;
  height_cm: number | null;
  /** BUY: ordina (titolare, atleta maggiorenne); WISH: solo la lista dei desideri. */
  mode: "BUY" | "WISH";
  kimono_name: string;
  single_name_only: boolean;
}

export interface TradeInChoice { kimono_type: KimonoType; color: JudogiColor; brand: string; size_cm: number | null }
export interface JudogiChoice {
  kimono_type: KimonoType;
  color: JudogiColor;
  brand: string;
  size_cm: number | null;
  height_cm?: number | null;
  trade_in?: TradeInChoice | null;
}

export interface JudogiQuote {
  kimono_type: KimonoType;
  type_label: string;
  color: JudogiColor;
  color_label: string;
  brand: string;
  size_cm: number;
  base_price_cents: number;
  customization_cents: number;
  subtotal_cents: number;
  trade_in: (TradeInChoice & { type_label: string; color_label: string; value_cents: number; percent: number; discount_cents: number }) | null;
  trade_in_discount_cents: number;
  total_cents: number;
}

export interface JudogiOrder {
  id: string;
  athlete_id: string;
  athlete_name: string | null;
  kimono_name: string;
  kimono_type: KimonoType;
  type_label: string;
  color: JudogiColor | null;
  color_label: string;
  brand: string;
  size_cm: number;
  price_cents: number | null;
  base_price_cents: number | null;
  customization_cents: number | null;
  trade_in_discount_cents: number | null;
  trade_in: JudogiQuote["trade_in"];
  notes: string | null;
  status: OrderStatus;
  fee_id: string | null;
  fee_status: "DUE" | "PAID" | "WAIVED" | null;
  delivered_on: string | null;
  created_at: string;
}

export interface Wish {
  id: string;
  kind: "PRODUCT" | "JUDOGI";
  status: "OPEN" | "ORDERED" | "DISMISSED";
  note: string | null;
  created_at: string;
  athlete_id: string;
  athlete_name: string;
  athlete_first_name: string;
  product: { id: string; name: string; image_url: string | null; available: boolean } | null;
  variant: { id: string; label: string; price_cents: number } | null;
  judogi: { choice: JudogiChoice; kimono_name: string | null; quote: JudogiQuote } | null;
  equipment_order_id: string | null;
  jav_market_order_id: string | null;
  can_decide: boolean;
  can_remove: boolean;
}

export interface JudogiPrice {
  id: string;
  kimono_type: KimonoType;
  type_label: string;
  brand: string;
  color: JudogiColor;
  color_label: string;
  size_cm: number;
  price_cents: number;
  active: boolean;
}

export const JUDOGI_KEYS = {
  catalog: (height: number | null) => ["club", "judogi", "catalog", height ?? 0] as const,
  athletes: ["club", "judogi", "athletes"] as const,
  orders: ["club", "judogi", "orders"] as const,
  wishes: ["club", "wishlist"] as const,
};
