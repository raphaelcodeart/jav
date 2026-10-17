"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ContractDocumentsPanel } from "@/components/contract-documents-panel";
import { friendlyApiError } from "@/lib/api-error";
import { contractStatusBadge } from "@/lib/contract-status";
import { useI18n } from "@/lib/i18n/provider";
import type { ContractRequestDetailRead, ContractRequestPointRead, ContractRequestSummaryRead } from "@/lib/types";

export type WizardTarget = {
  requestId: string;
  step?: "documents" | "packages" | "summary";
  /** Session 66: which customer the pratica belongs to, when the list spans
      several of them (the promoter's "Attivazioni"). */
  customer?: { id: string; kind: string | null; email: string | null; firstName?: string | null; lastName?: string | null };
};

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

type T = ReturnType<typeof useI18n>["t"];

/** "1 contratto" / "3 contratti". */
function contractsCount(t: T, n: number): string {
  return n === 1 ? t("ctr.count.oneContract") : t("ctr.count.nContracts", { n });
}

/** What a pratica is waiting for, in one sentence -- the first thing the
    customer (or their promoter) reads on the card. */
function nextStepFor(
  t: T,
  euro: (cents: number) => string,
  r: ContractRequestSummaryRead,
  canPay: boolean,
): { text: string; tone: "action" | "wait" | "done" } {
  if (r.status === "DRAFT") {
    return {
      text: r.points_total === 0
        ? t("ctr.next.draftComplete")
        : r.points_without_package > 0
          ? t("ctr.next.draftChooseOffer", { contracts: contractsCount(t, r.points_without_package) })
          : t("ctr.next.draftReady"),
      tone: "action",
    };
  }
  if (r.bank_transfer_pending) {
    return {
      text: canPay
        ? r.bank_transfer_total_cents
          ? t("ctr.next.transferChosenAmount", { amount: euro(r.bank_transfer_total_cents) })
          : t("ctr.next.transferChosen")
        : t("ctr.next.transferPending"),
      tone: "wait",
    };
  }
  if (r.points_payable > 0) {
    return {
      text: canPay
        ? t("ctr.next.toPay", { contracts: contractsCount(t, r.points_payable) })
        : t("ctr.next.awaitingCustomerPayment", { contracts: contractsCount(t, r.points_payable) }),
      tone: "action",
    };
  }
  if (r.points_documents_pending > 0) {
    return {
      text: t("ctr.next.documentsMissing", { contracts: contractsCount(t, r.points_documents_pending) }),
      tone: "action",
    };
  }
  if (r.points_active === r.points_total && r.points_total > 0) return { text: t("ctr.next.allActive"), tone: "done" };
  if (r.points_to_review > 0) return { text: t("ctr.next.underReview"), tone: "wait" };
  return { text: t("ctr.next.inProgress"), tone: "wait" };
}

/** "I miei Contratti" as a list of pratiche (Session 52): each one opens on
    its contracts, each one with its own status, package and documents.

    `mode="customer"` lists the logged-in customer's own; `mode="promoter"`
    one customer of the promoter's (`customerId`), with everything except
    the payment. */
