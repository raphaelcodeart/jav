"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { SpendPinStatusRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

/** Session 87: come il cliente conferma l'uso dei JavCash. Lo leggono le
 *  Impostazioni e ogni checkout; il server resta l'unico a decidere (anche
 *  con il PIN acceso, se è bloccato, risponde EMAIL). */
export function useSpendPinStatus() {
  return useQuery({
    queryKey: ["me", "spend-pin"],
    queryFn: async (): Promise<SpendPinStatusRead> => {
      const res = await fetch("/api/proxy/auth/me/spend-pin");
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
    staleTime: 30_000,
  });
}

const linkButton =
  "text-[11px] font-semibold text-brand-600 hover:text-brand-600 cursor-pointer disabled:opacity-50";

/** La conferma dei JavCash dentro un checkout, uguale in tutti i negozi.
 *
 *  Con il PIN acceso chiede il PIN e non manda niente; altrimenti manda il
 *  codice via email come prima. «Non ricordi il PIN?» passa all'email per
 *  questo acquisto soltanto. Il codice resta nello stato del checkout
 *  (`code`), perché è il checkout a spedirlo con l'ordine; `requested`
 *  anche, perché è il checkout che lo azzera quando cambia l'importo. */
export function JavCashConfirmCode({
  requestUrl,
  requestBody,
  code,
  onCodeChange,
  requested,
  onRequestedChange,
  showSentNotice = false,
}: {
  requestUrl: string;
  requestBody: unknown;
  code: string;
  onCodeChange: (code: string) => void;
  requested: boolean;
  onRequestedChange: (requested: boolean) => void;
  /** «Codice inviato -- controlla la tua email» sopra il campo. */
  showSentNotice?: boolean;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { data: status } = useSpendPinStatus();
  const [viaEmail, setViaEmail] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const usePin = status?.method === "PIN" && !viaEmail;

  async function request(forceEmail: boolean) {
    setRequesting(true);
    setError(null);
    try {
      const res = await fetch(forceEmail ? `${requestUrl}?via=email` : requestUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const data: { method?: string } = await res.json().catch(() => ({}));
      if (data.method === "PIN") {
        // Il PIN è stato acceso in un'altra scheda: nessuna email è partita.
        await queryClient.invalidateQueries({ queryKey: ["me", "spend-pin"] });
        return;
      }
      if (forceEmail) {
        setViaEmail(true);
        onCodeChange("");
      }
      onRequestedChange(true);
    } catch (err) {
      setError((err as Error).message || t("acct.jcCode.sendError"));
    } finally {
      setRequesting(false);
    }
  }

  if (usePin) {
    return (
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="password"
            inputMode="numeric"
            autoComplete="off"
            maxLength={4}
            value={code}
            onChange={(e) => onCodeChange(e.target.value.replace(/\D/g, "").slice(0, 4))}
            placeholder={t("acct.jcCode.pinPlaceholder")}
            aria-label={t("acct.jcCode.pinAria")}
            className="w-full max-w-[140px] rounded-lg glass-input px-3 py-2 text-sm font-mono tracking-[0.4em] focus:border-brand-500"
          />
          <button type="button" onClick={() => request(true)} disabled={requesting} className={linkButton}>
            {requesting ? t("acct.jcCode.sending") : t("acct.jcCode.forgotPin")}
          </button>
        </div>
        {error && <p className="text-[11px] text-rose-400">{error}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {status?.locked_until && (
        <p className="text-[11px] text-amber-700">
          {t("acct.jcCode.locked")}
        </p>
      )}
      {!requested ? (
        <button
          type="button"
          onClick={() => request(false)}
          disabled={requesting}
          className="px-4 py-2 rounded-lg bg-brand-600/15 hover:bg-brand-600/25 border border-brand-500/30 text-xs font-semibold text-brand-600 transition cursor-pointer disabled:opacity-50"
        >
          {requesting ? t("acct.jcCode.sending") : t("acct.jcCode.confirmEmail")}
        </button>
      ) : (
        <>
          {showSentNotice && (
            <p className="text-[11px] text-emerald-400 flex items-center gap-1">
              <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
              </svg>
              {t("acct.jcCode.sent")}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <input
              inputMode="numeric"
              autoFocus
              value={code}
              onChange={(e) => onCodeChange(e.target.value)}
              placeholder={t("acct.jcCode.codePlaceholder")}
              className="w-full max-w-[200px] rounded-lg glass-input px-3 py-2 text-sm font-mono tracking-wider focus:border-brand-500"
            />
            <button type="button" onClick={() => request(true)} disabled={requesting} className={linkButton}>
              {t("acct.jcCode.resend")}
            </button>
          </div>
        </>
      )}
      {error && <p className="text-[11px] text-rose-400">{error}</p>}
    </div>
  );
}
