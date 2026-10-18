// Il curriculum del treinador (apps/api/app/domains/club/coach_cv.py,
// coach_cv_router.py): l'archivio dei diplomi, il CV che scrive lui, il
// Curriculum Desportivo ricostruito dallo storico, i PDF e le versioni
// salvate. È suo, non del club: le chiamate valgono in qualunque club stia
// lavorando, e le chiavi delle query stanno fuori dal prefisso ["club"].

import { friendlyApiError } from "@/lib/api-error";

export const CV = (path = "") => `/staff/cv${path}`;
export const CV_KEY = ["coach-cv"] as const;

export type DocumentStatus = "VALID" | "EXPIRING" | "EXPIRED";

export const DOCUMENT_CATEGORIES = [
  "COACH_DIPLOMA", "FEDERATION", "COURSE", "FIRST_AID", "ACADEMIC", "PROFESSIONAL", "PERSONAL", "OTHER",
] as const;
export type DocumentCategory = (typeof DOCUMENT_CATEGORIES)[number];

export const CATEGORY_ICONS: Record<string, string> = {
  COACH_DIPLOMA: "🥋", FEDERATION: "🏛️", COURSE: "🎓", FIRST_AID: "⛑️", ACADEMIC: "📚",
  PROFESSIONAL: "💼", PERSONAL: "🪪", OTHER: "📄",
};

export interface CvDocument {
  id: string;
  title: string;
  category: DocumentCategory | string;
  category_label: string;
  issuer: string | null;
  issued_on: string | null;
  expires_on: string | null;
  description: string | null;
  has_file: boolean;
  original_filename: string | null;
  content_type: string | null;
  size_bytes: number | null;
  show_in_cv: boolean;
  /** Senza scadenza è sempre VALID; EXPIRING = meno di 60 giorni. */
  status: DocumentStatus;
  created_at: string;
  updated_at: string | null;
}

export interface CvMe {
  user_id: string;
  name: string;
  first_name: string | null;
  photo_url: string | null;
  email: string;
}

export interface CvClub {
  club_id: string;
  name: string;
  active: boolean;
  since: string | null;
  last_activity: string | null;
  courses: string[];
}

export interface CvBelt {
  code: string;
  label: string;
  dan: number | null;
}

export interface CvExperience {
  role: string;
  organization?: string | null;
  city?: string | null;
  /** "AAAA" o "AAAA-MM". */
  start?: string | null;
  end?: string | null;
  current: boolean;
  description?: string | null;
}

export interface CvEducation {
  title: string;
  institution?: string | null;
  start?: string | null;
  end?: string | null;
  description?: string | null;
}

export interface CvShow {
  photo: boolean;
  birth_date: boolean;
  phone: boolean;
  email: boolean;
  clubs: boolean;
}

/** Quello che scrive il treinador (coach_profiles.data, CvWrite dell'API). */
export interface CvData {
  headline?: string | null;
  summary?: string | null;
  birth_date?: string | null;
  nationality?: string | null;
  phone?: string | null;
  email?: string | null;
  city?: string | null;
  links: { label?: string | null; url: string }[];
  experiences: CvExperience[];
  education: CvEducation[];
  skills: { technical: string[]; pedagogical: string[]; organizational: string[] };
  languages: { name: string; level?: string | null }[];
  specializations: string[];
  custom_sections: { title: string; body: string }[];
  show: CvShow;
}

export interface CvResponse {
  me: CvMe;
  /** {} per chi non ha ancora scritto niente. */
  data: Partial<CvData>;
  updated_at: string | null;
  clubs: CvClub[];
  belt: CvBelt | null;
  documents: CvDocument[];
}

export const EVENT_TYPES = ["COMPETITION", "STAGE", "SEMINAR", "COURSE", "GRADING", "REFEREEING", "OTHER"] as const;
export const EVENT_ROLES = ["ATHLETE", "COACH", "ASSISTANT_COACH", "REFEREE", "ORGANIZER", "OTHER"] as const;
export const EVENT_LEVELS = [
  "CLUB", "REGIONAL", "ZONAL", "OPENS", "NATIONAL", "INTERNATIONAL", "EUROPEAN_CUP", "EUROPEAN_CHAMPIONSHIP",
  "WORLD_CHAMPIONSHIP", "OLYMPIC_GAMES",
] as const;
export const PLACEMENTS = [1, 2, 3, 5, 7, 0] as const;

export type Medal = "GOLD" | "SILVER" | "BRONZE";

export interface SportItem {
  id: string;
  source: "OFFICIAL" | "MANUAL";
  kind: string;
  kind_label: string;
  role: string;
  role_label: string;
  date: string;
  end_date: string | null;
  title: string;
  location: string | null;
  /** Il club (ufficiale) o l'organizzazione scritta a mano. */
  club: string | null;
  level: string | null;
  level_label: string | null;
  category: string | null;
  placement: number | null;
  placement_label: string | null;
  medal: Medal | null;
  result: string | null;
  description: string | null;
  document_id: string | null;
}

export interface SportGrade {
  /** La cintura (OFFICIAL) o l'evento GRADING dichiarato (MANUAL). */
  id: string;
  grade: string | null;
  label: string;
  date: string;
  club: string | null;
  source: "OFFICIAL" | "MANUAL";
}

