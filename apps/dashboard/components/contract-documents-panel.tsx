"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { DocumentPreviewModal } from "@/components/document-preview-modal";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";

type DocumentRead = {
  id: string;
  /** Exactly one of these two is set: a document of one contract, or of its
      whole pratica (Session 52), which then counts for every point in it. */
  contract_id: string | null;
  contract_request_id: string | null;
  document_type: string;
  /** Only ever set on an extra attachment -- what its uploader called it. */
  description: string | null;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  uploaded_by_user_id: string;
  uploaded_by_role: string;
  uploaded_by_name: string | null;
  status: string;
  reviewed_by_user_id: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
};

type RequiredDocumentStatus = {
  document_type: string;
  /** False for a slot that is offered but never blocks the contract (the
      visura of a ditta individuale). Older responses omit it; the server
      defaults it to true, and so does the destructuring below. */
  required?: boolean;
  /** The latest page, or null when nothing was uploaded. */
  document: DocumentRead | null;
  /** Every page, oldest first: front and back of an ID, a 20-page bill. */
  pages?: DocumentRead[];
};

type ContractDocumentsRead = {
  contract_id?: string | null;
  contract_request_id?: string | null;
  required: RequiredDocumentStatus[];
  extra?: DocumentRead[];
  /** Pratica only: what must still be uploaded before going on. */
  blocking_missing?: string[];
};

/** Pages one document may have (MAX_PAGES_PER_DOCUMENT in the API). */
const MAX_PAGES = 20;

/* Slot labels: `ctr.docs.type.<TYPE>`; what each slot is for, in the words
   a customer standing at a scanner would use: `ctr.docs.hint.<TYPE>`. */

const ACCEPTED_CONTENT_TYPES = "application/pdf,image/jpeg,image/png";
const MIN_DESCRIPTION_LENGTH = 3;
const MAX_DESCRIPTION_LENGTH = 120;

function statusColor(status: string): string {
  if (status === "APPROVED") return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
  if (status === "REJECTED") return "bg-rose-500/10 text-rose-400 border-rose-500/20";
  if (status === "MISSING") return " bg-slate-900/5 text-slate-400 border-slate-300";
  return "bg-amber-500/10 text-amber-700 border-amber-500/20";
}

async function fetchDocuments(path: string): Promise<ContractDocumentsRead> {
  const res = await fetch(path);
  if (!res.ok) throw new Error("documents fetch failed");
  return res.json();
}

function documentsPath({ contractId, requestId }: { contractId?: string; requestId?: string }): string {
  return contractId
    ? `/api/proxy/contracts/${contractId}/documents`
    : `/api/proxy/contract-requests/${requestId}/documents`;
}

async function fetchDocumentUrl(documentId: string, errorText: string): Promise<string> {
  const res = await fetch(`/api/proxy/documents/${documentId}/url`);
  if (!res.ok) throw new Error(errorText);
  const data = await res.json();
  return data.url;
}

/** How many of the documents that actually block this contract are in.
    Exported because the contract card outside this panel says the same
    thing ("mancano 2 documenti") and must never disagree with it. */
export function missingRequiredCount(data: ContractDocumentsRead | undefined): number {
  if (!data) return 0;
  return data.required.filter((row) => row.required !== false && row.document === null).length;
}

export function useContractDocuments(contractId: string) {
  return useQuery({
    queryKey: ["documents", "contract", contractId],
    queryFn: () => fetchDocuments(documentsPath({ contractId })),
  });
}

/** The documents uploaded once for a whole pratica (Session 52). */
export function useRequestDocuments(requestId: string) {
  return useQuery({
    queryKey: ["documents", "request", requestId],
    queryFn: () => fetchDocuments(documentsPath({ requestId })),
  });
}

/** One contract's documents (`contractId`) or a pratica's shared ones
    (`requestId`) -- same slots, same upload, same review.

    `onlyTypes` narrows the slots shown, for a screen that only needs some
    of them (the identity and fiscal code already live on the pratica). */
