"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { fetchCurrentClub } from "@/components/club/current-club";
import { fetchStaffCourses, STAFF_COURSES_KEY } from "@/lib/ext-courses";
import type { MessageKey } from "@/lib/i18n/messages/it";
import { useI18n } from "@/lib/i18n/provider";

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

  // Il club della famiglia (non quello del treinador): nei corsi JAV i
  // bambini non hanno un'area dell'atleta, e la voce non si offre.
  const { data: familyClub } = useQuery({
    queryKey: ["club", "current"],
    queryFn: () => fetchCurrentClub(),
    enabled: roles.includes("CUSTOMER") && !roles.includes("ATHLETE"),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const noAthleteArea = !roles.includes("ATHLETE") && familyClub?.kind === "JAV_COURSES";

  // I corsi esterni in cui lavora (scuola o treinador): l'area Escola si
  // offre anche al treinador che non ha il ruolo EXT_SCHOOL.
  const { data: extCourses } = useQuery({
    queryKey: STAFF_COURSES_KEY,
    queryFn: fetchStaffCourses,
    enabled: roles.includes("INSTRUCTOR") || roles.includes("EXT_SCHOOL"),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const school = roles.includes("EXT_SCHOOL") || (extCourses?.length ?? 0) > 0;

  return {
    hasBothRoles: roles.includes("CUSTOMER") && roles.includes("PROMOTER"),
    isCustomerArea: pathname?.startsWith("/customer") ?? false,
    clubAreas: clubAreasFor(roles, { athleteArea: !noAthleteArea, school })
      .filter((a) => !pathname?.startsWith(a.href.split("?")[0] ?? a.href)),
  };
}

/** Le aree del club di chi ha più ruoli: un genitore che si allena e
 *  insegna passa da famiglia ad atleta a treinador dal menu utente. Senza
 *  questo l'area treinador si apriva solo scrivendo /staff. */
export function clubAreasFor(roles: string[], { athleteArea = true, school = false }: { athleteArea?: boolean; school?: boolean } = {}): AreaLink[] {
  const out: AreaLink[] = [];
  if (roles.includes("SECRETARY")) out.push({ href: "/club", labelKey: "shell.area.secretary", icon: "🗂️" });
  if (roles.includes("CUSTOMER")) out.push({ href: "/customer", labelKey: "shell.area.family", icon: "👪" });
  if (roles.includes("ATHLETE") || (roles.includes("CUSTOMER") && athleteArea)) out.push({ href: "/atleta", labelKey: "shell.area.athlete", icon: "🥋" });
  if (roles.includes("INSTRUCTOR")) out.push({ href: "/staff", labelKey: "shell.area.coach", icon: "🧑‍🏫" });
  // I corsi esterni (extcourses), un mondo a parte: i figli iscritti a un
  // corso nella scuola, e l'area della scuola / del treinador del corso.
  // ?area=familia: il ruolo appena dato può non essere ancora nel token.
  if (roles.includes("EXT_FAMILY")) out.push({ href: "/cursos?area=familia", labelKey: "ext.area.courses", icon: "🎒" });
  if (school) out.push({ href: "/escola", labelKey: "ext.area.school", icon: "🏫" });
  return out.length > 1 ? out : [];
}

export interface AreaLink { href: string; labelKey: MessageKey; icon: string }

/** Always-visible customer/promoter toggle for anyone who holds BOTH roles --
 * e.g. a customer who "lavora con noi"-activated into a promoter, or a
 * promoter who was also invited as a customer. Renders nothing for anyone
 * who holds only one of the two roles. */
export function AreaSwitcher() {
  const { hasBothRoles, isCustomerArea } = useDualRoleAreas();
  const { t } = useI18n();

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
        {t("acct.area.customer")}
      </Link>
      <Link
        href="/promoter"
        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
          !isCustomerArea
            ? "bg-brand-600 text-white"
            : " text-slate-600 hover:bg-slate-900/10"
        }`}
      >
        {t("acct.area.promoter")}
      </Link>
    </div>
  );
}
