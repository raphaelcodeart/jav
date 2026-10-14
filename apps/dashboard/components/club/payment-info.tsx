"use client";

import { useQuery } from "@tanstack/react-query";
import { useCurrentClub } from "@/components/club/current-club";

export interface PaymentInfo {
  iban: string | null;
  holder: string | null;
  instructions: string | null;
}

/** Le coordinate della piattaforma: lo Shop e ogni altro "paga con bonifico"
 *  che non sia una quota del club. */
export function usePaymentInfo() {
  return useQuery({
    queryKey: ["organization", "payment-info"],
    queryFn: async (): Promise<PaymentInfo> => {
      const res = await fetch("/api/proxy/organizations/me/payment-info");
      if (!res.ok) return { iban: null, holder: null, instructions: null };
      return res.json();
    },
    staleTime: 5 * 60_000,
  });
}

/** Le coordinate del club: le quote (mensilità, iscrizione, gare) si pagano
 *  al club, non alla piattaforma. Le imposta la segreteria. */
export function useClubPaymentInfo(): { data: PaymentInfo | undefined } {
  const { data: club } = useCurrentClub();
  return {
    data: club
      ? {
          iban: club.settings.bank_iban,
          holder: club.settings.bank_account_holder,
          instructions: club.settings.bank_transfer_instructions,
        }
      : undefined,
  };
}
