"use client";

import { Fragment, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ContractRequestWizard } from "@/components/contract-request-wizard";
import { NewCustomerForm } from "@/components/new-customer-form";
import { Pagination, usePagination } from "@/components/pagination";
import { PhotoUpload } from "@/components/photo-upload";
import { UnlockAccountModal } from "@/components/admin-unlock-account-modal";
import { friendlyApiError } from "@/lib/api-error";
import { downloadCsv } from "@/lib/csv-export";
import { useI18n } from "@/lib/i18n/provider";
import type { AgentListItemRead, ContractRead, CustomerDetailRead, CustomerRead, WalletRead } from "@/lib/types";

function contractStatusColor(status: string): string {
  if (status === "ACTIVE" || status === "RENEWED") return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
  if (status === "REJECTED" || status === "CANCELLED") return "bg-rose-500/10 text-rose-400 border-rose-500/20";
  if (status === "DRAFT") return "bg-slate-500/10 text-slate-400 border-slate-500/20";
  return "bg-amber-500/10 text-amber-700 border-amber-500/20";
}

async function fetchAllContracts(): Promise<ContractRead[]> {
  const res = await fetch("/api/proxy/contracts");
  if (!res.ok) throw new Error("Impossibile caricare i contratti.");
  return res.json();
}

async function fetchCustomers(): Promise<CustomerRead[]> {
  const res = await fetch("/api/proxy/customers");
  if (!res.ok) throw new Error("Impossibile caricare i clienti.");
  return res.json();
}

async function fetchCustomerDetail(id: string): Promise<CustomerDetailRead> {
  const res = await fetch(`/api/proxy/customers/${id}`);
  if (!res.ok) throw new Error("Impossibile caricare i dettagli del cliente.");
  return res.json();
}

async function fetchAgentsForReassign(): Promise<AgentListItemRead[]> {
  const res = await fetch("/api/proxy/network/agents");
  if (!res.ok) throw new Error("Impossibile caricare i promoter.");
  return res.json();
}

