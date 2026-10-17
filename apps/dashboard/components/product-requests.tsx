"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import type { ProductRequestDetailRead, ProductRequestRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

/** «Non hai trovato ciò che cercavi?» -- il lato cliente delle richieste di
 *  prodotto. Un sistema di ticket a sé (API /product-requests), separato da
 *  «Supporto & Assistenza»: qui si chiede un prodotto, là si segnala un
 *  problema.
 *
 *  - `ProductRequestBanner`: il riquadro nello Shop, sopra la ricerca, con il
 *    form in una finestra -- il cliente non lascia lo Shop per chiedere;
 *  - `CustomerProductRequestsPanel`: la scheda «Le mie richieste», dove legge
 *    le risposte e risponde a sua volta. */

/** Italian labels, still read by the staff panel; this file shows
 *  `shopx.requests.status.*` instead. */
export const PRODUCT_REQUEST_STATUS_LABELS: Record<string, string> = {
  OPEN: "Inviata",
  IN_PROGRESS: "In lavorazione",
  FOUND: "Trovato",
  NOT_FOUND: "Non trovato",
  CLOSED: "Chiusa",
};

export function productRequestStatusColor(status: string): string {
  switch (status) {
    case "OPEN":
      return "bg-amber-500/10 text-amber-700 border-amber-500/20";
    case "IN_PROGRESS":
      return "bg-sky-500/10 text-sky-400 border-sky-500/20";
    case "FOUND":
      return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
    case "NOT_FOUND":
      return "bg-rose-500/10 text-rose-400 border-rose-500/20";
    default:
      return "bg-slate-500/10 text-slate-400 border-slate-500/20";
  }
}

/** `tag` is the reader's Intl tag (`fmt.tag`). */
export function formatDateTime(iso: string, tag?: string): string {
  return new Date(iso).toLocaleString(tag, { dateStyle: "short", timeStyle: "short" });
}

const labelCls = "text-xs font-semibold text-slate-600 uppercase block";
const inputCls = "w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-brand-500";

