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
import { contractStatusBadge } from "@/lib/contract-status";
import { useI18n } from "@/lib/i18n/provider";
import { productAllowsCustomerKind } from "@/lib/product-audience";
import type {
  CommissionPreviewRead,
  ProductCatalogRead,
  ContractRead,
  ContractRequestDetailRead,
  ContractRequestPointRead,
  ContractRequestSummaryRead,
} from "@/lib/types";

type Filter = "ALL" | "TO_REVIEW" | "BANK_TRANSFER" | "TO_PAY" | "DOCUMENTS" | "DRAFT";

/* Filter labels: `ctr.adm.filter.<key>`; origins: `ctr.adm.origin.<role>`. */
const FILTERS: { key: Filter; match: (r: ContractRequestSummaryRead) => boolean }[] = [
  { key: "TO_REVIEW", match: (r) => r.points_to_review > 0 },
  { key: "BANK_TRANSFER", match: (r) => r.bank_transfer_pending },
  { key: "DOCUMENTS", match: (r) => r.points_documents_pending > 0 },
  { key: "TO_PAY", match: (r) => r.status === "SUBMITTED" && r.points_payable > 0 },
  { key: "DRAFT", match: (r) => r.status === "DRAFT" },
  { key: "ALL", match: (r) => r.status !== "CANCELLED" },
];

type T = ReturnType<typeof useI18n>["t"];

/** Shared by the screens below: dates, contract names and labels in the reader's language. */
function useLabels() {
  const { t, fmt } = useI18n();
  return {
    t,
    fmt,
    euro: fmt.euro,
    formatDate: (v: string | null | undefined) => (v ? new Date(v).toLocaleDateString(fmt.tag) : "—"),
    pointCode: (point: { position?: number }) =>
      point.position ? t("ctr.point.codeN", { n: point.position }) : t("ctr.point.code"),
    origin: (role: string | null | undefined) => (role ? t.dyn(`ctr.adm.origin.${role}`, "—") : "—"),
    status: (code: string) => t.dyn(`ctr.status.${code}`, code),
    plan: (code: string) => t.dyn(`ctr.plan.${code}`, code),
  };
}

