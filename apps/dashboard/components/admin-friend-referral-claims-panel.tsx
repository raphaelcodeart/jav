"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import type { FriendReferralAdminClaimRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

// Tab labels: net.claims.tab.<key>
const STATUS_TABS = ["REQUESTED", "FULFILLED", "REJECTED", "ALL"] as const;

const STATUS_COLORS: Record<string, string> = {
  REQUESTED: "bg-amber-500/10 text-amber-700 border-amber-500/20",
  FULFILLED: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  REJECTED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
};

async function fetchClaims(status: string): Promise<FriendReferralAdminClaimRead[]> {
  const res = await fetch(`/api/proxy/friend-referrals/admin/reward-claims?status_filter=${status}`);
  if (!res.ok) throw new Error("Impossibile caricare le richieste omaggio.");
  return res.json();
}

/** "Omaggi Inviti": the requests customers send when they hit a
 *  multiple of 5 activated referrals.
 *
 *  Deliberately NOT an automatic payout -- the business chose to keep a human
 *  in the loop so the gift can be anything (JavCash, a product, a voucher),
 *  decided case by case. The note written here is shown back to the customer.
 */
export function AdminFriendReferralClaimsPanel() {
  const { t, fmt } = useI18n();
  const formatDate = (iso: string) =>
    fmt.date(new Date(iso), { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("REQUESTED");
  const [handlingId, setHandlingId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);

  const { data: claims, error } = useQuery({
    queryKey: ["admin", "friend-referral-claims", statusFilter],
    queryFn: () => fetchClaims(statusFilter),
  });

  const pagination = usePagination(claims ?? []);

  async function handle(id: string, status: "FULFILLED" | "REJECTED") {
    setLoadingId(id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/friend-referrals/admin/reward-claims/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, note: note.trim() || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setHandlingId(null);
      setNote("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "friend-referral-claims"] });
    } catch (err: any) {
      setActionError(err.message || t("net.claims.updateError"));
    } finally {
      setLoadingId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">{t("net.claims.title")}</h3>
        <p className="text-xs text-slate-500 mt-1">
          {t("net.claims.intro1")} <strong>{t("net.claims.intro2")}</strong>{t("net.claims.intro3")}{" "}
          <strong>{t("net.claims.intro4")}</strong>{t("net.claims.intro5")}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((key) => (
          <button
            key={key}
            onClick={() => setStatusFilter(key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer border ${
              statusFilter === key
                ? "bg-brand-600 text-white border-brand-500"
                : " bg-slate-900/5 text-slate-600 border-slate-300 hover:bg-slate-100"
            }`}
          >
            {t(`net.claims.tab.${key}`)}
          </button>
        ))}
      </div>

      {error && <p className="text-sm text-rose-400">{t("net.claims.loadError")}</p>}
      {actionError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
          {actionError}
        </div>
      )}

      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 divide-y divide-slate-200 overflow-hidden">
        {claims === undefined ? (
          <p className="text-center py-8 text-slate-500 text-sm">{t("net.adminComm.loading")}</p>
        ) : claims.length === 0 ? (
          <p className="text-center py-8 text-slate-500 text-sm">{t("net.claims.empty")}</p>
        ) : (
          pagination.pageItems.map((c) => (
            <div key={c.id} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="font-medium text-slate-900">{c.referrer_name}</span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_COLORS[c.status]}`}>
                      {t.dyn(`net.claims.status.${c.status}`, c.status)}
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-brand-500/10 text-brand-600 border-brand-500/20">
                      {t("net.claims.milestone", { n: c.milestone })}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">
                    {c.referrer_email} · {t("net.claims.requestedOn", { date: formatDate(c.requested_at) })}
                    {c.handled_at ? ` · ${t("net.claims.handledOn", { date: formatDate(c.handled_at) })}` : ""}
                  </p>
                  {c.note && <p className="text-xs text-slate-500 mt-1">{t("net.claims.note", { note: c.note })}</p>}
                </div>
                {c.status === "REQUESTED" && handlingId !== c.id && (
                  <button
                    onClick={() => {
                      setHandlingId(c.id);
                      setNote("");
                      setActionError(null);
                    }}
                    className="shrink-0 px-4 py-2 rounded-xl bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-600 text-xs font-semibold transition cursor-pointer"
                  >
                    {t("net.claims.handle")}
                  </button>
                )}
              </div>

              {handlingId === c.id && (
                <div className="mt-4 pt-4 border-t border-slate-200 space-y-3">
                  <div className="space-y-1">
                    <label className=" font-semibold text-slate-600 uppercase block">
                      {t("net.claims.noteLabel")}
                    </label>
                    <input
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      maxLength={500}
                      placeholder={t("net.claims.notePlaceholder")}
                      className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500"
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => handle(c.id, "FULFILLED")}
                      disabled={loadingId === c.id}
                      className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                    >
                      {loadingId === c.id ? "..." : t("net.claims.fulfil")}
                    </button>
                    <button
                      onClick={() => handle(c.id, "REJECTED")}
                      disabled={loadingId === c.id}
                      className="px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                    >
                      {loadingId === c.id ? "..." : t("net.claims.reject")}
                    </button>
                    <button
                      onClick={() => setHandlingId(null)}
                      className="px-4 py-1.5 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer"
                    >
                      {t("common.cancel")}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
      <Pagination {...pagination} label={t("net.claims.pagLabel")} />
    </div>
  );
}
