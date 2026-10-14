"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { formatEuroCents as euro } from "@/lib/product-audience";
import type { ContractRequestPaymentOptionRead, ContractRequestPaymentOptionsRead } from "@/lib/types";

function javCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} JavCash`;
}

export function useRequestPaymentOptions(requestId: string) {
  return useQuery<ContractRequestPaymentOptionsRead>({
    queryKey: ["contract-request", requestId, "payment-options"],
    queryFn: async () => {
      const res = await fetch(`/api/proxy/contract-requests/${requestId}/payment-options`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
    // The administration confirms the transfer from its own screen: coming
    // back to this tab must show it.
    refetchOnWindowFocus: true,
  });
}

function OptionCard({
  option,
  selected,
  onSelect,
  vatIncluded,
}: {
  option: ContractRequestPaymentOptionRead;
  selected: boolean;
  onSelect: () => void;
  /** Session 85: the amounts are final, VAT inside -- said on a business pratica. */
  vatIncluded: boolean;
}) {
  return (
    <button
      onClick={() => option.available && onSelect()}
      disabled={!option.available}
      className={`relative w-full text-left p-4 rounded-xl border-2 transition ${
        !option.available
          ? "opacity-50 cursor-not-allowed bg-slate-900/5 border-slate-300"
          : selected
            ? "cursor-pointer bg-brand-500/10 border-brand-500/60"
            : "cursor-pointer bg-slate-900/5 border-slate-300 hover:bg-slate-100"
      }`}
    >
      <div className="min-w-0 pr-12">
        <p className="text-sm font-semibold text-slate-900">{option.label}</p>
        <p className=" text-slate-500 mt-0.5">
          {option.available ? option.description : option.unavailable_reason}
        </p>
      </div>
      <div className="flex items-end justify-end gap-3 mt-2">
        <div className="text-right shrink-0">
          <p className="font-extrabold tabular-nums text-lg text-brand-600">
            {euro(option.instalment_cents)}
          </p>
          {option.instalments > 1 && <p className="text-[10px] text-slate-500">al mese × {option.instalments}</p>}
          {vatIncluded && <p className=" font-semibold text-slate-500">IVA inclusa</p>}
        </div>
      </div>
      {option.instalments > 1 && (
        <p className="text-[10px] text-slate-500 mt-2 pt-2 border-t border-slate-200">
          Totale {euro(option.total_cents)}
          {vatIncluded ? " IVA inclusa" : ""}
          {option.rounding_difference_cents !== 0 && (
            <span className="text-slate-600">
              {" "}({option.rounding_difference_cents > 0 ? "+" : ""}
              {(option.rounding_difference_cents / 100).toFixed(2).replace(".", ",")} € per arrotondamento delle rate)
            </span>
          )}
        </p>
      )}
    </button>
  );
}

/** "Paga la pratica": one payment for every contract of the pratica that is
 *  sent and not paid yet (Session 52).
 *
 *  By bank transfer, in one go or in instalments: the contracts are paid
 *  when the administration confirms the money arrived. Every amount on this
 *  screen comes from the server: the browser only sends back a plan key,
 *  and only an administrator marks anything paid.
 */
export function ContractRequestPaymentPanel({ requestId }: { requestId: string }) {
  const queryClient = useQueryClient();
  const { data, error } = useRequestPaymentOptions(requestId);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["contract-request", requestId] });
    await queryClient.invalidateQueries({ queryKey: ["contract-requests"] });
  }

  async function handlePayTransfer() {
    if (!selected) return;
    setLoading(true);
    setPayError(null);
    try {
      const res = await fetch(`/api/proxy/contract-requests/${requestId}/bank-transfer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payment_plan: selected }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await refresh();
    } catch (err: any) {
      setPayError(err.message || "Impossibile scegliere il bonifico.");
    } finally {
      setLoading(false);
    }
  }

  if (error) return <p className="text-sm text-rose-400">{(error as Error).message}</p>;
  if (!data) return <div className="h-32 rounded-2xl bg-slate-900/5 animate-pulse" />;

  if (data.lines.length === 0) {
    return (
      <div className="rounded-2xl p-5 border border-emerald-500/25 bg-emerald-500/10">
        <p className="text-sm font-semibold text-emerald-400">
          {data.points_paid > 0 ? "Pagamento ricevuto" : "Niente da pagare in questo momento"}
        </p>
        <p className="text-xs text-slate-600 mt-1">
          {data.points_paid > 0
            ? "Ogni contratto si attiva appena l'amministrazione approva i suoi documenti. Se ne mancano ancora, puoi caricarli quando vuoi."
            : "I contratti di questa pratica non sono in attesa di pagamento."}
        </p>
      </div>
    );
  }

  if (data.bank_transfer_pending) {
    return <BankTransferInstructions data={data} requestId={requestId} onChanged={refresh} />;
  }

  const selectedOption = data.options.find((o) => o.key === selected) ?? null;

  if (!data.bank_transfer_available) {
    return (
      <div className="glass-card rounded-2xl p-5 border-slate-200 bg-white/70">
        <p className="text-sm text-amber-700">
          Il pagamento non è ancora attivo. Contatta l&apos;assistenza per completare l&apos;attivazione.
        </p>
      </div>
    );
  }

  return (
    <div className="glass-card rounded-2xl p-5 border-slate-200 bg-white/70">
      <h4 className="text-sm font-semibold text-slate-900">Scegli come pagare</h4>
      <p className="text-xs text-slate-500 mt-1">
        Un solo pagamento per {data.lines.length === 1 ? "il contratto" : `tutti i ${data.lines.length} contratti`} della
        pratica. Ogni contratto resta indipendente: si attiva quando i suoi documenti sono approvati.
      </p>

      <div className="mt-3 rounded-xl border border-slate-200 divide-y divide-slate-200">
        {data.lines.map((line) => (
          <div key={line.contract_id} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
            <span className=" text-slate-600 min-w-0 truncate">{line.label}</span>
            <span className="text-right shrink-0">
              <span className="block text-slate-900 font-semibold tabular-nums">{euro(line.gross_cents)}</span>
              {/* Session 84: in rate a contract costs its own, higher price. */}
              {line.instalments_gross_cents > 0 && line.instalments_gross_cents !== line.gross_cents && (
                <span className="block text-[10px] text-slate-500 tabular-nums">
                  a rate {euro(line.instalments_gross_cents)}
                </span>
              )}
            </span>
          </div>
        ))}
        <div className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
          <span className="font-semibold text-slate-600">
            {data.lines.some((l) => l.instalments_gross_cents > 0 && l.instalments_gross_cents !== l.gross_cents)
              ? "Totale in unica soluzione"
              : "Totale"}
          </span>
          <span className="text-right">
            <span className="block font-bold text-slate-900 tabular-nums">{euro(data.total_gross_cents)}</span>
            {data.vat_included && <span className="block text-[10px] text-slate-500">IVA inclusa</span>}
          </span>
        </div>
      </div>

      {data.cashback_total_cents > 0 && (
        <div className="mt-3 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
          <p className="text-xs text-emerald-400 font-semibold">
            Ricevi in cashback: {javCash(selectedOption?.cashback_cents ?? data.cashback_total_cents)}
          </p>
          <p className=" text-slate-500 mt-0.5">
            {data.cashback_mode === "UPFRONT"
              ? "Accreditato per intero sul tuo wallet appena paghi — anche a rate, già alla prima rata."
              : "Accreditato in automatico sul tuo wallet appena paghi — con le rate, una parte a ogni rata pagata."}
          </p>
        </div>
      )}

      <div className="space-y-2.5 mt-4">
        {data.options.map((option) => (
          <OptionCard
            key={option.key}
            option={option}
            selected={selected === option.key}
            onSelect={() => setSelected(option.key)}
            vatIncluded={data.vat_included}
          />
        ))}
      </div>

      {payError && (
        <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{payError}</div>
      )}

      <div className="mt-4">
        <button
          onClick={handlePayTransfer}
          disabled={!selectedOption || loading}
          className="w-full rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 py-2.5 text-sm font-semibold text-white shadow-lg transition disabled:opacity-50 cursor-pointer"
        >
          {loading
            ? "..."
            : selectedOption
              ? `Paga con bonifico · ${euro(selectedOption.instalment_cents)}${data.vat_included ? " IVA inclusa" : ""}`
              : "Scegli una modalità per pagare con bonifico"}
        </button>
      </div>
      <p className="text-[10px] text-slate-500 mt-2 text-center">
        I contratti risultano pagati appena l&apos;amministrazione riceve il bonifico. Non serve aspettare
        l&apos;approvazione dei documenti.
      </p>
    </div>
  );
}

