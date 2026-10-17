"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import { ShareButtons } from "@/components/share-buttons";
import type { FriendReferralSummaryRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

const STATE_COLORS: Record<string, string> = {
  INVITED: " bg-slate-900/5 text-slate-400 border-slate-300",
  IN_PROGRESS: "bg-amber-500/10 text-amber-700 border-amber-500/20",
  ACTIVE: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
};

async function fetchSummary(): Promise<FriendReferralSummaryRead> {
  const res = await fetch("/api/proxy/friend-referrals/me");
  if (!res.ok) throw new Error("Impossibile caricare i tuoi inviti.");
  return res.json();
}

/** "Invita un amico": every account's own one-level invite list.
 *
 * Deliberately NOT the commercial network. There are no commissions here and
 * no hierarchy -- it exists so somebody who is not a promoter can still see
 * who they brought in, and so the "un omaggio ogni 5 attivati" count has
 * somewhere to live. Where an invited customer lands in the commercial tree
 * is decided entirely by the backend, by the existing rules, and is not shown
 * or implied anywhere on this screen.
 */
export function FriendReferralsPanel({ organizationId }: { organizationId?: string }) {
  const { t, fmt } = useI18n();
  const formatDate = (iso: string) => fmt.date(new Date(iso), { day: "numeric", month: "long", year: "numeric" });
  const queryClient = useQueryClient();
  const { data, error } = useQuery({ queryKey: ["friend-referrals", "me"], queryFn: fetchSummary });
  const [claimLoading, setClaimLoading] = useState(false);
  const [claimError, setClaimError] = useState<string | null>(null);

  const pagination = usePagination(data?.referrals ?? []);

  function personalLink(): string {
    if (typeof window === "undefined" || !data) return "";
    const url = new URL(`/r/${data.code}`, window.location.origin);
    if (organizationId) url.searchParams.set("org", organizationId);
    return url.toString();
  }

  async function handleClaim() {
    setClaimLoading(true);
    setClaimError(null);
    try {
      const res = await fetch("/api/proxy/friend-referrals/me/reward-claims", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["friend-referrals", "me"] });
    } catch (err: any) {
      setClaimError(err.message || t("net.friends.claimError"));
    } finally {
      setClaimLoading(false);
    }
  }

  if (error) {
    return <p className="text-sm text-rose-400">{t("net.friends.loadError")}</p>;
  }
  if (!data) {
    return <div className="glass-card rounded-2xl p-6 border-slate-200 animate-pulse h-40" />;
  }

  const towardsNext = data.active_total % data.reward_every;
  const progress = data.claimable_milestone ? 100 : (towardsNext / data.reward_every) * 100;

  return (
    <div className="space-y-6">
      {/* Link personale */}
      <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
        <h3 className="text-lg font-semibold text-slate-900">{t("net.promoter.nav.invita_amici")}</h3>
        <p className="text-xs text-slate-500 mt-1 mb-4">
          {t("net.friends.intro1")} <strong>{t("net.friends.every", { n: data.reward_every })}</strong>
          {t("net.friends.intro2")}{" "}
          <strong>{data.reward_description}</strong>
          {t("net.friends.intro3", { n: data.reward_every, n2: data.reward_every * 2, n3: data.reward_every * 3 })}
        </p>
        <code className="block w-full truncate rounded-xl bg-slate-900/5 border border-slate-300 px-3 py-2.5 text-xs font-mono text-slate-600 mb-3">
          {personalLink() || `…/r/${data.code}`}
        </code>
        {/* One tap straight into the app they actually use. "Copia link" is
            still there for everything else. */}
        <ShareButtons
          url={personalLink()}
          text={t("net.friends.shareText")}
        />
      </div>

      {/* Avanzamento verso l'omaggio */}
      <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-4">
          <div>
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">
              {t("net.friends.activeLabel")}
            </p>
            <p className="text-3xl font-bold text-slate-900 tabular-nums">
              {data.active_total}
              <span className="text-base font-semibold text-slate-500"> / {t("net.friends.signedUp", { n: data.invited_total })}</span>
            </p>
          </div>
          {data.claimable_milestone ? (
            <button
              onClick={handleClaim}
              disabled={claimLoading}
              className="px-5 py-2.5 rounded-xl text-xs font-bold bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-white shadow-lg shadow-emerald-500/20 transition cursor-pointer disabled:opacity-50"
            >
              {claimLoading ? t("net.friends.sending") : t("net.friends.claim", { reward: data.reward_description })}
            </button>
          ) : (
            <p className="text-xs text-slate-500">
              {t("net.friends.missing1")} <strong className="text-brand-600">{data.missing_for_next_reward}</strong> {t("net.friends.missing2")}{" "}
              {data.reward_description}
            </p>
          )}
        </div>

        <div className="h-2 rounded-full bg-slate-900/10 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-400 transition-all"
            style={{ width: `${Math.min(100, progress)}%` }}
          />
        </div>

        {claimError && (
          <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
            {claimError}
          </div>
        )}

        {data.claims.length > 0 && (
          <div className="mt-5 pt-4 border-t border-slate-200 space-y-2">
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">{t("net.friends.yourClaims")}</p>
            {data.claims.map((c) => (
              <div key={c.id} className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className=" text-slate-600">
                  {t("net.friends.claimFor", { n: c.milestone })}
                </span>
                <div className="flex items-center gap-2">
                  {c.note && <span className="text-slate-500">{c.note}</span>}
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                      c.status === "FULFILLED"
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        : c.status === "REJECTED"
                          ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                          : "bg-amber-500/10 text-amber-700 border-amber-500/20"
                    }`}
                  >
                    {t.dyn(`net.friends.claimStatus.${c.status}`, c.status)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* La lista */}
      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="px-5 pt-5 pb-3">
          <h4 className="text-sm font-semibold text-slate-900">{t("net.friends.listTitle")}</h4>
        </div>
        {data.referrals.length === 0 ? (
          <p className="text-center py-10 text-slate-500 text-sm">
            {t("net.friends.empty")}
          </p>
        ) : (
          <>
            <div className="divide-y divide-slate-200">
              {pagination.pageItems.map((r) => (
                <div key={r.id} className="px-5 py-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-slate-900">{r.display_name}</p>
                    <p className="text-[11px] text-slate-500">{t("net.friends.joinedOn", { date: formatDate(r.invited_at) })}</p>
                  </div>
                  <span
                    className={`px-2.5 py-1 rounded-full text-[10px] font-bold border ${STATE_COLORS[r.state]}`}
                  >
                    {t.dyn(`net.friends.state.${r.state}`, r.state)}
                  </span>
                </div>
              ))}
            </div>
            <div className="px-5 pb-4">
              <Pagination {...pagination} label={t("net.friends.pagLabel")} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
