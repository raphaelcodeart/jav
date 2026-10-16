"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";

// Gli sponsor della rete (apps/api/app/domains/club/sponsors.py): la barra
// dei loghi della home e la pagina /patrocinadores/<slug>. Li gestisce lo
// staff della piattaforma: nome, riga sotto il nome, descrizione, logo,
// sito, colore, ordine, acceso/spento.

interface Sponsor {
  id: string;
  name: string;
  slug: string;
  tagline: string | null;
  description: string | null;
  logo_url: string | null;
  website_url: string | null;
  color: string | null;
  sort_order: number;
  active: boolean;
}

const BASE = "/api/proxy/sponsors";

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.status === 204 ? (undefined as T) : res.json();
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function SponsorsPanel() {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ["sponsors"], queryFn: () => call<Sponsor[]>(BASE) });
  const [editing, setEditing] = useState<Sponsor | "new" | null>(null);

  async function toggle(s: Sponsor) {
    try {
      await call(`${BASE}/${s.id}`, json("PATCH", { active: !s.active }));
      await queryClient.invalidateQueries({ queryKey: ["sponsors"] });
    } catch (e) {
      toast({ tone: "error", title: t("sponsors.saveError"), text: (e as Error).message });
    }
  }
  async function remove(s: Sponsor) {
    if (!window.confirm(t("sponsors.confirmDelete", { name: s.name }))) return;
    try {
      await call(`${BASE}/${s.id}`, { method: "DELETE" });
      await queryClient.invalidateQueries({ queryKey: ["sponsors"] });
      toast({ tone: "success", title: t("sponsors.deleted") });
    } catch (e) {
      toast({ tone: "error", title: t("sponsors.saveError"), text: (e as Error).message });
    }
  }

  if (isLoading) return <Skeleton className="h-64" />;
  if (error || !data) return <EmptyState title={t("sponsors.loadError")} text={(error as Error)?.message} />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-ink-600">{t("sponsors.intro")}</p>
        <div className="flex gap-2">
          <a href="/" target="_blank" rel="noopener noreferrer"><Button variant="secondary">{t("sponsors.seeHome")} ↗</Button></a>
          <Button onClick={() => setEditing("new")}>＋ {t("sponsors.add")}</Button>
        </div>
      </div>
      {data.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🤝</span>} title={t("sponsors.empty")} action={<Button onClick={() => setEditing("new")}>{t("sponsors.add")}</Button>} />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((s) => (
            <li key={s.id} className="glass-card flex flex-col gap-3 rounded-3xl p-5">
              <div className="flex items-center gap-3">
                <span className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-white ring-1 ring-ink-100">
                  {s.logo_url
                    // eslint-disable-next-line @next/next/no-img-element -- logo caricato da qui
                    ? <img src={s.logo_url} alt="" className="max-h-full max-w-full object-contain" />
                    : <span className="flex h-full w-full items-center justify-center font-display text-white" style={{ backgroundColor: s.color ?? "#E13F22" }}>{s.name.slice(0, 2).toUpperCase()}</span>}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-ink-900">{s.name}</p>
                  <p className="truncate text-xs text-ink-500">{s.tagline ?? "—"}</p>
                  <p className="truncate text-xs text-brand-700">{s.website_url ?? t("sponsors.noWebsite")}</p>
                </div>
                <Badge tone={s.active ? "success" : "neutral"} dot>{s.active ? t("sponsors.active") : t("sponsors.inactive")}</Badge>
              </div>
              <div className="mt-auto flex flex-wrap gap-2 border-t border-ink-100 pt-3">
                <Button size="sm" variant="secondary" onClick={() => setEditing(s)}>✎ {t("sponsors.edit")}</Button>
                <Button size="sm" variant="ghost" onClick={() => toggle(s)}>{s.active ? t("sponsors.hide") : t("sponsors.show")}</Button>
                <a href={`/patrocinadores/${s.slug}`} target="_blank" rel="noopener noreferrer" className="inline-flex h-8 items-center px-2 text-sm font-semibold text-brand-700 hover:underline">{t("sponsors.page")} ↗</a>
                <Button size="sm" variant="ghost" className="ml-auto text-rose-600" onClick={() => remove(s)}>{t("sponsors.delete")}</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {editing && <SponsorModal sponsor={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function SponsorModal({ sponsor, onClose }: { sponsor: Sponsor | null; onClose: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState({
    name: sponsor?.name ?? "", tagline: sponsor?.tagline ?? "", description: sponsor?.description ?? "",
    website_url: sponsor?.website_url ?? "", color: sponsor?.color ?? "#E13F22", sort_order: String(sponsor?.sort_order ?? 0),
  });
  const [logo, setLogo] = useState<string | null>(sponsor?.logo_url ?? null);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const { url } = await call<{ url: string }>(`${BASE}/logo`, { method: "POST", body });
      setLogo(url);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    const payload = {
      name: form.name, tagline: form.tagline || null, description: form.description || null,
      website_url: form.website_url || null, color: form.color || null, sort_order: Number(form.sort_order) || 0, logo_url: logo,
    };
    try {
      await call(sponsor ? `${BASE}/${sponsor.id}` : BASE, json(sponsor ? "PATCH" : "POST", payload));
      await queryClient.invalidateQueries({ queryKey: ["sponsors"] });
      toast({ tone: "success", title: t("sponsors.saved") });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} size="lg" title={sponsor ? t("sponsors.editTitle") : t("sponsors.add")}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
        <Button onClick={save} loading={busy} disabled={form.name.trim().length < 2 || uploading}>{t("common.save")}</Button>
      </>}
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("sponsors.name")}><Input value={form.name} maxLength={120} onChange={set("name")} placeholder="Câmara Municipal de Lagos" /></Field>
          <Field label={t("sponsors.tagline")}><Input value={form.tagline} maxLength={200} onChange={set("tagline")} placeholder="Município de Lagos" /></Field>
        </div>
        <Field label={t("sponsors.description")} hint={t("sponsors.descriptionHint")}>
          <Textarea rows={5} value={form.description} maxLength={5000} onChange={set("description")} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-[1fr_120px_100px]">
          <Field label={t("sponsors.website")}><Input value={form.website_url} maxLength={500} onChange={set("website_url")} placeholder="https://www.cm-lagos.pt" inputMode="url" /></Field>
          <Field label={t("sponsors.color")}><Input type="color" value={form.color} onChange={set("color")} className="h-11 p-1" /></Field>
          <Field label={t("sponsors.order")}><Input type="number" min={0} max={999} value={form.sort_order} onChange={set("sort_order")} /></Field>
        </div>
        <Field label={t("sponsors.logo")} hint={t("sponsors.logoHint")}>
          <div className="flex flex-wrap items-center gap-3">
            {logo && (
              // eslint-disable-next-line @next/next/no-img-element -- anteprima del logo
              <img src={logo} alt="" className="h-14 w-auto max-w-[10rem] rounded-xl bg-white object-contain p-1 ring-1 ring-ink-100" />
            )}
            <Input ref={input} type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }} />
            {uploading && <span className="text-xs text-ink-500">{t("board.uploading")}</span>}
            {logo && <Button size="sm" variant="ghost" onClick={() => setLogo(null)}>{t("sponsors.removeLogo")}</Button>}
          </div>
        </Field>
        {error && <p className="text-sm text-rose-600">{error}</p>}
      </div>
    </Modal>
  );
}
