// Gli eventi visti dallo staff, i risultati dal treinador e i relatórios
// (apps/api/app/domains/club/competition_staff_router.py). I tipi seguono
// gli schemi del router; le chiamate passano da clubGet/clubSend.

export interface EventInfo {
  id: string;
  name: string;
  description: string | null;
  kind: string;
  level: string;
  status: string;
  starts_on: string;
  ends_on: string;
  starts_at_time: string | null;
  ends_at_time: string | null;
  location: string | null;
  organizer: string | null;
  registration_deadline: string;
  registration_deadline_time: string | null;
  fee_cents: number;
  min_age: number | null;
  max_age: number | null;
  age_groups: string[];
  categories: string | null;
  requires_agonistic_certificate: boolean;
  circular_url: string | null;
  circular_filename: string | null;
  image_url: string | null;
  transport_mode: string;
  transport_info: string | null;
  network: boolean;
  club_name: string | null;
}

export interface StaffEvent extends EventInfo {
  entries_count: number;
  results_count: number;
}

export interface EventContact {
  name: string | null;
  email: string | null;
  phone: string | null;
  /** true: è l'encarregado (atleta minorenne). */
  is_guardian: boolean;
}

export interface EventEntry {
  entry_id: string;
  athlete_id: string;
  athlete_name: string;
  photo_url: string | null;
  category: string | null;
  placement: number | null;
  rank: number | null;
  points: number;
  // Solo per lo staff.
  sex?: string | null;
  age?: number | null;
  weight_kg?: string | null;
  result_notes?: string | null;
  contact?: EventContact | null;
}

export interface EventDetail extends EventInfo {
  entries: EventEntry[];
}

export const COST_KINDS = ["HOTEL", "TRAVEL", "FUEL", "FOOD", "ENTRY_FEES", "OTHER"] as const;
export type CostKind = (typeof COST_KINDS)[number];

export const COST_ICONS: Record<CostKind, string> = {
  HOTEL: "🏨", TRAVEL: "✈️", FUEL: "⛽", FOOD: "🍽️", ENTRY_FEES: "🎟️", OTHER: "🧾",
};

export interface ReportCost {
  kind: CostKind;
  amount_cents: number;
  note: string | null;
}

export interface ReportResult {
  athlete_id: string;
  athlete_name: string;
  category: string | null;
  weight_kg: string | null;
  placement: number | null;
  rank: number | null;
  result_notes: string | null;
  points: number;
}

export interface EventReport {
  id: string;
  competition_id: string;
  competition_name: string;
  competition_kind: string;
  competition_level: string;
  starts_on: string;
  ends_on: string;
  location: string | null;
  author_user_id: string;
  author_name: string;
  title: string;
  description: string | null;
  narrative: string | null;
  costs: ReportCost[];
  total_cents: number;
  photos: { id: string; url: string | null }[];
  results: ReportResult[];
  created_at: string;
  updated_at: string | null;
  can_edit: boolean;
}

/** Le medaglie del podio; gli altri piazzamenti hanno il numero. */
export const MEDALS: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

/** Il numero per un link WhatsApp: solo cifre, con il prefisso del
 *  Portogallo quando è un cellulare portoghese scritto senza (9 cifre). */
export function whatsappNumber(phone: string): string {
  const digits = phone.replace(/\D/g, "").replace(/^00/, "");
  return digits.length === 9 && digits.startsWith("9") ? `351${digits}` : digits;
}
