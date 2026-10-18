"use client";

import { motion } from "motion/react";
import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { ChipScroller } from "@/components/ui/chip-scroller";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { CV_QUERY, DOCS_QUERY, DocumentStatusChip, SPORT_QUERY, Switch, useCvDocuments } from "@/components/club/coach-cv-common";
import { clubSend } from "@/lib/club";
import {
  CATEGORY_ICONS, CV, DOCUMENT_CATEGORIES, MAX_FILE_BYTES, formatBytes, openPresigned, type CvDocument,
} from "@/lib/coach-cv";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import type { Translator } from "@/lib/i18n/translate";

// L'archivio del treinador: diplomi, qualifiche federative, corsi, primo
// soccorso, titoli di studio, documenti personali. Ogni documento ha i suoi
// dati e, se vuole, il file (PDF o foto); quelli con «No CV» acceso entrano
// nelle certificazioni del curriculum.

const ACCEPTED = ["application/pdf", "image/jpeg", "image/png"];

export const categoryLabel = (t: Translator, code: string, fallback: string) => t.dyn(`cv.cat.${code}`, fallback);

/** Il controllo prima di caricare: il server dice lo stesso, ma dopo aver
 *  aspettato tutto l'upload dal telefono. */
function fileProblem(t: Translator, file: File): string | null {
  if (file.type && !ACCEPTED.includes(file.type)) return t("cv.docs.fileType");
  if (file.size > MAX_FILE_BYTES) return t("cv.docs.fileTooBig");
  return null;
}

function invalidate(qc: ReturnType<typeof useQueryClient>) {
  // Le certificazioni compaiono anche nel CV, e un documento può essere il
  // giustificativo di un evento del Curriculum Desportivo.
  return Promise.all([
    qc.invalidateQueries({ queryKey: DOCS_QUERY }),
    qc.invalidateQueries({ queryKey: CV_QUERY }),
    qc.invalidateQueries({ queryKey: SPORT_QUERY }),
  ]);
}

