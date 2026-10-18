"use client";

import { motion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend } from "@/lib/club";
import {
  CV, CV_KEY, fetchCvPdf, formatBytes, openPresigned, saveBlob,
  type CvDocument, type CvExport, type CvResponse, type PdfKind, type SportHistory,
} from "@/lib/coach-cv";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// I pezzi comuni alle tre schede del curriculum (coach-cv.tsx): le query, la
// scheda bianca delle sezioni, lo stato di un documento, i bottoni del PDF
// (anteprima, download, versione salvata) e l'elenco delle versioni.

export const CV_QUERY = [...CV_KEY, "cv"];
export const DOCS_QUERY = [...CV_KEY, "documents"];
export const SPORT_QUERY = [...CV_KEY, "sport"];
export const EXPORTS_QUERY = [...CV_KEY, "exports"];

export function useCv() {
  return useQuery({ queryKey: CV_QUERY, queryFn: () => clubGet<CvResponse>(CV()), staleTime: 60_000 });
}

export function useCvDocuments() {
  return useQuery({ queryKey: DOCS_QUERY, queryFn: () => clubGet<CvDocument[]>(CV("/documents")), staleTime: 60_000 });
}

export function useSport() {
  return useQuery({ queryKey: SPORT_QUERY, queryFn: () => clubGet<SportHistory>(CV("/sport")), staleTime: 60_000 });
}

/** La scheda bianca di una sezione, come nell'Início del treinador. */
export function CvCard({ title, icon, hint, action, className, children }: {
  title: ReactNode; icon: string; hint?: ReactNode; action?: ReactNode; className?: string; children: ReactNode;
}) {
  return (
    <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className={cn("rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5 sm:p-5", className)}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-base text-ink-900"><span aria-hidden="true">{icon}</span>{title}</h3>
          {hint && <p className="mt-0.5 text-xs text-ink-500">{hint}</p>}
        </div>
        {action}
      </div>
      {children}
    </motion.section>
  );
}

const STATUS_TONE: Record<string, Tone> = { VALID: "success", EXPIRING: "warning", EXPIRED: "danger" };

/** Válido / a expirar / expirado, con la data quando c'è una scadenza. */
export function DocumentStatusChip({ doc }: { doc: Pick<CvDocument, "status" | "expires_on"> }) {
  const { t, fmt } = useI18n();
  const date = fmt.shortDate(doc.expires_on);
  const label = doc.status === "EXPIRED" ? t("cv.status.expired", { date })
    : doc.status === "EXPIRING" ? t("cv.status.expiring", { date })
      : doc.expires_on ? t("cv.status.validUntil", { date }) : t("cv.status.valid");
  return <Badge tone={STATUS_TONE[doc.status] ?? "neutral"} dot>{label}</Badge>;
}

/** «Declarado»: una voce scritta dal treinador, non verificata dal club. */
export function DeclaredBadge() {
  const { t } = useI18n();
  return <span title={t("cv.sport.declaredHint")}><Badge tone="accent">✍️ {t("cv.sport.declared")}</Badge></span>;
}

/** I bottoni del PDF di un curriculum. `beforeAction` (il CV) salva prima le
 *  modifiche: il PDF si costruisce da quello che è salvato, e risponde false
 *  se il salvataggio non è riuscito. */
