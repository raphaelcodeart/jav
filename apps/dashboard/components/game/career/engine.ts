// Motore di "Judo Career": puro, senza React, deterministico dato il seme.
// Tutto è finto: atleti, gare e club non hanno nulla a che fare con il
// gestionale vero. Ogni funzione riceve uno stato e ne restituisce uno nuovo.

export const CAREER_VERSION = 1 as const;

export const BELTS = ["WHITE", "YELLOW", "ORANGE", "GREEN", "BLUE", "BROWN", "BLACK"] as const;
export type Belt = (typeof BELTS)[number];

export const CITIES = ["Lagos", "Albufeira", "Portimão", "Faro", "Lisboa", "Porto"] as const;
export type City = (typeof CITIES)[number];

export const TECHNIQUES = [
  "O-soto-gari", "O-goshi", "Seoi-nage", "O-uchi-gari", "Ko-uchi-gari", "Uchi-mata",
  "Harai-goshi", "Tai-otoshi", "De-ashi-barai", "Kesa-gatame", "Tomoe-nage", "Sumi-gaeshi",
] as const;

export const HERO_COLORS = ["red", "blue", "green", "purple", "orange", "teal"] as const;
export type HeroColor = (typeof HERO_COLORS)[number];
export const AVATARS = ["🥋", "🦁", "🐯", "🦊", "🐼", "🐉", "🦅", "⚡"] as const;

// Il calendario di gioco è compresso: 2 settimane al mese, 12 mesi all'anno
// (la stagione parte a settembre), così la carriera non dura migliaia di clic.
export const WEEKS_PER_MONTH = 2;
export const WEEKS_PER_YEAR = 24;
export const BLACK_BELT_MIN_AGE = 15;
export const COACH_MIN_AGE = 16;
const MAX_MEDALS = 160;
export const START_AGE = 10;
export const MAX_ACTIONS = 2;
export const WEEK_XP_CAP = 1400;

export type Phase = "ATHLETE" | "COACH" | "CLUB_OWNER";
export type ActionId =
  | "TRAIN_TECH" | "TRAIN_PHYS" | "REST" | "STUDY" | "COMPETE"
  | "REFEREE" | "REF_COURSE" | "COACH_COURSE" | "TEACH";

/** Energia spesa (positivo) o recuperata (negativo) da ogni azione. */
export const ACTION_ENERGY: Record<ActionId, number> = {
  TRAIN_TECH: 25, TRAIN_PHYS: 30, REST: -35, STUDY: 10, COMPETE: 35,
  REFEREE: 15, REF_COURSE: 15, COACH_COURSE: 20, TEACH: 20,
};

export const REF_COURSE_COST = 80;
export const REF_COURSE_SESSIONS = 4;
export const COACH_COURSE_COST = 150;
export const COACH_COURSE_SESSIONS = 6;
export const MEDICAL_COST = 25;
export const CLUB_START_BALANCE = 1000;

export type CompLevel = "REGIONAL" | "NACIONAL" | "INTERNACIONAL";
export type MedalKind = "GOLD" | "SILVER" | "BRONZE";
export type Intensity = "LOW" | "MEDIUM" | "HIGH";
export type CourseStatus = "NONE" | "ENROLLED" | "DONE";

export interface Hero {
  name: string;
  avatar: string;
  color: HeroColor;
  city: City;
  belt: Belt;
  tecnica: number;
  fisico: number;
  mental: number;
  energia: number;
  dinheiro: number;
  reputacao: number;
  weeksAtBelt: number;
  study: number;
  injury: number;
}

export interface Course { status: CourseStatus; sessions: number }

export interface Competition {
  id: string;
  week: number;
  level: CompLevel;
  city: City;
  minBelt: Belt;
  fee: number;
  prize: number;
}

export interface Medal {
  id: string;
  week: number;
  level: CompLevel;
  city: City;
  kind: MedalKind;
  owner: string;
  byClub: boolean;
}

export interface Athlete {
  id: number;
  name: string;
  age: number;
  belt: Belt;
  tecnica: number;
  fisico: number;
  humor: number;
  lesao: number;
  medicalUntil: number;
  feePaid: boolean;
  lateMonths: number;
  techniques: string[];
  discount: boolean;
  joinedWeek: number;
  medals: number;
}

export interface MonthLedger {
  month: number;
  fees: number;
  sponsor: number;
  rent: number;
  insurance: number;
  medical: number;
  competitions: number;
  equipment: number;
  balanceEnd: number;
}

export interface Sponsor { name: string; perMonth: number; monthsLeft: number }

export interface Club {
  name: string;
  color: HeroColor;
  city: City;
  balance: number;
  fee: number;
  reputation: number;
  intensity: Intensity;
  athletes: Athlete[];
  nextId: number;
  equipmentBroken: boolean;
  sponsor: Sponsor | null;
  ledger: MonthLedger[];
  current: MonthLedger;
  registrations: Record<string, number[]>;
  lastCollectWeek: number;
  foundedWeek: number;
}

export type GameEvent =
  | { kind: "NEW_ATHLETE"; athlete: Athlete }
  | { kind: "TALENT"; athlete: Athlete }
  | { kind: "SPONSOR"; sponsor: Sponsor }
  | { kind: "PARENT_COMPLAINT"; athleteName: string }
  | { kind: "EQUIPMENT_BREAK"; cost: number };

// Chiavi dei messaggi del registro: il testo vive in i18n.ts.
export type LogKey =
  | "log_trainTech" | "log_trainPhys" | "log_rest" | "log_study" | "log_injured" | "log_healed"
  | "log_compGold" | "log_compSilver" | "log_compBronze" | "log_compOut" | "log_referee"
  | "log_refSession" | "log_refDone" | "log_coachSession" | "log_coachDone" | "log_teach"
  | "log_promoted" | "log_newYear" | "log_monthFees" | "log_athleteQuit" | "log_athleteLeftFees"
  | "log_athleteInjured" | "log_athleteMedal" | "log_athleteOut" | "log_athleteSkip"
  | "log_athleteJoined" | "log_sponsorEnd" | "log_clubOpened" | "log_collected" | "log_allowance"
  | "log_eventAccepted" | "log_eventDeclined" | "log_medical" | "log_repair" | "log_noShow";

export interface LogLine { key: LogKey; vars?: Record<string, string | number> }

