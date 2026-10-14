"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CommissionPreviewView } from "@/components/contract-commission-preview";
import { ContractDocumentsPanel } from "@/components/contract-documents-panel";
import { ContractDossierActions } from "@/components/contract-dossier-actions";
import { ContractRequestWizard } from "@/components/contract-request-wizard";
import { FullScreenPanel } from "@/components/full-screen-panel";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import {
  CONTRACT_STATUS_LABELS,
  PAYMENT_PLAN_LABELS,
  contractStatusBadge,
  formatDate,
  pointCode,
} from "@/lib/contract-status";
import { formatEuroCents as euro, productAllowsCustomerKind } from "@/lib/product-audience";
import type {
  CommissionPreviewRead,
  ProductCatalogRead,
  ContractRead,
  ContractRequestDetailRead,
  ContractRequestPointRead,
  ContractRequestSummaryRead,
} from "@/lib/types";

type Filter = "ALL" | "TO_REVIEW" | "BANK_TRANSFER" | "TO_PAY" | "DOCUMENTS" | "DRAFT";

const FILTERS: { key: Filter; label: string; match: (r: ContractRequestSummaryRead) => boolean }[] = [
  { key: "TO_REVIEW", label: "Da verificare", match: (r) => r.points_to_review > 0 },
  { key: "BANK_TRANSFER", label: "Bonifici da confermare", match: (r) => r.bank_transfer_pending },
  { key: "DOCUMENTS", label: "Documenti mancanti", match: (r) => r.points_documents_pending > 0 },
  { key: "TO_PAY", label: "Non pagate", match: (r) => r.status === "SUBMITTED" && r.points_payable > 0 },
  { key: "DRAFT", label: "In compilazione", match: (r) => r.status === "DRAFT" },
  { key: "ALL", label: "Tutte", match: (r) => r.status !== "CANCELLED" },
];

const ORIGIN_LABELS: Record<string, string> = {
  CUSTOMER: "Dal cliente",
  PROMOTER: "Dal promoter",
  ADMIN: "Dall'amministrazione",
};

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** "Pratiche": every pratica di attivazione, for the back office (Session 52).
 *
 *  The list answers "what needs me?" -- pratiche with contracts to verify,
 *  missing documents, unpaid, failed instalments. The detail shows one
 *  pratica as the customer filled it in: the holder, the shared documents,
 *  every payment attempt, and each point as the independent contract it
 *  is. Approving, rejecting and the commission preview stay per contract --
 *  the same review modal as "Tutti i Contratti", opened from here -- with
 *  one addition: approving every contract waiting for review at once, each
 *  with its own preview accepted. */
