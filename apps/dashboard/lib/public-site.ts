import "server-only";

// Il sito pubblico JudoArteVida (docs/club-portal.md, "Sito pubblico"). Le
// pagine sono server component: leggono l'API direttamente, senza sessione
// e senza passare dal proxy BFF, perché qui non c'è niente di personale da
// proteggere -- tutto ciò che l'API /public-site restituisce è già pubblico.
// I tipi rispecchiano apps/api/app/domains/club/site_schemas.py.

import type { BrandTheme } from "@/lib/brand";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Niente cache dei dati: si legge sempre l'API. Con la cache di Next
 *  (revalidate) una risposta 404 non sostituisce quella vecchia, e un club
 *  tolto, una pagina messa offline o -- peggio -- un judoca a cui la famiglia
 *  ha ritirato il consenso restavano visibili. La privacy viene prima della
 *  velocità; le query del portale sono poche e leggere. */

export interface ClubRef {
  name: string;
  slug: string;
  logo_url: string | null;
}

export interface ClubCard extends ClubRef {
  city: string | null;
  tagline: string | null;
  hero_image_url: string | null;
  athletes_active: number;
  judoka_public: number;
}

export interface Judoka {
  id: string;
  display_name: string;
  photo_url: string | null;
  /** false: in classifica senza consenso alla pagina pubblica (niente scheda). */
  has_page?: boolean;
  belt: string | null;
  age_band: string;
  club: ClubRef;
  points: number;
  competitions: number;
  gold: number;
  silver: number;
  bronze: number;
}

export interface RankingRow extends Judoka {
  position: number;
}

export interface PublicEvent {
  id: string;
  name: string;
  kind: "COMPETITION" | "STAGE" | string;
  level: string;
  status: string;
  starts_on: string;
  ends_on: string;
  registration_deadline: string;
  location: string | null;
  organizer: string | null;
  /** null per un evento della rete (il calendário comune dei club). */
  club: ClubRef | null;
  /** Le fasce federali ammesse; vuoto = tutte. */
  age_groups?: string[];
  transport_mode?: string;
  /** Quanto costa iscriversi (dell'organizzatore). */
  price_cents: number;
  starts_at_time?: string | null;
  registration_deadline_time?: string | null;
  places?: number | null;
  circular_url?: string | null;
  /** Quanti atleti iscritti (solo il numero). */
  entries_count: number;
}

export interface Medal {
  athlete_id: string;
  display_name: string;
  photo_url: string | null;
  belt: string | null;
  placement: number;
  category: string | null;
  event_id: string;
  event_name: string;
  event_level: string;
  date: string;
  club: ClubRef;
}

export interface PortalHome {
  season: number;
  season_label: string;
  clubs: ClubCard[];
  totals: { clubs: number; athletes_active: number; judoka_public: number };
  upcoming_events: PublicEvent[];
  top_ranking: RankingRow[];
  latest_medals: Medal[];
}

export interface GalleryItem {
  url: string;
  caption: string | null;
}

export interface Coach {
  name: string;
  role: string | null;
  photo_url: string | null;
  grade?: string | null;
  bio?: string | null;
}

export interface Highlight { value: string; label: string }
export interface HistoryStep { year: number; title: string; text: string | null }
export interface Pillar { title: string; text: string | null }
export interface NewsPost { date: string; title: string; text: string | null; image_url: string | null; link_url: string | null }
export interface ClubVideo { youtube_id: string; caption: string | null }

export interface ScheduleDay {
  weekday: number;
  slots: {
    course: string;
    level: string | null;
    min_age: number | null;
    max_age: number | null;
    starts_at: string;
    ends_at: string;
    room: string | null;
  }[];
}

export interface SiteContent {
  tagline: string | null;
  about: string | null;
  city: string | null;
  hero_image_url: string | null;
  logo_url: string | null;
  gallery: GalleryItem[];
  coaches: Coach[];
  contact_phone: string | null;
  contact_email: string | null;
  address: string | null;
  map_url: string | null;
  instagram_url: string | null;
  facebook_url: string | null;
  youtube_url: string | null;
  website_url: string | null;
  brand_primary: string | null;
  brand_secondary: string | null;
  brand_accent: string | null;
  founded_year: number | null;
  venue: string | null;
  highlights: Highlight[];
  history: HistoryStep[];
  pillars: Pillar[];
  news: NewsPost[];
  videos: ClubVideo[];
}