export function ContractDocumentsPanel({
  contractId,
  requestId,
  isStaff = false,
  onlyTypes,
}: {
  contractId?: string;
  requestId?: string;
  isStaff?: boolean;
  onlyTypes?: string[];
}) {
  const { t, fmt } = useI18n();
  const typeLabel = (type: string) => t.dyn(`ctr.docs.type.${type}`, type);
  const typeHint = (type: string) => t.dyn(`ctr.docs.hint.${type}`, "");
  const statusLabel = (status: string) => t.dyn(`ctr.docs.status.${status}`, status);
  const queryClient = useQueryClient();
  const contractQuery = useQuery({
    queryKey: ["documents", "contract", contractId],
    queryFn: () => fetchDocuments(documentsPath({ contractId })),
    enabled: Boolean(contractId),
  });
  const requestQuery = useQuery({
    queryKey: ["documents", "request", requestId],
    queryFn: () => fetchDocuments(documentsPath({ requestId })),
    enabled: !contractId && Boolean(requestId),
  });
  const { data: rawData, error, isLoading } = contractId ? contractQuery : requestQuery;
  const ownerKey = contractId ?? requestId ?? "";
  const data = rawData && onlyTypes
    ? { ...rawData, required: rawData.required.filter((row) => onlyTypes.includes(row.document_type)) }
    : rawData;

  const [uploadingType, setUploadingType] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const [extraLabel, setExtraLabel] = useState("");
  const [addingExtra, setAddingExtra] = useState(false);
  const extraFileInput = useRef<HTMLInputElement>(null);
  const extraCameraInput = useRef<HTMLInputElement>(null);

  const trimmedExtraLabel = extraLabel.trim();
  const canPickExtraFile = trimmedExtraLabel.length >= MIN_DESCRIPTION_LENGTH;

  async function refresh() {
    // Every contract of a pratica shows the pratica's documents too, and the
    // pratica screens count what is missing: all of it is stale now.
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["documents"] }),
      queryClient.invalidateQueries({ queryKey: ["contract-request"] }),
      queryClient.invalidateQueries({ queryKey: ["contract-requests"] }),
    ]);
  }

  async function handleUpload(documentType: string, file: File, description?: string) {
    setUploadingType(documentType);
    setUploadError(null);
    try {
      const formData = new FormData();
      formData.append("document_type", documentType);
      if (description) formData.append("description", description);
      formData.append("file", file);
      const res = await fetch(documentsPath({ contractId, requestId }), { method: "POST", body: formData });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await refresh();
      return true;
    } catch (err: any) {
      // The server's own message when there is one (a file too large, a
      // label too short) -- it says something the generic sentence can't.
      setUploadError(err?.message || t("ctr.docs.uploadFailed", { type: typeLabel(documentType) }));
      return false;
    } finally {
      setUploadingType(null);
    }
  }

  /** Several pages picked at once (a multi-page bill photographed in one
      go) go up one after the other, in the order they were picked. */
  async function handleUploadMany(documentType: string, files: FileList | null, room: number) {
    if (!files) return;
    const list = Array.from(files).slice(0, Math.max(0, room));
    if (files.length > list.length) {
      setUploadError(t("ctr.docs.tooManyPages", { max: MAX_PAGES, n: list.length }));
    }
    for (const file of list) {
      const ok = await handleUpload(documentType, file);
      if (!ok) break;
    }
  }

  const [deletingId, setDeletingId] = useState<string | null>(null);
  async function handleDelete(doc: DocumentRead) {
    if (!window.confirm(t("ctr.docs.confirmRemovePage", { name: doc.original_filename }))) return;
    setDeletingId(doc.id);
    setUploadError(null);
    try {
      const res = await fetch(`/api/proxy/documents/${doc.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await refresh();
    } catch (err: any) {
      setUploadError(err?.message || t("ctr.docs.removePageError"));
    } finally {
      setDeletingId(null);
    }
  }

  async function handleExtraUpload(file: File) {
    const ok = await handleUpload("OTHER", file, trimmedExtraLabel);
    if (ok) {
      setExtraLabel("");
      setAddingExtra(false);
    }
  }

  // "Visualizza" opens the document in a popup on this page (Session 57),
  // never in a new tab: whoever is checking a document keeps their place.
  const [previewDoc, setPreviewDoc] = useState<DocumentRead | null>(null);

  async function handleReview(documentId: string, newStatus: "APPROVED" | "REJECTED") {
    try {
      const res = await fetch(`/api/proxy/documents/${documentId}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus, review_note: reviewNote || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setReviewingId(null);
      setReviewNote("");
      await refresh();
    } catch {
      setUploadError(t("ctr.docs.reviewError"));
    }
  }

  /** The staff-only Approva/Respingi strip, identical for a slot document
      and for an extra attachment. */
  function reviewControls(doc: DocumentRead) {
    if (!isStaff || doc.status !== "PENDING_REVIEW") return null;
    return (
      <div className="mt-3 pt-3 border-t border-slate-200 space-y-2">
        {reviewingId === doc.id ? (
          <>
            <input
              value={reviewNote}
              onChange={(e) => setReviewNote(e.target.value)}
              placeholder={t("ctr.docs.notePlaceholder")}
              className="w-full rounded-lg glass-input px-3 py-1.5 text-xs focus:border-brand-500"
            />
            <div className="flex gap-2">
              <button
                onClick={() => handleReview(doc.id, "APPROVED")}
                className="px-3 py-1 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-xs font-semibold transition cursor-pointer"
              >
                {t("ctr.docs.approve")}
              </button>
              <button
                onClick={() => handleReview(doc.id, "REJECTED")}
                className="px-3 py-1 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-xs font-semibold transition cursor-pointer"
              >
                {t("ctr.docs.reject")}
              </button>
              <button
                onClick={() => { setReviewingId(null); setReviewNote(""); }}
                className="px-3 py-1 rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-400 text-xs font-semibold transition cursor-pointer"
              >
                {t("common.cancel")}
              </button>
            </div>
          </>
        ) : (
          <button
            onClick={() => setReviewingId(doc.id)}
            className="px-3 py-1 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer"
          >
            {t("ctr.docs.review")}
          </button>
        )}
      </div>
    );
  }

  if (isLoading) return <p className="text-sm text-slate-500">{t("ctr.docs.loading")}</p>;
  if (error) return <p className="text-sm text-rose-400">{t("ctr.docs.loadError")}</p>;
  if (!data) return null;

  const extra = data.extra ?? [];
  const requiredRows = data.required.filter((row) => row.required !== false);
  const uploadedRequired = requiredRows.filter((row) => row.document !== null).length;
  const missing = requiredRows.length - uploadedRequired;

  return (
    <div className="space-y-3">
      {/* What is still missing, said once at the top -- before this, the
          only way to know was to read four status badges and count. */}
      <div
        className={`flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl border text-xs ${
          missing === 0
            ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
            : "bg-amber-500/10 border-amber-500/20 text-amber-700"
        }`}
      >
        <span className="font-semibold">
          {missing === 0
            ? t("ctr.docs.allUploaded")
            : missing === 1
              ? t("ctr.docs.missingOne")
              : t("ctr.docs.missingN", { n: missing })}
        </span>
        <span className="font-bold tabular-nums shrink-0">
          {uploadedRequired}/{requiredRows.length}
        </span>
      </div>

      {uploadError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{uploadError}</div>
      )}

      {data.required.map((row) => {
        const doc = row.document;
        const pages = row.pages ?? (doc ? [doc] : []);
        const isRequired = row.required !== false;
        const inputId = `doc-upload-${ownerKey}-${row.document_type}`;
        // On a contract, a slot filled by its pratica's document.
        const inherited = Boolean(contractId && doc?.contract_request_id);
        // Pages added here go to this owner: on a contract whose slot is
        // filled by the pratica, the first own page starts a new document.
        const ownPages = inherited ? 0 : pages.length;
        const room = MAX_PAGES - ownPages;
        const busyHere = uploadingType === row.document_type;
        return (
          <div
            key={row.document_type}
            className="p-3 rounded-xl bg-slate-900/5 border border-slate-200"
          >
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-900">
                  {typeLabel(row.document_type)}
                  {isRequired ? (
                    <span className="ml-2 text-[10px] font-semibold text-brand-600 uppercase tracking-wide">
                      {t("ctr.docs.required")}
                    </span>
                  ) : (
                    <span className="ml-2 text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
                      {t("common.optional")}
                    </span>
                  )}
                </p>
                {typeHint(row.document_type) && pages.length === 0 && (
                  <p className=" text-slate-500 mt-0.5">
                    {typeHint(row.document_type)}
                  </p>
                )}
                {pages.length > 0 && (
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    {pages.length === 1 ? t("ctr.docs.onePage") : t("ctr.docs.nPages", { n: pages.length })}
                    {inherited && ` · ${t("ctr.docs.inherited")}`}
                  </p>
                )}
              </div>
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border shrink-0 ${statusColor(doc?.status ?? "MISSING")}`}>
                {doc ? statusLabel(doc.status) : t("ctr.docs.notUploaded")}
              </span>
            </div>

            {/* Said every time, not only while empty (Session 83): an old
                visura is the most common reason a business pratica is
                rejected, and the one the uploader can check before sending. */}
            {row.document_type === "CHAMBER_OF_COMMERCE" && (
              <div className="mt-2 flex items-start gap-2 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/25 text-amber-700 leading-snug">
                <svg className="w-4 h-4 shrink-0 mt-px" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                </svg>
                <span>
                  <strong>{t("ctr.docs.visuraMaxAge")}</strong> {t("ctr.docs.visuraMaxAgeBody")}
                </span>
              </div>
            )}

            {pages.length > 0 && (
              <ol className="mt-2.5 space-y-1.5">
                {pages.map((pageDoc, i) => (
                  <li
                    key={pageDoc.id}
                    className="rounded-lg bg-white border border-slate-200 px-2.5 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <span className="w-6 h-6 rounded-md bg-brand-500/15 text-brand-600 text-[10px] font-bold flex items-center justify-center shrink-0">
                        {i + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs text-slate-700 truncate">{pageDoc.original_filename}</p>
                        <p className="text-[10px] text-slate-500 truncate">
                          {pageDoc.uploaded_by_name ?? "—"} · {new Date(pageDoc.created_at).toLocaleDateString(fmt.tag)}
                        </p>
                      </div>
                      {pageDoc.status !== "PENDING_REVIEW" && (
                        <span className={`px-1.5 py-0.5 rounded-full text-[9px] font-bold border shrink-0 ${statusColor(pageDoc.status)}`}>
                          {statusLabel(pageDoc.status)}
                        </span>
                      )}
                      <button
                        onClick={() => setPreviewDoc(pageDoc)}
                        className="px-2 py-1 rounded-md font-semibold text-slate-600 hover:bg-slate-100 cursor-pointer shrink-0"
                      >
                        {t("ctr.docs.view")}
                      </button>
                      {pageDoc.status !== "APPROVED" && !(inherited && !isStaff) && (
                        <button
                          onClick={() => handleDelete(pageDoc)}
                          disabled={deletingId === pageDoc.id}
                          title={t("ctr.docs.removeThisPage")}
                          aria-label={t("ctr.docs.removePageN", { n: i + 1 })}
                          className="p-1 rounded-md text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer shrink-0 disabled:opacity-40"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      )}
                    </div>
                    {pageDoc.review_note && (
                      <p className=" text-slate-500 mt-1.5">
                        <span className="font-semibold">{t("ctr.docs.adminNote")}</span> {pageDoc.review_note}
                      </p>
                    )}
                    {reviewControls(pageDoc)}
                  </li>
                ))}
              </ol>
            )}

            <input
              type="file"
              multiple
              accept={ACCEPTED_CONTENT_TYPES}
              id={inputId}
              className="hidden"
              onChange={(e) => {
                handleUploadMany(row.document_type, e.target.files, room);
                e.target.value = "";
              }}
            />
            {/* Straight to the camera (Session 55): one shot per page, and
                "Foto" again for the next one -- the back of the ID, page 2
                of the bill. On a computer it is just a file picker. */}
            <input
              type="file"
              accept="image/jpeg,image/png"
              capture="environment"
              id={`${inputId}-camera`}
              className="hidden"
              onChange={(e) => {
                handleUploadMany(row.document_type, e.target.files, room);
                e.target.value = "";
              }}
            />
            {room > 0 ? (
              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                <label
                  htmlFor={`${inputId}-camera`}
                  className={`px-3 py-1.5 rounded-lg bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-600 text-xs font-semibold cursor-pointer transition inline-flex items-center gap-1.5 ${busyHere ? "pointer-events-none opacity-50" : ""}`}
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  {ownPages === 0 ? t("ctr.docs.takePhoto") : t("ctr.docs.takePhotoAnother")}
                </label>
                <label
                  htmlFor={inputId}
                  className={`px-3 py-1.5 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold cursor-pointer transition ${busyHere ? "pointer-events-none opacity-50" : ""}`}
                >
                  {busyHere
                    ? t("ctr.common.loading")
                    : inherited
                      ? t("ctr.docs.uploadForThis")
                      : ownPages === 0
                        ? t("ctr.docs.uploadFile")
                        : t("ctr.docs.addPageFromFile")}
                </label>
                {ownPages > 0 && (
                  <span className="text-[10px] text-slate-500">
                    {t("ctr.docs.pagesRatio", { n: ownPages, max: MAX_PAGES })}
                  </span>
                )}
              </div>
            ) : (
              <p className="mt-2 text-[11px] text-slate-500">
                {t("ctr.docs.maxReached", { max: MAX_PAGES })}
              </p>
            )}
          </div>
        );
      })}

      {/* --- Allegati aggiuntivi ------------------------------------------
          Everything the fixed slots don't cover: the back of an ID, a
          delega, a lease, a visura somebody was asked for by hand. Each
          one is labelled by whoever uploads it, which is why the label is
          asked for BEFORE the file picker opens rather than after. */}
      <div className="pt-1">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
          {t("ctr.docs.otherTitle")}
        </p>

        {extra.length === 0 && !addingExtra && (
          <p className="text-[11px] text-slate-500 mb-2">
            {t("ctr.docs.noExtra")}
          </p>
        )}

        <div className="space-y-2">
          {extra.map((doc) => (
            <div
              key={doc.id}
              className="p-3 rounded-xl bg-slate-900/5 border border-slate-200"
            >
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900">
                    {doc.description || typeLabel(doc.document_type)}
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    {doc.original_filename} ·{" "}
                    {t("ctr.docs.uploadedByOn", { name: doc.uploaded_by_name ?? "—", date: new Date(doc.created_at).toLocaleDateString(fmt.tag) })}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${statusColor(doc.status)}`}>
                    {statusLabel(doc.status)}
                  </span>
                  <button
                    onClick={() => setPreviewDoc(doc)}
                    className="px-2.5 py-1 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer"
                  >
                    {t("ctr.docs.show")}
                  </button>
                </div>
              </div>
              {doc.review_note && (
                <p className=" text-slate-500 mt-2">
                  <span className="font-semibold">{t("ctr.docs.adminNote")}</span> {doc.review_note}
                </p>
              )}
              {reviewControls(doc)}
            </div>
          ))}
        </div>

        {addingExtra ? (
          <div className="mt-2 p-3 rounded-xl bg-slate-900/5 border border-brand-500/20 space-y-2">
            <label className=" font-semibold text-slate-600 uppercase block">
              {t("ctr.docs.extraQuestion")}
            </label>
            <input
              autoFocus
              value={extraLabel}
              maxLength={MAX_DESCRIPTION_LENGTH}
              onChange={(e) => setExtraLabel(e.target.value)}
              placeholder={t("ctr.docs.extraPlaceholder")}
              className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-brand-500"
            />
            <p className="text-[10px] text-slate-500">
              {t("ctr.docs.extraHint")}
            </p>
            <input
              ref={extraFileInput}
              type="file"
              accept={ACCEPTED_CONTENT_TYPES}
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleExtraUpload(file);
                e.target.value = "";
              }}
            />
            <input
              ref={extraCameraInput}
              type="file"
              accept="image/jpeg,image/png"
              capture="environment"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleExtraUpload(file);
                e.target.value = "";
              }}
            />
            <div className="flex gap-2">
              <button
                onClick={() => extraFileInput.current?.click()}
                disabled={!canPickExtraFile || uploadingType === "OTHER"}
                className="px-3 py-1.5 rounded-lg bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-600 text-xs font-semibold transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {uploadingType === "OTHER" ? t("ctr.common.loading") : t("ctr.docs.chooseAndUpload")}
              </button>
              <button
                onClick={() => extraCameraInput.current?.click()}
                disabled={!canPickExtraFile || uploadingType === "OTHER"}
                className="px-3 py-1.5 rounded-lg bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 text-xs font-semibold transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {t("ctr.docs.shootPhoto")}
              </button>
              <button
                onClick={() => { setAddingExtra(false); setExtraLabel(""); }}
                className="px-3 py-1.5 rounded-lg bg-slate-900/5 hover:bg-slate-100 text-slate-400 text-xs font-semibold transition cursor-pointer"
              >
                {t("common.cancel")}
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setAddingExtra(true)}
            className="mt-2 w-full px-3 py-2.5 rounded-xl border border-dashed border-slate-300 text-slate-600 hover:border-brand-500/40 hover:text-brand-600 text-xs font-semibold transition cursor-pointer"
          >
            {t("ctr.docs.addAnother")}
          </button>
        )}
      </div>
      {previewDoc && (
        <DocumentPreviewModal
          key={previewDoc.id}
          title={previewDoc.description || t.dyn(`ctr.docs.type.${previewDoc.document_type}`, t("ctr.docs.document"))}
          filename={previewDoc.original_filename}
          contentType={previewDoc.content_type}
          loadUrl={() => fetchDocumentUrl(previewDoc.id, t("ctr.docs.openError"))}
          onClose={() => setPreviewDoc(null)}
        />
      )}
    </div>
  );
}