export type FightEventType = "GRIP" | "ATTACK" | "BLOCK" | "SHIDO" | "YUKO" | "WAZA_ARI" | "IPPON";
export interface FightEvent { t: FightEventType; by: "A" | "B"; technique?: string }
export interface Score { waza: number; ippon: number; shido: number; yuko?: number }
export interface Fight {
  round: number;
  rounds: number;
  opponent: { name: string; city: City; belt: Belt };
  events: FightEvent[];
  won: boolean;
}

export interface ClubResult { name: string; medal: MedalKind | null; wins: number; comp: Competition }

export interface WeekReport {
  week: number;
  xp: number;
  lines: LogLine[];
  fights: Fight[];
  comp: Competition | null;
  medal: MedalKind | null;
  clubResults: ClubResult[];
  monthClosed: MonthLedger | null;
}

export interface CareerState {
  version: typeof CAREER_VERSION;
  seed: number;
  rng: number;
  week: number;
  phase: Phase;
  hero: Hero;
  careerXp: number;
  referee: Course;
  coachCourse: Course;
  club: Club | null;
  calendar: Competition[];
  heroRegs: string[];
  medals: Medal[];
  pendingEvent: GameEvent | null;
  log: Array<LogLine & { week: number }>;
}

export interface WeekPlan {
  actions: ActionId[];
  teach?: { technique: string; athleteIds: number[] };
  /** I turni della gara combattuti passo a passo sul server (fights.py):
   *  se ci sono, valgono loro e il motore non simula. */
  compFights?: Fight[];
}

/* ---------------- RNG con seme (mulberry32), lo stato vive in `rng` ---------------- */

interface HasRng { rng: number }

function rand(d: HasRng): number {
  let t = (d.rng = (d.rng + 0x6d2b79f5) | 0);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

function mix(a: number, b: number): number {
  let h = (a ^ Math.imul(b + 0x9e3779b9, 0x85ebca6b)) | 0;
  h = Math.imul(h ^ (h >>> 16), 0x7feb352d);
  h = Math.imul(h ^ (h >>> 15), 0x846ca68b);
  return (h ^ (h >>> 16)) | 0;
}

function randInt(d: HasRng, min: number, max: number): number {
  return min + Math.floor(rand(d) * (max - min + 1));
}

function pick<T>(d: HasRng, list: readonly T[]): T {
  const v = list[Math.floor(rand(d) * list.length)];
  if (v === undefined) throw new Error("empty list");
  return v;
}

const clamp = (v: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, v));
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

/* ---------------- Calendario e utilità ---------------- */

export const beltRank = (b: Belt) => BELTS.indexOf(b);
export const nextBelt = (b: Belt): Belt | null => BELTS[beltRank(b) + 1] ?? null;

export function gameDate(week: number) {
  const w = week - 1;
  return {
    year: Math.floor(w / WEEKS_PER_YEAR) + 1,
    month: Math.floor(w / WEEKS_PER_MONTH) % 12,
    weekOfMonth: (w % WEEKS_PER_MONTH) + 1,
    absMonth: Math.floor(w / WEEKS_PER_MONTH),
  };
}

export const heroAge = (s: CareerState) => START_AGE + Math.floor((s.week - 1) / WEEKS_PER_YEAR);

export type AgeGroup = "U13" | "U15" | "U18" | "U21" | "SENIOR";
export function ageGroup(age: number): AgeGroup {
  if (age < 13) return "U13";
  if (age < 15) return "U15";
  if (age < 18) return "U18";
  if (age < 21) return "U21";
  return "SENIOR";
}

/** Grado più alto superato nella Dojo Academy (gli esami si superano lì). */
export function examRank(examsPassed: string[]): number {
  let r = 0;
  for (const e of examsPassed) {
    const i = BELTS.indexOf(e.toUpperCase() as Belt);
    if (i > r) r = i;
  }
  return r;
}

const FIRST_NAMES = [
  "Tiago", "Rita", "Inês", "Duarte", "Beatriz", "Martim", "Leonor", "Rodrigo", "Matilde", "Afonso",
  "Carolina", "Gonçalo", "Mariana", "Tomás", "Sofia", "Diogo", "Lara", "Santiago", "Francisca", "Salvador",
  "Madalena", "Vicente", "Benedita", "Lourenço", "Clara", "Gabriel", "Alice", "Rafael", "Joana", "Miguel",
];
const SURNAMES = ["Silva", "Santos", "Ferreira", "Pereira", "Costa", "Oliveira", "Rodrigues", "Martins", "Sousa", "Gomes", "Lopes", "Marques"];
const SPONSORS = ["Pastelaria Sol", "Surf Algarve", "Peixaria Mar Azul", "Talho Central", "Oficina Rápida", "Farmácia Saúde", "Gelados Praia"];

function personName(d: HasRng): string {
  return `${pick(d, FIRST_NAMES)} ${pick(d, SURNAMES)}`;
}

function generateCalendar(d: HasRng, year: number): Competition[] {
  const start = (year - 1) * WEEKS_PER_YEAR + 1;
  const used = new Set<number>();
  const comps: Competition[] = [];
  const plan: CompLevel[] = ["REGIONAL", "REGIONAL", "REGIONAL", "REGIONAL", "REGIONAL", "REGIONAL", "NACIONAL", "NACIONAL", "NACIONAL", "INTERNACIONAL"];
  plan.forEach((level, i) => {
    let w = randInt(d, 3, WEEKS_PER_YEAR - 1);
    // settimana occupata: si prova la successiva, ricominciando dalla 3
    while (used.has(w)) w = w >= WEEKS_PER_YEAR - 1 ? 3 : w + 1;
    used.add(w);
    const minBelt: Belt = level === "REGIONAL" ? "WHITE" : level === "NACIONAL" ? pick(d, ["YELLOW", "ORANGE"] as const) : "GREEN";
    comps.push({
      id: `y${year}c${i}`,
      week: start + w - 1,
      level,
      city: pick(d, CITIES),
      minBelt,
      fee: level === "REGIONAL" ? 10 : level === "NACIONAL" ? 20 : 45,
      prize: level === "REGIONAL" ? 15 : level === "NACIONAL" ? 40 : 100,
    });
  });
  return comps.sort((a, b) => a.week - b.week);
}

