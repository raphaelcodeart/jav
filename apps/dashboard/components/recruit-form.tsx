"use client";

import { useEffect, useState } from "react";
import { friendlyApiError } from "@/lib/api-error";
import type { RankRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

/** Lets a promoter enroll a new direct collaborator under themselves (calls the
 * network.recruit-gated POST /network/agents/recruit -- scoped server-side to
 * the caller's own agent as parent, see apps/api/app/domains/network/router.py). */
export function RecruitForm({ onRecruited }: { onRecruited: () => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [ranks, setRanks] = useState<RankRead[]>([]);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [promoterCode, setPromoterCode] = useState("");
  const [rankId, setRankId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!open) return;
    fetch("/api/proxy/commissions/ranks")
      .then((r) => r.json())
      .then(setRanks)
      .catch(() => setRanks([]));
  }, [open]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/network/agents/recruit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
          promoter_code: promoterCode,
          current_rank_id: rankId || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setSuccess(true);
      setFirstName("");
      setLastName("");
      setPromoterCode("");
      setRankId("");
      onRecruited();
      setTimeout(() => {
        setSuccess(false);
        setOpen(false);
      }, 1200);
    } catch (err: any) {
      setError(err.message || t("net.recruit.error"));
    } finally {
      setLoading(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-500/20 transition cursor-pointer"
      >
        {t("net.recruit.open")}
      </button>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-slate-900">{t("net.recruit.title")}</h3>
          <button onClick={() => setOpen(false)}
            className="p-1 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-900 transition cursor-pointer">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          {t("net.recruit.hint")}
        </p>

        {success ? (
          <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-center animate-scale-up">
            {t("net.recruit.success")}
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("net.recruit.firstName")}</label>
                <input required value={firstName} onChange={(e) => setFirstName(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("net.recruit.lastName")}</label>
                <input required value={lastName} onChange={(e) => setLastName(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-600 uppercase block">{t("net.promoter.code")}</label>
              <input required value={promoterCode} onChange={(e) => setPromoterCode(e.target.value)}
                placeholder={t("net.recruit.codePlaceholder")}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-brand-500" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-600 uppercase block">{t("net.recruit.initialRank")}</label>
              <select value={rankId} onChange={(e) => setRankId(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-white focus:border-brand-500">
                <option value="">{t("net.recruit.noRank")}</option>
                {ranks.map((r) => (
                  <option key={r.id} value={r.id}>{r.code} — {r.name}</option>
                ))}
              </select>
            </div>

            {error && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{error}</div>
            )}

            <div className="flex justify-end gap-3 mt-4">
              <button type="button" onClick={() => setOpen(false)}
                className="px-4 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 text-xs font-semibold text-slate-600 border border-slate-200 transition cursor-pointer">
                {t("common.cancel")}
              </button>
              <button type="submit" disabled={loading}
                className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                {loading ? t("net.recruit.submitting") : t("net.recruit.submit")}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
