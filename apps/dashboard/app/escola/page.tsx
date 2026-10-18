import { ExtSchoolArea } from "@/components/ext-courses/school-area";
import { getSession } from "@/lib/session";

/** L'area della scuola e del treinador dei corsi esterni (extcourses):
 *  `?curso=<id>` apre quel corso (dalla scelta del club del treinador o da
 *  "Abrir como escola" della console). */
export default async function SchoolHome({ searchParams }: { searchParams: Promise<{ curso?: string }> }) {
  const [session, { curso }] = await Promise.all([getSession(), searchParams]);
  return <ExtSchoolArea email={session?.email} initialCourse={curso} />;
}