// null (not an error) means "this user has never transacted yet" -- the
// admin view deliberately does not lazily create a wallet just by looking.
async function fetchCustomerWallet(userId: string): Promise<WalletRead | null> {
  const res = await fetch(`/api/proxy/wallets/admin/${userId}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Impossibile caricare il wallet.");
  return res.json();
}

function CustomerAvatar({ url, size = 36 }: { url: string | null; size?: number }) {
  return (
    <div
      className="rounded-full overflow-hidden border border-slate-200 bg-slate-100 flex items-center justify-center shrink-0"
      style={{ width: size, height: size }}
    >
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element -- externally-hosted, variable-source uploaded photo
        <img src={url} alt="" className="w-full h-full object-cover" />
      ) : (
        <svg className="w-1/2 h-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      )}
    </div>
  );
}

const PRIVATE_LIKE = new Set(["PRIVATE", "SOLE_PROPRIETOR"]);

export function AdminCustomersPanel({
  initialActiveOnly = false,
  isSuperAdmin = false,
}: { initialActiveOnly?: boolean; isSuperAdmin?: boolean } = {}) {
  const { t, fmt } = useI18n();
  const kindLabel = (kind: string) => t.dyn(`adm.kind.${kind}`, kind);
  const queryClient = useQueryClient();
  // Session 88: il superadmin sblocca un cliente fermo ai controlli d'ingresso.
  const [unlocking, setUnlocking] = useState<CustomerRead | null>(null);
  const { data: customers, error: loadError } = useQuery({
    queryKey: ["admin", "customers"],
    queryFn: fetchCustomers,
  });
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");
  const [activeOnly, setActiveOnly] = useState(initialActiveOnly);

  // View popup
  const [viewingId, setViewingId] = useState<string | null>(null);
  const { data: viewingDetail, error: viewError } = useQuery({
    queryKey: ["admin", "customers", "detail", viewingId],
    queryFn: () => fetchCustomerDetail(viewingId!),
    enabled: viewingId !== null,
  });
  const { data: allContracts } = useQuery({
    queryKey: ["admin", "contracts", "all"],
    queryFn: fetchAllContracts,
  });
  const customerIdsWithActiveContract = new Set(
    (allContracts ?? []).filter((c) => c.status === "ACTIVE" || c.status === "RENEWED").map((c) => c.customer_id)
  );
  const [expandedContractId, setExpandedContractId] = useState<string | null>(null);
  const customerContracts = (allContracts ?? []).filter((c) => c.customer_id === viewingId);

  // Wallet ("Ricarica") -- shown inside the same detail popup, only when the
  // customer has a login (user_id) to attach a wallet to.
  const { data: viewingWallet } = useQuery({
    queryKey: ["admin", "wallets", "by-user", viewingDetail?.user_id],
    queryFn: () => fetchCustomerWallet(viewingDetail!.user_id!),
    enabled: !!viewingDetail?.user_id,
  });
  const [topUpAmount, setTopUpAmount] = useState("");
  const [topUpNote, setTopUpNote] = useState("");
  const [topUpLoading, setTopUpLoading] = useState(false);
  const [topUpError, setTopUpError] = useState<string | null>(null);
  const [topUpSuccess, setTopUpSuccess] = useState(false);
  // Stable across retries of the SAME top-up, rotated only once one actually
  // succeeds. A fresh key per click (what this used to send) meant that
  // clicking "Ricarica" again after an error could credit the wallet twice --
  // and an error was reachable on a top-up that had in fact already gone
  // through, because the credit is committed before the confirmation email is
  // attempted. See also core/email.py::send_html_email_best_effort.
  const topUpKeyRef = useRef<string>("");

  async function handleTopUp(e: React.FormEvent) {
    e.preventDefault();
    if (!viewingDetail?.user_id) return;
    const amountCents = Math.round(parseFloat(topUpAmount.replace(",", ".")) * 100);
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      setTopUpError(t("adm.cust.invalidAmount"));
      return;
    }
    setTopUpLoading(true);
    setTopUpError(null);
    try {
      const res = await fetch("/api/proxy/wallets/admin/topup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: viewingDetail.user_id,
          amount_cents: amountCents,
          note: topUpNote || null,
          idempotency_key: topUpKeyRef.current,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setTopUpSuccess(true);
      setTopUpAmount("");
      setTopUpNote("");
      // This form stays open after a successful top-up, so the next one is a
      // genuinely different operation and needs its own key.
      topUpKeyRef.current = crypto.randomUUID();
      await queryClient.invalidateQueries({ queryKey: ["admin", "wallets", "by-user", viewingDetail.user_id] });
      setTimeout(() => setTopUpSuccess(false), 3000);
    } catch (err: any) {
      setTopUpError(err.message || t("adm.cust.topUpFailed"));
    } finally {
      setTopUpLoading(false);
    }
  }

  // Freeze/unfreeze login (SUPER_ADMIN only, see users/router.py)
  const [freezeLoadingId, setFreezeLoadingId] = useState<string | null>(null);
  const [freezeError, setFreezeError] = useState<string | null>(null);

  async function handleToggleFreeze(userId: string, currentlyFrozen: boolean) {
    setFreezeLoadingId(userId);
    setFreezeError(null);
    try {
      const res = await fetch(`/api/proxy/users/${userId}/${currentlyFrozen ? "unfreeze" : "freeze"}`, { method: "PATCH" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
    } catch (err: any) {
      setFreezeError(err.message || t("adm.cust.freezeFailed"));
    } finally {
      setFreezeLoadingId(null);
    }
  }

  // Edit form
  const [editingCustomer, setEditingCustomer] = useState<CustomerRead | null>(null);
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editPec, setEditPec] = useState("");
  const [editFirstName, setEditFirstName] = useState("");
  const [editLastName, setEditLastName] = useState("");
  const [editCompanyName, setEditCompanyName] = useState("");
  const [editFiscalCode, setEditFiscalCode] = useState("");
  const [editVatNumber, setEditVatNumber] = useState("");
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editPhotoUrl, setEditPhotoUrl] = useState<string | null>(null);

  const { data: editingDetail } = useQuery({
    queryKey: ["admin", "customers", "detail", editingCustomer?.id],
    queryFn: () => fetchCustomerDetail(editingCustomer!.id),
    enabled: !!editingCustomer,
  });
  const { data: agentsForReassign } = useQuery({
    queryKey: ["admin", "agents", "for-reassign"],
    queryFn: fetchAgentsForReassign,
  });

  // Reassign promoter
  const [reassignAgentId, setReassignAgentId] = useState("");
  const [reassignReason, setReassignReason] = useState("");
  const [reassignLoading, setReassignLoading] = useState(false);
  const [reassignError, setReassignError] = useState<string | null>(null);
  const [reassignSuccess, setReassignSuccess] = useState(false);

  async function handleReassign(e: React.FormEvent) {
    e.preventDefault();
    if (!editingCustomer || !reassignAgentId) return;
    setReassignLoading(true);
    setReassignError(null);
    try {
      const res = await fetch(`/api/proxy/customers/${editingCustomer.id}/reassign-promoter`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_agent_id: reassignAgentId, reason: reassignReason }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setReassignSuccess(true);
      setReassignAgentId("");
      setReassignReason("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers", "detail", editingCustomer.id] });
      setTimeout(() => setReassignSuccess(false), 3000);
    } catch (err: any) {
      setReassignError(err.message || t("adm.cust.reassignFailed"));
    } finally {
      setReassignLoading(false);
    }
  }

  function openView(id: string) {
    setTopUpAmount("");
    setTopUpNote("");
    setTopUpError(null);
    setTopUpSuccess(false);
    topUpKeyRef.current = crypto.randomUUID();
    setViewingId(id);
  }

  function openEdit(c: CustomerRead) {
    setEditEmail(c.email);
    setEditPhone(c.phone ?? "");
    setEditPec(c.pec ?? "");
    setEditFiscalCode(c.fiscal_code ?? "");
    setEditVatNumber(c.vat_number ?? "");
    const parts = c.display_name.trim().split(/\s+/);
    if (PRIVATE_LIKE.has(c.kind)) {
      setEditFirstName(parts.slice(0, -1).join(" ") || parts[0] || "");
      setEditLastName(parts.length > 1 ? parts[parts.length - 1]! : "");
      setEditCompanyName("");
    } else {
      setEditFirstName("");
      setEditLastName("");
      setEditCompanyName(c.display_name);
    }
    setEditError(null);
    setEditPhotoUrl(c.photo_url);
    setReassignAgentId("");
    setReassignReason("");
    setReassignError(null);
    setEditingCustomer(c);
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editingCustomer) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const res = await fetch(`/api/proxy/customers/${editingCustomer.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: editEmail,
          phone: editPhone || null,
          pec: editPec || null,
          fiscal_code: editFiscalCode || null,
          vat_number: editVatNumber || null,
          first_name: PRIVATE_LIKE.has(editingCustomer.kind) ? editFirstName : null,
          last_name: PRIVATE_LIKE.has(editingCustomer.kind) ? editLastName : null,
          company_name: PRIVATE_LIKE.has(editingCustomer.kind) ? null : editCompanyName,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setEditingCustomer(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
    } catch (err: any) {
      setEditError(err.message || t("adm.cust.editFailed"));
    } finally {
      setEditLoading(false);
    }
  }

  // A pratica opened from this list (Session 67): right after registering a
  // customer, or from a row's "Attiva contratti".
  const [wizardFor, setWizardFor] = useState<{ customer: CustomerRead; producer: string | null } | null>(null);
  const [loginLoadingId, setLoginLoadingId] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  async function handleCreateLogin(c: CustomerRead) {
    if (!window.confirm(t("adm.cust.createLoginConfirm", { name: c.display_name, email: c.email }))) return;
    setLoginLoadingId(c.id);
    setLoginError(null);
    try {
      const res = await fetch(`/api/proxy/customers/${c.id}/account`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
    } catch (err: any) {
      setLoginError(err.message || t("adm.cust.createLoginFailed"));
    } finally {
      setLoginLoadingId(null);
    }
  }

  const filtered = (customers ?? []).filter(
    (c) =>
      (!activeOnly || customerIdsWithActiveContract.has(c.id)) &&
      (c.display_name.toLowerCase().includes(search.toLowerCase()) ||
        c.email.toLowerCase().includes(search.toLowerCase()))
  );

  // Paginates the FILTERED list, so search/filters narrow the result set
  // first and paging then walks whatever is left. CSV export below
  // deliberately still uses `filtered`, not the current page -- exporting
  // only the 25 rows you happen to be looking at would be a trap.
  const pagination = usePagination(filtered);

  const handleExportCsv = () => {
    downloadCsv(
      `clienti_${new Date().toISOString().slice(0, 10)}`,
      ["ID", t("adm.cust.name"), t("adm.cust.kind"), "Email", t("adm.cust.phone"), t("adm.cust.fiscalCode"), t("adm.cust.vatNumber"), t("adm.cust.hasActiveContract")],
      filtered.map((c) => [
        c.id, c.display_name, c.kind, c.email, c.phone ?? "", c.fiscal_code ?? "", c.vat_number ?? "",
        customerIdsWithActiveContract.has(c.id) ? t("adm.cust.yes") : t("adm.cust.no"),
      ])
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
        <div className="w-full sm:max-w-xs relative">
          <input
            type="text"
            placeholder={t("adm.cust.search")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl glass-input pl-10 pr-4 py-2 text-xs focus:border-brand-500"
          />
          <svg className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <label className="flex items-center gap-1.5 text-xs text-slate-500 cursor-pointer whitespace-nowrap">
            <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} className="cursor-pointer" />
            {t("adm.cust.activeOnly")}
          </label>
          <button
            onClick={handleExportCsv}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            CSV
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-500/20 transition cursor-pointer"
          >
            + {t("adm.cust.newCustomer")}
          </button>
        </div>
      </div>

      {loadError && <p className="text-sm text-rose-400">{t("adm.cust.loadFailed")}</p>}
      {freezeError && <p className="text-sm text-rose-400">{freezeError}</p>}
      {loginError && <p className="text-sm text-rose-400">{loginError}</p>}

      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                <th className="py-3 px-6"></th>
                <th className="py-3 px-6">{t("adm.cust.fullName")}</th>
                <th className="py-3 px-6">{t("adm.cust.type")}</th>
                <th className="py-3 px-6">Email</th>
                <th className="py-3 px-6">{t("adm.cust.phone")}</th>
                <th className="py-3 px-6 text-right">{t("adm.client.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {customers === undefined ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-slate-500">{t("adm.overview.loading")}</td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-slate-500">{t("adm.cust.noneFound")}</td>
                </tr>
              ) : (
                pagination.pageItems.map((c) => (
                  <tr key={c.id} className=" text-slate-600 hover:bg-slate-100 transition-colors">
                    <td className="py-4 px-6"><CustomerAvatar url={c.photo_url} /></td>
                    <td className="py-4 px-6">
                      <p className="font-medium text-slate-900">{c.display_name}</p>
                      <p className="text-[10px] text-slate-500">{c.email}</p>
                      <p className="text-[10px] text-slate-500">{t("adm.cust.joined", { date: fmt.shortDate(c.created_at) })}</p>
                      {!c.user_id && (
                        <span className="inline-block mt-1.5 px-1.5 py-0.5 rounded text-[9px] font-bold border bg-amber-500/10 text-amber-700 border-amber-500/20">
                          {t("adm.cust.noLogin")}
                        </span>
                      )}
                      {c.user_id && (
                        <div className="flex items-center gap-1 mt-1.5">
                          <span
                            title={c.email_verified ? t("adm.cust.emailVerified") : t("adm.cust.emailNotVerified")}
                            className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${
                              c.email_verified
                                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                            }`}
                          >
                            Email {c.email_verified ? "✓" : "✗"}
                          </span>
                          <span
                            title={c.privacy_accepted ? t("adm.unlock.privacyAccepted") : t("adm.cust.privacyNotAccepted")}
                            className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${
                              c.privacy_accepted
                                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                            }`}
                          >
                            {t("adm.cust.privacyBadge")} {c.privacy_accepted ? "✓" : "✗"}
                          </span>
                          {c.profile_complete != null && (
                            <span
                              title={c.profile_complete ? t("adm.cust.profileComplete") : t("adm.cust.profileIncomplete")}
                              className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${
                                c.profile_complete
                                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                  : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                              }`}
                            >
                              {t("adm.cust.profileBadge")} {c.profile_complete ? "✓" : "✗"}
                            </span>
                          )}
                          {isSuperAdmin && (!c.email_verified || !c.privacy_accepted || c.profile_complete === false) && (
                            <button
                              onClick={() => setUnlocking(c)}
                              title={t("adm.cust.unlockTitle")}
                              className="px-1.5 py-0.5 rounded text-[9px] font-bold border border-brand-500/40 text-brand-600 hover:bg-brand-500/10 cursor-pointer"
                            >
                              {t("adm.cust.unlock")}
                            </button>
                          )}
                          {c.user_status === "FROZEN" && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold border bg-sky-500/10 text-sky-400 border-sky-500/20">
                              {t("adm.cust.frozen")}
                            </span>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="py-4 px-6">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 text-amber-700 border-amber-500/20">
                        {kindLabel(c.kind)}
                      </span>
                    </td>
                    <td className="py-4 px-6">{c.email}</td>
                    <td className="py-4 px-6">{c.phone ?? "—"}</td>
                    <td className="py-4 px-6">
                      <div className="flex items-center justify-end gap-1.5">
                        {c.user_id ? (
                          <button
                            onClick={() => setWizardFor({ customer: c, producer: null })}
                            title={t("adm.cust.activateContractsTitle")}
                            className="px-2.5 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-[11px] font-bold transition cursor-pointer whitespace-nowrap"
                          >
                            + {t("adm.client.contracts")}
                          </button>
                        ) : (
                          <button
                            onClick={() => handleCreateLogin(c)}
                            disabled={loginLoadingId === c.id}
                            title={t("adm.cust.noLoginTitle")}
                            className="px-2.5 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-700 text-[11px] font-bold transition cursor-pointer whitespace-nowrap disabled:opacity-50"
                          >
                            {loginLoadingId === c.id ? t("adm.cust.creating") : t("adm.cust.createLogin")}
                          </button>
                        )}
                        <button
                          onClick={() => openView(c.id)}
                          title={t("adm.cust.showDetails")}
                          className="p-1.5 rounded-lg bg-slate-900/5 hover:bg-slate-100 text-slate-500 hover:text-slate-900 transition cursor-pointer"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                          </svg>
                        </button>
                        <button
                          onClick={() => openEdit(c)}
                          title={t("adm.cust.editCustomer")}
                          className="p-1.5 rounded-lg bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-600 transition cursor-pointer"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                        </button>
                        {isSuperAdmin && c.user_id && (
                          <button
                            onClick={() => handleToggleFreeze(c.user_id!, c.user_status === "FROZEN")}
                            disabled={freezeLoadingId === c.user_id}
                            title={c.user_status === "FROZEN" ? t("adm.cust.reactivate") : t("adm.cust.freeze")}
                            className={`p-1.5 rounded-lg border transition cursor-pointer disabled:opacity-50 ${
                              c.user_status === "FROZEN"
                                ? "bg-emerald-600/10 hover:bg-emerald-600/20 border-emerald-500/20 text-emerald-400"
                                : "bg-sky-600/10 hover:bg-sky-600/20 border-sky-500/20 text-sky-400"
                            }`}
                          >
                            {c.user_status === "FROZEN" ? (
                              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 11V7a4 4 0 118 0m-4 8v2m-6 2h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z" />
                              </svg>
                            ) : (
                              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                              </svg>
                            )}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="px-6 pb-5">
          <Pagination {...pagination} label={t("adm.cust.customersLower")} />
        </div>
      </div>

      {unlocking?.user_id && (
        <UnlockAccountModal
          userId={unlocking.user_id}
          customerName={unlocking.display_name}
          onClose={() => setUnlocking(null)}
        />
      )}
      {wizardFor && (
        <ContractRequestWizard
          customer={{
            id: wizardFor.customer.id,
            kind: wizardFor.customer.kind,
            email: wizardFor.customer.email,
            firstName: wizardFor.customer.first_name,
            lastName: wizardFor.customer.last_name,
            pec: wizardFor.customer.pec,
            fiscalCode: wizardFor.customer.fiscal_code,
          }}
          producerAgentId={wizardFor.producer}
          onClose={() => setWizardFor(null)}
        />
      )}

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-slate-900">{t("adm.cust.newCustomer")}</h3>
              <button
                onClick={() => setShowCreate(false)}
                className="p-1 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-900 transition cursor-pointer"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p className="text-xs text-slate-500 mb-4">
              {t("adm.cust.newCustomerHint")}
            </p>
            <NewCustomerForm
              mode="admin"
              agents={agentsForReassign}
              submitLabel={t("adm.cust.registerAndActivate")}
              onCancel={() => setShowCreate(false)}
              onCreated={async (customer, promoterAgentId) => {
                setShowCreate(false);
                await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
                setWizardFor({ customer, producer: promoterAgentId });
              }}
            />
          </div>
        </div>
      )}

      {viewingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-slate-900">{t("adm.cust.details")}</h3>
              <button onClick={() => setViewingId(null)}
                className="p-1 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-900 transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {viewError && <p className="text-sm text-rose-400">{t("adm.cust.detailsFailed")}</p>}
            {!viewingDetail && !viewError && <p className="text-sm text-slate-500 text-center py-8">{t("adm.overview.loading")}</p>}

            {viewingDetail && (
              <div className="space-y-4 text-sm">
                <div>
                  <p className="text-lg font-semibold text-slate-900">{viewingDetail.display_name}</p>
                  <span className="inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 text-amber-700 border-amber-500/20">
                    {kindLabel(viewingDetail.kind)}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-4 p-4 rounded-xl bg-slate-900/5 border border-slate-200">
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">Email</span>
                    <p className=" text-slate-700">{viewingDetail.email}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">{t("adm.cust.phone")}</span>
                    <p className=" text-slate-700">{viewingDetail.phone ?? "—"}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">PEC</span>
                    <p className=" text-slate-700">{viewingDetail.pec ?? "—"}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">{t("adm.cust.fiscalCode")}</span>
                    <p className="font-mono text-xs text-slate-700">{viewingDetail.fiscal_code ?? "—"}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">{t("adm.cust.vatNumber")}</span>
                    <p className="font-mono text-xs text-slate-700">{viewingDetail.vat_number ?? "—"}</p>
                  </div>
                </div>

                <div>
                  <p className="text-[10px] text-slate-500 uppercase font-semibold mb-2">{t("adm.client.contracts")}</p>
                  {customerContracts.length === 0 ? (
                    <p className="text-xs text-slate-500">{t("adm.cust.noContracts")}</p>
                  ) : (
                    <div className="rounded-xl border border-slate-200 overflow-hidden">
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className=" bg-slate-900/5 text-slate-500">
                            <th className="py-2 px-3 font-semibold">{t("adm.client.product")}</th>
                            <th className="py-2 px-3 font-semibold">{t("adm.client.status")}</th>
                            <th className="py-2 px-3 font-semibold">{t("adm.client.csv.expiry")}</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200">
                          {customerContracts.map((c) => (
                            <Fragment key={c.id}>
                              <tr
                                onClick={() => setExpandedContractId(expandedContractId === c.id ? null : c.id)}
                                className="cursor-pointer hover:bg-slate-100 transition-colors text-slate-600"
                              >
                                <td className="py-2 px-3">
                                  <div className="font-medium text-slate-900">{c.product_name ?? t("adm.client.product")}</div>
                                </td>
                                <td className="py-2 px-3">
                                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${contractStatusColor(c.status)}`}>
                                    {t.dyn(`adm.contractStatus.${c.status}`, c.status)}
                                  </span>
                                </td>
                                <td className="py-2 px-3">
                                  {c.expires_at ? fmt.shortDate(c.expires_at) : "—"}
                                </td>
                              </tr>
                              {expandedContractId === c.id && (
                                <tr className=" bg-slate-900/5">
                                  <td colSpan={3} className="py-3 px-3 text-slate-600 space-y-1">
                                    <div><span className="text-slate-500">{t("adm.cust.created")}</span> {fmt.shortDate(c.created_at)}</div>
                                    {c.activated_at && (
                                      <div><span className="text-slate-500">{t("adm.cust.activated")}</span> {fmt.shortDate(c.activated_at)}</div>
                                    )}
                                    {c.notes && <div><span className="text-slate-500">{t("adm.cust.notes")}</span> {c.notes}</div>}
                                    <div className="font-mono text-[10px] text-slate-500">{c.id}</div>
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {viewingDetail.addresses.length > 0 && (
                  <div>
                    <p className="text-[10px] text-slate-500 uppercase font-semibold mb-2">{t("adm.cust.addresses")}</p>
                    <div className="space-y-2">
                      {viewingDetail.addresses.map((a) => (
                        <div key={a.id} className="p-3 rounded-xl bg-slate-900/5 border border-slate-200 text-xs text-slate-600">
                          {a.street}, {a.postal_code} {a.city} ({a.province}) — {a.country}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {viewingDetail.user_id && (
                  <div>
                    <p className="text-[10px] text-slate-500 uppercase font-semibold mb-2">Wallet</p>
                    <div className="p-4 rounded-xl bg-slate-900/5 border border-slate-200 space-y-3">
                      {viewingWallet === undefined ? (
                        <p className="text-xs text-slate-500">{t("adm.overview.loading")}</p>
                      ) : viewingWallet === null ? (
                        <p className="text-xs text-slate-500">{t("adm.cust.noWallet")}</p>
                      ) : (
                        <div className="flex items-center justify-between">
                          <div>
                            <span className="text-[10px] text-slate-500 uppercase font-semibold">{t("adm.cust.balance")}</span>
                            <p className="text-lg font-bold text-slate-900">{fmt.euro(viewingWallet.balance_cents)}</p>
                          </div>
                          <span className="font-mono text-[10px] text-slate-500">{viewingWallet.address}</span>
                        </div>
                      )}

                      <form onSubmit={handleTopUp} className="flex items-end gap-2 pt-2 border-t border-slate-200">
                        <div className="space-y-1 flex-1">
                          <label className=" font-semibold text-slate-600 uppercase block">{t("adm.cust.amountEur")}</label>
                          <input
                            required
                            inputMode="decimal"
                            value={topUpAmount}
                            onChange={(e) => setTopUpAmount(e.target.value)}
                            placeholder="0,00"
                            className="w-full rounded-lg glass-input px-3 py-1.5 text-sm focus:border-brand-500"
                          />
                        </div>
                        <div className="space-y-1 flex-1">
                          <label className=" font-semibold text-slate-600 uppercase block">{t("adm.cust.noteOptional")}</label>
                          <input
                            value={topUpNote}
                            onChange={(e) => setTopUpNote(e.target.value)}
                            placeholder={t("adm.cust.notePlaceholder")}
                            className="w-full rounded-lg glass-input px-3 py-1.5 text-sm focus:border-brand-500"
                          />
                        </div>
                        <button type="submit" disabled={topUpLoading}
                          className="px-4 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50 shrink-0">
                          {topUpLoading ? "..." : t("adm.cust.topUp")}
                        </button>
                      </form>
                      {topUpError && (
                        <div className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{topUpError}</div>
                      )}
                      {topUpSuccess && (
                        <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">{t("adm.cust.topUpDone")}</div>
                      )}
                    </div>
                  </div>
                )}

                <p className="font-mono text-[10px] text-slate-500 pt-2 border-t border-slate-200">{viewingDetail.id}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {editingCustomer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-slate-900">{t("adm.cust.editCustomer")}</h3>
              <button onClick={() => setEditingCustomer(null)}
                className="p-1 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-900 transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="mb-5 pb-5 border-b border-slate-200">
              <label className="text-xs font-semibold text-slate-600 uppercase block mb-2">{t("adm.cust.photo")}</label>
              <PhotoUpload
                crop
                currentUrl={editPhotoUrl}
                uploadPath={`customers/${editingCustomer.id}/photo`}
                onUploaded={(url) => {
                  setEditPhotoUrl(url);
                  queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
                }}
                alt={editingCustomer.display_name}
              />
            </div>

            <form onSubmit={handleEditSave} className="space-y-4">
              {PRIVATE_LIKE.has(editingCustomer.kind) ? (
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.cust.firstName")}</label>
                    <input required value={editFirstName} onChange={(e) => setEditFirstName(e.target.value)}
                      className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.cust.lastName")}</label>
                    <input required value={editLastName} onChange={(e) => setEditLastName(e.target.value)}
                      className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                  </div>
                </div>
              ) : (
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.cust.companyName")}</label>
                  <input required value={editCompanyName} onChange={(e) => setEditCompanyName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600 uppercase block">Email</label>
                  <input required type="email" value={editEmail} onChange={(e) => setEditEmail(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.cust.phone")}</label>
                  <input value={editPhone} onChange={(e) => setEditPhone(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">PEC</label>
                <input type="email" value={editPec} onChange={(e) => setEditPec(e.target.value)}
                  placeholder="nome@pec.it"
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.cust.fiscalCode")}</label>
                  <input value={editFiscalCode} onChange={(e) => setEditFiscalCode(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.cust.vatNumber")}</label>
                  <input value={editVatNumber} onChange={(e) => setEditVatNumber(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              </div>

              {editError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{editError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setEditingCustomer(null)}
                  className="px-4 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 text-xs font-semibold text-slate-600 border border-slate-200 transition cursor-pointer">
                  {t("common.cancel")}
                </button>
                <button type="submit" disabled={editLoading}
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {editLoading ? t("adm.client.saving") : t("adm.cust.saveChanges")}
                </button>
              </div>
            </form>

            <div className="mt-6 pt-5 border-t border-slate-200">
              <label className="text-xs font-semibold text-slate-600 uppercase block mb-2">{t("adm.cust.refPromoter")}</label>
              <p className="text-xs text-slate-500 mb-3">
                {t("adm.cust.currentlyAssigned")} <span className="font-semibold text-slate-900">{editingDetail?.current_promoter_name ?? "—"}</span>
              </p>
              <form onSubmit={handleReassign} className="space-y-3">
                <select
                  required
                  value={reassignAgentId}
                  onChange={(e) => setReassignAgentId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-white focus:border-brand-500"
                >
                  <option value="">{t("adm.cust.selectPromoter")}</option>
                  {(agentsForReassign ?? [])
                    .filter((a) => a.id !== editingDetail?.current_promoter_agent_id)
                    .map((a) => (
                      <option key={a.id} value={a.id}>{a.display_name} ({a.promoter_code})</option>
                    ))}
                </select>
                <input
                  required
                  value={reassignReason}
                  onChange={(e) => setReassignReason(e.target.value)}
                  placeholder={t("adm.cust.reassignReason")}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500"
                />
                {reassignError && (
                  <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{reassignError}</div>
                )}
                {reassignSuccess && (
                  <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">{t("adm.cust.reassignDone")}</div>
                )}
                <button type="submit" disabled={reassignLoading}
                  className="w-full px-4 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 text-xs font-semibold text-slate-600 border border-slate-300 transition cursor-pointer disabled:opacity-50">
                  {reassignLoading ? t("adm.cust.reassigning") : t("adm.cust.reassign")}
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
