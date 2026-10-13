"use client";

export function LogoutButton({ className = "" }: { className?: string }) {
  async function handleLogout() {
    // A full page load, and whatever the call answered (Session 85): a soft
    // router.push could hang on a page left open across a deploy, leaving
    // "Esci" doing nothing.
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    window.location.assign("/login");
  }

  return (
    <button
      onClick={handleLogout}
      className={`flex items-center gap-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 hover:border-rose-500/30 px-4 py-2 text-xs font-semibold text-rose-400 light:text-rose-600 transition cursor-pointer ${className}`}
    >
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
      </svg>
      Esci
    </button>
  );
}
