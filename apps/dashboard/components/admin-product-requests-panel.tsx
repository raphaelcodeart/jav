"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { PRODUCT_REQUEST_STATUS_LABELS, productRequestStatusColor } from "@/components/product-requests";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";
import type { ProductRequestDetailRead, ProductRequestRead } from "@/lib/types";

/** «Richieste prodotti»: il lato staff delle richieste fatte dallo Shop con
 *  «Non hai trovato ciò che cercavi?». Stessa meccanica dei Ticket di
 *  Supporto, coda separata (API /product-requests). Ogni risposta arriva al
 *  cliente come notifica e come email. */

const OPENER_LABELS: Record<string, string> = { CUSTOMER: "Cliente", PROMOTER: "Promoter", ADMIN: "Staff" };
const DELETABLE = new Set(["FOUND", "NOT_FOUND", "CLOSED"]);

// Per lo staff "Inviata" si legge meglio come "Nuova".
const STAFF_STATUS_LABELS: Record<string, string> = { ...PRODUCT_REQUEST_STATUS_LABELS, OPEN: "Nuova" };

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`/api/proxy${path}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

function TrashIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  );
}

export function AdminProductRequestsPanel() {
  const { t, fmt } = useI18n();
  const formatDateTime = (iso: string) =>
    new Date(iso).toLocaleString(fmt.tag, { dateStyle: "short", timeStyle: "short" });
  const statusLabel = (code: string) => t.dyn(`mkt.preq.status.${code}`, STAFF_STATUS_LABELS[code] ?? code);
  const openerLabel = (role: string) => t.dyn(`mkt.preq.opener.${role}`, OPENER_LABELS[role] ?? role);
  const queryClient = useQueryClient();
  const { data: requests, error: listError } = useQuery({
    queryKey: ["admin", "product-requests"],
    queryFn: () => getJson<ProductRequestRead[]>("/product-requests"),
  });
  const [statusFilter, setStatusFilter] = useState("ACTIVE");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: detail } = useQuery({
    queryKey: ["admin", "product-requests", "detail", selectedId],
    queryFn: () => getJson<ProductRequestDetailRead>(`/product-requests/${selectedId}`),
    enabled: !!selectedId,
  });

  const [reply, setReply] = useState("");
  const [replyLoading, setReplyLoading] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [deleting, setDeleting] = useState<ProductRequestRead | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const filtered = (requests ?? []).filter((r) => {
    const matchesStatus =
      statusFilter === "ALL" ||
      (statusFilter === "ACTIVE" ? r.status === "OPEN" || r.status === "IN_PROGRESS" : r.status === statusFilter);
    const q = searchQuery.trim().toLowerCase();
    const matchesSearch =
      q === "" || r.product_name.toLowerCase().includes(q) || (r.opened_by_name ?? "").toLowerCase().includes(q);
    return matchesStatus && matchesSearch;
  });
  const pagination = usePagination(filtered);
  const waiting = (requests ?? []).filter(
    (r) => r.status !== "CLOSED" && r.last_author_role !== "ADMIN",
  ).length;

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["admin", "product-requests"] });
  }

  async function handleReply(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedId) return;
    setReplyLoading(true);
    setReplyError(null);
    try {
      const res = await fetch(`/api/proxy/product-requests/${selectedId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: reply }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setReply("");
      await refresh();
    } catch (err: unknown) {
      setReplyError((err as Error).message || t("mkt.preq.replyFailed"));
    } finally {
      setReplyLoading(false);
    }
  }

  async function handleStatusChange(newStatus: string) {
    if (!selectedId) return;
    setStatusLoading(true);
    setReplyError(null);
    try {
      const res = await fetch(`/api/proxy/product-requests/${selectedId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await refresh();
    } catch (err: unknown) {
      setReplyError((err as Error).message || t("mkt.preq.statusFailed"));
    } finally {
      setStatusLoading(false);
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/proxy/product-requests/${deleting.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res, t("mkt.preq.deleteFailed")));
      if (selectedId === deleting.id) setSelectedId(null);
      setDeleting(null);
      await refresh();
    } catch (err: unknown) {
      setDeleteError((err as Error).message || t("mkt.preq.deleteFailed"));
    } finally {
      setDeleteLoading(false);
    }
  }

  const deleteModal = deleting && (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md glass-card rounded-2xl p-6 border-slate-300 bg-white animate-scale-up">
        <h3 className="text-lg font-bold text-slate-900 mb-2">{t("mkt.preq.delete")}</h3>
        <p className="text-xs text-slate-500 mb-4">
          {t("mkt.preq.deleteConfirmBefore")}{" "}
          <span className="font-semibold text-slate-700">«{deleting.product_name}»</span>{" "}
          {t("mkt.preq.deleteConfirmAfter")}
        </p>
        {deleteError && <p className="text-xs text-rose-400 mb-3">{deleteError}</p>}
        <div className="flex justify-end gap-3">
          <button
            onClick={() => { setDeleting(null); setDeleteError(null); }}
            className="px-4 py-2 rounded-xl bg-slate-900/5 hover:bg-slate-100 text-xs font-semibold text-slate-600 border border-slate-200 transition cursor-pointer"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={handleDelete}
            disabled={deleteLoading}
            className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
          >
            {deleteLoading ? t("mkt.preq.deleting") : t("mkt.preq.deleteForever")}
          </button>
        </div>
      </div>
    </div>
  );

  if (selectedId && detail) {
    const canDelete = DELETABLE.has(detail.status);
    return (
      <div className="space-y-4">
        <button
          onClick={() => setSelectedId(null)}
          className="text-xs text-slate-400 hover:text-slate-900 transition cursor-pointer flex items-center gap-1"
        >
          ← {t("mkt.preq.back")}
        </button>

        <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-4">
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-wider text-brand-600">{t("mkt.preq.productSought")}</p>
              <h3 className="text-lg font-semibold text-slate-900 break-words">{detail.product_name}</h3>
              <p className="text-xs text-slate-500 mt-1">
                {openerLabel(detail.opened_by_role)} · {detail.opened_by_name ?? "—"} ·{" "}
                {t("mkt.preq.openedOn", { date: formatDateTime(detail.created_at) })}
              </p>
              {detail.reference_url && (
                <a
                  href={detail.reference_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-brand-600 hover:text-brand-600 break-all"
                >
                  {detail.reference_url}
                </a>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <select
                value={detail.status}
                onChange={(e) => handleStatusChange(e.target.value)}
                disabled={statusLoading}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold border bg-white cursor-pointer ${productRequestStatusColor(detail.status)}`}
              >
                {Object.keys(STAFF_STATUS_LABELS).map((code) => (
                  <option key={code} value={code}>{statusLabel(code)}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => { if (canDelete) setDeleting(detail); }}
                disabled={!canDelete}
                title={canDelete ? t("mkt.preq.delete") : t("mkt.preq.deleteOnlyDoneLong")}
                className="p-2 rounded-xl border border-slate-300 text-slate-400 hover:text-rose-400 hover:border-rose-500/30 hover:bg-rose-500/10 transition cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:text-slate-400 disabled:hover:border-slate-300 disabled:hover:bg-transparent"
              >
                <TrashIcon className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="space-y-3 mb-6">
            {detail.messages.map((m) => {
              const isStaff = m.author_role === "ADMIN";
              return (
                <div key={m.id} className={`flex ${isStaff ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                      isStaff
                        ? "bg-brand-600/10 border border-brand-500/20 text-slate-700"
                        : " bg-slate-900/5 border border-slate-200 text-slate-700"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        {isStaff ? `${openerLabel("ADMIN")}${m.author_name ? ` · ${m.author_name}` : ""}` : m.author_name ?? openerLabel(m.author_role)}
                      </span>
                      <span className="text-[10px] text-slate-500">{formatDateTime(m.created_at)}</span>
                    </div>
                    <p className="whitespace-pre-wrap break-words">{m.body}</p>
                  </div>
                </div>
              );
            })}
          </div>

          {detail.status !== "CLOSED" ? (
            <form onSubmit={handleReply} className="flex gap-2">
              <input
                required
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                placeholder={t("mkt.preq.replyPlaceholder")}
                className="flex-1 min-w-0 rounded-xl glass-input px-3 py-2.5 text-sm focus:border-brand-500"
              />
              <button
                type="submit"
                disabled={replyLoading}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white transition cursor-pointer disabled:opacity-50"
              >
                {replyLoading ? t("mkt.preq.sending") : t("mkt.preq.reply")}
              </button>
            </form>
          ) : (
            <p className="text-xs text-slate-500">{t("mkt.preq.closedHint")}</p>
          )}
          {replyError && <p className="text-xs text-rose-400 mt-2">{replyError}</p>}
        </div>
        {deleteModal}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <p className="text-sm text-slate-500 flex-1">
            {t("mkt.preq.intro")}{" "}
            <strong className=" text-slate-900">{waiting}</strong> {t("mkt.preq.waiting")}
          </p>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("mkt.preq.search")}
            className="rounded-xl glass-input px-3 py-2 text-xs bg-white focus:border-brand-500 w-full sm:w-64"
          />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-xl glass-input px-3 py-2 text-xs bg-white focus:border-brand-500"
          >
            <option value="ACTIVE">{t("mkt.preq.filterActive")}</option>
            <option value="ALL">{t("mkt.preq.filterAll")}</option>
            {Object.keys(STAFF_STATUS_LABELS).map((code) => (
              <option key={code} value={code}>{statusLabel(code)}</option>
            ))}
          </select>
        </div>
      </div>

      {listError && <p className="text-sm text-rose-400">{t("mkt.preq.loadFailed")}</p>}

      <div className="space-y-3">
        {requests === undefined ? (
          <p className="text-sm text-slate-500 text-center py-8">{t("mkt.preq.loading")}</p>
        ) : filtered.length === 0 ? (
          <div className="glass-card rounded-2xl p-12 text-center border-slate-200">
            <p className="text-sm text-slate-500">
              {(requests ?? []).length === 0 ? t("mkt.preq.empty") : t("mkt.preq.noMatch")}
            </p>
          </div>
        ) : (
          pagination.pageItems.map((r) => {
            const needsReply = r.status !== "CLOSED" && r.last_author_role !== "ADMIN";
            const canDelete = DELETABLE.has(r.status);
            return (
              <div
                key={r.id}
                className="glass-card rounded-2xl p-4 border-slate-200 bg-white/70 hover:bg-slate-100 transition flex items-center justify-between gap-4"
              >
                <button onClick={() => setSelectedId(r.id)} className="min-w-0 flex-1 text-left cursor-pointer">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-slate-900 truncate">{r.product_name}</p>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border shrink-0 ${productRequestStatusColor(r.status)}`}>
                      {statusLabel(r.status)}
                    </span>
                    {needsReply && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-brand-600 text-white shrink-0">
                        {t("mkt.preq.toAnswer")}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1">
                    {r.opened_by_name ?? "—"} · {t("mkt.preq.messages", { n: r.message_count })}
                    {r.last_message_at ? ` · ${t("mkt.preq.lastUpdate", { date: formatDateTime(r.last_message_at) })}` : ""}
                  </p>
                </button>
                <button
                  type="button"
                  onClick={() => { if (canDelete) setDeleting(r); }}
                  disabled={!canDelete}
                  title={canDelete ? t("mkt.preq.delete") : t("mkt.preq.deleteOnlyDone")}
                  className="shrink-0 p-2 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:text-slate-500 disabled:hover:bg-transparent"
                >
                  <TrashIcon className="w-4 h-4" />
                </button>
              </div>
            );
          })
        )}
      </div>
      <Pagination {...pagination} label={t("mkt.preq.paginationLabel")} />
      {deleteModal}
    </div>
  );
}
