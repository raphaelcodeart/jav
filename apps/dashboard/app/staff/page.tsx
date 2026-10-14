import { getSession } from "@/lib/session";
import { StaffClientPage } from "@/components/club/staff-client-page";

/** The instructor's area (role INSTRUCTOR): attendance and belts, nothing else. */
export default async function StaffHome() {
  const session = await getSession();
  return <StaffClientPage email={session?.email} />;
}
