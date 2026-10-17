"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { CollaborationDocumentViewer } from "@/components/collaboration-document-viewer";
import { friendlyApiError } from "@/lib/api-error";
import type { AgentProfileRead, CollaborationDocumentRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

async function fetchMyApplication(): Promise<AgentProfileRead | null> {
  const res = await fetch("/api/proxy/network/agents/me");
  if (!res.ok) throw new Error("Impossibile caricare lo stato della richiesta.");
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

interface CustomerPromoterApplicationCardProps {
  /** When true, renders nothing at all once the caller is an ACTIVE promoter
   * -- used on the customer home page, where the point of the card is only to
   * invite; once accepted, the always-visible area switcher (app-shell.tsx)
   * takes over as the way to reach the promoter dashboard. The dedicated
   * "Lavora con noi" tab keeps hideWhenActive unset, so it still shows a
   * confirmation there. */
  hideWhenActive?: boolean;
}

/** The legal text is NOT here. It is served by the backend
    (GET /network/agents/apply/documents) so there is exactly one copy of what
    people sign, it carries a version that gets recorded with the acceptance,
    and updating it needs no frontend release. This used to be a one-paragraph
    summary hardcoded in this file -- which meant the app showed a text that
    was not the contract. */
async function fetchCollaborationDocuments(): Promise<CollaborationDocumentRead[]> {
  const res = await fetch("/api/proxy/network/agents/apply/documents");
  if (!res.ok) throw new Error("Impossibile caricare il contratto di collaborazione.");
  return res.json();
}

export function CustomerPromoterApplicationCard({ hideWhenActive = false }: CustomerPromoterApplicationCardProps = {}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { data: application, isLoading } = useQuery({
    queryKey: ["customer", "promoter-application"],
    queryFn: fetchMyApplication,
  });
  const [modalOpen, setModalOpen] = useState(false);
  // One acceptance per document, keyed by document key -- the modal cannot be
  // submitted until every document the backend returned has been ticked, and
  // the backend independently refuses an application that is missing one.
  const [accepted, setAccepted] = useState<Record<string, boolean>>({});
  const { data: documents, error: documentsError } = useQuery({
    queryKey: ["promoter-application", "documents"],
    queryFn: fetchCollaborationDocuments,
    enabled: modalOpen,
  });
  const [otpRequested, setOtpRequested] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function openModal() {
    setAccepted({});
    setOtpRequested(false);
    setOtpCode("");
    setError(null);
    setModalOpen(true);
  }

  async function handleRequestOtp() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/network/agents/apply/request-otp", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res, t("net.apply.err.otp")));
      setOtpRequested(true);
    } catch (err: any) {
      setError(err.message || t("net.apply.err.otp"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApply() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/network/agents/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          accept_contract: true,
          // The version of each text actually shown on screen, echoed back:
          // that is what gets recorded, so "accepted" means a specific
          // wording, not just a ticked box. A stale version (the page was
          // open while the contract changed) is refused by the backend.
          accepted_documents: Object.fromEntries((documents ?? []).map((d) => [d.key, d.version])),
          otp_code: otpCode,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res, t("net.apply.err.apply")));
      await queryClient.invalidateQueries({ queryKey: ["customer", "promoter-application"] });
      // The access token's own baked-in roles won't show PROMOTER until the
      // next silent refresh -- nudge the area switcher (app-shell.tsx) to
      // re-check live roles right away instead of waiting for that.
      await queryClient.invalidateQueries({ queryKey: ["auth", "me", "roles"] });
      setModalOpen(false);
    } catch (err: any) {
      setError(err.message || t("net.apply.err.apply"));
    } finally {
      setSubmitting(false);
    }
  }

  // Derived, never stored: "all accepted" must follow from the documents the
  // backend actually returned, so a newly added document cannot be skipped by
  // a stale flag.
  const allAccepted = !!documents && documents.length > 0 && documents.every((d) => accepted[d.key]);

  if (isLoading) {
    return <div className="glass-card rounded-2xl p-6 border-slate-200 animate-pulse h-40" />;
  }

  if (application?.status === "ACTIVE") {
    if (hideWhenActive) return null;
    return (
      <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
        <h3 className="text-lg font-semibold text-slate-900">{t("net.apply.active.title")}</h3>
        <p className="text-sm text-slate-500 mt-2">
          {t("net.apply.active.body")}
        </p>
        <Link
          href="/promoter"
          className="inline-block mt-4 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-sm font-semibold cursor-pointer"
        >
          {t("net.apply.active.cta")}
        </Link>
      </div>
    );
  }

  if (application?.status === "PENDING_APPROVAL") {
    return (
      <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
        <h3 className="text-lg font-semibold text-slate-900">{t("net.apply.title")}</h3>
        <span className="inline-block mt-3 px-3 py-1 rounded-full text-xs font-bold border bg-amber-500/10 text-amber-700 border-amber-500/20">
          {t("net.apply.pending.badge")}
        </span>
        <p className="text-sm text-slate-500 mt-3">
          {t("net.apply.pending.body")}
        </p>
      </div>
    );
  }

  // Blacklisted: only ever true on a row that already exists (TERMINATED +
  // is_blacklisted, set by an admin -- see network/router.py update_agent).
  // Deliberately does NOT call handleApply -- re-applying while blacklisted
  // would just land in PENDING_APPROVAL server-side anyway (network/service.py
  // apply_as_promoter), but showing that as a normal "in attesa" state here
  // would hide the real reason from someone who has no idea they're blocked.
  if (application?.is_blacklisted) {
    return (
      <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
        <h3 className="text-lg font-semibold text-slate-900">{t("net.apply.title")}</h3>
        <div className="flex gap-3 p-4 mt-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-sm">
          <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <span className="font-semibold block">{t("net.apply.blocked.title")}</span>
            <span className="text-xs text-rose-300/90 block mt-1">
              {t("net.apply.blocked.body")}
            </span>
          </div>
        </div>
        <button
          disabled
          title={t("net.apply.blocked.tooltip")}
          className="mt-4 px-4 py-2 rounded-lg bg-slate-600/30 text-slate-400 text-sm font-semibold cursor-not-allowed opacity-60"
        >
          {t("net.apply.title")}
        </button>
      </div>
    );
  }

  // No application yet, or a previous one that's TERMINATED (rejected, or
  // deactivated by an admin) and not blacklisted -- free to (re)try, always
  // auto-activates immediately (network/service.py apply_as_promoter).
  return (
    <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
      <h3 className="text-lg font-semibold text-slate-900">{t("net.apply.title")}</h3>
      <p className="text-sm text-slate-500 mt-2">
        {t("net.apply.intro")}
      </p>
      {application?.status === "TERMINATED" && application.rejection_reason && (
        <p className="text-xs text-slate-500 mt-2">{t("net.apply.lastNote", { reason: application.rejection_reason })}</p>
      )}
      <button
        onClick={openModal}
        className="mt-4 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-sm font-semibold cursor-pointer"
      >
        {t("net.apply.title")}
      </button>

      {modalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm px-4 py-8 overflow-y-auto">
          <div className="w-full max-w-2xl glass-card rounded-2xl p-6 my-auto animate-scale-up">
            <h3 className="text-base font-semibold text-slate-900">{t("net.apply.modal.title")}</h3>
            <p className="text-xs text-slate-500 mt-1 mb-4">
              {t("net.apply.modal.hint")}
            </p>

            {documentsError && (
              <p className="text-xs text-rose-400 mb-3">{t("net.apply.modal.docsError")}</p>
            )}
            {!documents && !documentsError && (
              <div className="h-40 rounded-xl bg-slate-900/5 animate-pulse mb-4" />
            )}

            <div className="space-y-5 mb-5">
              {(documents ?? []).map((doc) => (
                <div key={doc.key}>
                  <CollaborationDocumentViewer document={doc} />
                  <label className="flex items-start gap-2.5 text-xs text-slate-600 cursor-pointer mt-2.5">
                    <input
                      type="checkbox"
                      checked={!!accepted[doc.key]}
                      onChange={(e) => setAccepted((prev) => ({ ...prev, [doc.key]: e.target.checked }))}
                      className="mt-0.5 w-4 h-4 rounded border-slate-200 accent-brand-500 shrink-0"
                    />
                    <span>{doc.acceptance_label}</span>
                  </label>
                </div>
              ))}
            </div>

            {!otpRequested ? (
              <button
                onClick={handleRequestOtp}
                disabled={!allAccepted || submitting}
                className="w-full rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 py-2.5 text-sm font-semibold text-white shadow-lg transition duration-300 disabled:opacity-50 cursor-pointer"
              >
                {submitting ? t("net.apply.otp.sending") : t("net.apply.otp.send")}
              </button>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-slate-500">
                  {t("net.apply.otp.sent")}
                </p>
                <input
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder={t("net.apply.otp.placeholder")}
                  inputMode="numeric"
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm text-center tracking-[0.3em] font-mono focus:border-brand-500"
                />
                <button
                  onClick={handleApply}
                  disabled={otpCode.length !== 6 || submitting}
                  className="w-full rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 py-2.5 text-sm font-semibold text-white shadow-lg transition duration-300 disabled:opacity-50 cursor-pointer"
                >
                  {submitting ? t("net.apply.confirming") : t("net.apply.confirm")}
                </button>
                <button
                  onClick={handleRequestOtp}
                  disabled={submitting}
                  className="w-full text-xs text-brand-600 hover:text-brand-600 transition cursor-pointer disabled:opacity-50"
                >
                  {t("net.apply.otp.resend")}
                </button>
              </div>
            )}

            {error && <p className="text-xs text-rose-400 mt-3">{error}</p>}

            <button
              onClick={() => setModalOpen(false)}
              className="w-full mt-3 text-xs text-slate-500 hover:text-slate-300 transition cursor-pointer"
            >
              {t("common.cancel")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