/** Un gruppo del club (un piano attivo), come lo dice anche JAVBOT: età e
 *  allenamenti sempre; i prezzi solo se il club li mostra (altrimenti null). */
export interface ClubGroup {
  name: string;
  min_age: number | null;
  max_age: number | null;
  slots: { weekday: number; starts_at: string; ends_at: string; course: string }[];
  monthly_price_cents: number | null;
  enrollment_price_cents: number | null;
  due_day: number | null;
  billing_months: number[] | null;
  description: string | null;
}

export interface ClubPage extends SiteContent {
  name: string;
  slug: string;
  /** I colori del club con il contrasto già controllato (club/brand.py). */
  theme: BrandTheme;
  updated_at: string;
  season_label: string;
  athletes_active: number;
  schedule: ScheduleDay[];
  show_prices: boolean;
  groups: ClubGroup[];
  upcoming_events: PublicEvent[];
  judoka: Judoka[];
  /** I primi dieci del club nel ranking della stagione. */
  ranking: RankingRow[];
  recent_medals: Medal[];
}

export interface JudokaProfile extends Judoka {
  bio: string | null;
  season_label: string;
  season_points: number;
  results: {
    event_id: string;
    event_name: string;
    level: string;
    date: string;
    location: string | null;
    placement: number;
    category: string | null;
    points: number;
  }[];
  /** La scheda in stile IJF: la categoria scritta sulle iscrizioni (mai il
   *  peso vero), il posto nel ranking della fascia, il percorso delle
   *  cinture, le prove in programma e i media pubblicati dal club. */
  category: string | null;
  ranking: { position: number; total: number; age_band: string; points: number } | null;
  belt_history: { grade: string; awarded_on: string }[];
  upcoming: (PublicEvent & { category: string | null })[];
  photos: { id: string; url: string; caption: string | null }[];
  videos: { id: string; youtube_id: string; caption: string | null }[];
  ijf_profile_url: string | null;
  favorite_technique: string | null;
  dominant_side: "LEFT" | "RIGHT" | null;
}

export interface EventDetail extends PublicEvent {
  description: string | null;
  categories: string | null;
  participants_count: number;
  participants: {
    athlete_id: string;
    display_name: string;
    photo_url: string | null;
    belt: string | null;
    age_band: string;
    category: string | null;
    placement: number | null;
    points: number;
  }[];
}

export interface PublicRanking {
  season: number;
  season_label: string;
  /** "year" (l'anno solare: il ranking che conta), "month" o "all". */
  period: RankingPeriod;
  month: number | null;
  clubs: ClubRef[];
  rows: RankingRow[];
}

export type RankingPeriod = "year" | "month" | "all";

/** La Taça dos Clubes: i club per punti dei loro atleti. */
export interface ClubRankingRow {
  position: number;
  club: ClubRef;
  city: string | null;
  points: number;
  results: number;
  gold: number;
  silver: number;
  bronze: number;
  athletes: number;
  events: number;
}

export interface ClubRanking {
  season: number;
  season_label: string;
  period: RankingPeriod;
  month: number | null;
  /** L'anno è chiuso: il primo ha vinto la coppa. */
  is_final: boolean;
  rows: ClubRankingRow[];
  winners: { year: number; club: ClubRef; points: number }[];
}

/** Il popup di un judoca della classifica: la scheda completa se la famiglia
 *  ha dato il consenso, altrimenti solo ciò che dice una classifica. */
export interface RankingCard {
  has_page: boolean;
  profile: JudokaProfile | null;
  card: (Judoka & {
    season_label: string;
    season_points: number;
    ranking: { position: number; total: number; age_band: string; points: number } | null;
    results: { event_id: string; event_name: string; level: string; date: string; location: string | null; placement: number; points: number }[];
  }) | null;
}

