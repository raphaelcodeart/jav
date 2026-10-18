"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Textarea } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { UsageCard } from "@/components/javbot/usage-card";
import { friendlyApiError } from "@/lib/api-error";
import type { MessageKey } from "@/lib/i18n/messages/it";
import { useI18n } from "@/lib/i18n/provider";

// La base di conoscenza di JAVBOT (apps/api/app/domains/javbot/knowledge.py):
// i PDF che l'assistente dell'area riservata consulta e le istruzioni su come
// deve rispondere. La segreteria lavora sul suo club (/club/admin/javbot: il
// club lo decide l'API) e vede, senza toccarli, i documenti comuni; la console
// di JudoArteVida lavora sulla base comune a tutti i club (/javbot/admin).
//
// Non tutti i documenti li carica qualcuno: il regolamento di un evento
// (EVENT) entra da solo quando la segreteria lo allega alla prova, e le
// «fichas» del club (DATA: orari, prezzi, corsi) le scrive il gestionale
// (javbot/rag.py). Quelli si cambiano dove nascono, non da qui.

interface KnowledgeDocument {
  id: string;
  title: string;
  filename: string;
  size_bytes: number;
  page_count: number;
  status: "READY" | "EMPTY";
  common: boolean;
  created_at: string;
  source?: "UPLOAD" | "EVENT" | "DATA" | string;
  source_ref?: string | null;
  has_file?: boolean;
}

interface Knowledge {
  documents: KnowledgeDocument[];
  common_documents: KnowledgeDocument[];
  instructions: string;
  common_instructions: string;
  assistant_enabled: boolean;
  provider?: "openai" | "anthropic" | string | null;
  model?: string | null;
}

const MAX_INSTRUCTIONS = 8000;

const SOURCES: Record<string, { icon: string; label: MessageKey; tone: "neutral" | "info" | "accent" }> = {
  UPLOAD: { icon: "📄", label: "jbx.src.UPLOAD", tone: "neutral" },
  EVENT: { icon: "🏆", label: "jbx.src.EVENT", tone: "info" },
  DATA: { icon: "🗂️", label: "jbx.src.DATA", tone: "accent" },
};

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.status === 204 ? (undefined as T) : res.json();
}

export function KnowledgePanel({ mode }: { mode: "club" | "platform" }) {
  const { t } = useI18n();
  const base = mode === "club" ? "/api/proxy/club/admin/javbot/knowledge" : "/api/proxy/javbot/admin/knowledge";
  const queryKey = mode === "club" ? ["club", "javbot", "knowledge"] : ["javbot", "knowledge"];
  const { data, isLoading, error } = useQuery({ queryKey, queryFn: () => call<Knowledge>(base) });

  if (isLoading) return <Skeleton className="h-64" />;
  if (error || !data) return <EmptyState icon={<span className="text-3xl">🤖</span>} title={t("kb.loadError")} text={(error as Error)?.message} />;

  return (
    <div className="space-y-6">
      {!data.assistant_enabled && (
        <Card className="border-l-4 border-l-accent-400">
          <p className="text-sm font-semibold text-ink-900">{t("kb.offTitle")}</p>
          <p className="mt-1 text-sm text-ink-600">{t("kb.offText")}</p>
        </Card>
      )}
      <Instructions key={data.instructions} base={base} queryKey={queryKey} mode={mode} initial={data.instructions} common={data.common_instructions} />
      <UsageCard mode={mode} provider={data.provider ?? null} model={data.model ?? null} />
      <Documents base={base} queryKey={queryKey} mode={mode} documents={data.documents} />
      {mode === "club" && data.common_documents.length > 0 && (
        <Card>
          <CardHeader icon={<span aria-hidden="true">🌍</span>} title={t("kb.commonDocs")} subtitle={t("kb.commonDocsText")} />
          <DocumentList base={base} documents={data.common_documents} readOnly />
        </Card>
      )}
    </div>
  );
}

