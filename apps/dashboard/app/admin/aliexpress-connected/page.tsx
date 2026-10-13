import Link from "next/link";

/** Dove torna l'amministratore dopo aver autorizzato l'account AliExpress. */
export default async function AliexpressConnected({
  searchParams,
}: {
  searchParams: Promise<{ aliexpress?: string; message?: string }>;
}) {
  const { aliexpress, message } = await searchParams;
  const ok = aliexpress === "connected";
  return (
    <main className="min-h-screen flex items-center justify-center p-6 bg-slate-950 light:bg-slate-50">
      <div className="max-w-md w-full glass-card rounded-2xl p-6 space-y-4 text-center">
        <h1 className={`text-lg font-bold ${ok ? "text-emerald-400" : "text-amber-400"}`}>
          {ok ? "Account AliExpress collegato" : "Collegamento AliExpress non riuscito"}
        </h1>
        <p className="text-sm text-slate-300 light:text-slate-600">
          {ok
            ? "L'autorizzazione è salvata. Torna in Shop AliExpress e premi “Verifica connessione”."
            : message || "Riprova dal pannello Shop AliExpress."}
        </p>
        <Link href="/admin" className="inline-block px-4 py-2 rounded-xl bg-orange-500 text-white text-sm font-semibold">
          Torna all&apos;amministrazione
        </Link>
      </div>
    </main>
  );
}
