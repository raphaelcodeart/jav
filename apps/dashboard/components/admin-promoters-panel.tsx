"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { ShareButtons } from "@/components/share-buttons";
import { PhotoUpload } from "@/components/photo-upload";
import { AdminPromoterNetworkModal } from "@/components/admin-promoter-network-modal";
import { friendlyApiError } from "@/lib/api-error";
import { downloadCsv } from "@/lib/csv-export";
import { useI18n } from "@/lib/i18n/provider";
import type { AgentListItemRead, PromoterCodeRead, RankEvaluationChangeRead, RankRead, RootPromoterCreateResponse, WalletAdminListItemRead } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  SUSPENDED: "bg-amber-500/10 text-amber-700 border-amber-500/20",
  TERMINATED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
  PENDING_APPROVAL: "bg-sky-500/10 text-sky-400 border-sky-500/20",
};

async function fetchAgents(): Promise<AgentListItemRead[]> {
  const res = await fetch("/api/proxy/network/agents");
  if (!res.ok) throw new Error("Impossibile caricare la rete commerciale.");
  return res.json();
}

async function fetchWallets(): Promise<WalletAdminListItemRead[]> {
  const res = await fetch("/api/proxy/wallets/admin");
  if (!res.ok) throw new Error("Impossibile caricare i wallet.");
  return res.json();
}

async function fetchRanks(): Promise<RankRead[]> {
  const res = await fetch("/api/proxy/commissions/ranks");
  if (!res.ok) throw new Error("Impossibile caricare le qualifiche.");
  return res.json();
}

function AgentAvatar({ url, size = 36 }: { url: string | null; size?: number }) {
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
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
        </svg>
      )}
    </div>
  );
}