export interface Sponsor {
  id: string;
  name: string;
  slug: string;
  tagline: string | null;
  description: string | null;
  logo_url: string | null;
  website_url: string | null;
  color: string | null;
}

/** Lo Shop JAV sul sito (jav_market/public_router.py): prezzi IVA compresa. */
export interface PublicShopProduct {
  id: string;
  name: string;
  description: string;
  image_url: string | null;
  price_cents: number;
  max_price_cents: number;
  in_stock: boolean;
  category_ids: string[];
}

export interface PublicShop {
  items: PublicShopProduct[];
  total: number;
  shop_total: number;
  offset: number;
  next_offset: number | null;
  categories: { id: string; name: string; count: number }[];
}

/** null quando l'API dice 404 (club non pubblicato, judoca senza consenso):
 *  la pagina chiama notFound(). Qualunque altro errore sale fino a
 *  app/error.tsx, che sa come dirlo a chi legge. */
async function get<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API_INTERNAL_URL}/api/public-site${path}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`public-site ${path}: ${res.status}`);
  return (await res.json()) as T;
}

function query(params: Record<string, string | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** "Cursos JAV nas escolas": luogo, orario, età. Nessuna persona. */
export interface PublicCourse {
  id: string;
  name: string;
  level: string | null;
  min_age: number | null;
  max_age: number | null;
  venue_name: string | null;
  venue_address: string | null;
  venue_city: string | null;
  description: string | null;
  coach_name: string | null;
  slots: { weekday: number; starts_at: string; ends_at: string }[];
  signup_path: string;
}

export interface PublicCourses {
  unit: {
    name: string; slug: string; tagline: string | null; about: string | null; hero_image_url: string | null;
    contact_phone: string | null; contact_email: string | null;
  } | null;
  courses: PublicCourse[];
}

export interface ChannelVideo {
  id: string;
  title: string;
  published: string | null;
  views: number | null;
  thumbnail: string;
  url: string;
}

/** Il video dietro l'header del portale: lo stesso che usava judoartevida.com.
 *  Non l'ultimo del canale, perché un video qualsiasi (una riunione, un
 *  messaggio) non è uno sfondo. */
export const HERO_VIDEO_ID = "RIZHYD0y1mw";

export const publicSite = {
  home: () => get<PortalHome>("/home"),
  videos: () => get<ChannelVideo[]>("/videos"),
  clubs: () => get<ClubCard[]>("/clubs"),
  courses: () => get<PublicCourses>("/courses"),
  club: (slug: string) => get<ClubPage>(`/clubs/${encodeURIComponent(slug)}`),
  clubVideos: (slug: string) => get<ChannelVideo[]>(`/clubs/${encodeURIComponent(slug)}/videos`),
  judoka: (id: string) => get<JudokaProfile>(`/judoka/${encodeURIComponent(id)}`),
  events: (filters: { club?: string; kind?: string; when?: string; from?: string; to?: string; limit?: string }) =>
    get<PublicEvent[]>(`/events${query(filters)}`),
  /** Le foto già pubblicate dai club, per le testate. */
  photos: () => get<{ url: string; club: string }[]>("/photos"),
  event: (id: string) => get<EventDetail>(`/events/${encodeURIComponent(id)}`),
  ranking: (filters: { age_band?: string; club?: string; season?: string; period?: RankingPeriod; month?: string }) =>
    get<PublicRanking>(`/ranking${query(filters)}`),
  clubRanking: (filters: { season?: string; period?: RankingPeriod; month?: string }) =>
    get<ClubRanking>(`/ranking/clubs${query(filters)}`),
  sponsors: () => get<Sponsor[]>("/sponsors"),
  shop: (filters: { q?: string; category_id?: string; offset?: string; limit?: string }) => get<PublicShop>(`/shop${query(filters)}`),
  sponsor: (slug: string) => get<Sponsor>(`/sponsors/${encodeURIComponent(slug)}`),
};

/** Un id che non è un UUID non arriva nemmeno all'API (che risponderebbe 422). */
export function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
