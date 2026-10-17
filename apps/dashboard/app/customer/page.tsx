import { redirect } from "next/navigation";
import { apiFetchOrRedirectToLogin } from "@/lib/api-client";
import { decodeRolesFromAccessToken, getSession } from "@/lib/session";
import { CustomerClientPage } from "@/components/customer-client-page";
import type { ContractRead } from "@/lib/types";

export default async function CustomerDashboard() {
  const session = await getSession();
  // Solo la famiglia (CUSTOMER) ha quest'area: un atleta con il suo accesso
  // che ci arriva (un link vecchio, l'«indietro» del browser dopo aver
  // cambiato account) torna nella sua, invece dell'errore 403 dei contratti.
  const roles = session ? decodeRolesFromAccessToken(session.accessToken) : [];
  if (roles.length > 0 && !roles.includes("CUSTOMER")) redirect("/area");
  const contracts = await apiFetchOrRedirectToLogin<ContractRead[]>("/contracts/mine");

  return (
    <CustomerClientPage
      contracts={contracts}
      email={session?.email}
      organizationId={session?.organizationId}
    />
  );
}
