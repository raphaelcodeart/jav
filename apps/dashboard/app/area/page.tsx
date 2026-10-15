import { redirect } from "next/navigation";
import { decodeRolesFromAccessToken, getSession } from "@/lib/session";

const ADMIN_ROLES = ["SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN", "BACK_OFFICE_OPERATOR", "ACCOUNTING_OPERATOR", "SALES_MANAGER"];

/** "A minha área" dal sito pubblico: ognuno nella sua, secondo il ruolo,
 *  con le stesse regole del login (app/login/page.tsx). Prima il link
 *  portava sempre all'area promoter, che per una famiglia non esiste. */
export default async function MyArea() {
  const session = await getSession();
  if (!session) redirect("/login");
  const roles = decodeRolesFromAccessToken(session.accessToken);
  if (roles.some((r) => ADMIN_ROLES.includes(r))) redirect("/admin");
  if (roles.includes("SECRETARY")) redirect("/club");
  if (roles.includes("CUSTOMER")) redirect("/customer");
  if (roles.includes("INSTRUCTOR")) redirect("/staff");
  if (roles.includes("ATHLETE")) redirect("/atleta");
  redirect("/promoter");
}