export interface SportHistory {
  me: CvMe;
  belt: CvBelt | null;
  is_athlete: boolean;
  athlete: { competitions: number; medals: Record<Medal, number>; items: SportItem[] };
  coach: { clubs: CvClub[]; items: SportItem[] };
  grades: SportGrade[];
  items: SportItem[];
}

export interface EventWrite {
  title: string;
  event_type: string;
  role: string;
  starts_on: string;
  ends_on: string | null;
  location: string | null;
  organization_name: string | null;
  level: string | null;
  category: string | null;
  placement: number | null;
  result: string | null;
  description: string | null;
  document_id: string | null;
}

export type PdfKind = "CV" | "SPORT";

export interface CvExport {
  id: string;
  kind: PdfKind;
  filename: string;
  size_bytes: number;
  note: string | null;
  created_at: string;
}

export const MAX_FILE_BYTES = 15 * 1024 * 1024;

/** Il CV vuoto: ogni elenco c'è sempre, così il modulo non deve chiedersi
 *  se un campo esiste. Per chi apre il CV la prima volta, tutto acceso. */
export function cvDefaults(data: Partial<CvData>): CvData {
  return {
    headline: data.headline ?? "",
    summary: data.summary ?? "",
    birth_date: data.birth_date ?? "",
    nationality: data.nationality ?? "",
    phone: data.phone ?? "",
    email: data.email ?? "",
    city: data.city ?? "",
    links: data.links ?? [],
    experiences: data.experiences ?? [],
    education: data.education ?? [],
    skills: {
      technical: data.skills?.technical ?? [],
      pedagogical: data.skills?.pedagogical ?? [],
      organizational: data.skills?.organizational ?? [],
    },
    languages: data.languages ?? [],
    specializations: data.specializations ?? [],
    custom_sections: data.custom_sections ?? [],
    show: { photo: true, birth_date: true, phone: true, email: true, clubs: true, ...data.show },
  };
}

const blank = (v: string | null | undefined) => (v ?? "").trim() || null;

/** Il corpo del PUT: testi ripuliti, righe vuote tolte (una riga aggiunta e
 *  lasciata vuota non deve far fallire il salvataggio con un 422). */
export function cvPayload(d: CvData): CvData {
  return {
    headline: blank(d.headline), summary: blank(d.summary), birth_date: blank(d.birth_date),
    nationality: blank(d.nationality), phone: blank(d.phone), email: blank(d.email), city: blank(d.city),
    links: d.links.filter((l) => l.url.trim()).map((l) => ({ label: blank(l.label), url: l.url.trim() })),
    experiences: d.experiences.filter((e) => e.role.trim()).map((e) => ({
      role: e.role.trim(), organization: blank(e.organization), city: blank(e.city), start: blank(e.start),
      end: e.current ? null : blank(e.end), current: e.current, description: blank(e.description),
    })),
    education: d.education.filter((e) => e.title.trim()).map((e) => ({
      title: e.title.trim(), institution: blank(e.institution), start: blank(e.start), end: blank(e.end),
      description: blank(e.description),
    })),
    skills: d.skills,
    languages: d.languages.filter((l) => l.name.trim()).map((l) => ({ name: l.name.trim(), level: blank(l.level) })),
    specializations: d.specializations,
    custom_sections: d.custom_sections.filter((s) => s.title.trim() && s.body.trim())
      .map((s) => ({ title: s.title.trim(), body: s.body.trim() })),
    show: d.show,
  };
}

/** Il nome del file che decide il server (Content-Disposition). */
function filenameOf(res: Response, fallback: string): string {
  const disposition = res.headers.get("content-disposition") ?? "";
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  const plain = /filename="([^"]+)"/i.exec(disposition);
  return (utf8?.[1] && decodeURIComponent(utf8[1])) || plain?.[1] || fallback;
}

/** Il PDF di adesso (non salvato), in memoria: l'anteprima lo mostra da un
 *  blob: perché il server manda X-Frame-Options DENY a ogni risposta. */
export async function fetchCvPdf(kind: PdfKind): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(`/api/proxy/club${CV(`/pdf?kind=${kind}`)}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  const blob = await res.blob();
  return { blob: new Blob([blob], { type: "application/pdf" }), filename: filenameOf(res, kind === "CV" ? "curriculo.pdf" : "curriculo-desportivo.pdf") };
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Subito revocato il download si interrompe su alcuni browser.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Apre un URL presigned di pochi minuti in una scheda nuova. La finestra si
 *  apre subito, nel clic: dopo un'attesa i browser la bloccano. */
export async function openPresigned(path: string) {
  const win = window.open("", "_blank");
  try {
    const res = await fetch(`/api/proxy/club${path}`);
    if (!res.ok) throw new Error(await friendlyApiError(res));
    const { url } = (await res.json()) as { url: string };
    if (win) win.location.replace(url);
    else window.location.assign(url);
  } catch (e) {
    win?.close();
    throw e;
  }
}

/** Oggi in ISO (giorno locale): le date nel futuro l'API le rifiuta. */
export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function formatBytes(n: number | null | undefined): string {
  if (!n) return "";
  return n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
}
