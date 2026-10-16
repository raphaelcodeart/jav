import Image from "next/image";
import { redirect } from "next/navigation";
import { GamesHub } from "@/components/game/games-hub";
import { getSession } from "@/lib/session";

/** JAV Games a pagina intera: per l'atleta con il suo accesso (dalla sua
 *  area) e per chiunque sia entrato. La famiglia la trova anche nel menu. */
export default async function GamesPage() {
  const session = await getSession();
  if (!session) redirect("/login");
  return (
    <div className="min-h-screen bg-gradient-to-b from-indigo-50/60 via-white to-white">
      <header className="sticky top-0 z-30 border-b border-ink-900/10 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <a href="/area" className="shrink-0"><Image src="/judoartevida-logo.jpg" alt="Judo Arte e Vida" width={110} height={48} className="h-9 w-auto" /></a>
          <span className="font-display text-lg text-ink-900">🎮 JAV Games</span>
          <a href="/area" className="ml-auto rounded-xl px-3 py-2 text-sm font-semibold text-ink-600 hover:bg-ink-50">← A minha área</a>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:py-10">
        <GamesHub />
      </main>
    </div>
  );
}