export function CvDocuments() {
  const { t } = useI18n();
  const { data, isLoading, error } = useCvDocuments();
  const [filter, setFilter] = useState<string>("ALL");
  const [editing, setEditing] = useState<CvDocument | "new" | null>(null);
  if (isLoading) return <div className="space-y-3"><Skeleton className="h-14" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div>;
  if (error || !data) return <EmptyState icon={<span className="text-3xl">🗂️</span>} title={t("cv.loadFailed")} text={error?.message} />;

  const counts = new Map<string, number>();
  for (const d of data) counts.set(d.category, (counts.get(d.category) ?? 0) + 1);
  const expired = data.filter((d) => d.status === "EXPIRED").length;
  const expiring = data.filter((d) => d.status === "EXPIRING").length;
  const visible = filter === "ALL" ? data : data.filter((d) => d.category === filter);
  // Raggruppati nell'ordine delle categorie (prima i diplomi da treinador).
  const groups = DOCUMENT_CATEGORIES.map((c) => ({ code: c, items: visible.filter((d) => d.category === c) }))
    .filter((g) => g.items.length > 0);
  const chip = (active: boolean) => cn("shrink-0 cursor-pointer rounded-full px-3.5 py-1.5 text-sm font-semibold ring-1 transition",
    active ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-ink-700 ring-ink-200 hover:ring-brand-300");

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-ink-500">{t("cv.docs.intro")}</p>
        <Button onClick={() => setEditing("new")} className="shrink-0" icon={<span aria-hidden="true">＋</span>}>{t("cv.docs.add")}</Button>
      </div>

      {(expired > 0 || expiring > 0) && (
        <div className="flex items-start gap-3 rounded-3xl bg-amber-50 p-4 text-sm text-amber-900 ring-1 ring-amber-200">
          <span className="text-xl" aria-hidden="true">⏰</span>
          <p>
            {expired > 0 && <strong className="font-semibold">{t("cv.docs.expiredCount", { n: expired })}</strong>}
            {expired > 0 && expiring > 0 && " · "}
            {expiring > 0 && <span>{t("cv.docs.expiringCount", { n: expiring })}</span>}
            <span className="block text-xs text-amber-800">{t("cv.docs.renewHint")}</span>
          </p>
        </div>
      )}

      {data.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🎓</span>} title={t("cv.docs.empty")} text={t("cv.docs.emptyText")}
          action={<Button onClick={() => setEditing("new")}>{t("cv.docs.addFirst")}</Button>} />
      ) : (
        <>
          <ChipScroller label={t("cv.docs.category")}>
            <button type="button" aria-pressed={filter === "ALL"} onClick={() => setFilter("ALL")} className={chip(filter === "ALL")}>
              {t("cv.docs.all")} <span className="opacity-70">{data.length}</span>
            </button>
            {DOCUMENT_CATEGORIES.filter((c) => counts.has(c)).map((c) => (
              <button key={c} type="button" aria-pressed={filter === c} onClick={() => setFilter(c)} className={chip(filter === c)}>
                <span aria-hidden="true">{CATEGORY_ICONS[c]}</span> {categoryLabel(t, c, c)} <span className="opacity-70">{counts.get(c)}</span>
              </button>
            ))}
          </ChipScroller>
          <div className="space-y-6">
            {groups.map((g) => (
              <section key={g.code}>
                <h3 className="mb-2 flex items-center gap-2 px-1 text-sm font-bold uppercase tracking-wider text-ink-500">
                  <span aria-hidden="true">{CATEGORY_ICONS[g.code]}</span>{categoryLabel(t, g.code, g.items[0]!.category_label)}
                </h3>
                <ul className="grid gap-3 lg:grid-cols-2">
                  {g.items.map((d, i) => (
                    <motion.li key={d.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }}>
                      <DocumentCard doc={d} onEdit={() => setEditing(d)} />
                    </motion.li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </>
      )}
      {editing && <DocumentModal doc={editing === "new" ? null : editing} defaultCategory={filter === "ALL" ? undefined : filter}
        onClose={() => setEditing(null)} />}
    </div>
  );
}

function DocumentCard({ doc, onEdit }: { doc: CvDocument; onEdit: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const replaceInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"cv" | "file" | "delete" | null>(null);

  async function open() {
    try {
      await openPresigned(CV(`/documents/${doc.id}/url`));
    } catch (e) {
      toast({ tone: "error", title: t("cv.docs.openFailed"), text: (e as Error).message });
    }
  }

  async function toggleCv(value: boolean) {
    setBusy("cv");
    try {
      await clubSend(CV(`/documents/${doc.id}`), "PATCH", { show_in_cv: value });
      await invalidate(qc);
    } catch (e) {
      toast({ tone: "error", title: t("cv.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function replace(file: File) {
    const problem = fileProblem(t, file);
    if (problem) {
      toast({ tone: "error", title: problem });
      return;
    }
    setBusy("file");
    try {
      const form = new FormData();
      form.append("file", file);
      await clubSend(CV(`/documents/${doc.id}/file`), "PUT", form);
      await invalidate(qc);
      toast({ tone: "success", title: t("cv.docs.fileReplaced") });
    } catch (e) {
      toast({ tone: "error", title: t("cv.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    if (!window.confirm(t("cv.docs.deleteConfirm", { title: doc.title }))) return;
    setBusy("delete");
    try {
      await clubSend(CV(`/documents/${doc.id}`), "DELETE");
      await invalidate(qc);
      toast({ tone: "success", title: t("cv.docs.deleted") });
    } catch (e) {
      toast({ tone: "error", title: t("cv.failed"), text: (e as Error).message });
      setBusy(null);
    }
  }

  const dates = [
    doc.issued_on ? t("cv.docs.issuedOn", { date: fmt.shortDate(doc.issued_on) }) : null,
    doc.expires_on ? t("cv.docs.expiresOn", { date: fmt.shortDate(doc.expires_on) }) : null,
  ].filter(Boolean).join(" · ");
  return (
    <article className={cn("h-full rounded-3xl bg-white p-4 shadow-soft ring-1",
      doc.status === "EXPIRED" ? "ring-rose-200" : doc.status === "EXPIRING" ? "ring-amber-200" : "ring-ink-900/5")}>
      <div className="flex items-start gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-100 to-accent-300 text-xl shadow-sm" aria-hidden="true">
          {CATEGORY_ICONS[doc.category] ?? "📄"}
        </span>
        <div className="min-w-0 flex-1">
          <h4 className="text-base leading-snug text-ink-900">{doc.title}</h4>
          {doc.issuer && <p className="truncate text-sm text-ink-600">{doc.issuer}</p>}
          {dates && <p className="text-xs text-ink-500">{dates}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <DocumentStatusChip doc={doc} />
            {doc.has_file
              ? <span className="text-xs text-ink-500">📎 {formatBytes(doc.size_bytes)}</span>
              : <span className="text-xs text-ink-400">{t("cv.docs.noFile")}</span>}
          </div>
        </div>
      </div>
      {doc.description && <p className="mt-2 line-clamp-3 whitespace-pre-line text-sm text-ink-600">{doc.description}</p>}
      <div className="mt-3 rounded-2xl bg-ink-50/70 px-3 py-1">
        <Switch checked={doc.show_in_cv} disabled={busy === "cv"} onChange={(v) => void toggleCv(v)}
          label={t("cv.docs.inCv")} hint={t("cv.docs.inCvHint")} />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {doc.has_file && <Button size="sm" variant="secondary" onClick={() => void open()}>👁️ {t("cv.docs.open")}</Button>}
        <Button size="sm" variant="ghost" onClick={onEdit}>✎ {t("cv.edit")}</Button>
        <Button size="sm" variant="ghost" loading={busy === "file"} onClick={() => replaceInput.current?.click()}>
          📎 {doc.has_file ? t("cv.docs.replaceFile") : t("cv.docs.addFile")}
        </Button>
        <Button size="sm" variant="ghost" className="ml-auto text-rose-600" loading={busy === "delete"} onClick={() => void remove()}>
          {t("cv.delete")}
        </Button>
        <input ref={replaceInput} type="file" accept="image/*,application/pdf" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void replace(f); }} />
      </div>
    </article>
  );
}

/** Aggiungere o correggere un documento. Il file è facoltativo: un diploma
 *  si può registrare anche solo con i dati, e la scansione arrivare dopo. */
function DocumentModal({ doc, defaultCategory, onClose }: { doc: CvDocument | null; defaultCategory?: string; onClose: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const [title, setTitle] = useState(doc?.title ?? "");
  const [category, setCategory] = useState<string>(doc?.category ?? defaultCategory ?? "COACH_DIPLOMA");
  const [issuer, setIssuer] = useState(doc?.issuer ?? "");
  const [issuedOn, setIssuedOn] = useState(doc?.issued_on ?? "");
  const [expiresOn, setExpiresOn] = useState(doc?.expires_on ?? "");
  const [description, setDescription] = useState(doc?.description ?? "");
  const [showInCv, setShowInCv] = useState(doc?.show_in_cv ?? category !== "PERSONAL");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const datesWrong = !!issuedOn && !!expiresOn && expiresOn < issuedOn;

  function pick(f: File | undefined) {
    if (!f) return;
    const problem = fileProblem(t, f);
    setError(problem);
    setFile(problem ? null : f);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (doc) {
        await clubSend(CV(`/documents/${doc.id}`), "PATCH", {
          title: title.trim(), category, issuer: issuer.trim() || null, issued_on: issuedOn || null,
          expires_on: expiresOn || null, description: description.trim() || null, show_in_cv: showInCv,
        });
        if (file) {
          const form = new FormData();
          form.append("file", file);
          await clubSend(CV(`/documents/${doc.id}/file`), "PUT", form);
        }
      } else {
        // Multipart: i campi vuoti non si mandano (una data "" non è una data).
        const form = new FormData();
        form.append("title", title.trim());
        form.append("category", category);
        if (issuer.trim()) form.append("issuer", issuer.trim());
        if (issuedOn) form.append("issued_on", issuedOn);
        if (expiresOn) form.append("expires_on", expiresOn);
        if (description.trim()) form.append("description", description.trim());
        form.append("show_in_cv", showInCv ? "true" : "false");
        if (file) form.append("file", file);
        await clubSend(CV("/documents"), "POST", form);
      }
      await invalidate(qc);
      toast({ tone: "success", title: t("cv.docs.saved") });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} size="lg" title={doc ? t("cv.docs.editTitle") : t("cv.docs.newTitle")} subtitle={t("cv.docs.formHint")}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button onClick={() => void save()} loading={busy} disabled={!title.trim() || datesWrong}>{t("common.save")}</Button>
      </>}>
      <div className="space-y-4">
        <Field label={t("cv.docs.title")}>
          <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={t("cv.docs.titlePlaceholder")} autoFocus />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("cv.docs.category")}>
            <Select value={category} onChange={(e) => setCategory(e.target.value)}>
              {DOCUMENT_CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_ICONS[c]} {categoryLabel(t, c, c)}</option>)}
            </Select>
          </Field>
          <Field label={t("cv.docs.issuer")}>
            <Input value={issuer} maxLength={200} onChange={(e) => setIssuer(e.target.value)} placeholder={t("cv.docs.issuerPlaceholder")} />
          </Field>
          <Field label={t("cv.docs.issued")}>
            <Input type="date" value={issuedOn} onChange={(e) => setIssuedOn(e.target.value)} />
          </Field>
          <Field label={t("cv.docs.expires")} hint={datesWrong ? undefined : t("cv.docs.expiresHint")} error={datesWrong ? t("cv.docs.datesWrong") : undefined}>
            <Input type="date" value={expiresOn} onChange={(e) => setExpiresOn(e.target.value)} />
          </Field>
        </div>
        <Field label={t("cv.docs.description")} hint={t("common.optional")}>
          <Textarea rows={3} value={description} maxLength={2000} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="rounded-2xl bg-ink-50/70 px-3 py-1">
          <Switch checked={showInCv} onChange={setShowInCv} label={t("cv.docs.inCv")} hint={t("cv.docs.inCvHint")} />
        </div>
        <Field label={doc?.has_file ? t("cv.docs.replaceFile") : t("cv.docs.file")} hint={t("cv.docs.fileHint")}>
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-xl border border-ink-200 bg-white px-4 text-sm font-semibold text-ink-900 shadow-soft hover:border-brand-300">
              📎 {t("cv.docs.chooseFile")}
              <input type="file" accept="image/*,application/pdf" className="sr-only" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
            {/* Sul telefono, la fotocamera direttamente: il diploma si fotografa. */}
            <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-xl border border-ink-200 bg-white px-4 text-sm font-semibold text-ink-900 shadow-soft hover:border-brand-300 sm:hidden">
              📷 {t("cv.docs.takePhoto")}
              <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
            {file && (
              <span className="inline-flex min-w-0 items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-200">
                <span className="truncate">✓ {file.name}</span>
                <button type="button" onClick={() => setFile(null)} className="cursor-pointer" aria-label={t("cv.docs.removeFile")}>✕</button>
              </span>
            )}
            {!file && doc?.has_file && <span className="truncate text-xs text-ink-500">📎 {doc.original_filename}</span>}
          </div>
        </Field>
        {error && <p className="rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-200">{error}</p>}
      </div>
    </Modal>
  );
}