function Instructions({ base, queryKey, mode, initial, common }: {
  base: string; queryKey: string[]; mode: "club" | "platform"; initial: string; common: string;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  // Il componente si rimonta quando il server cambia il testo (key in KnowledgePanel):
  // la bozza parte sempre da ciò che è salvato, senza un effetto che la sincronizzi.
  const [draft, setDraft] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [showCommon, setShowCommon] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const saved = await call<Knowledge>(`${base}/instructions`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: draft }),
      });
      queryClient.setQueryData(queryKey, saved);
      toast({ tone: "success", title: t("kb.saved") });
    } catch (e) {
      toast({ tone: "error", title: t("kb.saveError"), text: (e as Error).message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader
        icon={<span aria-hidden="true">✍️</span>}
        title={mode === "club" ? t("kb.clubPrompt") : t("kb.commonPrompt")}
        subtitle={mode === "club" ? t("kb.clubPromptText") : t("kb.commonPromptText")}
      />
      <Field hint={`${draft.length} / ${MAX_INSTRUCTIONS}`}>
        <Textarea
          rows={7}
          value={draft}
          maxLength={MAX_INSTRUCTIONS}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={mode === "club" ? t("kb.clubPromptPlaceholder") : t("kb.commonPromptPlaceholder")}
          aria-label={mode === "club" ? t("kb.clubPrompt") : t("kb.commonPrompt")}
        />
      </Field>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button onClick={save} loading={saving} disabled={draft === initial}>{t("kb.save")}</Button>
        {mode === "club" && common && (
          <Button variant="ghost" size="sm" onClick={() => setShowCommon((v) => !v)}>
            {showCommon ? t("kb.hideCommonPrompt") : t("kb.showCommonPrompt")}
          </Button>
        )}
      </div>
      {showCommon && (
        <p className="mt-3 whitespace-pre-line rounded-xl bg-ink-50 p-3 text-sm text-ink-700 ring-1 ring-ink-100">{common}</p>
      )}
    </Card>
  );
}

function Documents({ base, queryKey, mode, documents }: {
  base: string; queryKey: string[]; mode: "club" | "platform"; documents: KnowledgeDocument[];
}) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [uploading, setUploading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Le fichas si riscrivono da sole ogni notte; il bottone serve dopo aver
  // cambiato orari o prezzi, per non aspettare domani.
  async function refresh() {
    setRefreshing(true);
    try {
      if (mode === "club") {
        const fresh = await call<Knowledge>(`${base}/refresh`, { method: "POST" });
        queryClient.setQueryData(queryKey, fresh);
        toast({ tone: "success", title: t("jbx.kb.refreshed") });
      } else {
        const { written } = await call<{ written: number }>(`${base}/refresh`, { method: "POST" });
        await queryClient.invalidateQueries({ queryKey });
        toast({ tone: "success", title: t("jbx.kb.refreshed"), text: t("jbx.kb.refreshedN", { n: written }) });
      }
    } catch (e) {
      toast({ tone: "error", title: t("jbx.kb.refreshError"), text: (e as Error).message });
    } finally {
      setRefreshing(false);
    }
  }

  async function upload() {
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    if (title.trim()) form.append("title", title.trim());
    try {
      const document = await call<KnowledgeDocument>(`${base}/documents`, { method: "POST", body: form });
      await queryClient.invalidateQueries({ queryKey });
      setFile(null);
      setTitle("");
      if (input.current) input.current.value = "";
      if (document.status === "EMPTY") toast({ tone: "info", title: t("kb.emptyTitle"), text: t("kb.emptyText") });
      else toast({ tone: "success", title: t("kb.uploaded"), text: t("kb.uploadedText", { pages: document.page_count }) });
    } catch (e) {
      toast({ tone: "error", title: t("kb.uploadError"), text: (e as Error).message });
    } finally {
      setUploading(false);
    }
  }

  return (
    <Card>
      <CardHeader
        icon={<span aria-hidden="true">📚</span>}
        title={mode === "club" ? t("kb.clubDocs") : t("kb.commonDocsAdmin")}
        subtitle={mode === "club" ? t("kb.clubDocsText") : t("kb.commonDocsAdminText")}
        action={<Button variant="secondary" size="sm" loading={refreshing} onClick={refresh} icon={<span aria-hidden="true">↻</span>}>{t("jbx.kb.refresh")}</Button>}
      />
      <p className="-mt-2 mb-4 text-xs text-ink-500">{t("jbx.kb.refreshHint")}</p>
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <Field label={t("kb.file")} hint={t("kb.fileHint")}>
          <Input ref={input} type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
        <Field label={t("kb.title")}>
          <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={file?.name.replace(/\.pdf$/i, "") ?? t("kb.titlePlaceholder")} />
        </Field>
        <Button onClick={upload} loading={uploading} disabled={!file}>{t("kb.upload")}</Button>
      </div>
      <div className="mt-5">
        {documents.length === 0
          ? <p className="text-sm text-ink-500">{t("kb.none")}</p>
          : <DocumentList base={base} documents={documents} queryKey={queryKey} />}
      </div>
    </Card>
  );
}

function DocumentList({ base, documents, readOnly = false, queryKey }: {
  base: string; documents: KnowledgeDocument[]; readOnly?: boolean; queryKey?: string[];
}) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);

  async function open(doc: KnowledgeDocument) {
    // La finestra si apre subito, nel clic: un popup aperto dopo un'attesa i
    // browser lo bloccano. L'URL presigned arriva dopo.
    const win = window.open("", "_blank");
    try {
      const { url } = await call<{ url: string }>(`${base}/documents/${doc.id}/link`);
      if (win) win.location.replace(url);
      else window.location.assign(url);
    } catch (e) {
      win?.close();
      toast({ tone: "error", title: t("kb.openError"), text: (e as Error).message });
    }
  }

  async function remove(doc: KnowledgeDocument) {
    if (!window.confirm(t("kb.confirmDelete", { title: doc.title }))) return;
    setBusy(doc.id);
    try {
      await call(`${base}/documents/${doc.id}`, { method: "DELETE" });
      if (queryKey) await queryClient.invalidateQueries({ queryKey });
      toast({ tone: "success", title: t("kb.deleted") });
    } catch (e) {
      toast({ tone: "error", title: t("kb.deleteError"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <ul className="divide-y divide-ink-100">
      {documents.map((doc) => {
        const source = SOURCES[doc.source ?? "UPLOAD"] ?? SOURCES.UPLOAD!;
        const isData = doc.source === "DATA";
        return (
          <li key={doc.id} className="flex flex-wrap items-center gap-3 py-3">
            <span aria-hidden="true" className="text-xl">{source.icon}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold text-ink-900">{doc.title}</p>
              <p className="truncate text-xs text-ink-500">
                {isData
                  ? `${t("jbx.kb.dataMeta")} · ${fmt.shortDate(doc.created_at)}`
                  : `${doc.filename} · ${t("kb.pages", { pages: doc.page_count })} · ${(doc.size_bytes / 1024 / 1024).toFixed(1)} MB · ${fmt.shortDate(doc.created_at)}`}
              </p>
            </div>
            <Badge tone={source.tone}>{t(source.label)}</Badge>
            {doc.status === "EMPTY"
              ? <Badge tone="warning">{t("kb.statusEmpty")}</Badge>
              : <Badge tone="success" dot>{t("kb.statusReady")}</Badge>}
            {!readOnly && !isData && doc.has_file !== false && <Button variant="secondary" size="sm" onClick={() => open(doc)}>{t("kb.open")}</Button>}
            {/* Solo i PDF caricati si eliminano da qui: un regolamento si toglie
                dalla prova, una ficha la riscrive il gestionale. */}
            {!readOnly && (doc.source ?? "UPLOAD") === "UPLOAD" && (
              <Button variant="ghost" size="sm" onClick={() => remove(doc)} loading={busy === doc.id}>{t("kb.delete")}</Button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
