"use client";

import { useQuery } from "@tanstack/react-query";
import { EventsExplorer } from "@/components/site/events-explorer";

/** Il calendario degli eventi del sito pubblico (/eventos), lo stesso, dentro
 *  l'area di atleti e famiglie: lista (prossimi in cima), calendario del mese
 *  e anno, con ricerca e filtri. I dati sono quelli pubblici. */
export function AreaEvents() {
  const now = new Date();
  const todayIso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const { data: clubs } = useQuery({
    queryKey: ["site-clubs"],
    queryFn: async () => {
      const res = await fetch("/backend/api/public-site/clubs");
      return res.ok ? ((await res.json()) as { slug: string; name: string }[]) : [];
    },
    staleTime: 300_000,
  });
  return (
    <EventsExplorer
      embedded todayIso={todayIso} clubs={(clubs ?? []).map((c) => ({ slug: c.slug, name: c.name }))}
      initial={{ view: "list", year: now.getFullYear(), month: now.getMonth(), q: "", kind: "", level: "", club: "", age: "", open: false }}
    />
  );
}
