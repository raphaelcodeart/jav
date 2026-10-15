import { AthleteAreaPage } from "@/components/club/athlete-area";

/** L'area dell'atleta: la sua (accesso da atleta) o, per il titolare del
 *  conto, quella di ognuno dei suoi atleti (?a=<id>). */
export default async function AthletePage({ searchParams }: { searchParams: Promise<{ a?: string }> }) {
  const { a } = await searchParams;
  return <AthleteAreaPage initialId={a ?? null} />;
}
