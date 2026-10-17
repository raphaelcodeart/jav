"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";

type AccountStatus = {
  email_verified: boolean;
  privacy_accepted: boolean;
  profile_complete: boolean;
  missing_profile_fields: string[];
  suggested_profile: {
    fiscal_code: string | null;
    residence_street: string | null;
    residence_city: string | null;
    residence_province: string | null;
    residence_postal_code: string | null;
  };
};

const input = "w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500";
const label = "block font-semibold text-slate-500 uppercase tracking-wide mb-1";

/** Session 88: il superadmin sblocca un cliente fermo davanti ai controlli
 *  d'ingresso (email da confermare, privacy da accettare, profilo da
 *  completare), per esempio perché le email non gli arrivano. Email e
 *  privacy si segnano come fatte; codice fiscale e indirizzo vanno scritti,
 *  proposti dai dati che il cliente ha già dato nelle pratiche. */
export function UnlockAccountModal({
  userId,
  customerName,
  onClose,
}: {
  userId: string;
  customerName: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { data: status, error } = useQuery({
    queryKey: ["admin", "users", userId, "account-status"],
    queryFn: async (): Promise<AccountStatus> => {
      const res = await fetch(`/api/proxy/users/${userId}/account-status`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
  });
  const [edits, setEdits] = useState<Partial<AccountStatus["suggested_profile"]>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const profile = { ...(status?.suggested_profile ?? {}), ...edits };
  const field = (key: keyof AccountStatus["suggested_profile"]) => profile[key] ?? "";

  async function unlock() {
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch(`/api/proxy/users/${userId}/unlock`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          status?.profile_complete
            ? null
            : {
                fiscal_code: field("fiscal_code"),
                residence_street: field("residence_street"),
                residence_city: field("residence_city"),
                residence_province: field("residence_province"),
                residence_postal_code: field("residence_postal_code"),
              },
        ),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
      setMessage({ ok: true, text: t("adm.unlock.done") });
    } catch (err) {
      setMessage({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const tutto = status && status.email_verified && status.privacy_accepted && status.profile_complete;
  const riga = (ok: boolean | undefined, testo: string, sePassa: string) => (
    <li className="flex items-center gap-2 text-xs">
      <span className={ok ? "text-emerald-400" : "text-rose-400"}>{ok ? "✓" : "✗"}</span>
      <span className=" text-slate-700">
        {testo}
        {!ok && <span className="text-slate-500"> → {sePassa}</span>}
      </span>
    </li>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full sm:max-w-lg max-h-[92vh] overflow-y-auto rounded-t-3xl sm:rounded-2xl border border-slate-200 bg-white shadow-2xl animate-scale-up p-5 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-slate-900">{t("adm.unlock.title")}</h3>
            <p className="text-xs text-slate-500">{customerName}</p>
          </div>
          <button onClick={onClose} aria-label={t("common.close")} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 cursor-pointer">
            ✕
          </button>
        </div>

        {error && <p className="text-xs text-rose-400">{(error as Error).message}</p>}
        {!status && !error && <p className="text-xs text-slate-500">{t("adm.unlock.loading")}</p>}
        {status && (
          <>
            <ul className="space-y-1.5">
              {riga(status.email_verified, t("adm.unlock.emailVerified"), t("adm.unlock.emailVerifiedFix"))}
              {riga(status.privacy_accepted, t("adm.unlock.privacyAccepted"), t("adm.unlock.privacyAcceptedFix"))}
              {riga(status.profile_complete, t("adm.unlock.profileComplete"), t("adm.unlock.profileCompleteFix"))}
            </ul>

            {!status.profile_complete && (
              <div className="space-y-3 p-3 rounded-xl border border-slate-200">
                <p className=" text-slate-600">
                  {t("adm.unlock.profileHint")}
                </p>
                <div>
                  <span className={label}>{t("adm.unlock.fiscalCode")}</span>
                  <input className={input} value={field("fiscal_code")} onChange={(e) => setEdits({ ...edits, fiscal_code: e.target.value.toUpperCase() })} />
                </div>
                <div>
                  <span className={label}>{t("adm.unlock.street")}</span>
                  <input className={input} value={field("residence_street")} onChange={(e) => setEdits({ ...edits, residence_street: e.target.value })} />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <span className={label}>{t("adm.unlock.city")}</span>
                    <input className={input} value={field("residence_city")} onChange={(e) => setEdits({ ...edits, residence_city: e.target.value })} />
                  </div>
                  <div>
                    <span className={label}>{t("adm.unlock.province")}</span>
                    <input className={input} maxLength={2} value={field("residence_province")} onChange={(e) => setEdits({ ...edits, residence_province: e.target.value.toUpperCase() })} />
                  </div>
                  <div>
                    <span className={label}>{t("adm.unlock.postalCode")}</span>
                    <input className={input} value={field("residence_postal_code")} onChange={(e) => setEdits({ ...edits, residence_postal_code: e.target.value })} />
                  </div>
                </div>
              </div>
            )}

            <p className=" text-amber-700">
              {t("adm.unlock.privacyWarning")}
            </p>

            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={unlock}
                disabled={busy || !!tutto || message?.ok}
                className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
              >
                {busy ? t("adm.unlock.unlocking") : tutto ? t("adm.unlock.allGood") : t("adm.unlock.unlock")}
              </button>
              <button onClick={onClose} className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-slate-100 cursor-pointer">
                {t("common.close")}
              </button>
            </div>
            {message && <p className={`text-xs ${message.ok ? "text-emerald-400" : "text-rose-400"}`}>{message.text}</p>}
          </>
        )}
      </div>
    </div>
  );
}
