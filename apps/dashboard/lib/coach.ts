// I tipi e le chiamate dell'area del treinador oltre a lib/club.ts
// (apps/api/app/domains/club/coach_router.py): Início, quaderno, i miei
// atleti, i propri turni.

import type { ClubBelt, Lesson } from "@/lib/club";

export const COACH = (path: string) => `/staff/coach${path}`;

export interface HomeEvent {
  id: string; name: string; kind: string; level: string; status: string; starts_on: string; ends_on: string;
  location: string | null; image_url: string | null; registration_deadline: string; club_name: string | null; network: boolean;
}

export interface AthleteBrief {
  id: string; first_name: string; last_name: string; photo_url: string | null; belt: ClubBelt | null;
  last_present: string | null; certificate_status: CertificateStatus; certificate_expires_on: string | null;
}

export type CertificateStatus = "VALID" | "EXPIRING" | "EXPIRED" | "MISSING";

export interface CoachHome {
  today: string;
  lessons_today: Lesson[];
  missing_registers: Lesson[];
  missing_count: number;
  events: HomeEvent[];
  unread_club: number;
  unread_jav: number;
  athletes: number;
  courses: number;
  absent: AthleteBrief[];
  absent_count: number;
  certificates: AthleteBrief[];
  certificates_count: number;
  recent_notes: LessonNote[];
}

export interface LessonNote {
  id: string; course_id: string; course_name: string; lesson_date: string; title: string | null;
  techniques: string[]; body: string | null; author_user_id: string; author_name: string; mine: boolean;
  created_at: string; updated_at: string | null;
}

export interface LessonNotesPage {
  items: LessonNote[];
  total: number;
  techniques: { name: string; count: number; last_date: string }[];
}

export const NOTE_CATEGORIES = ["TECHNIQUE", "BEHAVIOUR", "HEALTH", "GOAL", "COMPETITION", "OTHER"] as const;
export type NoteCategory = (typeof NOTE_CATEGORIES)[number];
export const NOTE_ICONS: Record<NoteCategory, string> = {
  TECHNIQUE: "🥋", BEHAVIOUR: "🧠", HEALTH: "🩹", GOAL: "🎯", COMPETITION: "🏆", OTHER: "📝",
};

export interface AthleteNote {
  id: string; athlete_id: string; category: NoteCategory; body: string; author_user_id: string; author_name: string;
  mine: boolean; created_at: string; updated_at: string | null;
}

export interface MyAthlete {
  id: string; first_name: string; last_name: string; photo_url: string | null; sex: "M" | "F"; birth_date: string;
  belt: ClubBelt | null; courses: string[]; course_ids: string[]; attended_30d: number; last_present: string | null;
  certificate_status: CertificateStatus; certificate_expires_on: string | null; notes: number; last_note_at: string | null;
}

export interface AthleteSheet {
  id: string; first_name: string; last_name: string; photo_url: string | null; sex: "M" | "F"; birth_date: string;
  weight_kg: number | null; adapted_judo: boolean; belt: ClubBelt | null; courses: { id: string; name: string }[];
  certificate_status: CertificateStatus; certificate_expires_on: string | null;
  attendance: { date: string; course_id: string; course_name: string; present: boolean; note: string | null }[];
  present_90d: number;
  notes: AthleteNote[];
}

export interface SessionChange {
  id: string; session_id: string; action: "edited" | "added" | "deleted" | "corrected"; at: string;
  actor_name: string; user_id: string | null; user_name: string;
  before: { started_at: string | null; ended_at: string | null; note: string | null } | null;
  after: { started_at: string | null; ended_at: string | null; note: string | null } | null;
}

/** Il valore di un <input type="datetime-local"> per un istante ISO, nell'ora del telefono. */
export function toLocalInput(isoValue: string | null | undefined): string {
  if (!isoValue) return "";
  const d = new Date(isoValue);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** L'istante ISO (UTC) di un valore di <input type="datetime-local">. */
export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function isoDay(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function initials(first: string, last: string): string {
  return `${first.slice(0, 1)}${last.slice(0, 1)}`.toUpperCase();
}
