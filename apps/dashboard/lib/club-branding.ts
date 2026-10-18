"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { normalizeHex, paletteVars } from "@/lib/brand";

export interface ClubBranding {
  name: string;
  logo_url: string | null;
  brand_primary: string | null;
  brand_secondary: string | null;
  brand_accent: string | null;
}

/** Il tema del club dell'utente (GET /club/branding): colori e logo scelti
 *  nell'editor del sito. `enabled` falso (console della piattaforma, aree
 *  senza club) = niente richiesta, resta JAV. I colori si applicano a
 *  <html>, così valgono anche per le finestre che si aprono in un portale. */
export function useClubBranding(enabled: boolean): ClubBranding | null {
  // L'area del treinador prende il tema del club scelto entrando
  // (club/staff_clubs.py): l'API guarda quel cookie solo con `?area=staff`.
  const staff = usePathname()?.startsWith("/staff") ?? false;
  const { data } = useQuery({
    queryKey: staff ? ["club", "branding", "staff"] : ["club", "branding"],
    queryFn: async (): Promise<ClubBranding | null> => {
      const res = await fetch(staff ? "/api/proxy/club/branding?area=staff" : "/api/proxy/club/branding");
      return res.ok ? res.json() : null;
    },
    enabled,
    retry: false,
    // Dinamico: se la segreteria cambia i colori, famiglie, atleti e treinador
    // li vedono entro un minuto (o tornando sulla scheda).
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });
  const branding = enabled ? data ?? null : null;
  const primary = normalizeHex(branding?.brand_primary) ?? null;
  const secondary = normalizeHex(branding?.brand_secondary) ?? null;
  const accent = normalizeHex(branding?.brand_accent) ?? null;

  useEffect(() => {
    const vars = paletteVars(primary, secondary, accent);
    const root = document.documentElement;
    for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value);
    return () => {
      for (const name of Object.keys(vars)) root.style.removeProperty(name);
    };
  }, [primary, secondary, accent]);

  return branding;
}