function newLedger(month: number, balance: number): MonthLedger {
  return { month, fees: 0, sponsor: 0, rent: 0, insurance: 0, medical: 0, competitions: 0, equipment: 0, balanceEnd: balance };
}

function makeAthlete(d: HasRng, week: number, talent: boolean): Athlete {
  const age = randInt(d, 7, 16);
  const beltCap = Math.min(BELTS.length - 2, Math.floor((age - 6) / 2));
  const belt = BELTS[randInt(d, 0, Math.max(0, beltCap))] ?? "WHITE";
  const base = beltRank(belt) * 9;
  return {
    id: 0,
    name: personName(d),
    age,
    belt,
    tecnica: clamp(base + randInt(d, 5, 18) + (talent ? 22 : 0)),
    fisico: clamp(base + randInt(d, 8, 20) + (talent ? 15 : 0)),
    humor: randInt(d, 55, 85),
    lesao: 0,
    // alcuni arrivano con la visita medica quasi scaduta
    medicalUntil: week + randInt(d, -2, 16),
    feePaid: false,
    lateMonths: 0,
    techniques: [],
    discount: talent,
    joinedWeek: week,
    medals: 0,
  };
}

/* ---------------- Creazione e lettura ---------------- */

export interface NewCareerInput { name: string; avatar: string; color: HeroColor; city: City; seed: number }

export function newCareer(input: NewCareerInput, startXp: number): CareerState {
  const seed = input.seed | 0;
  const d: HasRng = { rng: mix(seed, 1) };
  return {
    version: CAREER_VERSION,
    seed,
    rng: d.rng,
    week: 1,
    phase: "ATHLETE",
    hero: {
      name: input.name.trim().slice(0, 24) || "Judoka",
      avatar: input.avatar,
      color: input.color,
      city: input.city,
      belt: "WHITE",
      tecnica: 8, fisico: 12, mental: 15,
      energia: 100, dinheiro: 20, reputacao: 0,
      weeksAtBelt: 0, study: 0, injury: 0,
    },
    careerXp: Math.max(0, Math.floor(startXp)),
    referee: { status: "NONE", sessions: 0 },
    coachCourse: { status: "NONE", sessions: 0 },
    club: null,
    calendar: generateCalendar(d, 1),
    heroRegs: [],
    medals: [],
    pendingEvent: null,
    log: [],
  };
}

/** Valida un salvataggio arrivato dal server; null se è di un'altra versione o rotto. */
export function parseCareer(raw: unknown): CareerState | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Partial<CareerState>;
  if (o.version !== CAREER_VERSION || typeof o.week !== "number" || typeof o.seed !== "number") return null;
  if (!o.hero || typeof o.hero !== "object" || !Array.isArray(o.calendar) || !Array.isArray(o.medals)) return null;
  return o as CareerState;
}

/* ---------------- Faixa ---------------- */

const PROMO: Record<Exclude<Belt, "WHITE">, { weeks: number; tec: number; fis: number; study: number }> = {
  YELLOW: { weeks: 5, tec: 16, fis: 16, study: 2 },
  ORANGE: { weeks: 7, tec: 26, fis: 24, study: 3 },
  GREEN: { weeks: 9, tec: 36, fis: 32, study: 4 },
  BLUE: { weeks: 11, tec: 46, fis: 40, study: 5 },
  BROWN: { weeks: 13, tec: 56, fis: 48, study: 6 },
  BLACK: { weeks: 15, tec: 68, fis: 56, study: 7 },
};

export interface PromotionStatus {
  next: Belt | null;
  req: { weeks: number; tec: number; fis: number; study: number; age: number } | null;
  statsOk: boolean;
  examOk: boolean;
  ready: boolean;
}

export function promotionStatus(s: CareerState, examsPassed: string[]): PromotionStatus {
  const next = nextBelt(s.hero.belt);
  if (!next || next === "WHITE") return { next: null, req: null, statsOk: false, examOk: false, ready: false };
  const req = { ...PROMO[next], age: next === "BLACK" ? BLACK_BELT_MIN_AGE : 0 };
  const h = s.hero;
  const statsOk = h.weeksAtBelt >= req.weeks && h.tecnica >= req.tec && h.fisico >= req.fis && h.study >= req.study && heroAge(s) >= req.age;
  const examOk = examRank(examsPassed) >= beltRank(next);
  return { next, req, statsOk, examOk, ready: statsOk && examOk };
}

export function promote(s: CareerState, examsPassed: string[]): CareerState {
  const st = promotionStatus(s, examsPassed);
  if (!st.ready || !st.next) return s;
  const d = clone(s);
  d.hero.belt = st.next;
  d.hero.weeksAtBelt = 0;
  d.hero.study = 0;
  d.hero.reputacao = clamp(d.hero.reputacao + 3);
  d.hero.mental = clamp(d.hero.mental + 4);
  d.careerXp += 80 * beltRank(st.next);
  pushLog(d, [{ key: "log_promoted", vars: { belt: st.next } }]);
  return d;
}

/* ---------------- Azioni disponibili ---------------- */

export function compThisWeek(s: CareerState): Competition | null {
  return s.calendar.find((c) => c.week === s.week) ?? null;
}

export type ActionBlock = "energy" | "injured" | "noComp" | "locked" | "noClub" | null;

export function actionAvailable(s: CareerState, a: ActionId): boolean {
  const h = s.hero;
  switch (a) {
    case "TRAIN_TECH": case "TRAIN_PHYS": return h.injury === 0;
    case "REST": case "STUDY": return true;
    case "COMPETE": {
      const c = compThisWeek(s);
      return !!c && s.heroRegs.includes(c.id) && h.injury === 0;
    }
    case "REFEREE": return s.referee.status === "DONE";
    case "REF_COURSE": return s.referee.status === "ENROLLED";
    case "COACH_COURSE": return s.coachCourse.status === "ENROLLED";
    case "TEACH": return !!s.club && s.club.athletes.length > 0;
  }
}

/** Le azioni della settimana che il gioco accetta davvero, nell'ordine dato. */
export function sanitizeActions(s: CareerState, actions: ActionId[]): ActionId[] {
  const out: ActionId[] = [];
  let energy = s.hero.energia;
  // se c'è una gara a cui sei iscritto, si combatte
  const forced: ActionId[] = actionAvailable(s, "COMPETE") ? ["COMPETE"] : [];
  for (const a of [...forced, ...actions]) {
    if (out.length >= MAX_ACTIONS || out.includes(a) || !actionAvailable(s, a)) continue;
    const cost = ACTION_ENERGY[a];
    if (cost > 0 && cost > energy) continue;
    energy = clamp(energy - cost);
    out.push(a);
  }
  return out;
}