export function PdfActions({ kind, beforeAction, className }: {
  kind: PdfKind; beforeAction?: () => Promise<boolean>; className?: string;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState<"preview" | "download" | null>(null);
  const [preview, setPreview] = useState<{ url: string; filename: string } | null>(null);
  const [saving, setSaving] = useState(false);
  // L'URL in memoria va liberato anche se la scheda si chiude con l'anteprima aperta.
  const live = useRef<string | null>(null);
  useEffect(() => () => { if (live.current) URL.revokeObjectURL(live.current); }, []);

  async function run(what: "preview" | "download") {
    if (beforeAction && !(await beforeAction())) return;
    setBusy(what);
    try {
      const { blob, filename } = await fetchCvPdf(kind);
      if (what === "download") {
        saveBlob(blob, filename);
      } else {
        const url = URL.createObjectURL(blob);
        live.current = url;
        setPreview({ url, filename });
      }
    } catch (e) {
      toast({ tone: "error", title: t("cv.pdf.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  function closePreview() {
    if (preview) URL.revokeObjectURL(preview.url);
    live.current = null;
    setPreview(null);
  }

  async function openSave() {
    if (beforeAction && !(await beforeAction())) return;
    setSaving(true);
  }

  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      <Button variant="dark" onClick={() => void run("preview")} loading={busy === "preview"} disabled={busy !== null}
        icon={<span aria-hidden="true">👁️</span>}>{t("cv.pdf.preview")}</Button>
      <Button variant="secondary" onClick={() => void run("download")} loading={busy === "download"} disabled={busy !== null}
        icon={<span aria-hidden="true">⬇️</span>}>{t("cv.pdf.download")}</Button>
      <Button variant="ghost" onClick={() => void openSave()} icon={<span aria-hidden="true">🗂️</span>}>{t("cv.pdf.saveVersion")}</Button>

      <Modal open={!!preview} onClose={closePreview} size="xl" title={kind === "CV" ? t("cv.pdf.previewCv") : t("cv.pdf.previewSport")}
        subtitle={t("cv.pdf.previewHint")}
        footer={preview && <>
          <a href={preview.url} target="_blank" rel="noopener" className="inline-flex h-10 items-center rounded-xl px-4 text-sm font-semibold text-ink-700 hover:bg-ink-100">
            ↗ {t("cv.pdf.openTab")}
          </a>
          <a href={preview.url} download={preview.filename} className="inline-flex h-10 items-center gap-2 rounded-xl bg-gradient-to-b from-brand-500 to-brand-600 px-4 text-sm font-semibold text-white shadow-brand">
            ⬇️ {t("cv.pdf.download")}
          </a>
        </>}>
        {preview && (
          <iframe src={preview.url} title={preview.filename} className="h-[65vh] w-full rounded-2xl bg-ink-50 ring-1 ring-ink-100 sm:h-[72vh]" />
        )}
      </Modal>
      {saving && <SaveVersionModal kind={kind} onClose={() => setSaving(false)} />}
    </div>
  );
}

function SaveVersionModal({ kind, onClose }: { kind: PdfKind; onClose: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await clubSend(CV("/exports"), "POST", { kind, note: note.trim() || null });
      await qc.invalidateQueries({ queryKey: EXPORTS_QUERY });
      toast({ tone: "success", title: t("cv.versions.saved") });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} size="sm" title={t("cv.versions.saveTitle")} subtitle={t("cv.versions.saveHint")}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button onClick={() => void save()} loading={busy}>{t("cv.pdf.saveVersion")}</Button>
      </>}>
      <div className="space-y-3">
        <Field label={t("cv.versions.note")} hint={t("common.optional")}>
          <Input value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} placeholder={t("cv.versions.notePlaceholder")} />
        </Field>
        {error && <p className="rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-200">{error}</p>}
      </div>
    </Modal>
  );
}

/** Le versioni PDF salvate, dei due curriculum. */
export function SavedVersions() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: EXPORTS_QUERY, queryFn: () => clubGet<CvExport[]>(CV("/exports")) });
  const [busy, setBusy] = useState<string | null>(null);

  async function download(row: CvExport) {
    try {
      await openPresigned(CV(`/exports/${row.id}/url`));
    } catch (e) {
      toast({ tone: "error", title: t("cv.pdf.failed"), text: (e as Error).message });
    }
  }

  async function remove(row: CvExport) {
    if (!window.confirm(t("cv.versions.deleteConfirm", { name: row.filename }))) return;
    setBusy(row.id);
    try {
      await clubSend(CV(`/exports/${row.id}`), "DELETE");
      await qc.invalidateQueries({ queryKey: EXPORTS_QUERY });
      toast({ tone: "success", title: t("cv.versions.deleted") });
    } catch (e) {
      toast({ tone: "error", title: t("cv.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <CvCard icon="🗂️" title={t("cv.versions.title")} hint={t("cv.versions.hint")}>
      {isLoading ? <Skeleton className="h-20" /> : !data?.length ? (
        <p className="text-sm text-ink-500">{t("cv.versions.empty")}</p>
      ) : (
        <ul className="divide-y divide-ink-100">
          {data.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-2.5">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-ink-50 text-lg ring-1 ring-ink-100" aria-hidden="true">
                {row.kind === "CV" ? "📄" : "🏅"}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-1.5">
                  <Badge tone={row.kind === "CV" ? "brand" : "accent"}>{row.kind === "CV" ? t("cv.tabs.cv") : t("cv.tabs.sport")}</Badge>
                  <span className="text-sm font-semibold text-ink-900">{fmt.shortDate(row.created_at)}</span>
                </span>
                <span className="block truncate text-xs text-ink-500">{row.note ? `${row.note} · ` : ""}{formatBytes(row.size_bytes)}</span>
              </span>
              <span className="flex gap-1">
                <Button size="sm" variant="secondary" onClick={() => void download(row)}>⬇️ {t("cv.pdf.download")}</Button>
                <Button size="sm" variant="ghost" className="text-rose-600" loading={busy === row.id} onClick={() => void remove(row)}
                  aria-label={t("cv.delete")}>🗑️</Button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </CvCard>
  );
}

/** Un interruttore grande da telefono, con l'etichetta accanto. */
export function Switch({ checked, onChange, label, hint, disabled }: {
  checked: boolean; onChange: (v: boolean) => void; label: ReactNode; hint?: ReactNode; disabled?: boolean;
}) {
  return (
    <label className={cn("flex cursor-pointer items-center justify-between gap-3 rounded-2xl px-1 py-1.5", disabled && "cursor-not-allowed opacity-60")}>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-ink-800">{label}</span>
        {hint && <span className="block text-xs text-ink-500">{hint}</span>}
      </span>
      <span className="relative inline-flex shrink-0">
        <input type="checkbox" role="switch" className="peer sr-only" checked={checked} disabled={disabled}
          onChange={(e) => onChange(e.target.checked)} />
        <span className="h-7 w-12 rounded-full bg-ink-200 transition-colors peer-checked:bg-emerald-500 peer-focus-visible:ring-2 peer-focus-visible:ring-brand-400 peer-focus-visible:ring-offset-2" />
        <span className="absolute left-1 top-1 h-5 w-5 rounded-full bg-white shadow transition-transform peer-checked:translate-x-5" />
      </span>
    </label>
  );
}
