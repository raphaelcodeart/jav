"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import type { TicketDetailRead, TicketRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

// Category codes the API accepts; labels come from i18n (acct.ticket.category.*).
const CATEGORY_CODES = ["ASSISTENZA_TECNICA", "FATTURAZIONE", "CONTRATTO", "COMMISSIONI", "ALTRO", "CHIUSURA_ACCOUNT"];

function statusColor(status: string): string {
  switch (status) {
    case "OPEN":
      return "bg-amber-500/10 text-amber-700 border-amber-500/20";
    case "IN_PROGRESS":
      return "bg-sky-500/10 text-sky-400 border-sky-500/20";
    case "RESOLVED":
      return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
    default:
      return "bg-slate-500/10 text-slate-400 border-slate-500/20";
  }
}

function formatDateTime(iso: string, tag: string): string {
  return new Date(iso).toLocaleString(tag, { dateStyle: "short", timeStyle: "short" });
}

async function fetchMyTickets(t: ReturnType<typeof useI18n>["t"]): Promise<TicketRead[]> {
  const res = await fetch("/api/proxy/support/tickets/mine");
  if (!res.ok) throw new Error(t("acct.tickets.loadError"));
  return res.json();
}

async function fetchTicketDetail(t: ReturnType<typeof useI18n>["t"], id: string): Promise<TicketDetailRead> {
  const res = await fetch(`/api/proxy/support/tickets/${id}`);
  if (!res.ok) throw new Error(t("acct.tickets.loadOneError"));
  return res.json();
}