/* ---------------- Combattimenti ---------------- */

export function heroPower(h: Hero): number {
  return (0.45 * h.tecnica + 0.3 * h.fisico + 0.25 * h.mental) * (0.65 + 0.35 * (h.energia / 100));
}

function athletePower(a: Athlete): number {
  return (0.5 * a.tecnica + 0.35 * a.fisico + 0.15 * a.humor) * 0.9;
}

const LEVEL_BASE: Record<CompLevel, number> = { REGIONAL: 9, NACIONAL: 24, INTERNACIONAL: 40 };
export const LEVEL_ROUNDS: Record<CompLevel, number> = { REGIONAL: 3, NACIONAL: 4, INTERNACIONAL: 5 };
const LEVEL_MULT: Record<CompLevel, number> = { REGIONAL: 1, NACIONAL: 2, INTERNACIONAL: 3.5 };

function winChance(power: number, level: CompLevel, round: number, d: HasRng): number {
  const opp = LEVEL_BASE[level] + round * 3 + rand(d) * 14;
  return 1 / (1 + Math.exp(-(power - opp) / 7));
}

function fightScript(d: HasRng, won: boolean): FightEvent[] {
  const W: "A" | "B" = won ? "A" : "B";
  const L: "A" | "B" = won ? "B" : "A";
  const ev: FightEvent[] = [{ t: "GRIP", by: rand(d) < 0.5 ? "A" : "B" }];
  ev.push({ t: "ATTACK", by: L, technique: pick(d, TECHNIQUES) }, { t: "BLOCK", by: W });
  if (rand(d) < 0.5) ev.push({ t: "SHIDO", by: rand(d) < 0.7 ? L : W });
  const r = rand(d);
  const tech = pick(d, TECHNIQUES);
  if (r < 0.55) {
    ev.push({ t: "ATTACK", by: W, technique: tech }, { t: "IPPON", by: W, technique: tech });
  } else if (r < 0.85) {
    ev.push({ t: "WAZA_ARI", by: W, technique: tech }, { t: "GRIP", by: L }, { t: "ATTACK", by: L, technique: pick(d, TECHNIQUES) }, { t: "BLOCK", by: W });
    const t2 = pick(d, TECHNIQUES);
    ev.push({ t: "WAZA_ARI", by: W, technique: t2 });
  } else {
    ev.push({ t: "WAZA_ARI", by: W, technique: tech }, { t: "GRIP", by: L }, { t: "BLOCK", by: W });
  }
  return ev;
}

/** Punteggio dopo i primi `n` eventi (usato anche dalla scena animata). */
export function scoreAt(events: FightEvent[], n: number): { A: Score; B: Score } {
  const s = { A: { waza: 0, ippon: 0, shido: 0, yuko: 0 }, B: { waza: 0, ippon: 0, shido: 0, yuko: 0 } };
  for (const e of events.slice(0, n)) {
    if (e.t === "YUKO") s[e.by].yuko++;
    if (e.t === "WAZA_ARI") s[e.by].waza++;
    if (e.t === "IPPON") s[e.by].ippon++;
    if (e.t === "SHIDO") s[e.by].shido++;
  }
  // due waza-ari fanno ippon (awasete ippon)
  for (const k of ["A", "B"] as const) if (s[k].waza >= 2) s[k].ippon = 1;
  return s;
}

function medalFor(wins: number, rounds: number): MedalKind | null {
  if (wins >= rounds) return "GOLD";
  if (wins === rounds - 1) return "SILVER";
  if (wins === rounds - 2) return "BRONZE";
  return null;
}

/* ---------------- Settimana ---------------- */

/** Tiene il salvataggio leggero: si scartano le medaglie del club più vecchie. */
function trimMedals(d: CareerState) {
  while (d.medals.length > MAX_MEDALS) {
    const i = d.medals.findIndex((m) => m.byClub);
    d.medals.splice(i >= 0 ? i : 0, 1);
  }
}

function pushLog(d: CareerState, lines: LogLine[]) {
  for (const l of lines) d.log.unshift({ ...l, week: d.week });
  d.log = d.log.slice(0, 40);
}

function gain(d: HasRng, stat: number, base: number): number {
  return Math.max(1, Math.round((base + rand(d) * 2) * (1 - stat / 125)));
}

