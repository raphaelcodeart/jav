// The club portal (docs/club-portal.md). Types mirror apps/api/app/domains/club/schemas.py;
// every call goes through the BFF proxy, like the rest of the dashboard.

import { friendlyApiError } from "@/lib/api-error";
import type { ApiBelt } from "@/lib/belts";

export type ClubBelt = ApiBelt & { rank: number };

export interface AgeBand {
  code: string;
  label: string;
  min_age: number;
  max_age: number | null;
}

export interface AchievementDef {
  code: string;
  label: string;
  description: string;
  target: number;
}

export interface ClubConfig {
  season: number;
  season_label: string;
  belts: ClubBelt[];
  age_bands: AgeBand[];
  placement_labels: Record<string, string>;
  /** [oro, argento, bronzo, partecipazione] per livello di gara. */
  level_points: Record<string, [number, number, number, number]>;
  level_labels: Record<string, string>;
  achievements: AchievementDef[];
  weekdays: string[];
}

export interface PlanSummary {
  id: string;
  name: string;
  monthly_fee_cents: number;
}

export interface Plan extends PlanSummary {
  description: string | null;
  min_age: number;
  max_age: number | null;
  enrollment_fee_cents: number;
  due_day: number;
  billing_months: number[];
  active: boolean;
}

export interface Fee {
  id: string;
  /** null per la quota socio del genitore (MEMBERSHIP). */
  athlete_id: string | null;
  athlete_name: string | null;
  kind: "MONTHLY" | "ENROLLMENT" | "COMPETITION" | string;
  period: string;
  description: string;
  amount_cents: number;
  /** Il listino prima degli sconti, e gli sconti già in parole. */
  gross_amount_cents: number | null;
  discount_cents: number;
  discount_note: string | null;
  due_date: string;
  status: "DUE" | "PAID" | "WAIVED" | string;
  overdue: boolean;
  paid_at: string | null;
  paid_via_proof_id: string | null;
  payment_note: string | null;
  /** Come è stata pagata: BANK_TRANSFER, CASH, CARD, WALLET (null se da
   *  pagare, o segnata pagata prima che il metodo si registrasse). */
  payment_method?: PaymentMethod | null;
  /** Per i contanti: a chi sono stati consegnati. */
  cash_received_by_name?: string | null;
  waive_reason: string | null;
  competition_id: string | null;
  /** Corsi JAV: il corso a cui la mensilità è attribuita (null = senza corso). */
  course_id?: string | null;
}

export type CertificateState = "MISSING" | "VALID" | "EXPIRING" | "EXPIRED";

export interface CertificateStatus {
  status: CertificateState | string;
  id: string | null;
  type: string | null;
  issued_on: string | null;
  expires_on: string | null;
}

export interface NextCompetition {
  competition_id: string;
  name: string;
  starts_on: string;
  location: string | null;
  category: string | null;
}

export interface AthleteCard {
  id: string;
  first_name: string;
  last_name: string;
  birth_date: string;
  age: number;
  season_age: number;
  /** Gli anni compiuti entro il 31 dicembre: decidono il gruppo. */
  federal_age?: number;
  sex: "M" | "F" | string;
  photo_url: string | null;
  is_self: boolean;
  status: string;
  weight_kg: string | number | null;
  fiscal_code: string | null;
  federation_number: string | null;
  federation_expires_on: string | null;
  social_tier: "A" | "B" | "C" | null;
  adapted_judo: boolean;
  plan: PlanSummary | null;
  plan_locked: boolean;
  belt: ClubBelt | null;
  next_fee: Fee | null;
  due_cents: number;
  overdue_count: number;
  certificate: CertificateStatus;
  next_competition: NextCompetition | null;
  ranking_points: number;
  medals: { gold: number; silver: number; bronze: number };
  attendances: number;
  xp: number;
  level: number;
  level_xp_floor: number;
  next_level_xp: number;
  progress: number;
  achievements_earned: number;
  competitions_count?: number;
  weight_category?: string | null;
  age_band?: string | null;
  club_name?: string | null;
  white_judogi?: boolean;
  obligations?: Obligations | null;
}

/** Gli obblighi dell'atleta (apps/api/app/domains/club/obligations.py). */
export interface Obligations {
  items: { code: "JUDOGI_COLOUR" | "WHITE_JUDOGI" | "CERTIFICATE" | "ANNUAL_FEE"; ok: boolean; rule?: string; state?: string; status?: string | null; declared?: boolean; due_cents?: number }[];
  missing: number;
  can_compete: boolean;
  compete_missing: string[];
}

