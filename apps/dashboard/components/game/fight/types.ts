// Gli incontri decisi dal server (apps/api/app/game/fights.py): come li
// riceve il browser. Mai la qualità di una risposta prima di averla data.

import type { Belt } from "@/components/game/career/engine";
import { friendlyApiError } from "@/lib/api-error";

export interface FightSide { name: string; belt: Belt; club: string | null; tec: number; str: number; men: number; sta: number; hp: number }
export interface FightScore { ippon: number; waza: number; yuko: number; shido: number }
export type Quality = "BEST" | "GOOD" | "RISKY" | "BAD";
export type ExchangeKind = "DEF" | "ATT" | "GRIP" | "NW_TOP" | "NW_BOT";
export interface Exchange {
  seq: number; kind: ExchangeKind; prompt: string; attack: string | null; choice: string; quality: Quality;
  success: boolean; by: "me" | "opp" | null; points: "IPPON" | "WAZA" | "YUKO" | "SHIDO" | null; tech: string | null;
  why: string; clock: number;
}
export interface Prompt { seq: number; kind: ExchangeKind; text: string; attack: string | null; options: { id: string; label: string }[]; seconds: number }
export type FightReason = "IPPON" | "AWASETE" | "HANSOKU" | "TIME" | "GOLDEN" | "DECISION" | "FORFEIT";
export interface TimelineEvent { t: "GRIP" | "ATTACK" | "BLOCK" | "SHIDO" | "YUKO" | "WAZA_ARI" | "IPPON"; by: "A" | "B"; technique?: string }
export interface FightView {
  id: string; kind: "CAREER" | "RANDORI"; mode: "SIM" | "STEP"; status: "ACTIVE" | "FINISHED";
  me: FightSide; opp: FightSide; clock: number; regulation: number; golden: boolean;
  score: { me: FightScore; opp: FightScore }; stamina: { me: number; opp: number };
  prompt: Prompt | null; history: Exchange[];
  result: { won: boolean; reason: FightReason; points: number } | null;
  timeline: TimelineEvent[];
  context: { comp_id?: string; round?: number; rounds?: number; level?: string; city?: string; stake_win?: number; stake_loss?: number } | null;
  last?: Exchange; my_points?: number;
}

export async function gameApi<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { cache: "no-store", ...init });
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return (await res.json()) as T;
}

export const postJson = (body?: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body),
});

/** Il punteggio dopo i primi `n` scambi (per la simulazione rivista passo per passo). */
export function scoreAfter(history: Exchange[], n: number): { me: FightScore; opp: FightScore } {
  const s = { me: { ippon: 0, waza: 0, yuko: 0, shido: 0 }, opp: { ippon: 0, waza: 0, yuko: 0, shido: 0 } };
  for (const e of history.slice(0, n)) {
    if (!e.by || !e.points) continue;
    const k = ({ IPPON: "ippon", WAZA: "waza", YUKO: "yuko", SHIDO: "shido" } as const)[e.points];
    s[e.by][k]++;
  }
  return s;
}
