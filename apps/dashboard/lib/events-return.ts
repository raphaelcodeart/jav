"use client";

import { useSyncExternalStore } from "react";
import type { ExplorerState } from "@/components/site/events-explorer";

/** Dove si era nel calendario degli eventi dell'area (atleta o famiglia)
 *  quando si è aperta la pagina di un evento: la sezione dell'area (`url`),
 *  vista, mese, filtri, il giorno scelto e lo scorrimento. Il bottone
 *  «Torna al calendario» della pagina dell'evento riporta lì, e il calendario
 *  riparte da questo stato. Vive in sessionStorage: solo questa scheda del
 *  browser, e scade dopo mezz'ora (chi torna all'area molto dopo riparte
 *  dalla home). Si consuma tornando al calendario (AreaEvents). */
export interface EventsReturn {
  url: string;
  state: ExplorerState;
  day: string | null;
  scrollY: number;
  at: number;
}

const KEY = "jav:events-return";
const MAX_AGE_MS = 30 * 60 * 1000;

export function saveEventsReturn(value: Omit<EventsReturn, "at">) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ ...value, at: Date.now() }));
  } catch {
    // Senza storage (navigazione privata bloccata) il bottone porta all'area.
  }
}

/** Solo un indirizzo nostro: mai «//altro-sito». */
function safe(url: unknown): url is string {
  return typeof url === "string" && url.startsWith("/") && !url.startsWith("//") && !url.includes("\\");
}

let cachedRaw: string | null = null;
let cachedValue: EventsReturn | null = null;

function read(): EventsReturn | null {
  let raw: string | null = null;
  try {
    raw = sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
  if (raw === cachedRaw) return cachedValue;
  cachedRaw = raw;
  cachedValue = null;
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as EventsReturn;
    if (safe(v.url) && v.state && Date.now() - v.at < MAX_AGE_MS) cachedValue = v;
  } catch {
    // Un valore rovinato vale come nessuno.
  }
  return cachedValue;
}

export function readEventsReturn(): EventsReturn | null {
  return typeof window === "undefined" ? null : read();
}

export function clearEventsReturn() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // niente da togliere
  }
}

const noop = () => () => {};

/** Il punto a cui tornare, letto solo nel browser (sul server è null). */
export function useEventsReturn(): EventsReturn | null {
  return useSyncExternalStore(noop, read, () => null);
}

/** true solo nel browser, dopo l'idratazione: per leggere lo storage senza
 *  disegnare sul server una cosa diversa dal browser. */
export function useIsClient(): boolean {
  return useSyncExternalStore(noop, () => true, () => false);
}
