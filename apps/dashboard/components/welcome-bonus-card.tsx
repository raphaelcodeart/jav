"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";

type WelcomeBonusStatus = { available: boolean; amount_cents: number };

function javCash(cents: number, tag: string): string {
  return `${(cents / 100).toLocaleString(tag, { minimumFractionDigits: 0, maximumFractionDigits: 2 })} JavCash`;
}

async function fetchWelcomeBonus(t: ReturnType<typeof useI18n>["t"]): Promise<WelcomeBonusStatus> {
  const res = await fetch("/api/proxy/wallets/me/welcome-bonus");
  if (!res.ok) throw new Error(t("acct.bonus.checkError"));
  return res.json();
}

/** "Riscatta il tuo omaggio": the one-off welcome bonus, shown on the
    dashboard home until it's claimed and then never again. `available`
    is false both before the claim exists and forever after (see
    wallets/schemas.py::WelcomeBonusStatusRead), so this component simply
    renders nothing when it's false -- there is no "already claimed" state
    to design for.

    Claiming is idempotent server-side (the idempotency key is derived from
    the user id), so a double-click can't mint a second bonus even if the
    button's own disabled state were bypassed. */
export function WelcomeBonusCard() {
  const { t, fmt } = useI18n();
  const queryClient = useQueryClient();
  const { data: bonus } = useQuery({
    queryKey: ["wallet", "welcome-bonus"],
    queryFn: () => fetchWelcomeBonus(t),
  });

  const [claiming, setClaiming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justClaimed, setJustClaimed] = useState(false);

  async function handleClaim() {
    setClaiming(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/wallets/me/welcome-bonus/claim", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setJustClaimed(true);
      // Refresh everything the new credit touches: the bonus status itself
      // (so the card disappears), the wallet balance, and the home stat
      // cards that read from both.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["wallet"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting"] }),
      ]);
    } catch (err: any) {
      setError(err.message || t("acct.bonus.claimError"));
      setClaiming(false);
    }
  }

  // Success flash, shown briefly in place of the card before it goes for good.
  if (justClaimed) {
    return (
      <div className="rounded-2xl p-5 border border-emerald-500/30 bg-gradient-to-br from-emerald-500/15 to-transparent flex items-center gap-4 animate-scale-up">
        <span className="p-3 rounded-xl bg-emerald-500/20 text-emerald-400 shrink-0">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </span>
        <div>
          <p className="text-sm font-bold text-slate-900">{t("acct.bonus.claimed")}</p>
          <p className="text-xs text-slate-500">
            {t("acct.bonus.claimedText", { amount: javCash(bonus?.amount_cents ?? 0, fmt.tag) })}
          </p>
        </div>
      </div>
    );
  }

  if (!bonus?.available) return null;

  return (
    <div className="relative overflow-hidden rounded-2xl p-5 border border-brand-500/30 bg-gradient-to-br from-brand-500/15 via-brand-400/5 to-transparent">
      {/* Decorative glow -- pointer-events-none so it never eats the click. */}
      <div className="pointer-events-none absolute -top-10 -right-10 w-40 h-40 rounded-full bg-brand-500/20 blur-3xl" />
      <div className="relative flex flex-col sm:flex-row sm:items-center gap-4">
        <span className="p-3 rounded-xl bg-brand-500/20 text-brand-600 shrink-0 w-fit">
          <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zM5 12h14M5 12a2 2 0 110-4h14a2 2 0 110 4M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7" />
          </svg>
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-slate-900">
            {t("acct.bonus.title")}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">
            {t("acct.bonus.textBefore")}<strong className="text-brand-600">{javCash(bonus.amount_cents, fmt.tag)}</strong>{t("acct.bonus.textAfter")}
          </p>
          {error && <p className="text-xs text-rose-400 mt-1.5">{error}</p>}
        </div>
        <button
          onClick={handleClaim}
          disabled={claiming}
          className="shrink-0 px-5 py-2.5 rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 text-white text-xs font-bold shadow-lg shadow-brand-500/20 transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]"
        >
          {claiming ? t("acct.bonus.claiming") : t("acct.bonus.claim")}
        </button>
      </div>
    </div>
  );
}