export function ContractRequestsList({
  mode,
  customerId,
  onOpenWizard,
}: {
  /** "admin" (Session 67): the pratiche the administration opened, or one
      customer's; like the promoter, everything but paying. */
  mode: "customer" | "promoter" | "admin";
  /** Left out in promoter mode: every pratica of every customer of theirs. */
  customerId?: string;
  onOpenWizard: (target: WizardTarget) => void;
}) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const formatDate = (v: string | null | undefined) => (v ? new Date(v).toLocaleDateString(fmt.tag) : "—");
  const allCustomers = mode !== "customer" && !customerId;
  const path =
    mode === "customer"
      ? "/api/proxy/contract-requests/mine"
      : mode === "admin"
        ? customerId
          ? `/api/proxy/contract-requests?customer_id=${customerId}`
          : "/api/proxy/contract-requests?created_by_role=ADMIN&limit=100"
        : allCustomers
          ? "/api/proxy/contract-requests/for-my-customers"
          : `/api/proxy/contract-requests/for-customer/${customerId}`;
  const { data, error, isLoading } = useQuery({
    queryKey: ["contract-requests", mode, customerId ?? (allCustomers ? "all" : "mine")],
    queryFn: () => fetchJson<ContractRequestSummaryRead[]>(path),
    refetchOnWindowFocus: true,
  });
  const [expanded, setExpanded] = useState<string | null>(null);
  const [summaryOf, setSummaryOf] = useState<string | null>(null);

  if (isLoading) return <div className="h-28 rounded-2xl bg-slate-900/5 animate-pulse" />;
  if (error) return <p className="text-sm text-rose-400">{(error as Error).message}</p>;
  if (!data || data.length === 0) {
    return (
      <div className="glass-card rounded-2xl p-8 text-center border-slate-200">
        <p className="text-sm font-semibold text-slate-900">{t("ctr.list.empty")}</p>
        <p className="text-xs text-slate-500 mt-1">
          {mode === "customer"
            ? t("ctr.list.emptyCustomer")
            : mode === "admin" && allCustomers
              ? t("ctr.list.emptyAdmin")
              : allCustomers
              ? t("ctr.list.emptyPromoterAll")
              : t("ctr.list.emptyPromoterOne")}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {data.map((r) => {
        const next = nextStepFor(t, euro, r, mode === "customer");
        const isOpen = expanded === r.id;
        return (
          <div key={r.id} className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
            <div className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
              <button onClick={() => setExpanded(isOpen ? null : r.id)} className="text-left min-w-0 flex-1 cursor-pointer">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-bold text-slate-900">
                    {allCustomers && r.customer_name ? r.customer_name : t("ctr.list.praticaCode", { code: r.code })}
                  </span>
                  {allCustomers && <span className="text-[11px] text-slate-500 font-mono">#{r.code}</span>}
                  {r.status === "DRAFT" && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-slate-500/10 text-slate-400 border-slate-500/20">
                      {t("ctr.status.DRAFT")}
                    </span>
                  )}
                  {r.created_by_role === "ADMIN" && mode !== "customer" && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-violet-500/10 text-violet-400 border-violet-500/20">
                      {t("ctr.list.openedByAdmin")}
                    </span>
                  )}
                  {r.activated_by_promoter_name && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-sky-500/10 text-sky-400 border-sky-500/20">
                      {mode === "customer"
                        ? r.created_by_role === "ADMIN"
                          ? t("ctr.list.preparedByJav")
                          : t("ctr.list.preparedByYourPromoter", { name: r.activated_by_promoter_name })
                        : r.created_by_role === "ADMIN"
                          ? t("ctr.list.promoterName", { name: r.activated_by_promoter_name })
                          : t("ctr.list.filledBy", { name: r.activated_by_promoter_name })}
                    </span>
                  )}
                  <span className="text-[11px] text-slate-500">
                    {formatDate(r.submitted_at ?? r.created_at)} · {contractsCount(t, r.points_total)}
                    {r.payment_plans.length > 0 && ` · ${r.payment_plans.map((p) => t.dyn(`ctr.plan.${p}`, p)).join(", ")}`}
                  </span>
                </div>
                <p
                  className={`text-xs mt-1 ${
                    next.tone === "action" ? "text-amber-700" : next.tone === "done" ? "text-emerald-400" : " text-slate-500"
                  }`}
                >
                  {next.text}
                </p>
                {r.holder_name && (
                  <p className=" text-slate-500 mt-1">{t("ctr.list.holderValue", { name: r.holder_name })}</p>
                )}
                {r.status !== "DRAFT" && r.points_total > 0 && (
                  <div className="mt-2 flex items-center gap-2">
                    <div className="h-1.5 flex-1 max-w-48 rounded-full bg-slate-200 overflow-hidden">
                      <div className="h-full bg-emerald-500" style={{ width: `${(r.points_active / r.points_total) * 100}%` }} />
                    </div>
                    <span className="text-[10px] text-slate-500 tabular-nums">
                      {t("ctr.list.activeRatio", { active: r.points_active, total: r.points_total })}
                    </span>
                  </div>
                )}
              </button>
              <div className="flex items-center gap-2 shrink-0">
                {r.total_gross_cents > 0 && (
                  <span className="text-right mr-1">
                    <span className="block text-sm font-bold text-slate-900 tabular-nums">{euro(r.total_gross_cents)}</span>
                    {r.points_paid > 0 && r.total_paid_cents > 0 && r.total_paid_cents !== r.total_gross_cents && (
                      <span className="block text-[10px] text-emerald-400 tabular-nums">{t("ctr.list.paidAmount", { amount: euro(r.total_paid_cents) })}</span>
                    )}
                  </span>
                )}
                {r.status !== "DRAFT" && (
                  <button
                    onClick={() => setSummaryOf(r.id)}
                    className="px-3 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-xs font-semibold text-slate-600 transition cursor-pointer"
                  >
                    {t("ctr.list.summary")}
                  </button>
                )}
                {r.status === "DRAFT" ? (
                  <button
                    onClick={() => onOpenWizard({ requestId: r.id, customer: wizardCustomer(r) })}
                    className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white transition cursor-pointer"
                  >
                    {t("ctr.list.resume")}
                  </button>
                ) : mode === "customer" && r.points_payable > 0 ? (
                  <button
                    onClick={() => onOpenWizard({ requestId: r.id, step: "summary", customer: wizardCustomer(r) })}
                    className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white transition cursor-pointer"
                  >
                    {r.bank_transfer_pending ? t("ctr.list.transferDetails") : t("ctr.list.pay")}
                  </button>
                ) : (
                  <button
                    onClick={() => setExpanded(isOpen ? null : r.id)}
                    className="px-3 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-xs font-semibold text-slate-600 transition cursor-pointer"
                  >
                    {isOpen ? t("common.close") : t("ctr.list.details")}
                  </button>
                )}
              </div>
            </div>
            {isOpen && (
              <RequestPoints requestId={r.id} mode={mode === "customer" ? "customer" : "promoter"} onOpenWizard={onOpenWizard} />
            )}
          </div>
        );
      })}
      {summaryOf && <RequestSummaryModal requestId={summaryOf} onClose={() => setSummaryOf(null)} />}
    </div>
  );
}

