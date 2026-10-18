import { friendlyApiError } from "@/lib/api-error";

// I corsi esterni (apps/api/app/domains/extcourses): judo nelle scuole,
// un sistema separato dai club. Niente atleti, cinture, gare, Shop, wallet:
// partecipanti, mensilità, prove, presenze, turni del treinador, avvisi.
// I tipi rispecchiano extcourses/service.py (course_dict, fee_dict, ...).

export interface ExtGroup {
  id: string;
  name: string;
  min_age: number | null;
  max_age: number | null;
  /** 0 = lunedì, come Python. */
  weekday: number;
  starts_at: string;
  ends_at: string;
  active: boolean;
}

export interface ExtCourse {
  id: string;
  name: string;
  school_name: string;
  school_address: string | null;
  school_city: string | null;
  school_logo_url: string | null;
  description: string | null;
  monthly_fee_cents: number;
  billing_months: number[];
  due_day: number;
  starts_on: string;
  ends_on: string;
  active: boolean;
  published: boolean;
  public_coach_name: string | null;
  groups: ExtGroup[];
}

export interface ExtFee {
  id: string;
  participant_id: string;
  participant_name: string | null;
  period: string;
  amount_cents: number;
  due_date: string;
  status: "DUE" | "PAID" | "WAIVED";
  overdue: boolean;
  paid_at: string | null;
  method: string | null;
}

export interface ExtNotice {
  id: string;
  title: string;
  body: string | null;
  created_at: string;
  course_id?: string;
}

export interface ExtFamily {
  children: {
    id: string; first_name: string; last_name: string; birth_date: string; age: number; course_id: string;
    group: ExtGroup | null; present_this_month: number; lessons_this_month: number;
  }[];
  courses: ExtCourse[];
  due_fees: ExtFee[];
  due_cents: number;
  overdue_cents: number;
  paid_fees: ExtFee[];
  proofs: { id: string; amount_cents: number; method: string; status: "ACCEPTED" | "REJECTED"; created_at: string; rejection_reason: string | null }[];
  notices: ExtNotice[];
  payment_info: { iban: string | null; holder: string | null; instructions: string | null } | null;
}

export type ExtRole = "COACH" | "SCHOOL" | "ADMIN";

export interface ExtStaffCourse extends ExtCourse {
  roles: ExtRole[];
  participants: number;
}

export interface ExtParticipant {
  id: string;
  first_name: string;
  last_name: string;
  age: number;
  group_id: string | null;
  status: string;
  notes: string | null;
  joined_on: string;
  present_this_month: number;
  // Solo per la scuola e il superadmin.
  guardian_name?: string | null;
  guardian_phone?: string | null;
  guardian_email?: string | null;
  due_cents?: number;
  overdue?: boolean;
  fees?: ExtFee[];
}

export interface ExtStaffProof {
  id: string;
  amount_cents: number;
  method: string;
  status: "ACCEPTED" | "REJECTED";
  has_file: boolean;
  created_at: string;
  note: string | null;
  parent_name: string | null;
}

export interface ExtRoster {
  course: ExtCourse;
  roles: ExtRole[];
  participants: ExtParticipant[];
  proofs?: ExtStaffProof[];
  notices: ExtNotice[];
}

export interface ExtAttendanceRow { id: string; first_name: string; last_name: string; present: boolean | null }

export interface ExtAttendanceDay {
  date: string;
  groups: (ExtGroup & { participants: ExtAttendanceRow[] })[];
  no_group: ExtAttendanceRow[];
}

export interface ExtClock {
  open: { course_id: string; started_at: string } | null;
  sessions: { course_id: string; started_at: string; ended_at: string | null; minutes: number | null }[];
}

export interface ExtMoney { income_cents: number; coach_cents: number; jav_cents: number }

export interface ExtAccounts {
  year: number;
  months: (ExtMoney & { period: string })[];
  courses: (ExtMoney & { course_id: string; name: string; school_name: string; due_cents: number })[];
  total: ExtMoney;
  due_cents: number;
}

export interface ExtStaffMember {
  id: string;
  user_id: string;
  role: "COACH" | "SCHOOL";
  share_pct: string | number | null;
  name: string | null;
  email: string | null;
}

export interface ExtAdminCourse extends ExtCourse {
  participants: number;
  due_cents: number;
  staff: ExtStaffMember[];
}

export interface ExtChildInput {
  first_name: string;
  last_name: string;
  birth_date: string;
  notes: string;
}

/** Le rotte /ext/... passano dal proxy BFF come tutte le altre. */
export async function extGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api/proxy/ext${path}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** JSON o multipart (FormData così com'è). */
export async function extSend<T = unknown>(path: string, method: "POST" | "PATCH" | "DELETE", body?: unknown): Promise<T> {
  const init: RequestInit = { method };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const res = await fetch(`/api/proxy/ext${path}`, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  if (res.status === 204) return undefined as T;
  return res.json();
}

/** I corsi in cui lavoro (scuola, treinador; il superadmin tutti). Chiave
 *  comune: la usano l'area Escola, il menu delle aree e la scelta del club
 *  del treinador. */
export const STAFF_COURSES_KEY = ["ext", "staff", "courses"] as const;
export const fetchStaffCourses = () => extGet<ExtStaffCourse[]>("/staff/courses");

/** L'età che il bambino avrà il giorno `on` (anni compiuti). */
export function ageOn(birth: string, on: Date): number | null {
  const [y, m, d] = birth.split("-").map(Number);
  if (!y || !m || !d) return null;
  const before = on.getMonth() + 1 < m || (on.getMonth() + 1 === m && on.getDate() < d);
  return on.getFullYear() - y - (before ? 1 : 0);
}

/** Il gruppo in cui il bambino *dovrebbe* finire, solo da mostrare: lo
 *  decide il server (service.pick_group), con la stessa regola — il primo
 *  gruppo che comprende l'età, all'inizio del corso se non è ancora cominciato. */
export function guessGroup(course: ExtCourse, birth: string): ExtGroup | null {
  const today = new Date();
  const start = new Date(`${course.starts_on}T00:00:00`);
  const age = ageOn(birth, start > today ? start : today);
  if (age == null) return null;
  return course.groups.find((g) => g.active && (g.min_age == null || age >= g.min_age) && (g.max_age == null || age <= g.max_age)) ?? null;
}

/** "YYYY-MM-DD" del giorno locale, non UTC: alle 00:30 di Lisbona è già oggi. */
export function isoDay(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Lunedì = 0, come l'API (Date.getDay ha la domenica a 0). */
export const apiWeekday = (d: Date) => (d.getDay() + 6) % 7;

export const EXT_PAY_METHODS = ["BANK_TRANSFER", "MBWAY", "CASH", "POS"] as const;
