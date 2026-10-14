import { decodeRolesFromAccessToken, getSession } from "@/lib/session";
import { AdminConsole } from "@/components/admin/admin-console";

/** La console della piattaforma JudoArteVida (staff della piattaforma). */
export default async function AdminDashboard() {
  const session = await getSession();
  const isSuperAdmin = session ? decodeRolesFromAccessToken(session.accessToken).includes("SUPER_ADMIN") : false;
  return <AdminConsole email={session?.email} isSuperAdmin={isSuperAdmin} />;
}