export function AdminContractRequestsPanel({
  openRequestId,
  onOpenRequest,
  onReview,
  onCommissions,
  onHistory,
  onContractsChanged,
}: {
  openRequestId: string | null;
  onOpenRequest: (requestId: string | null) => void;
  onReview: (contract: ContractRead) => void;
  onCommissions: (contractId: string) => void;
  onHistory: (contractId: string) => void;
  /** "Tutti i Contratti" keeps its own copy of the list: told to reload it
      after contracts were approved from here. */
  onContractsChanged: () => void;
}) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["admin", "contract-requests"],
    queryFn: () => fetchJson<ContractRequestSummaryRead[]>("/api/proxy/contract-requests"),
    refetchOnWindowFocus: true,
  });
  const [filter, setFilter] = useState<Filter>("TO_REVIEW");
  const [search, setSearch] = useState("");

  const all = data ?? [];
  const needle = search.trim().toLowerCase();
  const active = FILTERS.find((f) => f.key === filter)!;
  const rows = all.filter(
    (r) =>
      active.match(r) &&
      (!needle ||
        [r.code, r.customer_name, r.holder_name, r.activated_by_promoter_name, r.id]
          .filter(Boolean)
          .some((v) => v!.toLowerCase().includes(needle)))
  );
  const pagination = usePagination(rows);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {FILTERS.filter((f) => f.key !== "ALL" && f.key !== "DRAFT").map((f) => {
          const count = all.filter(f.match).length;
          return (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`glass-card rounded-2xl p-4 text-left border transition cursor-pointer ${
                filter === f.key ? "border-brand-500/50 bg-brand-500/5" : " border-slate-200 bg-slate-50"
              }`}
            >
              <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">{f.label}</span>
              <span className={`text-2xl font-bold ${count > 0 && f.key !== "TO_PAY" ? "text-brand-600" : " text-slate-900"}`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between p-4 rounded-2xl bg-slate-50 border border-slate-200">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Cerca per pratica, cliente, intestatario o promoter..."
          className="w-full sm:max-w-sm rounded-xl glass-input px-3 py-2 text-xs focus:border-brand-500"
        />
        <div className="flex gap-1.5 flex-wrap">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold transition cursor-pointer ${
                filter === f.key ? "bg-brand-600 text-white" : " bg-slate-900/5 text-slate-600 hover:bg-slate-100"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                <th className="py-3 px-5">Pratica</th>
                <th className="py-3 px-5">Cliente</th>
                <th className="py-3 px-5">Punti</th>
                <th className="py-3 px-5 text-right">Totale</th>
                <th className="py-3 px-5">Pagamento</th>
                <th className="py-3 px-5 text-right" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {isLoading && (
                <tr><td colSpan={6} className="py-8 text-center text-slate-500">Caricamento...</td></tr>
              )}
              {error && (
                <tr><td colSpan={6} className="py-8 text-center text-rose-400">{(error as Error).message}</td></tr>
              )}
              {pagination.pageItems.map((r) => (
                <tr key={r.id} className=" text-slate-600 hover:bg-slate-100 cursor-pointer" onClick={() => onOpenRequest(r.id)}>
                  <td className="py-3 px-5">
                    <div className="text-sm font-semibold text-slate-900">#{r.code}</div>
                    <div className="text-[10px] text-slate-500">
                      {r.status === "DRAFT" ? "Bozza · " : ""}
                      {formatDate(r.submitted_at ?? r.created_at)}
                    </div>
                  </td>
                  <td className="py-3 px-5">
                    <div className="text-sm font-semibold text-slate-900">{r.customer_name ?? "—"}</div>
                    <div className="text-[10px] text-slate-500">
                      {ORIGIN_LABELS[r.created_by_role ?? ""] ?? "—"}
                      {r.activated_by_promoter_name ? ` · ${r.activated_by_promoter_name}` : ""}
                    </div>
                    {r.notes && (
                      <div
                        title={r.notes}
                        className="mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold border bg-brand-500/10 text-brand-600 border-brand-500/25 max-w-[220px]"
                      >
                        <span className="shrink-0">Note:</span>
                        <span className="truncate font-medium">{r.notes}</span>
                      </div>
                    )}
                  </td>
                  <td className="py-3 px-5">
                    <div className="text-xs font-semibold text-slate-900">
                      {r.points_active}/{r.points_total} attivi
                    </div>
                    <div className="text-[10px] text-slate-500">
                      {[
                        r.points_to_review > 0 && `${r.points_to_review} da verificare`,
                        r.points_documents_pending > 0 && `${r.points_documents_pending} senza documenti`,
                        r.points_without_package > 0 && `${r.points_without_package} senza pacchetto`,
                      ].filter(Boolean).join(" · ") || "—"}
                    </div>
                  </td>
                  <td className="py-3 px-5 text-right text-sm font-semibold text-slate-900 tabular-nums">
                    {r.total_gross_cents > 0 ? euro(r.total_gross_cents) : "—"}
                  </td>
                  <td className="py-3 px-5">
                    <div className="text-xs">
                      {r.bank_transfer_pending ? (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 border-amber-500/30 text-amber-700">
                          Bonifico da confermare{r.bank_transfer_total_cents ? ` · ${euro(r.bank_transfer_total_cents)}` : ""}
                        </span>
                      ) : r.points_paid > 0 ? `Pagati ${r.points_paid}/${r.points_total}` : r.status === "DRAFT" ? "—" : "Non pagata"}
                    </div>
                    <div className="text-[10px] text-slate-500">
                      {r.payment_plans.map((p) => PAYMENT_PLAN_LABELS[p] ?? p).join(", ")}
                    </div>
                  </td>
                  <td className="py-3 px-5 text-right">
                    <span className="px-3 py-1 rounded-lg bg-brand-600/10 border border-brand-500/20 text-brand-600 text-xs font-semibold">
                      Apri
                    </span>
                  </td>
                </tr>
              ))}
              {!isLoading && !error && rows.length === 0 && (
                <tr><td colSpan={6} className="py-8 text-center text-slate-500">Nessuna pratica in “{active.label}”.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="px-5 pb-4">
          <Pagination {...pagination} label="pratiche" />
        </div>
      </div>

      {openRequestId && (
        <RequestDetail
          requestId={openRequestId}
          onClose={() => onOpenRequest(null)}
          onReview={onReview}
          onCommissions={onCommissions}
          onHistory={onHistory}
          onContractsChanged={onContractsChanged}
        />
      )}
    </div>
  );
}

function RequestDetail({
  requestId,
  onClose,
  onReview,
  onCommissions,
  onHistory,
  onContractsChanged,
}: {
  requestId: string;
  onClose: () => void;
  onReview: (contract: ContractRead) => void;
  onCommissions: (contractId: string) => void;
  onHistory: (contractId: string) => void;
  onContractsChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: request, error } = useQuery({
    queryKey: ["contract-request", requestId],
    queryFn: () => fetchJson<ContractRequestDetailRead>(`/api/proxy/contract-requests/${requestId}`),
    refetchOnWindowFocus: true,
  });
  const [openPoint, setOpenPoint] = useState<string | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [repackaging, setRepackaging] = useState<ContractRequestPointRead | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["contract-request", requestId] }),
      queryClient.invalidateQueries({ queryKey: ["admin", "contract-requests"] }),
    ]);
  }

  const toReview = (request?.points ?? []).filter((p) => p.status === "UNDER_REVIEW");

  // Session 89: «Sblocca pratica» -- sent, nothing paid, no bank transfer
  // receipt. The server checks it all again.
  const [unlocking, setUnlocking] = useState(false);
  const [editing, setEditing] = useState(false);
  const alivePoints = (request?.points ?? []).filter((p) => p.status !== "CANCELLED" && p.status !== "REJECTED");
  const canUnlock =
    request?.status === "SUBMITTED" &&
    !request.payment_proof_uploaded_at &&
    alivePoints.length > 0 &&
    (request.points ?? []).every((p) => !p.paid_at) &&
    alivePoints.every((p) => UNLOCKABLE_STATUSES.includes(p.status));

  async function unlock() {
    if (!request) return;
    if (
      !window.confirm(
        `Sbloccare la pratica #${request.code}?\n\nTorna in compilazione: il cliente, il suo promoter o l'amministrazione ` +
          "possono cambiare i pacchetti scelti, poi inviarla di nuovo e pagare il nuovo totale. Le approvazioni già date " +
          "si perdono (la pratica va rivista dopo il nuovo invio)" +
          (request.bank_transfer_pending ? " e il bonifico annunciato dal cliente viene annullato" : "") +
          ". I link di pagamento già aperti non funzionano più."
      )
    ) {
      return;
    }
    setUnlocking(true);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/contract-requests/${request.id}/unlock`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await refresh();
      onContractsChanged();
    } catch (err: any) {
      setActionError(err.message || "Impossibile sbloccare la pratica.");
    } finally {
      setUnlocking(false);
    }
  }

  return (
    <FullScreenPanel
      eyebrow="Pratica di attivazione"
      title={request ? `#${request.code} · ${request.customer_name ?? "Cliente"}` : "Pratica"}
      onClose={onClose}
      subtitle={
        request && (
          <p className=" text-slate-500">
            {ORIGIN_LABELS[request.created_by_role ?? ""] ?? "—"}
            {request.activated_by_promoter_name ? ` (${request.activated_by_promoter_name})` : ""} ·{" "}
            {request.status === "DRAFT" ? "in compilazione" : `inviata il ${formatDate(request.submitted_at)}`} ·{" "}
            {request.points_total} punti · {request.points_active} attivi · totale{" "}
            <strong className="text-brand-600">{euro(request.total_gross_cents)}</strong>
          </p>
        )
      }
    >
      {error && <p className="text-sm text-rose-400">{(error as Error).message}</p>}
      {!request ? (
        <div className="h-40 rounded-2xl bg-slate-900/5 animate-pulse" />
      ) : (
        <div className="space-y-6">
          {actionError && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{actionError}</div>
          )}

          <section className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 rounded-2xl bg-slate-900/5 border border-slate-200 text-xs">
            {request.company_name ? (
              <>
                <Fact label="Azienda" value={request.company_name} />
                <Fact label="Legale rappresentante" value={request.holder_name ?? "—"} />
                <Fact label="CF legale rappresentante" value={request.legal_rep_fiscal_code ?? "—"} mono />
              </>
            ) : (
              <>
                <Fact label="Intestatario" value={request.holder_name ?? "—"} />
                <Fact label="Codice fiscale" value={request.holder_fiscal_code ?? "—"} mono />
              </>
            )}
            {request.fiscal_code_problems.length > 0 && (
              <Fact label="Codice fiscale da verificare" value={request.fiscal_code_problems.join("; ")} />
            )}
            <Fact
              label="Nato/a"
              value={
                request.holder_birth_date
                  ? `${new Date(request.holder_birth_date).toLocaleDateString("it-IT")} a ${request.holder_birth_place ?? "—"}`
                  : "—"
              }
            />
            <Fact label="Email" value={request.email ?? "—"} />
            <Fact label="PEC" value={request.pec ?? "—"} />
            <Fact label="IBAN" value={request.iban ?? "—"} mono />
          </section>

          {request.notes && (
            <section className="p-4 rounded-2xl bg-brand-500/10 border border-brand-500/25">
              <div className="flex items-center justify-between gap-3 flex-wrap mb-1.5">
                <h3 className="text-xs font-bold text-brand-700 uppercase tracking-wider">
                  Note per l&apos;amministrazione
                </h3>
                {(request.notes_author || request.notes_updated_at) && (
                  <span className=" text-slate-500">
                    {request.notes_author ?? ""}
                    {request.notes_updated_at ? ` · ${formatDate(request.notes_updated_at)}` : ""}
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-800 whitespace-pre-wrap break-words">{request.notes}</p>
            </section>
          )}

          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <h3 className="text-sm font-bold text-slate-900">Contratti della pratica</h3>
              {request.status === "DRAFT" && (
                <button
                  onClick={() => setEditing(true)}
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white transition cursor-pointer"
                >
                  Modifica la pratica
                </button>
              )}
              {canUnlock && (
                <button
                  onClick={unlock}
                  disabled={unlocking}
                  title="Riporta la pratica in compilazione per cambiare i pacchetti, poi si invia e si paga di nuovo"
                  className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-xs font-bold text-white transition cursor-pointer disabled:opacity-50"
                >
                  {unlocking ? "Sblocco…" : "Sblocca pratica"}
                </button>
              )}
              {toReview.length > 0 && (
                <button
                  onClick={() => setBulkOpen(true)}
                  className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white transition cursor-pointer"
                >
                  Approva {toReview.length === 1 ? "il contratto in revisione" : `i ${toReview.length} contratti in revisione`}
                </button>
              )}
            </div>
            <div className="space-y-2">
              {request.points.map((point) => (
                <div key={point.id} className="rounded-2xl border border-slate-200 bg-white/70">
                  <div className="p-3.5 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_auto] items-start gap-x-4 gap-y-3">
                    <div className="min-w-0">
                      <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
                        Contratto {point.id.slice(0, 8).toUpperCase()}
                      </p>
                      <p className="text-sm font-bold text-slate-900 font-mono break-all">{pointCode(point)}</p>
                    </div>
                    <div className="min-w-0">
                      <p
                        className={`text-xs font-semibold break-words ${
                          point.product_name ? " text-slate-900" : "text-amber-700"
                        }`}
                      >
                        {point.product_name ?? "Senza pacchetto"}
                      </p>
                      <p className=" text-slate-500 tabular-nums">
                        {point.gross_amount_cents != null ? euro(point.gross_amount_cents) : "—"}
                        {point.vat_amount_cents ? ` (IVA ${point.vat_rate}%)` : ""}
                      </p>
                    </div>
                    <div className="min-w-0 space-y-1">
                      <button
                        onClick={() => onHistory(point.id)}
                        title="Storico stati"
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold border cursor-pointer ${contractStatusBadge(point.status)}`}
                      >
                        {CONTRACT_STATUS_LABELS[point.status] ?? point.status}
                      </button>
                      <p className="text-[10px] text-slate-500">
                        {point.paid_at ? (
                          <span className="text-emerald-400">
                            Pagato{point.payment_plan ? ` · ${PAYMENT_PLAN_LABELS[point.payment_plan] ?? point.payment_plan}` : ""}
                          </span>
                        ) : (
                          "Non pagato"
                        )}
                        {point.instalments_total && point.instalments_total > 1
                          ? ` · rate ${point.instalments_paid}/${point.instalments_total}`
                          : ""}
                      </p>
                      <p className={`text-[10px] ${point.documents_missing > 0 || point.documents_rejected > 0 ? "text-amber-700" : "text-slate-500"}`}>
                        {point.documents_missing > 0
                          ? `${point.documents_missing} documenti mancanti`
                          : point.documents_rejected > 0
                            ? `${point.documents_rejected} documenti respinti`
                            : "Documenti completi"}
                      </p>
                    </div>
                    <div className="min-w-0 flex flex-wrap items-center gap-1.5 sm:col-span-2 xl:col-span-1 xl:justify-end">
                      <button
                        onClick={() => setOpenPoint(openPoint === point.id ? null : point.id)}
                        className="px-2.5 py-1 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 font-semibold cursor-pointer"
                      >
                        {openPoint === point.id ? "Chiudi" : "Documenti"}
                      </button>
                      {canRepackage(point) && (
                        <button
                          onClick={() => setRepackaging(point)}
                          className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold cursor-pointer border ${
                            point.product_version_id
                              ? " bg-slate-900/5 hover:bg-slate-100 border-slate-300 text-slate-600"
                              : "bg-amber-500/10 hover:bg-amber-500/20 border-amber-500/30 text-amber-700"
                          }`}
                        >
                          {point.product_version_id ? "Cambia pacchetto" : "Scegli pacchetto"}
                        </button>
                      )}
                      {point.product_version_id && (
                        <button
                          onClick={() => onCommissions(point.id)}
                          className="px-2.5 py-1 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 font-semibold cursor-pointer"
                        >
                          Provvigioni
                        </button>
                      )}
                      {point.status !== "DRAFT" && (
                        <button
                          onClick={() => onReview(point)}
                          className="px-2.5 py-1 rounded-lg bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-600 text-[11px] font-semibold cursor-pointer"
                        >
                          Recensisci
                        </button>
                      )}
                    </div>
                  </div>
                  {openPoint === point.id && (
                    <div className="border-t border-slate-200 p-4 space-y-4">
                      <ContractDocumentsPanel contractId={point.id} isStaff />
                      <ContractDossierActions contractId={point.id} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-bold text-slate-900">Documenti dell&apos;intestatario</h3>
            <p className="text-xs text-slate-500">
              Caricati una volta sulla pratica: valgono per ogni contratto qui sopra, e compaiono anche nel fascicolo di
              ciascuno.
            </p>
            <ContractDocumentsPanel requestId={request.id} isStaff />
          </section>

          {request.bank_transfer_pending && (
            <BankTransferConfirm request={request} onDone={async () => { await refresh(); onContractsChanged(); }} />
          )}
        </div>
      )}

      {repackaging && (
        <PackagePicker
          point={repackaging}
          customerKind={request?.customer_kind ?? null}
          onClose={() => setRepackaging(null)}
          onChosen={async (versionId) => {
            const res = await fetch(`/api/proxy/contract-requests/${requestId}/points/${repackaging.id}/product`, {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ product_version_id: versionId }),
            });
            if (!res.ok) throw new Error(await friendlyApiError(res));
            setRepackaging(null);
            await refresh();
            onContractsChanged();
          }}
        />
      )}

      {editing && request && (
        <ContractRequestWizard
          requestId={request.id}
          customer={{ id: request.customer_id, kind: request.customer_kind ?? null, email: request.email }}
          onClose={async () => {
            setEditing(false);
            await refresh();
            onContractsChanged();
          }}
        />
      )}

      {bulkOpen && request && (
        <BulkApproveModal
          points={toReview}
          onClose={() => setBulkOpen(false)}
          onDone={async () => {
            await refresh();
            onContractsChanged();
          }}
        />
      )}
    </FullScreenPanel>
  );
}

/** Fino a quando l'amministratore può correggere il pacchetto di un contratto:
    finché quel contratto non è pagato e non è già attivo (il backend
    applica la stessa regola, requests.py). */
/** A pratica can be unlocked while every live contract is still before payment. */
const UNLOCKABLE_STATUSES = ["SUBMITTED", "DOCUMENTS_PENDING", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING"];

const REPACKAGEABLE_STATUSES = ["DRAFT", "SUBMITTED", "DOCUMENTS_PENDING", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING"];

function canRepackage(point: ContractRequestPointRead): boolean {
  return !point.paid_at && REPACKAGEABLE_STATUSES.includes(point.status);
}

/** Scelta (o correzione) del pacchetto di un contratto dal pannello
    Pratiche: stessi pacchetti che vedrebbe il cliente, filtrati per la sua
    tipologia (il backend applica la stessa regola). */
function PackagePicker({
  point,
  customerKind,
  onClose,
  onChosen,
}: {
  point: ContractRequestPointRead;
  customerKind: string | null;
  onClose: () => void;
  onChosen: (versionId: string) => Promise<void>;
}) {
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: products } = useQuery({
    queryKey: ["admin", "products", "catalog"],
    queryFn: () => fetchJson<ProductCatalogRead[]>("/api/proxy/products"),
  });
  const packages = (products ?? []).filter(
    (p) =>
      p.category === "INTERNAL" &&
      p.status === "ACTIVE" &&
      p.current_version?.status === "ACTIVE" &&
      productAllowsCustomerKind(p.customer_type, customerKind)
  );

  async function choose(versionId: string) {
    setSaving(versionId);
    setError(null);
    try {
      await onChosen(versionId);
    } catch (err: any) {
      setError(err.message || "Impossibile cambiare il pacchetto.");
    } finally {
      setSaving(null);
    }
  }

  return (
    <FullScreenPanel title={`Pacchetto di ${pointCode(point)}`} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-xs text-slate-500">
          {point.product_name
            ? `Ora è attivo “${point.product_name}”. Scegliendone un altro il prezzo del contratto viene ricalcolato subito.`
            : "Questo contratto non ha ancora un pacchetto: sceglilo qui per poter proseguire con la pratica."}
        </p>
        {error && <p className="text-xs text-rose-400">{error}</p>}
        {packages.length === 0 && <p className="text-xs text-slate-500">Nessun pacchetto disponibile per questo cliente.</p>}
        {packages.map((product) => {
          const version = product.current_version!;
          const current = version.id === point.product_version_id;
          return (
            <button
              key={version.id}
              disabled={current || saving !== null}
              onClick={() => choose(version.id)}
              className={`w-full text-left p-3.5 rounded-2xl border transition cursor-pointer disabled:cursor-default ${
                current
                  ? "border-emerald-500/40 bg-emerald-500/5"
                  : " border-slate-200 bg-white/70 hover:border-brand-500/40"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-bold text-slate-900 break-words">{version.name}</p>
                  <p className=" text-slate-500 break-words">
                    {product.code}
                  </p>
                </div>
                <p className="text-xs font-semibold text-slate-700 tabular-nums whitespace-nowrap">
                  {euro(version.contract_net_amount_cents || version.base_price_cents)}
                  {version.contract_instalments_net_amount_cents != null
                    ? ` · a rate ${euro(version.contract_instalments_net_amount_cents)}`
                    : ""}
                  {current ? " · attuale" : saving === version.id ? " · ..." : ""}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </FullScreenPanel>
  );
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] text-slate-500 uppercase tracking-wide">{label}</p>
      <p className={` text-slate-800 font-semibold break-words ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

type BulkResult = { contractId: string; ok: boolean; message: string };

/** Approving every contract waiting for review, in one go -- without
    skipping what makes approval safe. Each contract's commission preview is
    loaded and shown; the administrator accepts them all with one tick, and
    each transition is still sent on its own with its own checksum, so a
    preview that changed in the meantime is refused for that contract alone
    and the others go through. */
function BulkApproveModal({
  points,
  onClose,
  onDone,
}: {
  points: ContractRequestPointRead[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("Documenti verificati");
  const [checked, setChecked] = useState(false);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<BulkResult[] | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: previews, error } = useQuery({
    queryKey: ["admin", "bulk-previews", points.map((p) => p.id).join(",")],
    queryFn: async () => {
      const out: Record<string, CommissionPreviewRead> = {};
      for (const point of points) {
        out[point.id] = await fetchJson<CommissionPreviewRead>(`/api/proxy/contracts/${point.id}/commission-preview`);
      }
      return out;
    },
    staleTime: 0,
    gcTime: 0,
  });

  async function approveAll() {
    if (!previews) return;
    setRunning(true);
    const out: BulkResult[] = [];
    for (const point of points) {
      const preview = previews[point.id];
      if (!preview) continue;
      try {
        const res = await fetch(`/api/proxy/contracts/${point.id}/transition`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            to_status: "APPROVED",
            reason,
            notes: null,
            accept_commission_preview_checksum: preview.already_accepted ? null : preview.checksum,
          }),
        });
        if (!res.ok) throw new Error(await friendlyApiError(res));
        const updated = (await res.json()) as ContractRead;
        out.push({
          contractId: point.id,
          ok: true,
          message: `${pointCode(point)}: ${CONTRACT_STATUS_LABELS[updated.status] ?? updated.status}`,
        });
      } catch (err: any) {
        out.push({ contractId: point.id, ok: false, message: `${pointCode(point)}: ${err.message}` });
      }
    }
    setResults(out);
    setRunning(false);
    onDone();
  }

  const total = previews ? Object.values(previews).reduce((sum, p) => sum + p.total_commission_cents, 0) : 0;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
      <div className="w-full max-w-3xl max-h-[88vh] overflow-y-auto glass-card rounded-2xl p-6 border-slate-300 bg-white space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-900">
            Approva {points.length} {points.length === 1 ? "contratto" : "contratti"}
          </h3>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer">✕</button>
        </div>

        {results ? (
          <>
            <div className="space-y-1.5">
              {results.map((r) => (
                <p key={r.contractId} className={`text-xs ${r.ok ? "text-emerald-400" : "text-rose-400"}`}>
                  {r.ok ? "✓" : "✕"} {r.message}
                </p>
              ))}
            </div>
            <button onClick={onClose} className="w-full rounded-xl bg-slate-50 hover:bg-white/20 py-2.5 text-sm font-semibold text-slate-700 cursor-pointer">
              Chiudi
            </button>
          </>
        ) : (
          <>
            <p className="text-xs text-slate-500">
              Approvare un contratto fa partire le sue provvigioni (subito se già pagato, a ogni rata se a rate). Controlla le
              anteprime: ognuna viene accettata e salvata nel registro del suo contratto.
            </p>
            {error && <p className="text-xs text-rose-400">{(error as Error).message}</p>}
            {!previews ? (
              <div className="h-32 rounded-xl bg-slate-900/5 animate-pulse" />
            ) : (
              <div className="space-y-2">
                {points.map((point) => {
                  const preview = previews[point.id];
                  if (!preview) return null;
                  return (
                    <div key={point.id} className="rounded-xl border border-slate-200">
                      <button
                        onClick={() => setExpanded(expanded === point.id ? null : point.id)}
                        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left cursor-pointer"
                      >
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-slate-900 font-mono">{pointCode(point)}</span>
                          <span className="block text-[11px] text-slate-400">
                            {point.product_name} · {preview.beneficiaries.filter((b) => b.total_cents > 0).length} beneficiari
                            {preview.warnings.length > 0 && <span className="text-amber-700"> · {preview.warnings.length} avvisi</span>}
                            {preview.already_accepted && " · anteprima già accettata"}
                          </span>
                        </span>
                        <span className="text-sm font-bold text-brand-600 tabular-nums shrink-0">
                          {euro(preview.total_commission_cents)} {expanded === point.id ? "▾" : "▸"}
                        </span>
                      </button>
                      {expanded === point.id && (
                        <div className="border-t border-slate-200 p-4">
                          <CommissionPreviewView preview={preview} />
                        </div>
                      )}
                    </div>
                  );
                })}
                <p className="text-xs text-slate-700 text-right">
                  Provvigioni totali: <strong className="text-brand-600">{euro(total)}</strong>
                </p>
              </div>
            )}
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-600 block">Motivazione</label>
              <input
                required
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500"
              />
            </div>
            <label className="flex items-start gap-2 cursor-pointer">
              <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} className="mt-0.5 accent-brand-500" />
              <span className="text-xs text-slate-700">
                Ho verificato i documenti e controllato le anteprime: accetto che le provvigioni di ogni contratto partano
                come indicato.
              </span>
            </label>
            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="px-4 py-2 rounded-xl bg-slate-50 hover:bg-slate-100 text-xs font-semibold text-slate-600 cursor-pointer">
                Annulla
              </button>
              <button
                onClick={approveAll}
                disabled={!previews || !checked || !reason.trim() || running}
                className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
              >
                {running ? "Approvazione in corso..." : `Accetta e approva ${points.length}`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}


/** Session 65: the customer chose to pay the pratica by bank transfer. The
    contracts are paid only when an administrator confirms the money
    arrived. */
function BankTransferConfirm({ request, onDone }: { request: ContractRequestDetailRead; onDone: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toPay = request.points.filter((p) => p.payment_method === "BANK_TRANSFER" && !p.paid_at);

  async function openProof() {
    setError(null);
    try {
      const res = await fetch(`/api/proxy/contract-requests/${request.id}/bank-transfer/proof-url`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { url } = await res.json();
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function confirm() {
    if (!window.confirm(`Confermi di aver ricevuto il bonifico di ${euro(request.bank_transfer_total_cents ?? 0)} per la pratica #${request.code}? I ${toPay.length} contratti risulteranno pagati.`)) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/proxy/contract-requests/${request.id}/bank-transfer/confirm`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await onDone();
    } catch (err: any) {
      setError(err.message || "Impossibile confermare il bonifico.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-5 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700">Bonifico da confermare</p>
          <p className="text-2xl font-extrabold text-slate-900 tabular-nums">{euro(request.bank_transfer_total_cents ?? 0)}</p>
          <p className="text-xs text-slate-500">
            {toPay.length} {toPay.length === 1 ? "contratto" : "contratti"} · scelto il {formatDate(request.bank_transfer_requested_at)} ·
            causale “Pratica {request.code}”
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {request.payment_proof_uploaded_at ? (
            <button onClick={openProof} className="px-3 py-2 rounded-xl bg-sky-600/10 hover:bg-sky-600/20 border border-sky-500/20 text-sky-400 text-xs font-semibold cursor-pointer">
              Vedi ricevuta ({formatDate(request.payment_proof_uploaded_at)})
            </button>
          ) : (
            <span className="px-3 py-2 text-xs text-slate-500">Nessuna ricevuta caricata</span>
          )}
          <button onClick={confirm} disabled={busy} className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50">
            {busy ? "Conferma..." : "Conferma bonifico ricevuto"}
          </button>
        </div>
      </div>
      <div className=" text-slate-500 space-y-0.5">
        {toPay.map((p) => (
          <p key={p.id}>
            {pointCode(p)} · {p.product_name ?? "—"} · {euro(p.gross_amount_cents ?? 0)}
          </p>
        ))}
      </div>
      {error && <p className="text-xs text-rose-400">{error}</p>}
    </section>
  );
}