export interface BeltHistory extends ClubBelt {
  id: string;
  awarded_on: string;
  note: string | null;
}

export interface Certificate {
  id: string;
  type: string;
  issued_on: string;
  expires_on: string;
  status: string;
  original_filename: string;
}

export interface AthleteCompetition {
  competition_id: string;
  entry_id: string;
  name: string;
  starts_on: string;
  location: string | null;
  level: string;
  category: string | null;
  status: string;
  placement: number | null;
  points: number;
}

export interface Achievement {
  code: string;
  label: string;
  description: string;
  earned: boolean;
  current: number;
  target: number;
}

export interface AthleteDetail extends AthleteCard {
  belt_history: BeltHistory[];
  certificates: Certificate[];
  fees: Fee[];
  competitions: AthleteCompetition[];
  achievements: Achievement[];
}

export interface Proof {
  id: string;
  created_at: string;
  amount_cents: number;
  /** La parte pagata con il credito del wallet. */
  credit_cents: number;
  status: "ACCEPTED" | "REJECTED" | string;
  note: string | null;
  original_filename: string | null;
  rejection_reason: string | null;
  reviewed_at: string | null;
  uploaded_by_user_id: string;
  /** BANK_TRANSFER (con la ricevuta) o CASH (consegnati a qualcuno). */
  method?: "BANK_TRANSFER" | "MBWAY" | "CASH";
  cash_received_by_name?: string | null;
  /** "MEN-2026-0042": il numero della ricevuta. */
  receipt_number?: string | null;
  /** Il giorno del pagamento dichiarato (null = quello del caricamento). */
  paid_on?: string | null;
  fees: Fee[];
}

export interface AdminProof extends Proof {
  uploaded_by_email: string | null;
}

export interface Family {
  season: number;
  season_label: string;
  athletes: AthleteCard[];
  due_fees: Fee[];
  due_cents: number;
  overdue_cents: number;
  paid_season_cents: number;
  recent_proofs: Proof[];
  open_competitions: number;
  season_months?: AthleteSeasonMonths[];
  /** «Questo mese»: la mensilità di ogni figlio e ciò che resta. */
  this_month?: MonthBoard | null;
}

/** Lo stato della mensilità di un atleta nel mese (club/month_board.py). */
export type MonthBoardState = "PAID" | "DUE" | "OVERDUE" | "WAIVED" | "EXEMPT" | "NONE";

export interface MonthRow {
  athlete_id: string;
  first_name: string;
  last_name: string;
  photo_url: string | null;
  group: string | null;
  state: MonthBoardState;
  fee: Fee | null;
  /** I mesi passati ancora da pagare. */
  arrears: Fee[];
  /** Le altre quote scadute entro la fine del mese (gare, judogi, iscrizione...). */
  other_due: Fee[];
  guardian_email?: string | null;
}

export interface MonthBoard {
  period: string;
  first_day: string;
  last_day: string;
  is_current: boolean;
  rows: MonthRow[];
  totals: {
    athletes: number; expected_cents: number; collected_cents: number; missing_cents: number;
    paid: number; to_pay: number; overdue: number; exempt: number; none: number;
    arrears_cents: number; other_due_cents: number;
  };
}

/** Le mensilità della stagione di un atleta, in numeri (grafico famiglia). */
export interface AthleteSeasonMonths {
  athlete_id: string;
  first_name: string;
  paid_cents: number;
  due_cents: number;
  overdue_cents: number;
  months_paid: number;
  months_due: number;
  months_overdue: number;
}

export type PaymentMethod = "BANK_TRANSFER" | "MBWAY" | "CASH" | "CARD" | "WALLET";

export const PAYMENT_METHOD_ICONS: Record<string, string> = {
  BANK_TRANSFER: "🏦", CASH: "💶", CARD: "💳", WALLET: "🎁",
};

/** Lo stato di una casella del calendario (club/months.py). */
export type MonthState = "PAID" | "WAIVED" | "DUE" | "OVERDUE" | "UPCOMING" | "NOT_BILLED" | "NOT_ENROLLED" | "NONE";

export interface SeasonMonth {
  period: string;
  year: number;
  month: number;
  state: MonthState;
  current: boolean;
  federal_age: number;
  group_name: string | null;
  /** Solo nei mesi futuri: la previsione con il gruppo di quell'anno. */
  expected_cents: number | null;
  fee: Fee | null;
  proof: { id: string; method: string; has_file: boolean; status: string; created_at: string } | null;
  attendances: number;
}

