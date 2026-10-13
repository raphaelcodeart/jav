"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";

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

const input = "w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500";
const label = "block text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-1";

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
      setMessage({ ok: true, text: "Account sbloccato: il cliente ora può entrare." });
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
      <span className="text-slate-300 light:text-slate-700">
        {testo}
        {!ok && <span className="text-slate-500"> → {sePassa}</span>}
      </span>
    </li>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full sm:max-w-lg max-h-[92vh] overflow-y-auto rounded-t-3xl sm:rounded-2xl border border-white/10 light:border-slate-200 bg-slate-950 light:bg-white shadow-2xl animate-scale-up p-5 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-white light:text-slate-900">Sblocca l&apos;account</h3>
            <p className="text-xs text-slate-400 light:text-slate-500">{customerName}</p>
          </div>
          <button onClick={onClose} aria-label="Chiudi" className="p-1.5 rounded-lg text-slate-400 hover:bg-white/10 cursor-pointer">
            ✕
          </button>
        </div>

        {error && <p className="text-xs text-rose-400">{(error as Error).message}</p>}
        {!status && !error && <p className="text-xs text-slate-500">Caricamento…</p>}
        {status && (
          <>
            <ul className="space-y-1.5">
              {riga(status.email_verified, "Email confermata", "la segno come confermata")}
              {riga(status.privacy_accepted, "Privacy accettata", "la segno come accettata per conto del cliente")}
              {riga(status.profile_complete, "Profilo completo (codice fiscale e residenza)", "da completare qui sotto")}
            </ul>

            {!status.profile_complete && (
              <div className="space-y-3 p-3 rounded-xl border border-white/10 light:border-slate-200">
                <p className="text-[11px] text-slate-400 light:text-slate-600">
                  Codice fiscale e indirizzo non si possono inventare: controllali. Dove li conosciamo già (scheda del
                  cliente, ultima pratica) sono proposti.
                </p>
                <div>
                  <span className={label}>Codice fiscale</span>
                  <input className={input} value={field("fiscal_code")} onChange={(e) => setEdits({ ...edits, fiscal_code: e.target.value.toUpperCase() })} />
                </div>
                <div>
                  <span className={label}>Indirizzo di residenza</span>
                  <input className={input} value={field("residence_street")} onChange={(e) => setEdits({ ...edits, residence_street: e.target.value })} />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <span className={label}>Città</span>
                    <input className={input} value={field("residence_city")} onChange={(e) => setEdits({ ...edits, residence_city: e.target.value })} />
                  </div>
                  <div>
                    <span className={label}>Provincia</span>
                    <input className={input} maxLength={2} value={field("residence_province")} onChange={(e) => setEdits({ ...edits, residence_province: e.target.value.toUpperCase() })} />
                  </div>
                  <div>
                    <span className={label}>CAP</span>
                    <input className={input} value={field("residence_postal_code")} onChange={(e) => setEdits({ ...edits, residence_postal_code: e.target.value })} />
                  </div>
                </div>
              </div>
            )}

            <p className="text-[11px] text-amber-300 light:text-amber-700">
              La privacy risulterà accettata a tuo nome, per conto del cliente, e l&apos;operazione resta nel registro.
              Fallo solo se il cliente ha dato il consenso in un altro modo (a voce, per iscritto).
            </p>

            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={unlock}
                disabled={busy || !!tutto || message?.ok}
                className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
              >
                {busy ? "Sblocco…" : tutto ? "Già tutto a posto" : "Sblocca e rendi attivo"}
              </button>
              <button onClick={onClose} className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-white/5 cursor-pointer">
                Chiudi
              </button>
            </div>
            {message && <p className={`text-xs ${message.ok ? "text-emerald-400" : "text-rose-400"}`}>{message.text}</p>}
          </>
        )}
      </div>
    </div>
  );
}