export function SupportTicketsPanel({ title, subtitle }: { title: string; subtitle: string }) {
  const { t, fmt } = useI18n();
  const queryClient = useQueryClient();
  const { data: tickets, error: listError } = useQuery({ queryKey: ["support", "tickets", "mine"], queryFn: () => fetchMyTickets(t) });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: detail } = useQuery({
    queryKey: ["support", "tickets", "detail", selectedId],
    queryFn: () => fetchTicketDetail(t, selectedId as string),
    enabled: !!selectedId,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [subject, setSubject] = useState("");
  const [category, setCategory] = useState("ASSISTENZA_TECNICA");
  const [message, setMessage] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [reply, setReply] = useState("");
  const [replyLoading, setReplyLoading] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/support/tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject, category, message }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const newTicket = (await res.json()) as TicketRead;
      setSubject("");
      setMessage("");
      setShowCreate(false);
      await queryClient.invalidateQueries({ queryKey: ["support", "tickets", "mine"] });
      setSelectedId(newTicket.id);
    } catch (err: any) {
      setCreateError(err.message || t("acct.tickets.createError"));
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleReply(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedId) return;
    setReplyLoading(true);
    setReplyError(null);
    try {
      const res = await fetch(`/api/proxy/support/tickets/${selectedId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: reply }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setReply("");
      await queryClient.invalidateQueries({ queryKey: ["support", "tickets", "detail", selectedId] });
      await queryClient.invalidateQueries({ queryKey: ["support", "tickets", "mine"] });
    } catch (err: any) {
      setReplyError(err.message || t("acct.tickets.replyError"));
    } finally {
      setReplyLoading(false);
    }
  }

  // Declared before the detail-view early return below: a hook must run on
  // every render.
  const pagination = usePagination(tickets ?? []);

  if (selectedId && detail) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => setSelectedId(null)}
          className="text-xs text-slate-400 hover:text-slate-900 transition cursor-pointer flex items-center gap-1"
        >
          ← {t("acct.tickets.back")}
        </button>

        <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h3 className="text-lg font-semibold text-slate-900">{detail.subject}</h3>
              <p className="text-xs text-slate-500 mt-1">{t.dyn(`acct.ticket.category.${detail.category}`, detail.category)}</p>
            </div>
            <span className={`px-3 py-1 rounded-full text-xs font-bold border shrink-0 ${statusColor(detail.status)}`}>
              {t.dyn(`acct.ticket.status.${detail.status}`, detail.status)}
            </span>
          </div>

          <div className="space-y-3 mb-6">
            {detail.messages.map((m) => {
              const isStaff = m.author_role === "ADMIN";
              return (
                <div key={m.id} className={`flex ${isStaff ? "justify-start" : "justify-end"}`}>
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${
                      isStaff
                        ? "bg-brand-600/10 border border-brand-500/20 text-slate-700"
                        : " bg-slate-900/5 border border-slate-200 text-slate-700"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        {isStaff ? t("acct.tickets.support") : m.author_name ?? t("acct.tickets.you")}
                      </span>
                      <span className="text-[10px] text-slate-500">{formatDateTime(m.created_at, fmt.tag)}</span>
                    </div>
                    <p className="whitespace-pre-wrap">{m.body}</p>
                  </div>
                </div>
              );
            })}
          </div>

          {detail.status !== "CLOSED" && (
            <form onSubmit={handleReply} className="flex gap-2">
              <input
                required
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                placeholder={t("acct.tickets.replyPlaceholder")}
                className="flex-1 rounded-xl glass-input px-3 py-2.5 text-sm focus:border-brand-500"
              />
              <button
                type="submit"
                disabled={replyLoading}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white transition cursor-pointer disabled:opacity-50"
              >
                {replyLoading ? t("acct.wallet.sending") : t("acct.wallet.send")}
              </button>
            </form>
          )}
          {replyError && <p className="text-xs text-rose-400 mt-2">{replyError}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          <p className="text-sm text-slate-500 mt-1">{subtitle}</p>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-500/20 transition cursor-pointer shrink-0"
        >
          + {t("acct.tickets.new")}
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70 space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-600 uppercase block">{t("acct.tickets.subject")}</label>
            <input required value={subject} onChange={(e) => setSubject(e.target.value)}
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-600 uppercase block">{t("acct.tickets.category")}</label>
            <select value={category} onChange={(e) => setCategory(e.target.value)}
              className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-white focus:border-brand-500">
              {CATEGORY_CODES.filter((code) => code !== "CHIUSURA_ACCOUNT").map((code) => (
                <option key={code} value={code}>{t.dyn(`acct.ticket.category.${code}`, code)}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-600 uppercase block">{t("acct.tickets.message")}</label>
            <textarea required rows={4} value={message} onChange={(e) => setMessage(e.target.value)}
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500 resize-none" />
          </div>
          {createError && <p className="text-xs text-rose-400">{createError}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowCreate(false)}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-50 hover:bg-slate-100 text-slate-600 transition cursor-pointer">
              {t("common.cancel")}
            </button>
            <button type="submit" disabled={createLoading}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white transition cursor-pointer disabled:opacity-50">
              {createLoading ? t("acct.wallet.sending") : t("acct.tickets.open")}
            </button>
          </div>
        </form>
      )}

      {listError && <p className="text-sm text-rose-400">{t("acct.tickets.loadError")}</p>}

      <div className="space-y-3">
        {tickets === undefined ? (
          <p className="text-sm text-slate-500 text-center py-8">{t("acct.common.loading")}</p>
        ) : tickets.length === 0 ? (
          <div className="glass-card rounded-2xl p-12 text-center border-slate-200">
            <p className="text-sm text-slate-500">{t("acct.tickets.empty")}</p>
          </div>
        ) : (
          pagination.pageItems.map((ticket) => (
            <button
              key={ticket.id}
              onClick={() => setSelectedId(ticket.id)}
              className="w-full text-left glass-card rounded-2xl p-4 border-slate-200 bg-white/70 hover:bg-slate-100 transition flex items-center justify-between gap-4 cursor-pointer"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-slate-900 truncate">{ticket.subject}</p>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border shrink-0 ${statusColor(ticket.status)}`}>
                    {t.dyn(`acct.ticket.status.${ticket.status}`, ticket.status)}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  {t.dyn(`acct.ticket.category.${ticket.category}`, ticket.category)} · {t("acct.tickets.messages", { n: ticket.message_count })}
                  {ticket.last_message_at ? ` · ${t("acct.tickets.lastUpdate", { date: formatDateTime(ticket.last_message_at, fmt.tag) })}` : ""}
                </p>
              </div>
            </button>
          ))
        )}
      </div>
      <Pagination {...pagination} label={t("acct.tickets.plural")} />
    </div>
  );
}