function NewRequestForm({
  initialName = "",
  onCreated,
  onCancel,
}: {
  initialName?: string;
  onCreated: (request: ProductRequestRead) => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [productName, setProductName] = useState(initialName);
  const [message, setMessage] = useState("");
  const [referenceUrl, setReferenceUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/product-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_name: productName, message, reference_url: referenceUrl || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const created = (await res.json()) as ProductRequestRead;
      await queryClient.invalidateQueries({ queryKey: ["product-requests", "mine"] });
      onCreated(created);
    } catch (err: unknown) {
      setError((err as Error).message || t("shopx.requests.sendFailed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="space-y-1">
        <label className={labelCls}>{t("shopx.requests.whatProduct")} *</label>
        <input
          required
          minLength={2}
          maxLength={255}
          value={productName}
          onChange={(e) => setProductName(e.target.value)}
          placeholder={t("shopx.requests.whatPlaceholder")}
          className={inputCls}
        />
      </div>
      <div className="space-y-1">
        <label className={labelCls}>{t("shopx.requests.tellMore")} *</label>
        <textarea
          required
          rows={4}
          maxLength={5000}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={t("shopx.requests.tellMorePlaceholder")}
          className={`${inputCls} resize-none`}
        />
      </div>
      <div className="space-y-1">
        <label className={labelCls}>{t("shopx.requests.exampleLink")}</label>
        <input
          type="url"
          maxLength={1000}
          value={referenceUrl}
          onChange={(e) => setReferenceUrl(e.target.value)}
          placeholder={t("shopx.requests.exampleLinkPlaceholder")}
          className={inputCls}
        />
      </div>
      {error && <p className="text-xs text-rose-400">{error}</p>}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 rounded-xl text-xs font-semibold hover:bg-slate-100 bg-slate-900/5 text-slate-600 transition cursor-pointer"
        >
          {t("common.cancel")}
        </button>
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white transition cursor-pointer disabled:opacity-50"
        >
          {loading ? t("shopx.requests.sending") : t("shopx.requests.send")}
        </button>
      </div>
    </form>
  );
}

/** Il riquadro nello Shop, sopra la ricerca. `searchText` precompila il nome
 *  del prodotto: chi ha appena cercato "friggitrice ad aria" senza trovarla
 *  non deve riscriverlo. */
export function ProductRequestBanner({
  searchText = "",
  onOpenRequests,
}: {
  searchText?: string;
  onOpenRequests: () => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [sent, setSent] = useState<ProductRequestRead | null>(null);

  return (
    <>
      <div className="relative overflow-hidden rounded-2xl border border-ink-200 bg-ink-50 p-5 sm:p-6">
        <div className="relative flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-white border border-ink-200 shadow-sm flex items-center justify-center shrink-0">
            <svg className="w-6 h-6 text-brand-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0zM11 8v6m-3-3h6" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base sm:text-lg font-bold text-slate-900 leading-snug">
              {t("shopx.requests.bannerTitle")}
            </h3>
            <p className="text-sm text-slate-600 mt-0.5">
              {t("shopx.requests.bannerText")}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setSent(null);
              setOpen(true);
            }}
            className="px-5 py-2.5 rounded-xl text-sm font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-500/20 transition cursor-pointer shrink-0"
          >
            {t("shopx.requests.requestProduct")}
          </button>
        </div>
      </div>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm p-0 sm:p-4"
          onClick={() => setOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t("shopx.requests.requestProduct")}
            onClick={(e) => e.stopPropagation()}
            className="w-full sm:max-w-lg max-h-[92vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl bg-white border border-slate-200 p-6 space-y-4"
          >
            {sent ? (
              <div className="text-center space-y-4 py-4">
                <div className="w-14 h-14 mx-auto rounded-full bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center">
                  <svg className="w-7 h-7 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900">{t("shopx.requests.sentTitle")}</h3>
                  <p className="text-sm text-slate-500 mt-1">
                    {t("shopx.requests.sentText", { name: sent.product_name })}
                  </p>
                </div>
                <div className="flex justify-center gap-2">
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold hover:bg-slate-100 bg-slate-900/5 text-slate-600 transition cursor-pointer"
                  >
                    {t("shopx.requests.backToShop")}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      onOpenRequests();
                    }}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white transition cursor-pointer"
                  >
                    {t("shopx.requests.goToMine")}
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div>
                  <h3 className="text-lg font-bold text-slate-900">{t("shopx.requests.requestProduct")}</h3>
                  <p className="text-xs text-slate-500 mt-1">
                    {t("shopx.requests.formIntro")}
                  </p>
                </div>
                <NewRequestForm
                  initialName={searchText.trim()}
                  onCreated={(r) => setSent(r)}
                  onCancel={() => setOpen(false)}
                />
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`/api/proxy${path}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

export function CustomerProductRequestsPanel() {
  const { t, fmt } = useI18n();
  const queryClient = useQueryClient();
  const { data: requests, error: listError } = useQuery({
    queryKey: ["product-requests", "mine"],
    queryFn: () => getJson<ProductRequestRead[]>("/product-requests/mine"),
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: detail } = useQuery({
    queryKey: ["product-requests", "mine", "detail", selectedId],
    queryFn: () => getJson<ProductRequestDetailRead>(`/product-requests/mine/${selectedId}`),
    enabled: !!selectedId,
  });
  const [showCreate, setShowCreate] = useState(false);
  const [reply, setReply] = useState("");
  const [replyLoading, setReplyLoading] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);
  const pagination = usePagination(requests ?? []);

  async function handleReply(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedId) return;
    setReplyLoading(true);
    setReplyError(null);
    try {
      const res = await fetch(`/api/proxy/product-requests/mine/${selectedId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: reply }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setReply("");
      await queryClient.invalidateQueries({ queryKey: ["product-requests", "mine"] });
    } catch (err: unknown) {
      setReplyError((err as Error).message || t("shopx.requests.replyFailed"));
    } finally {
      setReplyLoading(false);
    }
  }

  if (selectedId && detail) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => setSelectedId(null)}
          className="text-xs text-slate-400 hover:text-slate-900 transition cursor-pointer flex items-center gap-1"
        >
          ← {t("shopx.requests.backToList")}
        </button>
        <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-wider text-brand-600">{t("shopx.requests.productSought")}</p>
              <h3 className="text-lg font-semibold text-slate-900 break-words">{detail.product_name}</h3>
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
            <span className={`px-3 py-1 rounded-full text-xs font-bold border shrink-0 ${productRequestStatusColor(detail.status)}`}>
              {t.dyn(`shopx.requests.status.${detail.status}`, PRODUCT_REQUEST_STATUS_LABELS[detail.status] ?? detail.status)}
            </span>
          </div>

          <div className="space-y-3 mb-6">
            {detail.messages.map((m) => {
              const isStaff = m.author_role === "ADMIN";
              return (
                <div key={m.id} className={`flex ${isStaff ? "justify-start" : "justify-end"}`}>
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                      isStaff
                        ? "bg-brand-600/10 border border-brand-500/20 text-slate-700"
                        : " bg-slate-900/5 border border-slate-200 text-slate-700"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        {isStaff ? "Jav" : t("shopx.requests.you")}
                      </span>
                      <span className="text-[10px] text-slate-500">{formatDateTime(m.created_at, fmt.tag)}</span>
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
                placeholder={t("shopx.requests.replyPlaceholder")}
                className="flex-1 min-w-0 rounded-xl glass-input px-3 py-2.5 text-sm focus:border-brand-500"
              />
              <button
                type="submit"
                disabled={replyLoading}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white transition cursor-pointer disabled:opacity-50"
              >
                {replyLoading ? t("shopx.requests.sending") : t("shopx.requests.sendReply")}
              </button>
            </form>
          ) : (
            <p className="text-xs text-slate-500">{t("shopx.requests.closed")}</p>
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
          <h2 className="text-lg font-semibold text-slate-900">{t("shopx.requests.mineTitle")}</h2>
          <p className="text-sm text-slate-500 mt-1">
            {t("shopx.requests.mineText")}
          </p>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-500/20 transition cursor-pointer shrink-0"
        >
          + {t("shopx.requests.new")}
        </button>
      </div>

      {showCreate && (
        <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
          <NewRequestForm
            onCreated={(r) => {
              setShowCreate(false);
              setSelectedId(r.id);
            }}
            onCancel={() => setShowCreate(false)}
          />
        </div>
      )}

      {listError && <p className="text-sm text-rose-400">{t("shopx.requests.loadFailed")}</p>}

      <div className="space-y-3">
        {requests === undefined ? (
          <p className="text-sm text-slate-500 text-center py-8">{t("shopx.loading")}</p>
        ) : requests.length === 0 ? (
          <div className="glass-card rounded-2xl p-12 text-center border-slate-200">
            <p className="text-sm text-slate-500">
              {t("shopx.requests.empty")}
            </p>
          </div>
        ) : (
          pagination.pageItems.map((r) => {
            const news = r.last_author_role === "ADMIN" && r.status !== "CLOSED";
            return (
              <button
                key={r.id}
                onClick={() => setSelectedId(r.id)}
                className="w-full text-left glass-card rounded-2xl p-4 border-slate-200 bg-white/70 hover:bg-slate-100 transition flex items-center justify-between gap-4 cursor-pointer"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-slate-900 truncate">{r.product_name}</p>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border shrink-0 ${productRequestStatusColor(r.status)}`}>
                      {t.dyn(`shopx.requests.status.${r.status}`, PRODUCT_REQUEST_STATUS_LABELS[r.status] ?? r.status)}
                    </span>
                    {news && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-brand-600 text-white shrink-0">
                        {t("shopx.requests.newReply")}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1">
                    {t("shopx.requests.messages", { n: r.message_count })}
                    {r.last_message_at ? ` · ${t("shopx.requests.lastUpdate", { date: formatDateTime(r.last_message_at, fmt.tag) })}` : ""}
                  </p>
                </div>
                <svg className="w-4 h-4 text-slate-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            );
          })
        )}
      </div>
      <Pagination {...pagination} label={t("shopx.requests.paginationLabel")} />
    </div>
  );
}
