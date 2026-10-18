"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { friendlyApiError } from "@/lib/api-error";

export interface ClubSettings {
  bank_iban: string | null;
  bank_account_holder: string | null;
  bank_transfer_instructions: string | null;
  contact_email: string | null;
  /** L'ente a cui si chiede il trasporto (di solito il comune). */
  transport_entity_name: string | null;
  transport_entity_email: string | null;
  /** La lingua delle lettere a terzi: "pt", "it", "en". */
  letters_language: string | null;
  /** Gli avvisi della mensilità (1, 10, 15) e la multa del 16 (club/payment_reminders.py). */
  late_fee_enabled?: boolean;
  late_fee_cents?: number;
}

export interface CurrentClub {
  id: string;
  name: string;
  slug: string;
  /** True quando chi guarda è staff della piattaforma "entrato" nel club. */
  entered: boolean;
  settings: ClubSettings;
  /** CLUB o JAV_COURSES: nei corsi JAV niente cinture, gare e ranking. */
  kind: "CLUB" | "JAV_COURSES" | string;
}

/** Il club su cui si sta lavorando (GET /club/current). `null` quando lo
 *  staff della piattaforma non ne ha ancora scelto uno: l'API risponde 409,
 *  e il pannello Club mostra l'elenco invece del club. */
export function useCurrentClub() {
  // Nell'area del treinador il club è quello scelto entrando (cookie
  // jav_staff_club): l'API lo considera solo con `?area=staff`, e la chiave
  // è un'altra perché la stessa scheda può avere anche l'area di famiglia.
  const staff = usePathname()?.startsWith("/staff") ?? false;
  return useQuery({
    queryKey: staff ? ["club", "current", "staff"] : ["club", "current"],
    queryFn: async (): Promise<CurrentClub | null> => {
      const res = await fetch(staff ? "/api/proxy/club/current?area=staff" : "/api/proxy/club/current");
      if (res.status === 409) return null;
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
    staleTime: 5 * 60_000,
    retry: false,
  });
}
