/** «2026-10-17» + «18:30» (o niente) → l'istante, nell'ora del browser.
 *  Senza ora: la scadenza vale fino alla fine del giorno, l'inizio della gara
 *  alle 9 (l'ora tipica del controllo del peso), così il conto non mente. */
export function moment(dateIso: string, time: string | null | undefined, fallback: "endOfDay" | "morning"): number {
  const [y, m, d] = dateIso.split("-").map(Number) as [number, number, number];
  if (time) {
    const [hh, mm] = time.split(":").map(Number) as [number, number];
    return new Date(y, m - 1, d, hh, mm).getTime();
  }
  return fallback === "endOfDay" ? new Date(y, m - 1, d, 23, 59, 59).getTime() : new Date(y, m - 1, d, 9, 0).getTime();
}

