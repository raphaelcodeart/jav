"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { useSpendPinStatus } from "@/components/javcash-confirm-code";
import type { SpendPinStatusRead, TicketRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

const card = "glass-card rounded-2xl p-6 border-slate-200 bg-white/70";
const input = "w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-brand-500";
const label = "block font-semibold text-slate-500 mb-1";

/** Session 87: le Impostazioni del cliente. Per ora una cosa sola: come
 *  confermare l'uso dei JavCash al checkout -- il codice via email di
 *  sempre, oppure un PIN di quattro cifre scelto dal cliente. Scegliere il
 *  PIN obbliga a crearlo subito: un metodo di conferma non può restare
 *  acceso senza niente da confermare. */
export function CustomerSettingsPanel() {
  const { t } = useI18n();
  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h2 className="text-lg font-bold text-slate-900">{t("acct.settings.title")}</h2>
        <p className="text-sm text-slate-500">{t("acct.settings.subtitle")}</p>
      </div>
      <SpendPinCard />
      <AccountClosureCard />
    </div>
  );
}

type Mode = "idle" | "set" | "disable";

function SpendPinCard() {
  const { t, fmt } = useI18n();
  const queryClient = useQueryClient();
  const { data: status, isLoading } = useSpendPinStatus();
  const [mode, setMode] = useState<Mode>("idle");
  const [pin, setPin] = useState("");
  const [pinConfirm, setPinConfirm] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const enabled = !!status?.enabled;
  const onlyDigits = (v: string) => v.replace(/\D/g, "").slice(0, 4);

  function open(next: Mode) {
    setMode(next);
    setPin("");
    setPinConfirm("");
    setPassword("");
    setMessage(null);
  }

  async function submit() {
    setBusy(true);
    setMessage(null);
    try {
      const res =
        mode === "set"
          ? await fetch("/api/proxy/auth/me/spend-pin", {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ pin, password }),
            })
          : await fetch("/api/proxy/auth/me/spend-pin/disable", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ password }),
            });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const next: SpendPinStatusRead = await res.json();
      queryClient.setQueryData(["me", "spend-pin"], next);
      setMessage({
        ok: true,
        text:
          mode === "set"
            ? enabled
              ? t("acct.settings.pinChanged")
              : t("acct.settings.pinEnabled")
            : t("acct.settings.pinDisabled"),
      });
      setMode("idle");
      setPin("");
      setPinConfirm("");
      setPassword("");
    } catch (err) {
      setMessage({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const pinMismatch = pinConfirm.length === 4 && pin !== pinConfirm;
  const canSubmit =
    !busy && password.length > 0 && (mode === "disable" || (pin.length === 4 && pin === pinConfirm));

  return (
    <div className={`${card} space-y-4`}>
      <div>
        <h3 className="text-sm font-bold text-slate-900">{t("acct.settings.pinTitle")}</h3>
        <p className="text-xs text-slate-500 mt-1 leading-relaxed">
          {t("acct.settings.pinIntro")}
        </p>
      </div>

      {isLoading ? (
        <div className="h-24 rounded-xl bg-slate-900/5 animate-pulse" />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <MethodOption
            active={!enabled}
            title={t("acct.settings.emailMethod")}
            text={t("acct.settings.emailMethodText")}
            onClick={() => (enabled ? open("disable") : undefined)}
          />
          <MethodOption
            active={enabled}
            title={t("acct.settings.pinMethod")}
            text={t("acct.settings.pinMethodText")}
            onClick={() => (enabled ? undefined : open("set"))}
          />
        </div>
      )}

      {status?.locked_until && (
        <p className="text-xs text-amber-700">
          {t("acct.settings.pinLocked", { time: new Date(status.locked_until).toLocaleTimeString(fmt.tag, { hour: "2-digit", minute: "2-digit" }) })}
        </p>
      )}

      {enabled && mode === "idle" && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => open("set")}
            className="px-4 py-2 rounded-xl border border-slate-300 text-xs font-semibold text-slate-700 hover:bg-slate-900/5 cursor-pointer"
          >
            {t("acct.settings.changePin")}
          </button>
          <button
            onClick={() => open("disable")}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-slate-900/5 cursor-pointer"
          >
            {t("acct.settings.backToEmail")}
          </button>
        </div>
      )}

      {mode !== "idle" && (
        <div className="space-y-3 p-4 rounded-xl border border-slate-200">
          <p className="text-xs font-semibold text-slate-900">
            {mode === "disable" ? t("acct.settings.backToEmail") : enabled ? t("acct.settings.changeThePin") : t("acct.settings.createPin")}
          </p>
          {mode === "set" && (
            <div className="grid grid-cols-2 gap-3 max-w-xs">
              <div>
                <span className={label}>{t("acct.settings.newPin")}</span>
                <input
                  type="password"
                  inputMode="numeric"
                  autoComplete="new-password"
                  maxLength={4}
                  value={pin}
                  onChange={(e) => setPin(onlyDigits(e.target.value))}
                  className={`${input} text-center font-mono tracking-[0.4em]`}
                />
              </div>
              <div>
                <span className={label}>{t("acct.settings.repeatPin")}</span>
                <input
                  type="password"
                  inputMode="numeric"
                  autoComplete="new-password"
                  maxLength={4}
                  value={pinConfirm}
                  onChange={(e) => setPinConfirm(onlyDigits(e.target.value))}
                  className={`${input} text-center font-mono tracking-[0.4em]`}
                />
              </div>
            </div>
          )}
          {mode === "set" && (
            <p className="text-[11px] text-slate-500">
              {t("acct.settings.pinRules")}
            </p>
          )}
          {pinMismatch && <p className="text-[11px] text-rose-400">{t("acct.settings.pinMismatch")}</p>}
          <div className="max-w-xs">
            <span className={label}>{t("acct.settings.password")}</span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={input}
            />
            <span className="block text-[11px] text-slate-500 mt-1">
              {t("acct.settings.passwordHint")}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
            >
              {busy ? t("acct.settings.saving") : mode === "disable" ? t("acct.settings.useEmail") : enabled ? t("acct.settings.changePin") : t("acct.settings.enablePin")}
            </button>
            <button
              onClick={() => open("idle")}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-slate-900/5 cursor-pointer"
            >
              {t("common.cancel")}
            </button>
          </div>
        </div>
      )}

      {message && (
        <p className={`text-xs ${message.ok ? "text-emerald-400" : "text-rose-400"}`}>{message.text}</p>
      )}
    </div>
  );
}