export function advanceWeek(s: CareerState, plan: WeekPlan): { state: CareerState; report: WeekReport } {
  const d = clone(s);
  const report: WeekReport = { week: s.week, xp: 0, lines: [], fights: [], comp: null, medal: null, clubResults: [], monthClosed: null };
  if (d.pendingEvent) return { state: s, report };
  const h = d.hero;
  const actions = sanitizeActions(s, plan.actions);
  const lines = report.lines;
  let xp = 0;
  let trained = false;

  for (const a of actions) {
    h.energia = clamp(h.energia - ACTION_ENERGY[a]);
    switch (a) {
      case "TRAIN_TECH": {
        const g = gain(d, h.tecnica, 4);
        h.tecnica = clamp(h.tecnica + g);
        xp += 15; trained = true;
        lines.push({ key: "log_trainTech", vars: { n: g } });
        break;
      }
      case "TRAIN_PHYS": {
        const g = gain(d, h.fisico, 4);
        h.fisico = clamp(h.fisico + g);
        xp += 15; trained = true;
        lines.push({ key: "log_trainPhys", vars: { n: g } });
        break;
      }
      case "REST":
        h.mental = clamp(h.mental + 1);
        lines.push({ key: "log_rest" });
        break;
      case "STUDY":
        h.study += 1;
        h.mental = clamp(h.mental + 2);
        xp += 10;
        lines.push({ key: "log_study" });
        break;
      case "COMPETE": {
        const c = compThisWeek(d);
        if (!c) break;
        report.comp = c;
        const rounds = LEVEL_ROUNDS[c.level];
        let wins = 0;
        const external = plan.compFights?.filter((f) => f.round >= 1 && f.round <= rounds).sort((a, b) => a.round - b.round);
        if (external && external.length > 0) {
          for (const f of external) {
            report.fights.push({ ...f, rounds });
            if (!f.won) break;
            wins++;
          }
        } else {
          for (let r = 1; r <= rounds; r++) {
            const won = rand(d) < winChance(heroPower(h), c.level, r, d);
            report.fights.push({
              round: r, rounds,
              opponent: { name: personName(d), city: pick(d, CITIES), belt: BELTS[Math.max(beltRank(c.minBelt), Math.min(6, beltRank(h.belt) + randInt(d, -1, 1)))] ?? h.belt },
              events: fightScript(d, won),
              won,
            });
            if (!won) break;
            wins++;
          }
        }
        const m = LEVEL_MULT[c.level];
        xp += Math.round(wins * 40 * m);
        h.mental = clamp(h.mental + 2 + wins);
        trained = true;
        const medal = medalFor(wins, rounds);
        report.medal = medal;
        if (medal) {
          const bonus = medal === "GOLD" ? 3 : medal === "SILVER" ? 2 : 1;
          xp += Math.round(bonus * 50 * m);
          h.reputacao = clamp(h.reputacao + Math.round(bonus * 2 * m));
          h.dinheiro += Math.round((c.prize * bonus) / 3);
          d.medals.push({ id: `${c.id}-hero`, week: c.week, level: c.level, city: c.city, kind: medal, owner: h.name, byClub: false });
          lines.push({ key: medal === "GOLD" ? "log_compGold" : medal === "SILVER" ? "log_compSilver" : "log_compBronze", vars: { city: c.city } });
        } else {
          lines.push({ key: "log_compOut", vars: { n: wins } });
        }
        break;
      }
      case "REFEREE": {
        const pay = 12 + randInt(d, 0, 10);
        h.dinheiro += pay;
        h.reputacao = clamp(h.reputacao + 1);
        xp += 30;
        lines.push({ key: "log_referee", vars: { n: pay } });
        break;
      }
      case "REF_COURSE":
        d.referee.sessions++;
        xp += 20;
        if (d.referee.sessions >= REF_COURSE_SESSIONS) {
          d.referee.status = "DONE"; xp += 100;
          lines.push({ key: "log_refDone" });
        } else lines.push({ key: "log_refSession", vars: { n: d.referee.sessions, total: REF_COURSE_SESSIONS } });
        break;
      case "COACH_COURSE":
        d.coachCourse.sessions++;
        xp += 25;
        if (d.coachCourse.sessions >= COACH_COURSE_SESSIONS) {
          d.coachCourse.status = "DONE"; xp += 200;
          if (d.phase === "ATHLETE") d.phase = "COACH";
          lines.push({ key: "log_coachDone" });
        } else lines.push({ key: "log_coachSession", vars: { n: d.coachCourse.sessions, total: COACH_COURSE_SESSIONS } });
        break;
      case "TEACH": {
        const club = d.club;
        const tp = plan.teach;
        if (!club || !tp) break;
        const ids = new Set(tp.athleteIds);
        let n = 0;
        for (const at of club.athletes) {
          if (!ids.has(at.id) || at.lesao > 0) continue;
          const known = at.techniques.includes(tp.technique);
          at.tecnica = clamp(at.tecnica + (known ? 1 : randInt(d, 2, 4)));
          at.humor = clamp(at.humor + (known ? -1 : 3));
          if (!known) at.techniques.push(tp.technique);
          n++;
        }
        h.tecnica = clamp(h.tecnica + (rand(d) < 0.3 ? 1 : 0));
        xp += 10 + n * 4;
        trained = true;
        lines.push({ key: "log_teach", vars: { tech: tp.technique, n } });
        break;
      }
    }
  }

  // un giudoka a corto di energia che si allena rischia
  if (trained && h.energia < 15 && h.injury === 0 && rand(d) < 0.15) {
    h.injury = randInt(d, 1, 3);
    lines.push({ key: "log_injured", vars: { n: h.injury } });
  } else if (h.injury > 0) {
    h.injury--;
    if (h.injury === 0) lines.push({ key: "log_healed" });
  }

  // ritmo settimanale
  if (trained) h.weeksAtBelt++;
  h.energia = clamp(h.energia + 12);
  h.dinheiro += 5;
  d.heroRegs = d.heroRegs.filter((id) => d.calendar.some((c) => c.id === id && c.week > d.week));

  if (d.club) xp += clubWeek(d, report);

  // nuova settimana
  d.week++;
  const date = gameDate(d.week);
  if ((d.week - 1) % WEEKS_PER_YEAR === 0) {
    d.calendar = generateCalendar(d, date.year);
    if (d.club) for (const a of d.club.athletes) a.age++;
    lines.push({ key: "log_newYear", vars: { n: date.year } });
  }
  if (d.club && (d.week - 1) % WEEKS_PER_MONTH === 0) xp += clubMonth(d, report);

  xp = Math.min(WEEK_XP_CAP, Math.max(0, xp));
  d.careerXp += xp;
  report.xp = xp;
  trimMedals(d);
  pushLog(d, lines);
  return { state: d, report };
}

