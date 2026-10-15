"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { friendlyApiError } from "@/lib/api-error";
import type { MessageKey } from "@/lib/i18n/messages/it";
import { useI18n } from "@/lib/i18n/provider";

// I documenti del club (apps/api/app/domains/club/club_documents.py): certidões,
// atas, rivalidazione alla federazione, assicurazioni, statuto. Nel bucket
// privato: si aprono con un link di pochi minuti. Con una scadenza la segreteria
// è avvisata 30 giorni prima.

const BASE = "/api/proxy/club/admin/club-documents";
const CATEGORIES = [
  "DECLARATION", "FEDERATION", "MINUTES", "TAX", "SOCIAL_SECURITY", "SPORTS", "INSURANCE", "STATUTES", "OTHER",
] as const;
const ICONS: Record<string, string> = {
  DECLARATION: "📝", FEDERATION: "🥋", MINUTES: "📒", TAX: "🧾", SOCIAL_SECURITY: "🛡️", SPORTS: "🏅",
  INSURANCE: "☂️", STATUTES: "📜", OTHER: "📁",
};
const STATUS: Record<string, { key: MessageKey; tone: Tone } | undefined> = {
  VALID: { key: "clubDocs.statusValid", tone: "success" },
  EXPIRING: { key: "clubDocs.statusExpiring", tone: "warning" },
  EXPIRED: { key: "clubDocs.statusExpired", tone: "danger" },
};

interface ClubDocument {
  id: string;
  category: string;
  title: string;
  issued_on: string | null;
  expires_on: string | null;
  notes: string | null;
  original_filename: string;
  size_bytes: number;
  status: "NONE" | "VALID" | "EXPIRING" | "EXPIRED";
  created_at: string;
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.status === 204 ? (undefined as T) : res.json();
}