/** Everything the customer filled in and what each contract costs, in one
    read (Session 65): holder, address, IBAN, and for every contract its package,
    price with VAT, payment and state. */
function RequestSummaryModal({ requestId, onClose }: { requestId: string; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const formatDate = (v: string | null | undefined) => (v ? new Date(v).toLocaleDateString(fmt.tag) : "—");
  const pointCode = (point: { position?: number }) =>
    point.position ? t("ctr.point.codeN", { n: point.position }) : t("ctr.point.code");
  const { data, error } = useQuery({
    queryKey: ["contract-request", requestId],
    queryFn: () => fetchJson<ContractRequestDetailRead>(`/api/proxy/contract-requests/${requestId}`),
  });
  const live = (data?.points ?? []).filter((p) => !["REJECTED", "CANCELLED"].includes(p.status));
  const listTotal = live.reduce((sum, p) => sum + (p.gross_amount_cents ?? 0), 0);
  const address = data ? [data.street, [data.postal_code, data.city].filter(Boolean).join(" "), data.province && `(${data.province})`].filter(Boolean).join(", ") : "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in" onClick={onClose}>
      <div
        className="w-full max-w-2xl max-h-[90vh] overflow-y-auto glass-card rounded-2xl border-slate-300 bg-white animate-scale-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-6 py-4 border-b border-slate-200 bg-white/95 backdrop-blur">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-brand-600">{t("ctr.summary.title")}</p>
            <h3 className="text-base font-bold text-slate-900">{data ? t("ctr.list.praticaCode", { code: data.code }) : t("ctr.summary.pratica")}</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer" aria-label={t("common.close")}>✕</button>
        </div>
        <div className="p-6 space-y-5">
          {error && <p className="text-sm text-rose-400">{(error as Error).message}</p>}
          {!data && !error && <div className="h-40 rounded-xl bg-slate-50 animate-pulse" />}
          {data && (
            <>
              <section className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-xs">
                {data.company_name && <SummaryFact label={t("ctr.f.company")} value={data.company_name} />}
                <SummaryFact label={data.company_name ? t("ctr.f.legalRep") : t("ctr.f.holder")} value={data.holder_name ?? "—"} />
                {data.legal_rep_fiscal_code && (
                  <SummaryFact label={t("ctr.f.legalRepFiscalCode")} value={data.legal_rep_fiscal_code} mono />
                )}
                {data.holder_fiscal_code && <SummaryFact label={t("ctr.f.fiscalCode")} value={data.holder_fiscal_code} mono />}
                {data.fiscal_code_problems.length > 0 && (
                  <SummaryFact label={t("ctr.f.fiscalCodeToCheck")} value={data.fiscal_code_problems.join("; ")} />
                )}
                {data.holder_birth_date && (
                  <SummaryFact
                    label={t("ctr.f.birthDatePlace")}
                    value={`${new Date(data.holder_birth_date).toLocaleDateString(fmt.tag)} · ${data.holder_birth_place ?? "—"}`}
                  />
                )}
                <SummaryFact label={t("ctr.f.submittedOn")} value={formatDate(data.submitted_at ?? data.created_at)} />
                <SummaryFact label="Email" value={data.email ?? "—"} />
                <SummaryFact label="PEC" value={data.pec ?? "—"} />
                <SummaryFact label={t("ctr.f.debitIban")} value={data.iban ?? "—"} mono />
                <SummaryFact label={t("ctr.f.address")} value={address || "—"} />
                {data.activated_by_promoter_name && <SummaryFact label={t("ctr.f.filledBy")} value={data.activated_by_promoter_name} />}
              </section>

              <section className="space-y-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  {t("ctr.summary.contractsN", { n: data.points.length })}
                </p>
                {data.points.map((p) => (
                  <div key={p.id} className="rounded-xl border border-slate-200 p-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900">
                          {pointCode(p)}
                        </p>
                        <p className="text-xs text-slate-700">{p.product_name ?? t("ctr.summary.contractNotChosen")}</p>
                      </div>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${contractStatusBadge(p.status)}`}>
                        {t.dyn(`ctr.status.${p.status}`, p.status)}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3 text-[11px]">
                      <SummaryFact label={t("ctr.f.price")} value={p.net_amount_cents != null ? euro(p.net_amount_cents) : "—"} />
                      <SummaryFact
                        label={p.vat_rate ? t("ctr.f.vatRate", { rate: p.vat_rate }) : t("ctr.f.vat")}
                        value={p.vat_amount_cents ? euro(p.vat_amount_cents) : t("ctr.f.vatNotApplied")}
                      />
                      <SummaryFact label={t("ctr.pay.total")} value={p.gross_amount_cents != null ? euro(p.gross_amount_cents) : "—"} strong />
                      <SummaryFact
                        label={t("ctr.log.col.payment")}
                        value={
                          p.paid_at
                            ? `${p.payment_plan ? t.dyn(`ctr.plan.${p.payment_plan}`, t("ctr.f.paid")) : t("ctr.f.paid")}${p.payment_method ? ` · ${t.dyn(`ctr.method.${p.payment_method}`, p.payment_method)}` : ""}`
                            : p.payment_method === "BANK_TRANSFER"
                              ? t("ctr.f.transferPending")
                              : t("ctr.f.toPay")
                        }
                      />
                    </div>
                    {p.instalments_total && p.instalments_total > 1 ? (
                      <p className="mt-1 text-[11px] text-slate-500">{t("ctr.f.instalmentsPaid", { paid: p.instalments_paid, total: p.instalments_total })}</p>
                    ) : null}
                    {(p.activated_at || p.expires_at) && (
                      <p className="mt-1 text-[11px] text-slate-500">
                        {t("ctr.f.activeFromExpires", { from: formatDate(p.activated_at), to: formatDate(p.expires_at) })}
                      </p>
                    )}
                  </div>
                ))}
              </section>

              <section className="rounded-xl bg-slate-900/5 border border-slate-200 p-4 space-y-1 text-sm">
                <div className="flex justify-between font-bold text-slate-900">
                  <span>{t("ctr.summary.contractsTotal")}</span>
                  <span className="tabular-nums">{euro(listTotal)}</span>
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryFact({ label, value, mono = false, strong = false }: { label: string; value: string; mono?: boolean; strong?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-slate-500">{label}</p>
      <p className={`truncate ${strong ? " text-slate-900 font-bold" : " text-slate-700 font-semibold"} ${mono ? "font-mono" : ""}`}>
        {value}
      </p>
    </div>
  );
}

/** Enough for the wizard to open an existing pratica of a customer the
    promoter is looking at from the all-customers list. */
function wizardCustomer(r: ContractRequestSummaryRead) {
  const [firstName, ...rest] = (r.holder_name ?? "").split(" ");
  return {
    id: r.customer_id,
    kind: r.customer_kind,
    email: null,
    firstName: firstName || null,
    lastName: rest.join(" ") || null,
  };
}

function RequestPoints({
  requestId,
  mode,
  onOpenWizard,
}: {
  requestId: string;
  mode: "customer" | "promoter";
  onOpenWizard: (target: WizardTarget) => void;
}) {
  const { data, error } = useQuery({
    queryKey: ["contract-request", requestId],
    queryFn: () => fetchJson<ContractRequestDetailRead>(`/api/proxy/contract-requests/${requestId}`),
  });
  const [openPoint, setOpenPoint] = useState<string | null>(null);
  const { t } = useI18n();

  if (error) return <p className="px-5 pb-4 text-sm text-rose-400">{(error as Error).message}</p>;
  if (!data) return <div className="mx-5 mb-4 h-20 rounded-xl bg-slate-900/5 animate-pulse" />;

  return (
    <div className="border-t border-slate-200 px-4 sm:px-5 py-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-slate-500">
        <span>
          {t("ctr.f.holder")}: <strong className=" text-slate-700">{data.holder_name ?? "—"}</strong>
          {data.email ? ` · ${data.email}` : ""}
          {data.activated_by_promoter_name ? ` · ${t("ctr.list.filledByLower", { name: data.activated_by_promoter_name })}` : ""}
        </span>
        {data.status !== "DRAFT" && (
          <button
            onClick={() => onOpenWizard({ requestId, step: "documents", customer: wizardCustomer(data) })}
            className="font-semibold text-brand-600 hover:text-brand-600 cursor-pointer"
          >
            {t("ctr.list.idDocuments")}
          </button>
        )}
      </div>

      {data.points.map((point) => (
        <PointRow
          key={point.id}
          point={point}
          open={openPoint === point.id}
          onToggle={() => setOpenPoint(openPoint === point.id ? null : point.id)}
          mode={mode}
        />
      ))}
    </div>
  );
}

function PointRow({
  point,
  open,
  onToggle,
  mode,
}: {
  point: ContractRequestPointRead;
  open: boolean;
  onToggle: () => void;
  mode: "customer" | "promoter";
}) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const formatDate = (v: string | null | undefined) => (v ? new Date(v).toLocaleDateString(fmt.tag) : "—");
  const pointCode = (pt: { position?: number }) =>
    pt.position ? t("ctr.point.codeN", { n: pt.position }) : t("ctr.point.code");
  return (
    <div className="rounded-xl border border-slate-200 bg-white">
      <button onClick={onToggle} className="w-full flex items-center justify-between gap-3 p-3 text-left cursor-pointer">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
            {point.product_name ?? t("ctr.point.offerToChoose")}
          </p>
          <p className="text-sm font-semibold text-slate-900 font-mono truncate">{pointCode(point)}</p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${contractStatusBadge(point.status)}`}>
            {t.dyn(`ctr.status.${point.status}`, point.status)}
          </span>
          <span className="text-[10px] text-slate-500">
            {point.paid_at ? t("ctr.f.paid") : point.gross_amount_cents != null ? euro(point.gross_amount_cents) : ""}
            {point.instalments_total && point.instalments_total > 1 ? ` · ${t("ctr.point.instalmentsRatio", { paid: point.instalments_paid, total: point.instalments_total })}` : ""}
          </span>
        </div>
      </button>
      {open && (
        <div className="border-t border-slate-200 p-3 space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-[11px]">
            <Fact label={t("ctr.point.code")} value={point.id.slice(0, 8).toUpperCase()} mono />
            <Fact label={t("ctr.point.activeFrom")} value={formatDate(point.activated_at)} />
            <Fact label={t("ctr.point.expiry")} value={formatDate(point.expires_at)} />
          </div>
          {point.status === "REJECTED" && (
            <p className="text-xs text-rose-400">
              {t("ctr.point.rejected")}
            </p>
          )}
          {point.documents_missing > 0 && (
            <p className="text-xs text-amber-700">
              {mode === "customer" ? t("ctr.point.uploadAttachments") : t("ctr.point.attachmentsMissing")}
            </p>
          )}
          {mode === "customer" && <IbanEditor contractId={point.id} initialIban={point.iban} />}
          <ContractDocumentsPanel contractId={point.id} />
        </div>
      )}
    </div>
  );
}

/** The IBAN of one contract, correctable after the pratica was sent -- a
    customer may change bank, or have typed it wrong. */
function IbanEditor({ contractId, initialIban }: { contractId: string; initialIban: string | null }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(initialIban ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/proxy/contracts/${contractId}/iban`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ iban: value.replace(/\s/g, "").toUpperCase() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setEditing(false);
      await queryClient.invalidateQueries({ queryKey: ["contract-request"] });
    } catch (err: any) {
      setError(err.message || t("ctr.iban.invalid"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="text-[11px]">
      <span className="text-slate-500">{t("ctr.f.debitIban")}</span>
      {editing ? (
        <div className="flex items-center gap-2 mt-0.5">
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="IT00A0000000000000000000000"
            className="w-full max-w-xs rounded-lg glass-input px-2 py-1 text-xs uppercase font-mono focus:border-brand-500"
          />
          <button onClick={handleSave} disabled={saving} className="font-semibold text-emerald-400 cursor-pointer disabled:opacity-50">
            {saving ? "..." : t("common.save")}
          </button>
          <button onClick={() => setEditing(false)} className="font-semibold text-slate-500 cursor-pointer">
            {t("common.cancel")}
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 mt-0.5">
          <span className="font-mono text-slate-600">{initialIban ?? t("ctr.iban.notSet")}</span>
          <button onClick={() => { setValue(initialIban ?? ""); setEditing(true); }} className="font-semibold text-brand-600 cursor-pointer">
            {initialIban ? t("ctr.iban.edit") : t("ctr.iban.add")}
          </button>
        </div>
      )}
      {error && <p className="text-rose-400 mt-1">{error}</p>}
    </div>
  );
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-slate-500">{label}</p>
      <p className={` text-slate-700 font-semibold ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

/** For the few places that just need to refresh every pratiche list. */
export function useInvalidateContractRequests() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["contract-requests"] });
    queryClient.invalidateQueries({ queryKey: ["contract-request"] });
  };
}