export interface SeasonMonths {
  season: number;
  season_label: string;
  months: SeasonMonth[];
  summary: {
    paid_cents: number;
    due_cents: number;
    overdue_cents: number;
    upcoming_cents: number;
    months_paid: number;
    months_due: number;
    months_overdue: number;
    months_upcoming: number;
    attendances: number;
  };
}

export interface CashReceiver {
  user_id: string;
  name: string;
}

export interface SchoolLetter {
  entry_id: string;
  athlete_name: string;
  body_text: string;
  generated_at: string | null;
}

export interface Competition {
  id: string;
  name: string;
  description: string | null;
  starts_on: string;
  ends_on: string;
  location: string | null;
  organizer: string | null;
  level: "CLUB" | "REGIONAL" | "NATIONAL" | "INTERNATIONAL" | string;
  registration_deadline: string;
  fee_cents: number;
  requires_agonistic_certificate: boolean;
  min_age: number | null;
  max_age: number | null;
  categories: string | null;
  status: "OPEN" | "CLOSED" | "DONE" | string;
  /** Gara (conta per il ranking) o stage. */
  kind: "COMPETITION" | "STAGE" | string;
  transport_needed: boolean;
  transport_entity_name: string | null;
  transport_entity_email: string | null;
  transport_departure: string | null;
  transport_return: string | null;
  transport_companions: number;
  transport_notes: string | null;
  transport_auto_send: boolean;
  /** La foto o la locandina; null = l'icona del tipo (EventIcon). */
  image_url?: string | null;
}

/** La lettera al comune (o all'ente) per il trasporto di un evento. */
export interface TransportRequest {
  id: string;
  competition_id: string;
  to_email: string | null;
  subject: string;
  body_text: string;
  status: "DRAFT" | "SENT" | string;
  athletes_count: number;
  current_athletes_count: number;
  sent_at: string | null;
  last_error: string | null;
}

export interface Pricing {
  tier_discount_pct: Record<string, number>;
  family_discount_cents: number;
  family_min_athletes: number;
  referral_credit_cents: number;
  parent_member_fee_cents: number;
  enrollment_includes: string;
}

export interface Invite {
  code: string;
  path: string;
  invited_count: number;
  earned_cents: number;
  credit_per_month_cents: number;
}

export interface AthleteEligibility {
  athlete_id: string;
  first_name: string;
  eligible: boolean;
  reason: string | null;
  entry_status: string | null;
  category: string | null;
  placement: number | null;
  /** La segreteria ha generato la giustificazione per la scuola. */
  school_letter_ready?: boolean;
}

export interface FamilyCompetition extends Competition {
  registrations_open: boolean;
  athletes: AthleteEligibility[];
}

export interface Entry {
  id: string;
  competition_id: string;
  athlete_id: string;
  athlete_name: string;
  category: string | null;
  weight_kg: string | number | null;
  status: string;
  placement: number | null;
  points: number;
  fee_status: string | null;
  /** Quando è stata generata la giustificazione per la scuola. */
  school_letter_at?: string | null;
}

export interface RankingRow {
  position: number;
  athlete_id: string;
  display_name: string;
  photo_url: string | null;
  sex: string;
  age_band: string;
  belt: string | null;
  is_mine: boolean;
  club_name?: string | null;
  points: number;
  competitions: number;
  gold: number;
  silver: number;
  bronze: number;
}

export interface Ranking {
  season: number;
  season_label: string;
  sex: string | null;
  age_band: string | null;
  rows: RankingRow[];
}

export interface Slot {
  id: string;
  weekday: number;
  starts_at: string;
  ends_at: string;
  room: string | null;
}

export interface Course {
  id: string;
  name: string;
  description: string | null;
  level: string | null;
  min_age: number | null;
  max_age: number | null;
  instructor_user_id: string | null;
  instructor_name: string | null;
  active: boolean;
  slots: Slot[];
  athletes_count: number;
  my_athlete_ids: string[];
  /** Corsi JAV: la scuola, il testo pubblico, la parte del treinador. */
  venue_name: string | null;
  venue_address: string | null;
  venue_city: string | null;
  public_description: string | null;
  public_coach_name: string | null;
  coach_share_pct: string | number | null;
  published: boolean;
}

/** Club ufficiale o unità dei corsi JAV nelle scuole (club/kinds.py). */
export type ClubKind = "CLUB" | "JAV_COURSES";

/** Che cosa c'è in un'unità: nei corsi JAV niente cinture, gare e ranking.
 *  Lo decide il server; qui serve solo a non mostrare ciò che non c'è. */