function BankTransferInstructions({
  data,
  requestId,
  onChanged,
}: {
  data: ContractRequestPaymentOptionsRead;
  requestId: string;
  onChanged: () => Promise<void>;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`/api/proxy/contract-requests/${requestId}/bank-transfer/proof`, { method: "POST", body });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await onChanged();
    } catch (err: any) {
      setError(err.message || "Impossibile caricare la ricevuta.");
    } finally {
      setUploading(false);
    }
  }

  function copy(label: string, value: string | null) {
    if (!value || !navigator.clipboard) return;
    navigator.clipboard
      .writeText(value)
      .then(() => {
        setCopied(label);
        window.setTimeout(() => setCopied(null), 1500);
      })
      .catch(() => undefined);
  }

  const row = (label: string, value: string | null, mono = false) => (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="text-[11px] text-slate-500 shrink-0">{label}</span>
      <span className="flex items-center gap-2 min-w-0">
        <span className={`text-sm text-slate-900 font-semibold truncate ${mono ? "font-mono" : ""}`}>{value ?? "—"}</span>
        {value && (
          <button onClick={() => copy(label, value)} className="text-[10px] font-semibold text-brand-600 hover:text-brand-600 cursor-pointer shrink-0">
            {copied === label ? "Copiato" : "Copia"}
          </button>
        )}
      </span>
    </div>
  );

  return (
    <div className="glass-card rounded-2xl p-5 border-2 border-amber-500/30 bg-white/70 space-y-4">
      <input ref={fileRef} type="file" accept="application/pdf,image/jpeg,image/png" className="hidden" onChange={upload} />
      <div>
        <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700">Pagamento con bonifico in attesa</p>
        <div className="flex items-end gap-3 flex-wrap mt-1">
          <p className="text-3xl font-extrabold text-slate-900 tabular-nums">
            {euro(data.bank_transfer_total_cents ?? 0)}
            {data.vat_included && <span className="ml-2 text-xs font-semibold text-slate-400">IVA inclusa</span>}
          </p>
        </div>
        <p className="text-xs text-slate-500 mt-1">
          I contratti risultano pagati appena l&apos;amministrazione riceve il bonifico. Nel frattempo puoi caricare i documenti.
        </p>
      </div>

      <div className="rounded-xl border border-slate-200 px-4 divide-y divide-slate-200">
        {row("Importo", euro(data.bank_transfer_total_cents ?? 0) + (data.vat_included ? " IVA inclusa" : ""))}
        {row("IBAN", data.bank_iban, true)}
        {row("Intestatario", data.bank_account_holder)}
        {row("Causale", data.bank_transfer_reference, true)}
      </div>
      {data.bank_transfer_instructions && (
        <p className=" text-slate-500">{data.bank_transfer_instructions}</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
        >
          {uploading ? "Caricamento..." : data.payment_proof_uploaded_at ? "Sostituisci la ricevuta" : "Carica la ricevuta del bonifico"}
        </button>
        {data.payment_proof_uploaded_at && <span className="text-[11px] text-emerald-400">✓ Ricevuta caricata</span>}
      </div>
      {error && <p className="text-xs text-rose-400">{error}</p>}
    </div>
  );
}