export function AdminPromotersPanel({
  initialStatusFilter,
  isSuperAdmin = false,
}: { initialStatusFilter?: string; isSuperAdmin?: boolean } = {}) {
  const { t, fmt } = useI18n();
  const statusLabel = (code: string) => t.dyn(`adm.prom.status.${code}`, code);
  const queryClient = useQueryClient();
  const { data: agents, error: loadError } = useQuery({
    queryKey: ["admin", "agents"],
    queryFn: fetchAgents,
  });
  const { data: ranks = [] } = useQuery({
    queryKey: ["admin", "ranks"],
    queryFn: fetchRanks,
  });
  const { data: wallets } = useQuery({
    queryKey: ["admin", "wallets", "all"],
    queryFn: fetchWallets,
  });
  const canTransferByUserId = new Map((wallets ?? []).map((w) => [w.user_id, w.can_transfer]));
  const [transferToggleId, setTransferToggleId] = useState<string | null>(null);

  // Freeze/unfreeze login (SUPER_ADMIN only, see users/router.py)
  const [freezeLoadingId, setFreezeLoadingId] = useState<string | null>(null);
  const [freezeError, setFreezeError] = useState<string | null>(null);

  async function handleToggleFreeze(userId: string, currentlyFrozen: boolean) {
    setFreezeLoadingId(userId);
    setFreezeError(null);
    try {
      const res = await fetch(`/api/proxy/users/${userId}/${currentlyFrozen ? "unfreeze" : "freeze"}`, { method: "PATCH" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setFreezeError(err.message || t("adm.cust.freezeFailed"));
    } finally {
      setFreezeLoadingId(null);
    }
  }

  async function handleToggleTransfer(userId: string, next: boolean) {
    setTransferToggleId(userId);
    try {
      const res = await fetch(`/api/proxy/wallets/admin/${userId}/transfer-permission`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ can_transfer: next }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
    } finally {
      setTransferToggleId(null);
    }
  }

  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState(initialStatusFilter ?? "ALL");

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [promoterCode, setPromoterCode] = useState("");
  const [parentAgentId, setParentAgentId] = useState("");
  const [rankId, setRankId] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const nameById = new Map((agents ?? []).map((a) => [a.id, a.display_name]));

  // Approval workflow -- only network.approve holders (SUPER_ADMIN/
  // ORGANIZATION_ADMIN, the "amministratore principale") can actually
  // succeed here; a plain ADMIN sees the buttons too but the backend 403s,
  // surfaced as approvalError below. Not worth plumbing role info through
  // the session just to hide two buttons the server already guards.
  const [approvalActionId, setApprovalActionId] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [rejectingAgent, setRejectingAgent] = useState<AgentListItemRead | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  // Deactivate/blacklist/reactivate -- "Lavora con noi" auto-activates a
  // promoter immediately (see network/service.py apply_as_promoter), so this
  // is the only way an admin takes that capability back. Blacklist is a
  // stricter deactivation: a blacklisted agent who re-applies goes through
  // the old manual PENDING_APPROVAL/approve flow instead of auto-activating.
  const [agentActionId, setAgentActionId] = useState<string | null>(null);
  const [agentActionError, setAgentActionError] = useState<string | null>(null);

  async function handleSetAgentStatus(agentId: string, patch: { status?: string; is_blacklisted?: boolean }) {
    setAgentActionId(agentId);
    setAgentActionError(null);
    try {
      const res = await fetch(`/api/proxy/network/agents/${agentId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setAgentActionError(err.message || t("common.failed"));
    } finally {
      setAgentActionId(null);
    }
  }

  // Opens an agent's personal referral link in a new tab -- lazily
  // get-or-created server-side (an agent may never have visited their own
  // dashboard yet, e.g. right after admin approval). The tab is opened
  // BEFORE the fetch resolves so it stays a direct result of the click
  // (popup blockers kill a window.open() that happens after an await).
  const [referralLinkLoadingId, setReferralLinkLoadingId] = useState<string | null>(null);

  async function handleOpenReferralLink(agentId: string) {
    setReferralLinkLoadingId(agentId);
    setAgentActionError(null);
    const newTab = window.open("", "_blank");
    try {
      const res = await fetch(`/api/proxy/network/agents/${agentId}/referral-link`);
      if (!res.ok) throw new Error(await friendlyApiError(res, t("adm.prom.linkFailed")));
      const data: PromoterCodeRead = await res.json();
      const url = new URL(`/r/${data.code}`, window.location.origin);
      if (newTab) newTab.location.href = url.toString();
    } catch (err: any) {
      newTab?.close();
      setAgentActionError(err.message || t("adm.prom.linkFailed"));
    } finally {
      setReferralLinkLoadingId(null);
    }
  }

  // Monthly rank evaluation -- same job Celery Beat runs automatically at
  // month-end (see celery_app.py::run_monthly_rank_evaluation_task), triggered
  // here on demand. commissions.evaluate_ranks-gated on the backend (SUPER_ADMIN/
  // ORGANIZATION_ADMIN only); a plain ADMIN sees the button but the backend 403s.
  const [evaluatingRanks, setEvaluatingRanks] = useState(false);
  const [evaluationError, setEvaluationError] = useState<string | null>(null);
  const [evaluationResult, setEvaluationResult] = useState<RankEvaluationChangeRead[] | null>(null);

  async function handleEvaluateRanks() {
    setEvaluatingRanks(true);
    setEvaluationError(null);
    try {
      const res = await fetch("/api/proxy/commissions/rank-evaluation/run", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const changes: RankEvaluationChangeRead[] = await res.json();
      setEvaluationResult(changes);
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setEvaluationError(err.message || t("adm.prom.evaluateFailed"));
    } finally {
      setEvaluatingRanks(false);
    }
  }

  async function handleApprove(agentId: string) {
    setApprovalActionId(agentId);
    setApprovalError(null);
    try {
      const res = await fetch(`/api/proxy/network/agents/${agentId}/approve`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: "{}" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setApprovalError(err.message || t("adm.prom.approveFailed"));
    } finally {
      setApprovalActionId(null);
    }
  }

  async function handleReject() {
    if (!rejectingAgent) return;
    setApprovalActionId(rejectingAgent.id);
    setApprovalError(null);
    try {
      const res = await fetch(`/api/proxy/network/agents/${rejectingAgent.id}/reject`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: rejectReason || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
      setRejectingAgent(null);
      setRejectReason("");
    } catch (err: any) {
      setApprovalError(err.message || t("adm.prom.rejectFailed"));
    } finally {
      setApprovalActionId(null);
    }
  }

  // Edit
  const [editingAgent, setEditingAgent] = useState<AgentListItemRead | null>(null);
  const [networkAgent, setNetworkAgent] = useState<AgentListItemRead | null>(null);
  const [editFirstName, setEditFirstName] = useState("");
  const [editLastName, setEditLastName] = useState("");
  const [editStatus, setEditStatus] = useState("ACTIVE");
  const [editRankId, setEditRankId] = useState("");
  const [editPhotoUrl, setEditPhotoUrl] = useState<string | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  function openEdit(a: AgentListItemRead) {
    setEditFirstName(a.first_name ?? "");
    setEditLastName(a.last_name ?? "");
    setEditStatus(a.status);
    setEditRankId(a.current_rank_id ?? "");
    setEditPhotoUrl(a.photo_url);
    setEditError(null);
    setEditingAgent(a);
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editingAgent) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const res = await fetch(`/api/proxy/network/agents/${editingAgent.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: editFirstName,
          last_name: editLastName,
          status: editStatus,
          current_rank_id: editRankId || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setEditingAgent(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setEditError(err.message || t("adm.cust.editFailed"));
    } finally {
      setEditLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/network/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
          promoter_code: promoterCode,
          parent_agent_id: parentAgentId || null,
          current_rank_id: rankId || null,
          customer_email: customerEmail || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setShowCreate(false);
      setFirstName("");
      setLastName("");
      setPromoterCode("");
      setParentAgentId("");
      setRankId("");
      setCustomerEmail("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setCreateError(err.message || t("adm.prom.createFailed"));
    } finally {
      setCreateLoading(false);
    }
  }

  // Root promoter bootstrap -- gated on network.approve (SUPER_ADMIN/
  // ORGANIZATION_ADMIN) on the backend, same "not worth hiding it" convention
  // as the approve/reject/evaluate-ranks buttons above. Unlike "+ Nuovo
  // Promoter" (which only ever suggests, PENDING_APPROVAL, no login), this
  // creates a ready-to-use login + ACTIVE parentless agent in one step --
  // the only way to start a brand-new independent branch, since every other
  // signup path requires an existing promoter's referral code.
  const [showCreateRoot, setShowCreateRoot] = useState(false);
  const [rootFirstName, setRootFirstName] = useState("");
  const [rootLastName, setRootLastName] = useState("");
  const [rootEmail, setRootEmail] = useState("");
  const [rootPromoterCode, setRootPromoterCode] = useState("");
  const [rootCreateLoading, setRootCreateLoading] = useState(false);
  const [rootCreateError, setRootCreateError] = useState<string | null>(null);
  const [rootCreateResult, setRootCreateResult] = useState<RootPromoterCreateResponse | null>(null);
  const [rootLinkCopied, setRootLinkCopied] = useState(false);
  const [rootPasswordCopied, setRootPasswordCopied] = useState(false);

  async function handleCreateRoot(e: React.FormEvent) {
    e.preventDefault();
    setRootCreateLoading(true);
    setRootCreateError(null);
    try {
      const res = await fetch("/api/proxy/network/agents/root", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: rootFirstName,
          last_name: rootLastName,
          email: rootEmail,
          promoter_code: rootPromoterCode || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const result: RootPromoterCreateResponse = await res.json();
      setShowCreateRoot(false);
      setRootFirstName("");
      setRootLastName("");
      setRootEmail("");
      setRootPromoterCode("");
      setRootCreateResult(result);
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setRootCreateError(err.message || t("adm.prom.createRootFailed"));
    } finally {
      setRootCreateLoading(false);
    }
  }

  const filtered = (agents ?? []).filter(
    (a) =>
      (statusFilter === "ALL" || a.status === statusFilter) &&
      (a.display_name.toLowerCase().includes(search.toLowerCase()) ||
        a.promoter_code.toLowerCase().includes(search.toLowerCase()))
  );

  // Paginates the FILTERED list. CSV export below keeps using `filtered`,
  // not the current page -- exporting only the visible rows would be a trap.
  const pagination = usePagination(filtered);

  const handleExportCsv = () => {
    downloadCsv(
      `promoter_${new Date().toISOString().slice(0, 10)}`,
      ["ID", t("adm.cust.name"), t("adm.prom.promoterCode"), t("adm.prom.rank"), "Sponsor", t("adm.client.status"), t("adm.prom.joinedOn")],
      filtered.map((a) => [
        a.id, a.display_name, a.promoter_code, a.rank_code ?? "",
        a.direct_parent_agent_id ? nameById.get(a.direct_parent_agent_id) ?? a.direct_parent_agent_id : t("adm.prom.root"),
        a.status, a.joined_at,
      ])
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
        <div className="w-full sm:max-w-xs relative">
          <input
            type="text"
            placeholder={t("adm.prom.search")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl glass-input pl-10 pr-4 py-2 text-xs focus:border-brand-500"
          />
          <svg className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-xl glass-input px-3 py-2 text-xs bg-white focus:border-brand-500"
          >
            <option value="ALL">{t("adm.prom.filter.all")}</option>
            <option value="ACTIVE">{t("adm.prom.filter.active")}</option>
            <option value="SUSPENDED">{t("adm.prom.filter.suspended")}</option>
            <option value="TERMINATED">{t("adm.prom.filter.terminated")}</option>
          </select>
          <button
            onClick={handleEvaluateRanks}
            disabled={evaluatingRanks}
            title={t("adm.prom.evaluateTitle")}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
            {evaluatingRanks ? t("adm.prom.evaluating") : t("adm.prom.evaluate")}
          </button>
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
            onClick={() => setShowCreateRoot(true)}
            title={t("adm.prom.createRootTitle")}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0H5a2 2 0 01-2-2v-4m6 6h10a2 2 0 002-2v-4" />
            </svg>
            + {t("adm.prom.rootPromoter")}
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-500/20 transition cursor-pointer"
          >
            + {t("adm.prom.newPromoter")}
          </button>
        </div>
      </div>

      {loadError && <p className="text-sm text-rose-400">{t("adm.prom.loadFailed")}</p>}
      {freezeError && <p className="text-sm text-rose-400">{freezeError}</p>}
      {approvalError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{approvalError}</div>
      )}
      {agentActionError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{agentActionError}</div>
      )}
      {evaluationError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{evaluationError}</div>
      )}
      {evaluationResult && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs">
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold text-emerald-400">
              {evaluationResult.length === 0
                ? t("adm.prom.evaluationNone")
                : evaluationResult.length === 1
                  ? t("adm.prom.evaluationOne")
                  : t("adm.prom.evaluationMany", { n: evaluationResult.length })}
            </span>
            <button
              onClick={() => setEvaluationResult(null)}
              className="text-slate-400 hover:text-slate-900 cursor-pointer"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {evaluationResult.length > 0 && (
            <ul className="space-y-1 text-slate-600">
              {evaluationResult.map((c) => (
                <li key={c.agent_id}>
                  <span className={c.direction === "PROMOTED" ? "text-emerald-400" : "text-amber-700"}>
                    {c.direction === "PROMOTED" ? "▲" : "▼"}
                  </span>{" "}
                  {c.display_name}: {c.previous_rank_code ?? "—"} → {c.new_rank_code}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="glass-card rounded-2xl border-slate-200 bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                <th className="py-3 px-6"></th>
                <th className="py-3 px-6">{t("adm.cust.name")}</th>
                <th className="py-3 px-6">{t("adm.prom.code")}</th>
                <th className="py-3 px-6">{t("adm.prom.rank")}</th>
                <th className="py-3 px-6">Sponsor</th>
                <th className="py-3 px-6">{t("adm.client.status")}</th>
                <th className="py-3 px-6 text-right">{t("adm.client.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {agents === undefined ? (
                <tr><td colSpan={7} className="text-center py-8 text-slate-500">{t("adm.overview.loading")}</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={7} className="text-center py-8 text-slate-500">{t("adm.prom.noneFound")}</td></tr>
              ) : (
                pagination.pageItems.map((a) => (
                  <tr key={a.id} className=" text-slate-600 hover:bg-slate-100 transition-colors">
                    <td className="py-4 px-6"><AgentAvatar url={a.photo_url} /></td>
                    <td className="py-4 px-6">
                      <div className="flex items-center gap-1.5">
                        <p className="font-medium text-slate-900">{a.display_name}</p>
                        <button
                          onClick={() => handleOpenReferralLink(a.id)}
                          disabled={referralLinkLoadingId === a.id}
                          title={t("adm.prom.openLinkTitle")}
                          className="p-1 rounded-md hover:bg-slate-900/10 text-slate-400 hover:text-brand-600 transition cursor-pointer disabled:opacity-40"
                        >
                          {referralLinkLoadingId === a.id ? (
                            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                          ) : (
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                            </svg>
                          )}
                        </button>
                      </div>
                      <p className="text-[10px] text-slate-500">{a.email ?? t("adm.prom.noAccount")}</p>
                      <p className="text-[10px] text-slate-500">{t("adm.cust.joined", { date: fmt.shortDate(a.joined_at) })}</p>
                      {a.user_id && (
                        <div className="flex items-center gap-1 mt-1.5 flex-wrap">
                          <span
                            title={a.email_verified ? t("adm.cust.emailVerified") : t("adm.cust.emailNotVerified")}
                            className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${
                              a.email_verified
                                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                            }`}
                          >
                            Email {a.email_verified ? "✓" : "✗"}
                          </span>
                          <span
                            title={a.privacy_accepted ? t("adm.unlock.privacyAccepted") : t("adm.cust.privacyNotAccepted")}
                            className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${
                              a.privacy_accepted
                                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                            }`}
                          >
                            {t("adm.cust.privacyBadge")} {a.privacy_accepted ? "✓" : "✗"}
                          </span>
                          <span
                            title={
                              a.collaboration_accepted_at
                                ? [
                                    t("adm.prom.acceptedOn", { date: new Date(a.collaboration_accepted_at).toLocaleString(fmt.tag) }),
                                    // Which documents, and at which wording -- an
                                    // acceptance is only meaningful with its version.
                                    ...Object.entries(a.collaboration_accepted_documents ?? {}).map(
                                      ([key, v]) => `${key} v${v.version}`
                                    ),
                                  ].join(" · ")
                                : t("adm.prom.collabNotAccepted")
                            }
                            className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${
                              a.collaboration_accepted_at
                                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                            }`}
                          >
                            {t("adm.prom.contractBadge")} {a.collaboration_accepted_at ? "✓" : "✗"}
                            {Object.keys(a.collaboration_accepted_documents ?? {}).length > 1 && (
                              <span className="ml-1 opacity-75">
                                {t("adm.prom.docsCount", { n: Object.keys(a.collaboration_accepted_documents ?? {}).length })}
                              </span>
                            )}
                          </span>
                          {a.user_status === "FROZEN" && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold border bg-sky-500/10 text-sky-400 border-sky-500/20">
                              {t("adm.cust.frozen")}
                            </span>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="py-4 px-6 font-mono text-xs">{a.promoter_code}</td>
                    <td className="py-4 px-6">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-brand-500/10 text-brand-600 border-brand-500/20">
                        {a.rank_code ?? "—"}
                      </span>
                    </td>
                    <td className="py-4 px-6 text-xs">
                      {a.direct_parent_agent_id ? nameById.get(a.direct_parent_agent_id) ?? "—" : t("adm.prom.root")}
                    </td>
                    <td className="py-4 px-6">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_COLORS[a.status] ?? STATUS_COLORS.ACTIVE}`}>
                        {statusLabel(a.status)}
                      </span>
                      {a.is_blacklisted && (
                        <span className="ml-1 px-2 py-0.5 rounded-full text-[10px] font-bold border bg-rose-500/10 text-rose-400 border-rose-500/20">
                          {t("adm.prom.inBlacklist")}
                        </span>
                      )}
                      {a.status === "TERMINATED" && a.rejection_reason && (
                        <p className="text-[10px] text-rose-400 mt-1 max-w-[160px]">{a.rejection_reason}</p>
                      )}
                    </td>
                    <td className="py-4 px-6 text-right">
                      {a.status === "PENDING_APPROVAL" ? (
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleApprove(a.id)}
                            disabled={approvalActionId === a.id}
                            className="px-2.5 py-1.5 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                          >
                            {t("adm.prom.approve")}
                          </button>
                          <button
                            onClick={() => setRejectingAgent(a)}
                            disabled={approvalActionId === a.id}
                            className="px-2.5 py-1.5 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                          >
                            {t("adm.prom.reject")}
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-2 flex-wrap">
                          <button
                            onClick={() => setNetworkAgent(a)}
                            title={t("adm.prom.openNetworkTitle")}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0H5a2 2 0 01-2-2v-4m6 6h10a2 2 0 002-2v-4m0-6h-6m6 0v6m0-6l-8 8" />
                            </svg>
                            {t("adm.prom.openNetwork")}
                          </button>
                          <button
                            onClick={() => openEdit(a)}
                            title={t("adm.prom.editPromoter")}
                            className="p-1.5 rounded-lg bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-600 transition cursor-pointer"
                          >
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                            </svg>
                          </button>
                          {isSuperAdmin && a.user_id && (
                            <button
                              onClick={() => handleToggleFreeze(a.user_id!, a.user_status === "FROZEN")}
                              disabled={freezeLoadingId === a.user_id}
                              title={a.user_status === "FROZEN" ? t("adm.cust.reactivate") : t("adm.cust.freeze")}
                              className={`p-1.5 rounded-lg border transition cursor-pointer disabled:opacity-50 ${
                                a.user_status === "FROZEN"
                                  ? "bg-emerald-600/10 hover:bg-emerald-600/20 border-emerald-500/20 text-emerald-400"
                                  : "bg-sky-600/10 hover:bg-sky-600/20 border-sky-500/20 text-sky-400"
                              }`}
                            >
                              {a.user_status === "FROZEN" ? (
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
                          {a.user_id && (() => {
                            const enabled = canTransferByUserId.get(a.user_id) ?? false;
                            return (
                              <button
                                onClick={() => handleToggleTransfer(a.user_id!, !enabled)}
                                disabled={transferToggleId === a.user_id}
                                title={enabled ? t("adm.prom.transferDisableTitle") : t("adm.prom.transferEnableTitle")}
                                className={`px-2.5 py-1.5 rounded-lg border text-xs font-semibold transition cursor-pointer disabled:opacity-50 ${
                                  enabled
                                    ? "bg-emerald-600/10 hover:bg-emerald-600/20 border-emerald-500/20 text-emerald-400"
                                    : " bg-slate-900/5 hover:bg-slate-100 border-slate-300 text-slate-600"
                                }`}
                              >
                                {transferToggleId === a.user_id ? "..." : enabled ? t("adm.prom.transferOn") : t("adm.prom.transferOff")}
                              </button>
                            );
                          })()}
                          {a.status === "ACTIVE" && (
                            <>
                              <button
                                onClick={() => handleSetAgentStatus(a.id, { status: "TERMINATED" })}
                                disabled={agentActionId === a.id}
                                title={t("adm.prom.deactivateTitle")}
                                className="px-2.5 py-1.5 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                              >
                                {t("adm.prom.deactivate")}
                              </button>
                              <button
                                onClick={() => handleSetAgentStatus(a.id, { status: "TERMINATED", is_blacklisted: true })}
                                disabled={agentActionId === a.id}
                                title={t("adm.prom.blacklistTitle")}
                                className="px-2.5 py-1.5 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                              >
                                Blacklist
                              </button>
                            </>
                          )}
                          {(a.status === "TERMINATED" || a.status === "SUSPENDED") && (
                            <>
                              <button
                                onClick={() => handleSetAgentStatus(a.id, { status: "ACTIVE" })}
                                disabled={agentActionId === a.id}
                                className="px-2.5 py-1.5 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                              >
                                {t("adm.prom.reactivate")}
                              </button>
                              {a.is_blacklisted && (
                                <button
                                  onClick={() => handleSetAgentStatus(a.id, { is_blacklisted: false })}
                                  disabled={agentActionId === a.id}
                                  title={t("adm.prom.unblacklistTitle")}
                                  className="px-2.5 py-1.5 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                                >
                                  {t("adm.prom.unblacklist")}
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="px-6 pb-5">
          <Pagination {...pagination} label={t("adm.prom.promotersLower")} />
        </div>
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-slate-900">{t("adm.prom.newPromoter")}</h3>
              <button onClick={() => setShowCreate(false)}
                className="p-1 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-900 transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.cust.firstName")}</label>
                  <input required value={firstName} onChange={(e) => setFirstName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.cust.lastName")}</label>
                  <input required value={lastName} onChange={(e) => setLastName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.prom.promoterCode")}</label>
                <input required value={promoterCode} onChange={(e) => setPromoterCode(e.target.value)}
                  placeholder={t("adm.prom.codePlaceholder")}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-brand-500" />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.prom.sponsorLabel")}</label>
                <select
                  value={parentAgentId}
                  onChange={(e) => setParentAgentId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-white focus:border-brand-500"
                >
                  <option value="">{t("adm.prom.noSponsor")}</option>
                  {(agents ?? []).map((a) => (
                    <option key={a.id} value={a.id}>{a.display_name} ({a.promoter_code})</option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.prom.existingCustomer")}</label>
                <input type="email" value={customerEmail} onChange={(e) => setCustomerEmail(e.target.value)}
                  placeholder={t("adm.prom.existingCustomerPlaceholder")}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                <p className="text-[11px] text-slate-500">{t("adm.prom.existingCustomerHint")}</p>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.prom.initialRank")}</label>
                <select
                  value={rankId}
                  onChange={(e) => setRankId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-white focus:border-brand-500"
                >
                  <option value="">{t("adm.prom.noneRank")}</option>
                  {ranks.map((r) => (
                    <option key={r.id} value={r.id}>{r.code} — {r.name}</option>
                  ))}
                </select>
              </div>

              {createError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{createError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setShowCreate(false)}
                  className="px-4 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 text-xs font-semibold text-slate-600 border border-slate-200 transition cursor-pointer">
                  {t("common.cancel")}
                </button>
                <button type="submit" disabled={createLoading}
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {createLoading ? t("adm.cust.creating") : t("adm.prom.create")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showCreateRoot && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-slate-900">{t("adm.prom.newRootPromoter")}</h3>
              <button onClick={() => setShowCreateRoot(false)}
                className="p-1 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-900 transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p className="text-xs text-slate-500 mb-4">
              {t("adm.prom.rootHint")}
            </p>

            <form onSubmit={handleCreateRoot} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.cust.firstName")}</label>
                  <input required value={rootFirstName} onChange={(e) => setRootFirstName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.cust.lastName")}</label>
                  <input required value={rootLastName} onChange={(e) => setRootLastName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">Email</label>
                <input required type="email" value={rootEmail} onChange={(e) => setRootEmail(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.prom.promoterCodeOptional")}</label>
                <input value={rootPromoterCode} onChange={(e) => setRootPromoterCode(e.target.value)}
                  placeholder={t("adm.prom.autoGenerated")}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-brand-500" />
              </div>

              {rootCreateError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{rootCreateError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setShowCreateRoot(false)}
                  className="px-4 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 text-xs font-semibold text-slate-600 border border-slate-200 transition cursor-pointer">
                  {t("common.cancel")}
                </button>
                <button type="submit" disabled={rootCreateLoading}
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {rootCreateLoading ? t("adm.cust.creating") : t("adm.prom.createRoot")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {rootCreateResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up">
            <h3 className="text-lg font-bold text-slate-900 mb-1">
              {t("adm.prom.isActive", { name: rootCreateResult.display_name })}
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              {t("adm.prom.credentialsHint")}
            </p>

            <div className="space-y-3 mb-4">
              <div>
                <label className="text-xs font-semibold text-slate-600 uppercase block mb-1">Email</label>
                <div className="rounded-xl glass-input px-3 py-2 text-sm font-mono">{rootCreateResult.email}</div>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600 uppercase block mb-1">{t("adm.prom.tempPassword")}</label>
                <div className="flex gap-2">
                  <div className="flex-1 rounded-xl glass-input px-3 py-2 text-sm font-mono">{rootCreateResult.temporary_password}</div>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(rootCreateResult.temporary_password);
                      setRootPasswordCopied(true);
                      setTimeout(() => setRootPasswordCopied(false), 2000);
                    }}
                    className="px-3 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-xs font-semibold text-slate-600 transition cursor-pointer"
                  >
                    {rootPasswordCopied ? t("adm.prom.copied") : t("adm.prom.copy")}
                  </button>
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600 uppercase block mb-1">{t("adm.prom.personalLink")}</label>
                <div className="flex gap-2">
                  <div className="flex-1 rounded-xl glass-input px-3 py-2 text-xs font-mono truncate">{rootCreateResult.personal_link}</div>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(rootCreateResult.personal_link);
                      setRootLinkCopied(true);
                      setTimeout(() => setRootLinkCopied(false), 2000);
                    }}
                    className="px-3 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-xs font-semibold text-slate-600 transition cursor-pointer"
                  >
                    {rootLinkCopied ? t("adm.prom.copied") : t("adm.prom.copy")}
                  </button>
                </div>
                {/* Same destinations as everywhere else: the admin creating a
                    root promoter usually has to get this link to them right
                    away, and retyping it into WhatsApp by hand is the step
                    that used to be missing. */}
                <ShareButtons
                  className="mt-2"
                  url={rootCreateResult.personal_link}
                  text={t("adm.prom.shareText")}
                />
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => setRootCreateResult(null)}
                className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer"
              >
                {t("adm.prom.done")}
              </button>
            </div>
          </div>
        </div>
      )}

      {editingAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-slate-900">{t("adm.prom.editPromoter")}</h3>
              <button onClick={() => setEditingAgent(null)}
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
                uploadPath={`network/agents/${editingAgent.id}/photo`}
                onUploaded={(url) => {
                  setEditPhotoUrl(url);
                  queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
                }}
                alt={editingAgent.display_name}
              />
            </div>

            <form onSubmit={handleEditSave} className="space-y-4">
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

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.prom.promoterCode")}</label>
                <input disabled value={editingAgent.promoter_code}
                  title={t("adm.prom.codeLockedTitle")}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono opacity-60 cursor-not-allowed" />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.prom.rank")}</label>
                <select
                  value={editRankId}
                  onChange={(e) => setEditRankId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-white focus:border-brand-500"
                >
                  <option value="">{t("adm.prom.noneRank")}</option>
                  {ranks.map((r) => (
                    <option key={r.id} value={r.id}>{r.code} — {r.name}</option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.client.status")}</label>
                <select
                  value={editStatus}
                  onChange={(e) => setEditStatus(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-white focus:border-brand-500"
                >
                  <option value="ACTIVE">{statusLabel("ACTIVE")}</option>
                  <option value="SUSPENDED">{statusLabel("SUSPENDED")}</option>
                  <option value="TERMINATED">{statusLabel("TERMINATED")}</option>
                </select>
              </div>

              {editError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{editError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setEditingAgent(null)}
                  className="px-4 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 text-xs font-semibold text-slate-600 border border-slate-200 transition cursor-pointer">
                  {t("common.cancel")}
                </button>
                <button type="submit" disabled={editLoading}
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {editLoading ? t("adm.client.saving") : t("adm.cust.saveChanges")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {networkAgent && (
        <AdminPromoterNetworkModal
          agentId={networkAgent.id}
          displayName={networkAgent.display_name}
          onClose={() => setNetworkAgent(null)}
        />
      )}

      {rejectingAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up">
            <h3 className="text-lg font-bold text-slate-900 mb-2">{t("adm.prom.rejectTitle", { name: rejectingAgent.display_name })}</h3>
            <p className="text-xs text-slate-500 mb-4">
              {t("adm.prom.rejectHint", { code: rejectingAgent.promoter_code })}
            </p>
            <label className="text-xs font-semibold text-slate-600 uppercase block mb-1">{t("adm.prom.reasonOptional")}</label>
            <textarea
              rows={3}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder={t("adm.prom.rejectPlaceholder")}
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500 resize-none mb-4"
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => { setRejectingAgent(null); setRejectReason(""); }}
                className="px-4 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 text-xs font-semibold text-slate-600 border border-slate-200 transition cursor-pointer"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={handleReject}
                disabled={approvalActionId === rejectingAgent.id}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
              >
                {approvalActionId === rejectingAgent.id ? t("adm.client.saving") : t("adm.prom.confirmReject")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