function filterLabel(t: T, key: Filter): string {
  return t(`ctr.adm.filter.${key}`);
}

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
  const { t, euro, formatDate, origin, plan } = useLabels();
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
              <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">{filterLabel(t, f.key)}</span>
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
          placeholder={t("ctr.adm.searchPlaceholder")}
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
              {filterLabel(t, f.key)}
            </button>
          ))}
        </div>
      </div>

      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                <th className="py-3 px-5">{t("ctr.summary.pratica")}</th>
                <th className="py-3 px-5">{t("ctr.create.customer")}</th>
                <th className="py-3 px-5">{t("ctr.adm.col.points")}</th>
                <th className="py-3 px-5 text-right">{t("ctr.pay.total")}</th>
                <th className="py-3 px-5">{t("ctr.log.col.payment")}</th>
                <th className="py-3 px-5 text-right" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {isLoading && (
                <tr><td colSpan={6} className="py-8 text-center text-slate-500">{t("ctr.common.loading")}</td></tr>
              )}
              {error && (
                <tr><td colSpan={6} className="py-8 text-center text-rose-400">{(error as Error).message}</td></tr>
              )}
              {pagination.pageItems.map((r) => (
                <tr key={r.id} className=" text-slate-600 hover:bg-slate-100 cursor-pointer" onClick={() => onOpenRequest(r.id)}>
                  <td className="py-3 px-5">
                    <div className="text-sm font-semibold text-slate-900">#{r.code}</div>
                    <div className="text-[10px] text-slate-500">
                      {r.status === "DRAFT" ? `${t("ctr.status.DRAFT")} · ` : ""}
                      {formatDate(r.submitted_at ?? r.created_at)}
                    </div>
                  </td>
                  <td className="py-3 px-5">
                    <div className="text-sm font-semibold text-slate-900">{r.customer_name ?? "—"}</div>
                    <div className="text-[10px] text-slate-500">
                      {origin(r.created_by_role)}
                      {r.activated_by_promoter_name ? ` · ${r.activated_by_promoter_name}` : ""}
                    </div>
                    {r.notes && (
                      <div
                        title={r.notes}
                        className="mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold border bg-brand-500/10 text-brand-600 border-brand-500/25 max-w-[220px]"
                      >
                        <span className="shrink-0">{t("ctr.history.notes")}</span>
                        <span className="truncate font-medium">{r.notes}</span>
                      </div>
                    )}
                  </td>
                  <td className="py-3 px-5">
                    <div className="text-xs font-semibold text-slate-900">
                      {t("ctr.list.activeRatio", { active: r.points_active, total: r.points_total })}
                    </div>
                    <div className="text-[10px] text-slate-500">
                      {[
                        r.points_to_review > 0 && t("ctr.adm.nToReview", { n: r.points_to_review }),
                        r.points_documents_pending > 0 && t("ctr.adm.nWithoutDocs", { n: r.points_documents_pending }),
                        r.points_without_package > 0 && t("ctr.adm.nWithoutPackage", { n: r.points_without_package }),
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
                          {t("ctr.adm.transferToConfirm")}{r.bank_transfer_total_cents ? ` · ${euro(r.bank_transfer_total_cents)}` : ""}
                        </span>
                      ) : r.points_paid > 0 ? t("ctr.adm.paidRatio", { paid: r.points_paid, total: r.points_total }) : r.status === "DRAFT" ? "—" : t("ctr.adm.unpaid")}
                    </div>
                    <div className="text-[10px] text-slate-500">
                      {r.payment_plans.map(plan).join(", ")}
                    </div>
                  </td>
                  <td className="py-3 px-5 text-right">
                    <span className="px-3 py-1 rounded-lg bg-brand-600/10 border border-brand-500/20 text-brand-600 text-xs font-semibold">
                      {t("ctr.adm.open")}
                    </span>
                  </td>
                </tr>
              ))}
              {!isLoading && !error && rows.length === 0 && (
                <tr><td colSpan={6} className="py-8 text-center text-slate-500">{t("ctr.adm.noneInFilter", { filter: filterLabel(t, active.key) })}</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="px-5 pb-4">
          <Pagination {...pagination} label={t("ctr.adm.praticheLower")} />
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
  const { t, fmt, euro, formatDate, pointCode, origin, status, plan } = useLabels();
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
        t(request.bank_transfer_pending ? "ctr.adm.unlockConfirmTransfer" : "ctr.adm.unlockConfirm", { code: request.code })
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
      setActionError(err.message || t("ctr.adm.unlockError"));
    } finally {
      setUnlocking(false);
    }
  }

  return (
    <FullScreenPanel
      eyebrow={t("ctr.adm.eyebrow")}
      title={request ? `#${request.code} · ${request.customer_name ?? t("ctr.create.customer")}` : t("ctr.summary.pratica")}
      onClose={onClose}
      subtitle={
        request && (
          <p className=" text-slate-500">
            {origin(request.created_by_role)}
            {request.activated_by_promoter_name ? ` (${request.activated_by_promoter_name})` : ""} ·{" "}
            {request.status === "DRAFT" ? t("ctr.adm.inProgressLower") : t("ctr.adm.submittedOn", { date: formatDate(request.submitted_at) })} ·{" "}
            {t("ctr.adm.pointsActiveTotal", { n: request.points_total, active: request.points_active })}{" "}
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
                <Fact label={t("ctr.f.company")} value={request.company_name} />
                <Fact label={t("ctr.f.legalRep")} value={request.holder_name ?? "—"} />
                <Fact label={t("ctr.f.legalRepFiscalCode")} value={request.legal_rep_fiscal_code ?? "—"} mono />
              </>
            ) : (
              <>
                <Fact label={t("ctr.f.holder")} value={request.holder_name ?? "—"} />
                <Fact label={t("ctr.f.fiscalCode")} value={request.holder_fiscal_code ?? "—"} mono />
              </>
            )}
            {request.fiscal_code_problems.length > 0 && (
              <Fact label={t("ctr.f.fiscalCodeToCheck")} value={request.fiscal_code_problems.join("; ")} />
            )}
            <Fact
              label={t("ctr.adm.born")}
              value={
                request.holder_birth_date
                  ? t("ctr.adm.bornValue", { date: new Date(request.holder_birth_date).toLocaleDateString(fmt.tag), place: request.holder_birth_place ?? "—" })
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
                  {t("ctr.adm.notesForAdmin")}
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
              <h3 className="text-sm font-bold text-slate-900">{t("ctr.adm.praticaContracts")}</h3>
              {request.status === "DRAFT" && (
                <button
                  onClick={() => setEditing(true)}
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white transition cursor-pointer"
                >
                  {t("ctr.adm.editPratica")}
                </button>
              )}
              {canUnlock && (
                <button
                  onClick={unlock}
                  disabled={unlocking}
                  title={t("ctr.adm.unlockTitle")}
                  className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-xs font-bold text-white transition cursor-pointer disabled:opacity-50"
                >
                  {unlocking ? t("ctr.adm.unlocking") : t("ctr.adm.unlock")}
                </button>
              )}
              {toReview.length > 0 && (
                <button
                  onClick={() => setBulkOpen(true)}
                  className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white transition cursor-pointer"
                >
                  {toReview.length === 1 ? t("ctr.adm.approveOneInReview") : t("ctr.adm.approveNInReview", { n: toReview.length })}
                </button>
              )}
            </div>
            <div className="space-y-2">
              {request.points.map((point) => (
                <div key={point.id} className="rounded-2xl border border-slate-200 bg-white/70">
                  <div className="p-3.5 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_auto] items-start gap-x-4 gap-y-3">
                    <div className="min-w-0">
                      <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
                        {t("ctr.adm.contractId", { id: point.id.slice(0, 8).toUpperCase() })}
                      </p>
                      <p className="text-sm font-bold text-slate-900 font-mono break-all">{pointCode(point)}</p>
                    </div>
                    <div className="min-w-0">
                      <p
                        className={`text-xs font-semibold break-words ${
                          point.product_name ? " text-slate-900" : "text-amber-700"
                        }`}
                      >
                        {point.product_name ?? t("ctr.adm.noPackage")}
                      </p>
                      <p className=" text-slate-500 tabular-nums">
                        {point.gross_amount_cents != null ? euro(point.gross_amount_cents) : "—"}
                        {point.vat_amount_cents ? ` (${t("ctr.f.vatRate", { rate: point.vat_rate ?? 0 })})` : ""}
                      </p>
                    </div>
                    <div className="min-w-0 space-y-1">
                      <button
                        onClick={() => onHistory(point.id)}
                        title={t("ctr.adm.statusHistory")}
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold border cursor-pointer ${contractStatusBadge(point.status)}`}
                      >
                        {status(point.status)}
                      </button>
                      <p className="text-[10px] text-slate-500">
                        {point.paid_at ? (
                          <span className="text-emerald-400">
                            {t("ctr.f.paid")}{point.payment_plan ? ` · ${plan(point.payment_plan)}` : ""}
                          </span>
                        ) : (
                          t("ctr.adm.notPaid")
                        )}
                        {point.instalments_total && point.instalments_total > 1
                          ? ` · ${t("ctr.point.instalmentsRatio", { paid: point.instalments_paid, total: point.instalments_total })}`
                          : ""}
                      </p>
                      <p className={`text-[10px] ${point.documents_missing > 0 || point.documents_rejected > 0 ? "text-amber-700" : "text-slate-500"}`}>
                        {point.documents_missing > 0
                          ? t("ctr.adm.docsMissingN", { n: point.documents_missing })
                          : point.documents_rejected > 0
                            ? t("ctr.adm.docsRejectedN", { n: point.documents_rejected })
                            : t("ctr.adm.docsComplete")}
                      </p>
                    </div>
                    <div className="min-w-0 flex flex-wrap items-center gap-1.5 sm:col-span-2 xl:col-span-1 xl:justify-end">
                      <button
                        onClick={() => setOpenPoint(openPoint === point.id ? null : point.id)}
                        className="px-2.5 py-1 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 font-semibold cursor-pointer"
                      >
                        {openPoint === point.id ? t("common.close") : t("ctr.pfc.flow.documents")}
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
                          {point.product_version_id ? t("ctr.adm.changePackage") : t("ctr.adm.choosePackage")}
                        </button>
                      )}
                      {point.product_version_id && (
                        <button
                          onClick={() => onCommissions(point.id)}
                          className="px-2.5 py-1 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 font-semibold cursor-pointer"
                        >
                          {t("ctr.preview.col.commissions")}
                        </button>
                      )}
                      {point.status !== "DRAFT" && (
                        <button
                          onClick={() => onReview(point)}
                          className="px-2.5 py-1 rounded-lg bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-600 text-[11px] font-semibold cursor-pointer"
                        >
                          {t("ctr.adm.reviewContract")}
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
            <h3 className="text-sm font-bold text-slate-900">{t("ctr.adm.holderDocs")}</h3>
            <p className="text-xs text-slate-500">
              {t("ctr.adm.holderDocsHint")}
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
  const { t, euro, pointCode } = useLabels();
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
      setError(err.message || t("ctr.adm.packageError"));
    } finally {
      setSaving(null);
    }
  }

  return (
    <FullScreenPanel title={t("ctr.adm.packageOf", { name: pointCode(point) })} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-xs text-slate-500">
          {point.product_name
            ? t("ctr.adm.packageCurrent", { name: point.product_name })
            : t("ctr.adm.packageNone")}
        </p>
        {error && <p className="text-xs text-rose-400">{error}</p>}
        {packages.length === 0 && <p className="text-xs text-slate-500">{t("ctr.adm.noPackages")}</p>}
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
                    ? ` · ${t("ctr.pay.inInstalments", { amount: euro(version.contract_instalments_net_amount_cents) })}`
                    : ""}
                  {current ? ` · ${t("ctr.adm.current")}` : saving === version.id ? " · ..." : ""}
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
  const { t, euro, pointCode, status } = useLabels();
  const [reason, setReason] = useState(() => t("ctr.adm.defaultReason"));
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
          message: `${pointCode(point)}: ${status(updated.status)}`,
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
            {points.length === 1 ? t("ctr.adm.approveOne") : t("ctr.adm.approveN", { n: points.length })}
          </h3>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer" aria-label={t("common.close")}>✕</button>
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
              {t("common.close")}
            </button>
          </>
        ) : (
          <>
            <p className="text-xs text-slate-500">
              {t("ctr.adm.bulkIntro")}
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
                            {point.product_name} · {t("ctr.adm.nBeneficiaries", { n: preview.beneficiaries.filter((b) => b.total_cents > 0).length })}
                            {preview.warnings.length > 0 && <span className="text-amber-700"> · {t("ctr.adm.nWarnings", { n: preview.warnings.length })}</span>}
                            {preview.already_accepted && ` · ${t("ctr.adm.previewAlreadyAccepted")}`}
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
                  {t("ctr.adm.totalCommissions")} <strong className="text-brand-600">{euro(total)}</strong>
                </p>
              </div>
            )}
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-600 block">{t("ctr.adm.reason")}</label>
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
                {t("ctr.adm.bulkConsent")}
              </span>
            </label>
            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="px-4 py-2 rounded-xl bg-slate-50 hover:bg-slate-100 text-xs font-semibold text-slate-600 cursor-pointer">
                {t("common.cancel")}
              </button>
              <button
                onClick={approveAll}
                disabled={!previews || !checked || !reason.trim() || running}
                className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
              >
                {running ? t("ctr.adm.approving") : t("ctr.adm.acceptApproveN", { n: points.length })}
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
  const { t, euro, formatDate, pointCode } = useLabels();
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
    if (!window.confirm(t("ctr.adm.confirmTransfer", { amount: euro(request.bank_transfer_total_cents ?? 0), code: request.code, n: toPay.length }))) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/proxy/contract-requests/${request.id}/bank-transfer/confirm`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await onDone();
    } catch (err: any) {
      setError(err.message || t("ctr.adm.confirmTransferError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-5 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700">{t("ctr.adm.transferToConfirm")}</p>
          <p className="text-2xl font-extrabold text-slate-900 tabular-nums">{euro(request.bank_transfer_total_cents ?? 0)}</p>
          <p className="text-xs text-slate-500">
            {toPay.length === 1 ? t("ctr.count.oneContract") : t("ctr.count.nContracts", { n: toPay.length })} ·{" "}
            {t("ctr.adm.chosenOn", { date: formatDate(request.bank_transfer_requested_at) })} ·{" "}
            {t("ctr.adm.referenceValue", { code: request.code })}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {request.payment_proof_uploaded_at ? (
            <button onClick={openProof} className="px-3 py-2 rounded-xl bg-sky-600/10 hover:bg-sky-600/20 border border-sky-500/20 text-sky-400 text-xs font-semibold cursor-pointer">
              {t("ctr.adm.viewProof", { date: formatDate(request.payment_proof_uploaded_at) })}
            </button>
          ) : (
            <span className="px-3 py-2 text-xs text-slate-500">{t("ctr.adm.noProof")}</span>
          )}
          <button onClick={confirm} disabled={busy} className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50">
            {busy ? t("ctr.adm.confirming") : t("ctr.adm.confirmTransferReceived")}
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

