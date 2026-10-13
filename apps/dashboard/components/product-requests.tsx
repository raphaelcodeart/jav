"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import type { ProductRequestDetailRead, ProductRequestRead } from "@/lib/types";

/** «Non hai trovato ciò che cercavi?» -- il lato cliente delle richieste di
 *  prodotto. Un sistema di ticket a sé (API /product-requests), separato da
 *  «Supporto & Assistenza»: qui si chiede un prodotto, là si segnala un
 *  problema.
 *
 *  - `ProductRequestBanner`: il riquadro nello Shop, sopra la ricerca, con il
 *    form in una finestra -- il cliente non lascia lo Shop per chiedere;
 *  - `CustomerProductRequestsPanel`: la scheda «Le mie richieste», dove legge
 *    le risposte e risponde a sua volta. */

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
      return "bg-amber-500/10 text-amber-400 border-amber-500/20";
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

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
}

const labelCls = "text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block";
const inputCls = "w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500";

function NewRequestForm({
  initialName = "",
  onCreated,
  onCancel,
}: {
  initialName?: string;
  onCreated: (request: ProductRequestRead) => void;
  onCancel: () => void;
}) {
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
      setError((err as Error).message || "Impossibile inviare la richiesta.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="space-y-1">
        <label className={labelCls}>Che prodotto cerchi? *</label>
        <input
          required
          minLength={2}
          maxLength={255}
          value={productName}
          onChange={(e) => setProductName(e.target.value)}
          placeholder="Es. macchina del caffè a capsule"
          className={inputCls}
        />
      </div>
      <div className="space-y-1">
        <label className={labelCls}>Raccontaci di più *</label>
        <textarea
          required
          rows={4}
          maxLength={5000}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Marca, modello, colore, taglia, quantità, quanto vorresti spendere…"
          className={`${inputCls} resize-none`}
        />
      </div>
      <div className="space-y-1">
        <label className={labelCls}>Link di esempio (facoltativo)</label>
        <input
          type="url"
          maxLength={1000}
          value={referenceUrl}
          onChange={(e) => setReferenceUrl(e.target.value)}
          placeholder="https://… un prodotto simile che hai visto online"
          className={inputCls}
        />
      </div>
      {error && <p className="text-xs text-rose-400">{error}</p>}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-white/5 hover:bg-white/10 light:bg-slate-900/5 text-slate-300 light:text-slate-600 transition cursor-pointer"
        >
          Annulla
        </button>
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white transition cursor-pointer disabled:opacity-50"
        >
          {loading ? "Invio…" : "Invia richiesta"}
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
  const [open, setOpen] = useState(false);
  const [sent, setSent] = useState<ProductRequestRead | null>(null);

  return (
    <>
      <div className="relative overflow-hidden rounded-2xl border border-orange-500/30 bg-gradient-to-br from-orange-600/15 via-amber-500/10 to-transparent p-5 sm:p-6">
        <div className="absolute -right-10 -top-10 w-40 h-40 rounded-full bg-orange-500/10 blur-2xl pointer-events-none" />
        <div className="relative flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-orange-500/15 border border-orange-500/30 flex items-center justify-center shrink-0">
            <svg className="w-6 h-6 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0zM11 8v6m-3-3h6" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base sm:text-lg font-bold text-white light:text-slate-900 leading-snug">
              Non hai trovato ciò che cercavi?
            </h3>
            <p className="text-sm text-slate-300 light:text-slate-600 mt-0.5">
              Faccelo sapere: lo cerchiamo noi per te e ti rispondiamo qui, in «Le mie richieste».
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setSent(null);
              setOpen(true);
            }}
            className="px-5 py-2.5 rounded-xl text-sm font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer shrink-0"
          >
            Richiedi un prodotto
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
            aria-label="Richiedi un prodotto"
            onClick={(e) => e.stopPropagation()}
            className="w-full sm:max-w-lg max-h-[92vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl bg-slate-900 light:bg-white border border-white/10 light:border-slate-200 p-6 space-y-4"
          >
            {sent ? (
              <div className="text-center space-y-4 py-4">
                <div className="w-14 h-14 mx-auto rounded-full bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center">
                  <svg className="w-7 h-7 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-lg font-bold text-white light:text-slate-900">Richiesta inviata!</h3>
                  <p className="text-sm text-slate-400 light:text-slate-500 mt-1">
                    Cerchiamo «{sent.product_name}» per te. Ti avvisiamo appena abbiamo una risposta, e la trovi in «Le mie richieste».
                  </p>
                </div>
                <div className="flex justify-center gap-2">
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-white/5 hover:bg-white/10 light:bg-slate-900/5 text-slate-300 light:text-slate-600 transition cursor-pointer"
                  >
                    Torna allo Shop
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      onOpenRequests();
                    }}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white transition cursor-pointer"
                  >
                    Vai a «Le mie richieste»
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div>
                  <h3 className="text-lg font-bold text-white light:text-slate-900">Richiedi un prodotto</h3>
                  <p className="text-xs text-slate-400 light:text-slate-500 mt-1">
                    Dicci cosa cerchi: più dettagli ci dai, prima lo troviamo.
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
      setReplyError((err as Error).message || "Impossibile inviare la risposta.");
    } finally {
      setReplyLoading(false);
    }
  }

  if (selectedId && detail) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => setSelectedId(null)}
          className="text-xs text-slate-400 hover:text-white light:hover:text-slate-900 transition cursor-pointer flex items-center gap-1"
        >
          ← Torna alle richieste
        </button>
        <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-wider text-orange-400">Prodotto cercato</p>
              <h3 className="text-lg font-semibold text-white light:text-slate-900 break-words">{detail.product_name}</h3>
              {detail.reference_url && (
                <a
                  href={detail.reference_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-orange-400 hover:text-orange-300 break-all"
                >
                  {detail.reference_url}
                </a>
              )}
            </div>
            <span className={`px-3 py-1 rounded-full text-xs font-bold border shrink-0 ${productRequestStatusColor(detail.status)}`}>
              {PRODUCT_REQUEST_STATUS_LABELS[detail.status] ?? detail.status}
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
                        ? "bg-orange-600/10 border border-orange-500/20 text-slate-200 light:text-slate-700"
                        : "bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200 text-slate-200 light:text-slate-700"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        {isStaff ? "Jav" : "Tu"}
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
                placeholder="Scrivi una risposta…"
                className="flex-1 min-w-0 rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500"
              />
              <button
                type="submit"
                disabled={replyLoading}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white transition cursor-pointer disabled:opacity-50"
              >
                {replyLoading ? "Invio…" : "Invia"}
              </button>
            </form>
          ) : (
            <p className="text-xs text-slate-500">Questa richiesta è chiusa. Se cerchi altro, aprine una nuova.</p>
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
          <h2 className="text-lg font-semibold text-white light:text-slate-900">Le mie richieste</h2>
          <p className="text-sm text-slate-400 light:text-slate-500 mt-1">
            I prodotti che ci hai chiesto di cercare. Qui trovi le nostre risposte e puoi risponderci.
          </p>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer shrink-0"
        >
          + Nuova richiesta
        </button>
      </div>

      {showCreate && (
        <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <NewRequestForm
            onCreated={(r) => {
              setShowCreate(false);
              setSelectedId(r.id);
            }}
            onCancel={() => setShowCreate(false)}
          />
        </div>
      )}

      {listError && <p className="text-sm text-rose-400">Impossibile caricare le richieste.</p>}

      <div className="space-y-3">
        {requests === undefined ? (
          <p className="text-sm text-slate-500 text-center py-8">Caricamento…</p>
        ) : requests.length === 0 ? (
          <div className="glass-card rounded-2xl p-12 text-center border-white/5 light:border-slate-200">
            <p className="text-sm text-slate-500">
              Nessuna richiesta. Se nello Shop non trovi quello che cerchi, usa «+ Nuova richiesta»: lo cerchiamo noi.
            </p>
          </div>
        ) : (
          pagination.pageItems.map((r) => {
            const news = r.last_author_role === "ADMIN" && r.status !== "CLOSED";
            return (
              <button
                key={r.id}
                onClick={() => setSelectedId(r.id)}
                className="w-full text-left glass-card rounded-2xl p-4 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 hover:bg-white/5 transition flex items-center justify-between gap-4 cursor-pointer"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-white light:text-slate-900 truncate">{r.product_name}</p>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border shrink-0 ${productRequestStatusColor(r.status)}`}>
                      {PRODUCT_REQUEST_STATUS_LABELS[r.status] ?? r.status}
                    </span>
                    {news && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-orange-600 text-white shrink-0">
                        Nuova risposta
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1">
                    {r.message_count} messaggi
                    {r.last_message_at ? ` · ultimo aggiornamento ${formatDateTime(r.last_message_at)}` : ""}
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
      <Pagination {...pagination} label="richieste" />
    </div>
  );
}