export function kindFeatures(kind: string | null | undefined) {
  const courses = kind === "JAV_COURSES";
  return { courses, belts: !courses, competitions: !courses, ranking: !courses };
}

export interface CourseFigures {
  course_id: string | null;
  name: string;
  venue_name: string | null;
  venue_city: string | null;
  active: boolean;
  published: boolean;
  coach_user_id: string | null;
  coach_name: string | null;
  coach_share_pct: string | number | null;
  athletes: number;
  attendances: number;
  income_cents: number;
  coach_share_cents: number;
  jav_share_cents: number;
  issued_cents: number;
  pending_cents: number;
  debt_cents: number;
  overdue_cents: number;
}

export interface CoursesReport {
  period: string;
  start: string;
  end: string;
  courses: CourseFigures[];
  totals: CourseFigures;
}

export interface CoachEarnings {
  year: number;
  rows: {
    month: string; course_id: string | null; course_name: string; venue_name: string | null;
    coach_share_pct: string | number; collected_cents: number; earned_cents: number;
    pending_cents: number; pending_earning_cents: number;
  }[];
  earned_year_cents: number;
  pending_cents: number;
}

export interface RosterRow {
  athlete_id: string;
  first_name: string;
  last_name: string;
  photo_url: string | null;
  belt: ClubBelt | null;
  present: boolean | null;
  note: string | null;
}

export interface Roster {
  course_id: string;
  date: string;
  rows: RosterRow[];
}

export interface AdminAthlete extends AthleteCard {
  guardian_user_id: string;
  guardian_email: string | null;
  /** Il nº de sócio del club. */
  member_number?: string | null;
  /** L'encarregado de educação (il titolare del conto). */
  guardian_name?: string | null;
  guardian_phone?: string | null;
  /** Chi ha portato l'atleta nel club: una persona (link «Invita un
   *  amico»), un nome scritto nel modulo; null = il club. */
  invited_by?: { kind: "PERSON" | "WRITTEN"; name: string; user_id?: string | null } | null;
}

export interface AdminCertificate {
  athlete_id: string;
  athlete_name: string;
  guardian_email: string | null;
  certificate: CertificateStatus;
}

export interface ClubStats {
  athletes_active: number;
  overdue_fees: number;
  overdue_cents: number;
  month: string;
  month_issued_cents: number;
  month_paid_cents: number;
}

/** GET through the proxy; a failed call throws the API's own Italian message. */
export async function clubGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api/proxy/club${path}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** JSON or multipart write; `body` FormData is sent as is. */
export async function clubSend<T = unknown>(
  path: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body?: unknown,
): Promise<T> {
  const init: RequestInit = { method };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const res = await fetch(`/api/proxy/club${path}`, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const euro = (cents: number) =>
  (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });

export const shortDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString("it-IT", { day: "numeric", month: "short", year: "numeric" }) : "—";

export function daysUntil(iso: string): number {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / 86_400_000);
}

export const CERTIFICATE_LABELS: Record<string, { label: string; tone: "success" | "warning" | "danger" | "neutral" }> = {
  VALID: { label: "Certificato valido", tone: "success" },
  EXPIRING: { label: "Certificato in scadenza", tone: "warning" },
  EXPIRED: { label: "Certificato scaduto", tone: "danger" },
  MISSING: { label: "Certificato mancante", tone: "danger" },
};

export const CERTIFICATE_TYPES: Record<string, string> = {
  AGONISTIC: "Agonistico",
  NON_AGONISTIC: "Non agonistico",
};

export const LEVEL_LABELS: Record<string, string> = {
  CLUB: "Club",
  REGIONAL: "Regionale",
  ZONAL: "Zonale",
  OPENS: "Open",
  NATIONAL: "Nazionale",
  INTERNATIONAL: "Internazionale",
  EUROPEAN_CUP: "Coppa Europa",
  EUROPEAN_CHAMPIONSHIP: "Campionato europeo",
  WORLD_CHAMPIONSHIP: "Campionato del mondo",
  OLYMPIC_GAMES: "Giochi Olimpici",
};

export const PLACEMENT_LABELS: Record<number, string> = {
  1: "1° posto",
  2: "2° posto",
  3: "3° posto",
  5: "5° posto",
  7: "7° posto",
  0: "Partecipazione",
};

export const FEE_KIND_LABELS: Record<string, string> = {
  MONTHLY: "Mensilità",
  ENROLLMENT: "Iscrizione",
  COMPETITION: "Gara",
  MEMBERSHIP: "Quota socio",
};

