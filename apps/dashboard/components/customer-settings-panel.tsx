"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { useSpendPinStatus } from "@/components/javcash-confirm-code";
import type { SpendPinStatusRead, TicketRead } from "@/lib/types";

const card = "glass-card rounded-2xl p-6 border-slate-200 bg-white/70";
const input = "w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-brand-500";
const label = "block font-semibold text-slate-500 mb-1";

/** Session 87: le Impostazioni del cliente. Per ora una cosa sola: come
 *  confermare l'uso dei JavCash al checkout -- il codice via email di
 *  sempre, oppure un PIN di quattro cifre scelto dal cliente. Scegliere il
 *  PIN obbliga a crearlo subito: un metodo di conferma non può restare
 *  acceso senza niente da confermare. */
export function CustomerSettingsPanel() {
  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h2 className="text-lg font-bold text-slate-900">Impostazioni</h2>
        <p className="text-sm text-slate-500">Le preferenze del tuo account.</p>
      </div>
      <SpendPinCard />
      <AccountClosureCard />
    </div>
  );
}

type Mode = "idle" | "set" | "disable";

function SpendPinCard() {
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
              ? "PIN cambiato. Ti abbiamo mandato un'email di conferma."
              : "PIN attivato: da ora ai checkout ti chiediamo il PIN invece di mandarti un codice."
            : "Fatto: da ora ti mandiamo di nuovo il codice via email.",
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
        <h3 className="text-sm font-bold text-slate-900">Conferma dei pagamenti con JavCash</h3>
        <p className="text-xs text-slate-500 mt-1 leading-relaxed">
          Quando usi i tuoi JavCash in un acquisto ti chiediamo una conferma. Puoi riceverla ogni volta come
          codice via email, oppure scegliere un PIN di 4 cifre da digitare al momento del pagamento.
        </p>
      </div>

      {isLoading ? (
        <div className="h-24 rounded-xl bg-slate-900/5 animate-pulse" />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <MethodOption
            active={!enabled}
            title="Codice via email"
            text="Ogni volta ti mandiamo un codice nuovo, valido 10 minuti."
            onClick={() => (enabled ? open("disable") : undefined)}
          />
          <MethodOption
            active={enabled}
            title="PIN personale"
            text="Un PIN di 4 cifre scelto da te. Niente email da aspettare."
            onClick={() => (enabled ? undefined : open("set"))}
          />
        </div>
      )}

      {status?.locked_until && (
        <p className="text-xs text-amber-700">
          Il PIN è bloccato per troppi tentativi sbagliati fino alle{" "}
          {new Date(status.locked_until).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}: nel
          frattempo ti mandiamo il codice via email.
        </p>
      )}

      {enabled && mode === "idle" && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => open("set")}
            className="px-4 py-2 rounded-xl border border-slate-300 text-xs font-semibold text-slate-700 hover:bg-slate-900/5 cursor-pointer"
          >
            Cambia PIN
          </button>
          <button
            onClick={() => open("disable")}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-slate-900/5 cursor-pointer"
          >
            Torna al codice via email
          </button>
        </div>
      )}

      {mode !== "idle" && (
        <div className="space-y-3 p-4 rounded-xl border border-slate-200">
          <p className="text-xs font-semibold text-slate-900">
            {mode === "disable" ? "Torna al codice via email" : enabled ? "Cambia il PIN" : "Crea il tuo PIN"}
          </p>
          {mode === "set" && (
            <div className="grid grid-cols-2 gap-3 max-w-xs">
              <div>
                <span className={label}>Nuovo PIN</span>
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
                <span className={label}>Ripeti il PIN</span>
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
              Quattro cifre, non tutte uguali e non in fila (niente 0000 o 1234). Dopo 5 tentativi sbagliati il PIN
              si blocca per 15 minuti.
            </p>
          )}
          {pinMismatch && <p className="text-[11px] text-rose-400">I due PIN non coincidono.</p>}
          <div className="max-w-xs">
            <span className={label}>Password del tuo account</span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={input}
            />
            <span className="block text-[11px] text-slate-500 mt-1">
              Serve a confermare che sei tu: nessuno può cambiare il PIN solo perché ha il tuo telefono sbloccato.
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
            >
              {busy ? "Salvo…" : mode === "disable" ? "Usa il codice via email" : enabled ? "Cambia PIN" : "Attiva PIN"}
            </button>
            <button
              onClick={() => open("idle")}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-slate-900/5 cursor-pointer"
            >
              Annulla
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
        {active && <span className="ml-auto text-[10px] font-bold uppercase tracking-wide text-brand-600">In uso</span>}
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
      setError(err.message || "Impossibile inviare la richiesta.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={card}>
      <h3 className="text-sm font-bold text-slate-900">Chiusura dell&apos;account</h3>
      {isLoading ? null : pending ? (
        <p className="text-sm text-slate-500 mt-2">
          Hai chiesto la chiusura dell&apos;account il{" "}
          {new Date(pending.created_at).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" })}.
          Il nostro staff la sta gestendo e ti contatterà; puoi seguirla dalla sezione Assistenza.
        </p>
      ) : (
        <>
          <p className="text-sm text-slate-500 mt-2">
            Vuoi chiudere il tuo account Jav? Invia la richiesta: lo staff la prende in carico e ti contatta
            per sistemare eventuali contratti, ordini o JavCash ancora aperti.
          </p>
          {!confirming ? (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="mt-4 px-4 py-2 rounded-xl border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs font-semibold transition cursor-pointer"
            >
              Richiedi chiusura account
            </button>
          ) : (
            <div className="mt-4 space-y-3">
              <div>
                <label className={label}>Perché vuoi chiudere l&apos;account? (facoltativo)</label>
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
                  {busy ? "Invio..." : "Conferma la richiesta"}
                </button>
                <button
                  type="button"
                  onClick={() => { setConfirming(false); setError(null); }}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer"
                >
                  Annulla
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