/** Il club nella settimana: allenamento, umore, infortuni, gare, eventi. Restituisce XP. */
function clubWeek(d: CareerState, report: WeekReport): number {
  const club = d.club;
  if (!club) return 0;
  let xp = 0;
  const fx = {
    LOW: { fis: 0.5, humor: 2, injury: 0.01 },
    MEDIUM: { fis: 1.2, humor: 0, injury: 0.03 },
    HIGH: { fis: 2.2, humor: -3, injury: 0.07 },
  }[club.intensity];
  const kept: Athlete[] = [];
  for (const a of club.athletes) {
    if (a.lesao > 0) {
      a.lesao--;
    } else {
      a.fisico = clamp(a.fisico + Math.round(fx.fis + rand(d)));
      a.humor = clamp(a.humor + fx.humor + randInt(d, -2, 2) - (club.equipmentBroken ? 2 : 0));
      if (rand(d) < fx.injury + (club.equipmentBroken ? 0.03 : 0)) {
        a.lesao = randInt(d, 1, 4);
        a.humor = clamp(a.humor - 5);
        report.lines.push({ key: "log_athleteInjured", vars: { name: a.name, n: a.lesao } });
      }
    }
    // promozione di cintura degli allievi, semplice
    const nb = nextBelt(a.belt);
    if (nb && a.tecnica >= (beltRank(nb) * 11 + 8) && rand(d) < 0.08) {
      a.belt = nb;
      a.humor = clamp(a.humor + 10);
      xp += 25;
    }
    if (a.humor < 15 && rand(d) < 0.3) {
      report.lines.push({ key: "log_athleteQuit", vars: { name: a.name } });
      club.reputation = clamp(club.reputation - 2);
      continue;
    }
    kept.push(a);
  }
  club.athletes = kept;

  // gare degli atleti iscritti
  const comp = compThisWeek(d);
  if (comp) {
    const ids = club.registrations[comp.id] ?? [];
    const rounds = LEVEL_ROUNDS[comp.level];
    for (const id of ids) {
      const a = club.athletes.find((x) => x.id === id);
      if (!a) continue;
      if (a.lesao > 0 || a.medicalUntil < comp.week) {
        report.lines.push({ key: "log_athleteSkip", vars: { name: a.name } });
        continue;
      }
      let wins = 0;
      for (let r = 1; r <= rounds; r++) {
        if (rand(d) < winChance(athletePower(a), comp.level, r, d)) wins++;
        else break;
      }
      const medal = medalFor(wins, rounds);
      report.clubResults.push({ name: a.name, medal, wins, comp });
      a.humor = clamp(a.humor + (medal ? 12 : wins > 0 ? 3 : -4));
      if (medal) {
        const bonus = medal === "GOLD" ? 3 : medal === "SILVER" ? 2 : 1;
        a.medals++;
        club.reputation = clamp(club.reputation + Math.ceil((bonus * LEVEL_MULT[comp.level]) / 3));
        xp += Math.round(bonus * 30 * LEVEL_MULT[comp.level]);
        d.medals.push({ id: `${comp.id}-a${a.id}`, week: comp.week, level: comp.level, city: comp.city, kind: medal, owner: a.name, byClub: true });
        report.lines.push({ key: "log_athleteMedal", vars: { name: a.name, medal } });
      } else {
        report.lines.push({ key: "log_athleteOut", vars: { name: a.name, n: wins } });
      }
    }
    delete club.registrations[comp.id];
  }

  // eventi a sorpresa (al massimo uno da decidere)
  if (!d.pendingEvent) {
    const arrival = Math.max(0.04, 0.16 + club.reputation / 500 - (club.fee - 30) / 300 - club.athletes.length / 150);
    const r = rand(d);
    if (r < arrival) {
      const talent = rand(d) < 0.15;
      const athlete = makeAthlete(d, d.week, talent);
      d.pendingEvent = talent ? { kind: "TALENT", athlete } : { kind: "NEW_ATHLETE", athlete };
    } else if (r < arrival + 0.12) {
      const k = randInt(d, 0, 2);
      if (k === 0 && !club.sponsor && club.reputation >= 5) {
        d.pendingEvent = { kind: "SPONSOR", sponsor: { name: pick(d, SPONSORS), perMonth: randInt(d, 5, 15) * 10, monthsLeft: 6 } };
      } else if (k === 1 && club.athletes.length > 0) {
        d.pendingEvent = { kind: "PARENT_COMPLAINT", athleteName: pick(d, club.athletes).name };
      } else if (!club.equipmentBroken) {
        d.pendingEvent = { kind: "EQUIPMENT_BREAK", cost: randInt(d, 8, 16) * 10 };
      }
    }
  }
  return xp;
}

const RENT: Record<City, number> = { Lagos: 150, Albufeira: 160, "Portimão": 150, Faro: 170, Lisboa: 260, Porto: 220 };
export const clubRent = (c: City) => RENT[c];
export const INSURANCE_PER_ATHLETE = 4;
export const UPKEEP = 10;

/** Inizio mese: si chiude il conto del mese scorso, si incassano le quote, si pagano le spese. */
function clubMonth(d: CareerState, report: WeekReport): number {
  const club = d.club;
  if (!club) return 0;
  club.current.balanceEnd = club.balance;
  report.monthClosed = club.current;
  club.ledger = [...club.ledger, club.current].slice(-12);
  const cur = newLedger(gameDate(d.week).absMonth, club.balance);
  club.current = cur;

  const stay: Athlete[] = [];
  let paid = 0;
  for (const a of club.athletes) {
    if (!a.feePaid) a.lateMonths++;
    if (a.lateMonths >= 3) {
      report.lines.push({ key: "log_athleteLeftFees", vars: { name: a.name } });
      continue;
    }
    const p = clamp(0.9 - (club.fee - 30) * 0.01 + club.reputation * 0.001 - a.lateMonths * 0.1, 0.2, 0.98);
    a.feePaid = rand(d) < p;
    if (a.feePaid) {
      const fee = a.discount ? Math.round(club.fee / 2) : club.fee;
      club.balance += fee;
      cur.fees += fee;
      a.lateMonths = 0;
      paid++;
    }
    stay.push(a);
  }
  club.athletes = stay;
  cur.rent = RENT[club.city];
  cur.insurance = INSURANCE_PER_ATHLETE * stay.length;
  cur.equipment += UPKEEP;
  if (club.sponsor) {
    cur.sponsor = club.sponsor.perMonth;
    club.sponsor.monthsLeft--;
    if (club.sponsor.monthsLeft <= 0) {
      report.lines.push({ key: "log_sponsorEnd", vars: { name: club.sponsor.name } });
      club.sponsor = null;
    }
  }
  club.balance += cur.sponsor - cur.rent - cur.insurance - UPKEEP;
  report.lines.push({ key: "log_monthFees", vars: { paid, total: stay.length } });
  // la fama si consuma un po' ogni mese, se non arrivano nuovi risultati
  club.reputation = clamp(club.reputation - 1);
  // in rosso: le famiglie si preoccupano e la reputazione scende
  if (club.balance < 0) {
    club.reputation = clamp(club.reputation - 2);
    for (const a of club.athletes) a.humor = clamp(a.humor - 3);
  }
  // crescere il club vale esperienza
  return stay.length * 5 + (club.balance > 0 ? 20 : 0);
}

/* ---------------- Azioni immediate (non consumano la settimana) ---------------- */

export type ActionError = "noMoney" | "deadline" | "belt" | "reputation" | "medical" | "injured" | "already" | "notAllowed";
export type Result = { state: CareerState; error?: ActionError };

