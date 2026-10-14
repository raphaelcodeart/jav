import { getSession } from "@/lib/session";
import { SecretaryClientPage } from "@/components/club/secretary-client-page";

/** L'area della segreteria di un club (ruolo SECRETARY): il suo club e
 *  nient'altro. Quale club, lo sa l'API dall'account (users.club_id). */
export default async function SecretaryHome() {
  const session = await getSession();
  return <SecretaryClientPage email={session?.email} />;
}
