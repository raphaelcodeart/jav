"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { EventsExplorer } from "@/components/site/events-explorer";
import { Skeleton } from "@/components/ui/skeleton";
import { clearEventsReturn, readEventsReturn, useIsClient } from "@/lib/events-return";

/** Il calendario degli eventi del sito pubblico (/eventos), lo stesso, dentro
 *  l'area di atleti e famiglie: lista (prossimi in cima), calendario del mese
 *  e anno, con ricerca e filtri. I dati sono quelli pubblici. `returnHref`:
 *  la sezione dell'area a cui riporta il bottone «Torna al calendario» della
 *  pagina di un evento; tornando, il calendario riparte da dove si era. */
export function AreaEvents({ returnHref }: { returnHref: string }) {
  // Il punto a cui tornare sta nello storage del browser: si legge lì.
  return useIsClient() ? <AreaEventsBody returnHref={returnHref} /> : <Skeleton className="h-96" />;
}

function AreaEventsBody({ returnHref }: { returnHref: string }) {
  const now = new Date();
  const todayIso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const [restored] = useState(readEventsReturn);
  useEffect(() => {
    if (restored) clearEventsReturn();
  }, [restored]);
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
      embedded returnHref={returnHref} restored={restored}
      todayIso={todayIso} clubs={(clubs ?? []).map((c) => ({ slug: c.slug, name: c.name }))}
      initial={{ view: "list", year: now.getFullYear(), month: now.getMonth(), q: "", kind: "", level: "", club: "", age: "", open: false }}
    />
  );
}