export function registrationOpen(s: CareerState, c: Competition): boolean {
  return s.week <= c.week - 1;
}

export function heroCanRegister(s: CareerState, c: Competition): ActionError | null {
  if (s.heroRegs.includes(c.id)) return "already";
  if (!registrationOpen(s, c)) return "deadline";
  if (beltRank(s.hero.belt) < beltRank(c.minBelt)) return "belt";
  if (c.level === "INTERNACIONAL" && s.hero.reputacao < 25) return "reputation";
  if (s.hero.dinheiro < c.fee) return "noMoney";
  return null;
}

export function registerHero(s: CareerState, compId: string): Result {
  const c = s.calendar.find((x) => x.id === compId);
  if (!c) return { state: s, error: "notAllowed" };
  const err = heroCanRegister(s, c);
  if (err) return { state: s, error: err };
  const d = clone(s);
  d.hero.dinheiro -= c.fee;
  d.heroRegs.push(c.id);
  return { state: d };
}

export function athleteCanRegister(s: CareerState, c: Competition, a: Athlete): ActionError | null {
  const regs = s.club?.registrations[c.id] ?? [];
  if (regs.includes(a.id)) return "already";
  if (!registrationOpen(s, c)) return "deadline";
  if (beltRank(a.belt) < beltRank(c.minBelt)) return "belt";
  if (a.medicalUntil < c.week) return "medical";
  if (a.lesao > 0) return "injured";
  if ((s.club?.balance ?? 0) < c.fee) return "noMoney";
  return null;
}

export function registerAthlete(s: CareerState, compId: string, athleteId: number): Result {
  const c = s.calendar.find((x) => x.id === compId);
  const a = s.club?.athletes.find((x) => x.id === athleteId);
  if (!c || !a || !s.club) return { state: s, error: "notAllowed" };
  const err = athleteCanRegister(s, c, a);
  if (err) return { state: s, error: err };
  const d = clone(s);
  const club = d.club!;
  club.balance -= c.fee;
  club.current.competitions += c.fee;
  club.registrations[c.id] = [...(club.registrations[c.id] ?? []), athleteId];
  return { state: d };
}

export function enrollRefereeCourse(s: CareerState): Result {
  if (s.referee.status !== "NONE" || beltRank(s.hero.belt) < beltRank("BROWN")) return { state: s, error: "notAllowed" };
  if (s.hero.dinheiro < REF_COURSE_COST) return { state: s, error: "noMoney" };
  const d = clone(s);
  d.hero.dinheiro -= REF_COURSE_COST;
  d.referee = { status: "ENROLLED", sessions: 0 };
  return { state: d };
}

export function enrollCoachCourse(s: CareerState): Result {
  if (s.coachCourse.status !== "NONE" || s.hero.belt !== "BLACK" || heroAge(s) < COACH_MIN_AGE) return { state: s, error: "notAllowed" };
  if (s.hero.dinheiro < COACH_COURSE_COST) return { state: s, error: "noMoney" };
  const d = clone(s);
  d.hero.dinheiro -= COACH_COURSE_COST;
  d.coachCourse = { status: "ENROLLED", sessions: 0 };
  return { state: d };
}

export function openClub(s: CareerState, input: { name: string; color: HeroColor; city: City }): Result {
  if (s.phase !== "COACH" || s.club) return { state: s, error: "notAllowed" };
  const d = clone(s);
  const month = gameDate(d.week).absMonth;
  const club: Club = {
    name: input.name.trim().slice(0, 32) || "Judo Clube",
    color: input.color,
    city: input.city,
    balance: CLUB_START_BALANCE,
    fee: 30,
    reputation: Math.round(d.hero.reputacao / 3),
    intensity: "MEDIUM",
    athletes: [],
    nextId: 1,
    equipmentBroken: false,
    sponsor: null,
    ledger: [],
    current: newLedger(month, CLUB_START_BALANCE),
    registrations: {},
    lastCollectWeek: 0,
    foundedWeek: d.week,
  };
  // i primi due allievi arrivano con l'apertura
  for (let i = 0; i < 2; i++) {
    const a = makeAthlete(d, d.week, false);
    a.id = club.nextId++;
    a.feePaid = true;
    club.balance += club.fee;
    club.current.fees += club.fee;
    club.athletes.push(a);
  }
  d.club = club;
  d.phase = "CLUB_OWNER";
  d.careerXp += 150;
  pushLog(d, [{ key: "log_clubOpened", vars: { name: club.name } }]);
  return { state: d };
}

export function resolveEvent(s: CareerState, accept: boolean): CareerState {
  const ev = s.pendingEvent;
  if (!ev) return s;
  const d = clone(s);
  d.pendingEvent = null;
  const club = d.club;
  if (!club) return d;
  const line: LogLine = { key: accept ? "log_eventAccepted" : "log_eventDeclined", vars: { kind: ev.kind } };
  switch (ev.kind) {
    case "NEW_ATHLETE":
    case "TALENT":
      if (accept) {
        const a = { ...ev.athlete, id: club.nextId++, feePaid: true, joinedWeek: d.week };
        const fee = a.discount ? Math.round(club.fee / 2) : club.fee;
        club.balance += fee;
        club.current.fees += fee;
        club.athletes.push(a);
        d.careerXp += 20;
        pushLog(d, [{ key: "log_athleteJoined", vars: { name: a.name } }]);
        return d;
      }
      if (ev.kind === "TALENT") club.reputation = clamp(club.reputation - 1);
      break;
    case "SPONSOR":
      if (accept) club.sponsor = ev.sponsor;
      break;
    case "PARENT_COMPLAINT":
      if (accept) {
        for (const a of club.athletes) a.humor = clamp(a.humor + 6);
        club.reputation = clamp(club.reputation + 1);
        d.hero.energia = clamp(d.hero.energia - 10);
      } else {
        for (const a of club.athletes) a.humor = clamp(a.humor - 4);
        club.reputation = clamp(club.reputation - 3);
      }
      break;
    case "EQUIPMENT_BREAK":
      if (accept) {
        club.balance -= ev.cost;
        club.current.equipment += ev.cost;
      } else club.equipmentBroken = true;
      break;
  }
  pushLog(d, [line]);
  return d;
}

export const REPAIR_COST = 120;