export function ClubDocumentsPanel() {
  const { t } = useI18n();
  const { data, isLoading, error } = useQuery({ queryKey: ["club", "club-documents"], queryFn: () => call<ClubDocument[]>(BASE) });
  const [uploading, setUploading] = useState(false);
  const [editing, setEditing] = useState<ClubDocument | null>(null);

  if (isLoading) return <Skeleton className="h-64" />;
  if (error || !data) return <EmptyState icon={<span className="text-3xl">📁</span>} title={t("clubDocs.loadError")} text={(error as Error)?.message} />;

  const alerts = data.filter((d) => d.status === "EXPIRED" || d.status === "EXPIRING");
  const byCategory = CATEGORIES.map((c) => [c, data.filter((d) => d.category === c)] as const).filter(([, docs]) => docs.length);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-ink-600">{t("clubDocs.intro")}</p>
        <Button onClick={() => setUploading(true)}>＋ {t("clubDocs.add")}</Button>
      </div>
      {alerts.length > 0 && (
        <Card className="border-l-4 border-l-amber-400">
          <p className="text-sm font-semibold text-ink-900">⚠️ {t("clubDocs.alertsTitle", { n: alerts.length })}</p>
          <ul className="mt-2 space-y-1 text-sm text-ink-700">
            {alerts.map((d) => <li key={d.id}>{d.title} — <DocStatus doc={d} /></li>)}
          </ul>
        </Card>
      )}
      {data.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">📁</span>} title={t("clubDocs.none")} text={t("clubDocs.noneText")} />
      ) : byCategory.map(([category, docs]) => (
        <Card key={category}>
          <CardHeader icon={<span aria-hidden="true">{ICONS[category]}</span>} title={t.dyn(`clubDocs.cat.${category}`, category)} />
          <ul className="divide-y divide-ink-100">
            {docs.map((d) => <DocumentRow key={d.id} doc={d} onEdit={() => setEditing(d)} />)}
          </ul>
        </Card>
      ))}
      {uploading && <DocumentModal onClose={() => setUploading(false)} />}
      {editing && <DocumentModal doc={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function DocStatus({ doc }: { doc: ClubDocument }) {
  const { t, fmt } = useI18n();
  const status = STATUS[doc.status];
  if (!status || !doc.expires_on) return null;
  return <Badge tone={status.tone} dot>{t(status.key, { date: fmt.shortDate(doc.expires_on) })}</Badge>;
}

function DocumentRow({ doc, onEdit }: { doc: ClubDocument; onEdit: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);

  async function open() {
    // La finestra si apre subito, nel clic: dopo un'attesa i browser la bloccano.
    const win = window.open("", "_blank");
    try {
      const { url } = await call<{ url: string }>(`${BASE}/${doc.id}/url`);
      if (win) win.location.replace(url);
      else window.location.assign(url);
    } catch (e) {
      win?.close();
      toast({ tone: "error", title: t("clubDocs.openError"), text: (e as Error).message });
    }
  }

  async function remove() {
    if (!window.confirm(t("clubDocs.confirmDelete", { title: doc.title }))) return;
    setBusy(true);
    try {
      await call(`${BASE}/${doc.id}`, { method: "DELETE" });
      await queryClient.invalidateQueries({ queryKey: ["club", "club-documents"] });
      toast({ tone: "success", title: t("clubDocs.deleted") });
    } catch (e) {
      toast({ tone: "error", title: t("clubDocs.deleteError"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-3 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold text-ink-900">{doc.title}</p>
        <p className="truncate text-xs text-ink-500">
          {doc.issued_on ? `${t("clubDocs.issued")} ${fmt.shortDate(doc.issued_on)} · ` : ""}
          {doc.expires_on ? `${t("clubDocs.expires")} ${fmt.shortDate(doc.expires_on)} · ` : ""}
          {doc.original_filename}
        </p>
        {doc.notes && <p className="mt-1 text-xs text-ink-600">{doc.notes}</p>}
      </div>
      <DocStatus doc={doc} />
      <Button variant="secondary" size="sm" onClick={open}>{t("clubDocs.open")}</Button>
      <Button variant="ghost" size="sm" onClick={onEdit}>{t("clubDocs.edit")}</Button>
      <Button variant="ghost" size="sm" onClick={remove} loading={busy}>{t("clubDocs.delete")}</Button>
    </li>
  );
}

function DocumentModal({ doc, onClose }: { doc?: ClubDocument; onClose: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [category, setCategory] = useState(doc?.category ?? "TAX");
  const [title, setTitle] = useState(doc?.title ?? "");
  const [issued, setIssued] = useState(doc?.issued_on ?? "");
  const [expires, setExpires] = useState(doc?.expires_on ?? "");
  const [notes, setNotes] = useState(doc?.notes ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (doc) {
        await call(`${BASE}/${doc.id}`, {
          method: "PATCH", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category, title, issued_on: issued || null, expires_on: expires || null, notes: notes || null }),
        });
      } else {
        if (!file) return;
        const form = new FormData();
        form.append("file", file);
        form.append("category", category);
        form.append("title", title);
        if (issued) form.append("issued_on", issued);
        if (expires) form.append("expires_on", expires);
        if (notes.trim()) form.append("notes", notes.trim());
        await call(BASE, { method: "POST", body: form });
      }
      await queryClient.invalidateQueries({ queryKey: ["club", "club-documents"] });
      toast({ tone: "success", title: doc ? t("clubDocs.saved") : t("clubDocs.uploaded") });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={doc ? t("clubDocs.editTitle") : t("clubDocs.add")}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
        <Button onClick={save} loading={busy} disabled={!title.trim() || (!doc && !file)}>{doc ? t("clubDocs.save") : t("clubDocs.upload")}</Button>
      </>}
    >
      <div className="space-y-4">
        <Field label={t("clubDocs.category")}>
          <Select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{ICONS[c]} {t.dyn(`clubDocs.cat.${c}`, c)}</option>)}
          </Select>
        </Field>
        <Field label={t("clubDocs.titleLabel")}>
          <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={t("clubDocs.titlePlaceholder")} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("clubDocs.issuedLabel")}>
            <Input type="date" value={issued} onChange={(e) => setIssued(e.target.value)} />
          </Field>
          <Field label={t("clubDocs.expiresLabel")} hint={t("clubDocs.expiresHint")}>
            <Input type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
          </Field>
        </div>
        <Field label={t("clubDocs.notes")}>
          <Textarea rows={2} value={notes} maxLength={2000} onChange={(e) => setNotes(e.target.value)} />
        </Field>
        {!doc && (
          <Field label={t("clubDocs.file")} hint={t("clubDocs.fileHint")}>
            <Input ref={input} type="file" accept="application/pdf,image/jpeg,image/png" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Field>
        )}
        {error && <p className="text-sm text-rose-600">{error}</p>}
      </div>
    </Modal>
  );
}