function MethodOption({
  active,
  title,
  text,
  onClick,
}: {
  active: boolean;
  title: string;
  text: string;
  onClick: () => void;
}) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`text-left p-4 rounded-xl border transition cursor-pointer ${
        active
          ? "border-brand-500/60 bg-brand-500/10"
          : " border-slate-200 hover:bg-slate-900/5"
      }`}
    >
      <div className="flex items-center gap-2">
        <span
          className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
            active ? "border-brand-500" : "border-slate-500"
          }`}
        >
          {active && <span className="w-2 h-2 rounded-full bg-brand-500" />}
        </span>
        <span className="text-sm font-semibold text-slate-900">{title}</span>
        {active && <span className="ml-auto text-[10px] font-bold uppercase tracking-wide text-brand-600">{t("acct.settings.inUse")}</span>}
      </div>
      <p className=" text-slate-500 mt-1.5 pl-6">{text}</p>
    </button>
  );
}

/** Session 89: «Richiedi chiusura account». Non cancella niente da sola:
 *  apre un ticket allo staff (che riceve anche l'email a info@example.com)
 *  e il cliente la segue dall'Assistenza. La chiusura la fa lo staff, dopo
 *  aver sistemato contratti, ordini e JavCash ancora aperti. */
function AccountClosureCard() {
  const { t, fmt } = useI18n();
  const queryClient = useQueryClient();
  const { data: pending, isLoading } = useQuery({
    queryKey: ["support", "account-closure"],
    queryFn: async (): Promise<TicketRead | null> => {
      const res = await fetch("/api/proxy/support/tickets/account-closure");
      if (!res.ok) return null;
      return res.json();
    },
  });
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/support/tickets/account-closure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: reason.trim() || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setConfirming(false);
      setReason("");
      await queryClient.invalidateQueries({ queryKey: ["support", "account-closure"] });
      await queryClient.invalidateQueries({ queryKey: ["support"] });
    } catch (err: any) {
      setError(err.message || t("acct.settings.closureError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={card}>
      <h3 className="text-sm font-bold text-slate-900">{t("acct.settings.closureTitle")}</h3>
      {isLoading ? null : pending ? (
        <p className="text-sm text-slate-500 mt-2">
          {t("acct.settings.closurePending", { date: fmt.date(new Date(pending.created_at), { day: "numeric", month: "long", year: "numeric" }) })}
        </p>
      ) : (
        <>
          <p className="text-sm text-slate-500 mt-2">
            {t("acct.settings.closureIntro")}
          </p>
          {!confirming ? (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="mt-4 px-4 py-2 rounded-xl border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs font-semibold transition cursor-pointer"
            >
              {t("acct.settings.closureRequest")}
            </button>
          ) : (
            <div className="mt-4 space-y-3">
              <div>
                <label className={label}>{t("acct.settings.closureReason")}</label>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={1000}
                  rows={3}
                  className={input}
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={submit}
                  disabled={busy}
                  className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition cursor-pointer disabled:opacity-50"
                >
                  {busy ? t("acct.wallet.sending") : t("acct.settings.closureConfirm")}
                </button>
                <button
                  type="button"
                  onClick={() => { setConfirming(false); setError(null); }}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer"
                >
                  {t("common.cancel")}
                </button>
              </div>
            </div>
          )}
          {error && <p className="text-xs text-rose-400 mt-3">{error}</p>}
        </>
      )}
    </div>
  );
}
