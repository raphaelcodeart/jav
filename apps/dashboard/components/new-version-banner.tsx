"use client";

import { useEffect, useState } from "react";

const CHECK_EVERY_MS = 5 * 60 * 1000;

async function currentBuild(): Promise<string | null> {
  try {
    const res = await fetch("/api/version", { cache: "no-store" });
    if (!res.ok) return null;
    return ((await res.json()) as { build_id?: string }).build_id ?? null;
  } catch {
    return null;
  }
}

/** A page left open across a deploy keeps running the old code (Session 85:
 *  a Shop button kept saying "Nessun prodotto" after its fix was live). The
 *  build the page loaded with is remembered; when the server's changes --
 *  checked every few minutes and whenever the tab comes back into view --
 *  a banner asks to reload. Never reloads by itself: it could throw away a
 *  form being filled in. */
export function NewVersionBanner() {
  const [outdated, setOutdated] = useState(false);

  useEffect(() => {
    let loadedWith: string | null = null;
    let stopped = false;
    async function check() {
      const now = await currentBuild();
      if (stopped || now === null) return;
      if (loadedWith === null) loadedWith = now;
      else if (now !== loadedWith) setOutdated(true);
    }
    void check();
    const timer = window.setInterval(check, CHECK_EVERY_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void check();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  if (!outdated) return null;
  return (
    <div className="fixed bottom-4 inset-x-4 sm:inset-x-auto sm:right-4 sm:max-w-sm z-[100] rounded-2xl border border-orange-500/40 bg-slate-900 light:bg-white shadow-2xl p-4 flex items-center gap-3">
      <p className="text-xs text-slate-200 light:text-slate-700 flex-1">
        È disponibile una versione aggiornata dell&apos;app. Ricarica la pagina per usarla.
      </p>
      <button
        onClick={() => window.location.reload()}
        className="shrink-0 rounded-xl bg-orange-600 hover:bg-orange-500 px-3 py-2 text-xs font-semibold text-white cursor-pointer"
      >
        Aggiorna
      </button>
    </div>
  );
}