export function repairEquipment(s: CareerState): Result {
  if (!s.club?.equipmentBroken) return { state: s, error: "notAllowed" };
  if (s.club.balance < REPAIR_COST) return { state: s, error: "noMoney" };
  const d = clone(s);
  const club = d.club!;
  club.equipmentBroken = false;
  club.balance -= REPAIR_COST;
  club.current.equipment += REPAIR_COST;
  pushLog(d, [{ key: "log_repair", vars: { n: REPAIR_COST } }]);
  return { state: d };
}

export function bookMedical(s: CareerState, athleteId: number): Result {
  const a = s.club?.athletes.find((x) => x.id === athleteId);
  if (!s.club || !a) return { state: s, error: "notAllowed" };
  if (a.medicalUntil >= s.week + WEEKS_PER_YEAR - 4) return { state: s, error: "already" };
  if (s.club.balance < MEDICAL_COST) return { state: s, error: "noMoney" };
  const d = clone(s);
  const club = d.club!;
  const at = club.athletes.find((x) => x.id === athleteId)!;
  at.medicalUntil = d.week + WEEKS_PER_YEAR;
  club.balance -= MEDICAL_COST;
  club.current.medical += MEDICAL_COST;
  pushLog(d, [{ key: "log_medical", vars: { name: at.name } }]);
  return { state: d };
}

/** Sollecita le famiglie in ritardo: una volta a settimana, qualcuno paga. */
export function collectFees(s: CareerState): { state: CareerState; collected: number; error?: ActionError } {
  const club = s.club;
  if (!club) return { state: s, collected: 0, error: "notAllowed" };
  if (club.lastCollectWeek === s.week) return { state: s, collected: 0, error: "already" };
  const d = clone(s);
  const c = d.club!;
  c.lastCollectWeek = d.week;
  let collected = 0;
  for (const a of c.athletes) {
    if (a.feePaid) continue;
    if (rand(d) < 0.55) {
      const fee = a.discount ? Math.round(c.fee / 2) : c.fee;
      a.feePaid = true;
      a.lateMonths = 0;
      c.balance += fee;
      c.current.fees += fee;
      collected++;
    } else a.humor = clamp(a.humor - 2);
  }
  pushLog(d, [{ key: "log_collected", vars: { n: collected } }]);
  return { state: d, collected };
}

export function setIntensity(s: CareerState, v: Intensity): CareerState {
  if (!s.club) return s;
  const d = clone(s);
  d.club!.intensity = v;
  return d;
}

export function setFee(s: CareerState, fee: number): CareerState {
  if (!s.club) return s;
  const d = clone(s);
  d.club!.fee = Math.max(15, Math.min(60, Math.round(fee)));
  return d;
}

/* ---------------- Avvisi ---------------- */

export type AlertKind =
  | "MEDICAL_EXPIRED" | "MEDICAL_SOON" | "LOW_MOOD" | "INJURY" | "UNPAID" | "NEGATIVE_BALANCE"
  | "REG_CLOSING" | "HERO_LOW_ENERGY" | "HERO_INJURED" | "EXAM_NEEDED" | "EQUIPMENT_BROKEN" | "EVENT_PENDING";

export interface GameAlert {
  id: string;
  kind: AlertKind;
  severity: "high" | "medium" | "low";
  vars: Record<string, string | number>;
  athleteId?: number;
  compId?: string;
}

export function computeAlerts(s: CareerState, examsPassed: string[]): GameAlert[] {
  const out: GameAlert[] = [];
  const h = s.hero;
  if (s.pendingEvent) out.push({ id: "ev", kind: "EVENT_PENDING", severity: "high", vars: {} });
  if (h.injury > 0) out.push({ id: "hinj", kind: "HERO_INJURED", severity: "medium", vars: { n: h.injury } });
  if (h.energia < 25) out.push({ id: "hen", kind: "HERO_LOW_ENERGY", severity: "low", vars: { n: h.energia } });
  const ps = promotionStatus(s, examsPassed);
  if (ps.statsOk && !ps.examOk && ps.next) out.push({ id: "exam", kind: "EXAM_NEEDED", severity: "medium", vars: { belt: ps.next } });
  for (const c of s.calendar) {
    if (c.week - 1 === s.week && !s.heroRegs.includes(c.id) && !(s.club?.registrations[c.id]?.length)) {
      out.push({ id: `reg-${c.id}`, kind: "REG_CLOSING", severity: "low", vars: { city: c.city, level: c.level }, compId: c.id });
    }
  }
  const club = s.club;
  if (club) {
    if (club.balance < 0) out.push({ id: "neg", kind: "NEGATIVE_BALANCE", severity: "high", vars: { n: club.balance } });
    if (club.equipmentBroken) out.push({ id: "eq", kind: "EQUIPMENT_BROKEN", severity: "medium", vars: {} });
    for (const a of club.athletes) {
      if (a.medicalUntil < s.week) out.push({ id: `med-${a.id}`, kind: "MEDICAL_EXPIRED", severity: "high", vars: { name: a.name }, athleteId: a.id });
      else if (a.medicalUntil < s.week + 4) out.push({ id: `meds-${a.id}`, kind: "MEDICAL_SOON", severity: "low", vars: { name: a.name, n: a.medicalUntil - s.week }, athleteId: a.id });
      if (a.humor < 30) out.push({ id: `mood-${a.id}`, kind: "LOW_MOOD", severity: a.humor < 15 ? "high" : "medium", vars: { name: a.name }, athleteId: a.id });
      if (a.lesao > 0) out.push({ id: `inj-${a.id}`, kind: "INJURY", severity: "medium", vars: { name: a.name, n: a.lesao }, athleteId: a.id });
      if (!a.feePaid) out.push({ id: `fee-${a.id}`, kind: "UNPAID", severity: a.lateMonths >= 1 ? "high" : "medium", vars: { name: a.name, n: a.lateMonths + 1 }, athleteId: a.id });
    }
  }
  const order = { high: 0, medium: 1, low: 2 };
  return out.sort((a, b) => order[a.severity] - order[b.severity]);
}

/** Entrate e uscite di un mese, già sommate. */
export function ledgerTotals(l: MonthLedger) {
  const income = l.fees + l.sponsor;
  const expenses = l.rent + l.insurance + l.medical + l.competitions + l.equipment;
  return { income, expenses, net: income - expenses };
}