/** An emoji per achievement code, so a medal is recognizable before it is read. */
export const ACHIEVEMENT_ICONS: Record<string, string> = {
  FIRST_TRAINING: "🥋",
  ATTENDANCE_10: "⭐",
  ATTENDANCE_50: "🔥",
  ATTENDANCE_100: "💯",
  NEW_BELT: "🎖️",
  FIRST_COMPETITION: "🏟️",
  FIRST_PODIUM: "🏅",
  GOLD_MEDAL: "🥇",
  FIVE_PODIUMS: "🏆",
  BLACK_BELT: "🥷",
};

export function fullName(a: { first_name: string; last_name: string }): string {
  return `${a.first_name} ${a.last_name}`;
}

// --- Persone, lezioni, cartellino, taxa de falta -----------------------------------------------

/** I tipi di una persona nel club, ognuno con il suo simbolo. */
export type PersonKind = "ATHLETE" | "PARENT" | "SECRETARY" | "COACH" | "ASSISTANT_COACH" | "MONITOR" | "ASSISTANT_MONITOR" | "REFEREE";

export const PERSON_KIND_ICONS: Record<PersonKind, string> = {
  ATHLETE: "🥋",
  PARENT: "👪",
  SECRETARY: "🗂️",
  COACH: "🧑‍🏫",
  ASSISTANT_COACH: "🤝",
  MONITOR: "🎽",
  ASSISTANT_MONITOR: "🎗️",
  REFEREE: "🧑‍⚖️",
};

export interface Person {
  kind: "ATHLETE" | "USER";
  id: string;
  user_id: string | null;
  name: string;
  kinds: PersonKind[];
  status: string;
  photo_url: string | null;
  belt: string | null;
  age: number | null;
  email: string | null;
  guardian_name: string | null;
  due_cents: number;
  children: { id: string; name: string }[] | null;
  social_tier: string | null;
  adapted_judo: boolean;
}

export interface PersonCard {
  debts: Fee[];
  payments: Fee[];
  proofs: { id: string; created_at: string; amount_cents: number; credit_cents: number; status: string; has_file: boolean }[];
  results: { competition_id: string; name: string; starts_on: string; kind: string; level: string; athlete_name: string; placement: number | null; status: string; points: number }[];
  belts: { athlete_name: string; belt: string }[];
  investments: { id: string; created_at: string; amount_cents: number; note: string | null; athlete_name: string | null }[];
  totals: { debt_cents: number; paid_cents: number; invested_cents: number };
}

export interface Lesson {
  course_id: string;
  course_name: string;
  slot_id: string;
  date: string;
  starts_at: string;
  ends_at: string;
  room: string | null;
  enrolled: number;
  present: number;
  current: boolean;
}

export interface WorkSession {
  id: string;
  user_id: string;
  started_at: string;
  ended_at: string | null;
  note: string | null;
  minutes: number;
}

export interface Clock {
  open_session: WorkSession | null;
  today_minutes: number;
  month_minutes: number;
  sessions: WorkSession[];
}

export interface StaffHours {
  user_id: string;
  name: string;
  minutes: number;
  sessions: WorkSession[];
}

export interface FamilyLesson {
  athlete_id: string;
  athlete_name: string;
  course_id: string;
  course_name: string;
  starts_at: string;
  ends_at: string;
  present: boolean | null;
  note: string | null;
}

export interface DayAttendance {
  athlete_id: string;
  athlete_name: string;
  course_id: string;
  course_name: string;
  present: boolean;
  note: string | null;
  recorded_by_kind: "STAFF" | "FAMILY" | string;
}

export interface AbsenceRow {
  fee: Fee;
  athlete_name: string;
  lessons_held: number;
  presences: number;
  suggestion: "HALF" | "FULL" | null;
  applied: "HALF" | "FULL" | null;
}

export interface PlatformOverview {
  month: string;
  clubs: { id: string; name: string; slug: string; status: string; kind?: string; athletes_active: number; overdue_cents: number; month_paid_cents: number; month_issued_cents: number }[];
  totals: { clubs_active: number; athletes_active: number; overdue_cents: number; month_paid_cents: number; month_issued_cents: number };
  upcoming_events: { id: string; club_id: string; club_name: string; name: string; kind: string; starts_on: string; location: string | null; status: string }[];
}

/** "2 h 15 min" da minuti. */
export function hoursLabel(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h} h${m ? ` ${m} min` : ""}` : `${m} min`;
}
