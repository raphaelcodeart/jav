"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";

async function fetchMyRoles(): Promise<string[]> {
  const res = await fetch("/api/proxy/auth/me");
  if (!res.ok) return [];
  const data = await res.json();
  return data.roles ?? [];
}

/** Shared by AreaSwitcher and the UserMenu dropdown entry so both read the
 * same live roles/area without duplicating the gating logic. Reads LIVE
 * roles (not the access token's own, which are only as fresh as the last
 * login/refresh -- see auth/router.py get_me) so it reacts the moment
 * someone auto-activates or is deactivated, without a re-login. */
export function useDualRoleAreas() {
  const pathname = usePathname();
  const { data: roles = [] } = useQuery({
    queryKey: ["auth", "me", "roles"],
    queryFn: fetchMyRoles,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });

  return {
    hasBothRoles: roles.includes("CUSTOMER") && roles.includes("PROMOTER"),
    isCustomerArea: pathname?.startsWith("/customer") ?? false,
    clubAreas: clubAreasFor(roles).filter((a) => !pathname?.startsWith(a.href)),
  };
}

/** Le aree del club di chi ha più ruoli: un genitore che si allena e
 *  insegna passa da famiglia ad atleta a treinador dal menu utente. Senza
 *  questo l'area treinador si apriva solo scrivendo /staff. */
export function clubAreasFor(roles: string[]): { href: string; key: "family" | "athlete" | "coach" | "secretary"; icon: string }[] {
  const out: { href: string; key: "family" | "athlete" | "coach" | "secretary"; icon: string }[] = [];
  if (roles.includes("SECRETARY")) out.push({ href: "/club", key: "secretary", icon: "🗂️" });
  if (roles.includes("CUSTOMER")) out.push({ href: "/customer", key: "family", icon: "👪" });
  if (roles.includes("CUSTOMER") || roles.includes("ATHLETE")) out.push({ href: "/atleta", key: "athlete", icon: "🥋" });
  if (roles.includes("INSTRUCTOR")) out.push({ href: "/staff", key: "coach", icon: "🧑‍🏫" });
  return out.length > 1 ? out : [];
}

/** Always-visible customer/promoter toggle for anyone who holds BOTH roles --
 * e.g. a customer who "lavora con noi"-activated into a promoter, or a
 * promoter who was also invited as a customer. Renders nothing for anyone
 * who holds only one of the two roles. */
export function AreaSwitcher() {
  const { hasBothRoles, isCustomerArea } = useDualRoleAreas();

  if (!hasBothRoles) return null;

  return (
    <div className="hidden sm:inline-flex items-center rounded-xl border border-slate-300 bg-slate-900/5 p-1 gap-1">
      <Link
        href="/customer"
        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
          isCustomerArea
            ? "bg-brand-600 text-white"
            : " text-slate-600 hover:bg-slate-900/10"
        }`}
      >
        Area Cliente
      </Link>
      <Link
        href="/promoter"
        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
          !isCustomerArea
            ? "bg-brand-600 text-white"
            : " text-slate-600 hover:bg-slate-900/10"
        }`}
      >
        Area Promoter
      </Link>
    </div>
  );
}
