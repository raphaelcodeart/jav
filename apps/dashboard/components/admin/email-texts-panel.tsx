"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { friendlyApiError } from "@/lib/api-error";
import { cn } from "@/lib/cn";

// I testi delle email (apps/api/app/domains/email_texts): il superadmin li
// personalizza, vede l'anteprima con il marchio di JudoArteVida o di un club
// e si manda una prova. I segnaposto tra graffe li riempie il sistema.

interface EmailText {
  key: string; label: string; audience: string; subject: string; heading: string; body: string; cta_label: string | null;
  has_cta: boolean; customized: boolean; updated_at: string | null;
  default: { subject: string; heading: string; body: string; cta_label: string | null };
  placeholders: { name: string; description: string; example: string }[];
}

const BASE = "/api/proxy/email-templates";

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}
const json = (method: string, body: unknown): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export function EmailTextsPanel() {
  const { data, isLoading } = useQuery({ queryKey: ["email-templates"], queryFn: () => call<EmailText[]>(BASE) });
  const [key, setKey] = useState<string | null>(null);
  const current = (data ?? []).find((t) => t.key === key) ?? data?.[0];
  if (isLoading || !data) return <Skeleton className="h-96" />;
  return (
    <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
      <ul className="space-y-2">
        {data.map((t) => (
          <li key={t.key}>
            <button type="button" onClick={() => setKey(t.key)}
              className={cn("w-full cursor-pointer rounded-2xl px-4 py-3 text-left ring-1 transition", current?.key === t.key ? "bg-brand-50 ring-brand-300" : "bg-white ring-ink-100 hover:ring-ink-200")}>
              <span className="flex items-center justify-between gap-2">
                <span className="font-semibold text-ink-900">✉️ {t.label}</span>
                {t.customized && <Badge tone="brand">Modificato</Badge>}
              </span>
              <span className="mt-0.5 block text-xs text-ink-500">{t.audience}</span>
            </button>
          </li>
        ))}
      </ul>
      {current && <Editor key={current.key + (current.updated_at ?? "")} text={current} />}
    </div>
  );
}

function Editor({ text }: { text: EmailText }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ subject: text.subject, heading: text.heading, body: text.body, cta_label: text.cta_label ?? "" });
  const [club, setClub] = useState("");
  const [preview, setPreview] = useState<{ subject: string; html: string } | null>(null);
  const [busy, setBusy] = useState<"save" | "reset" | "test" | null>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const clubs = useQuery({ queryKey: ["clubs"], queryFn: () => call<{ id: string; name: string; kind?: string }[]>("/api/proxy/clubs") });
  const payload = { ...form, cta_label: form.cta_label || null, club_id: club || null };

  // L'anteprima si aggiorna mezzo secondo dopo l'ultima modifica.
  const serialized = JSON.stringify(payload);
  useEffect(() => {
    const id = window.setTimeout(() => {
      call<{ subject: string; html: string }>(`${BASE}/${text.key}/preview`, json("POST", JSON.parse(serialized)))
        .then(setPreview).catch(() => undefined);
    }, 500);
    return () => window.clearTimeout(id);
  }, [serialized, text.key]);

  function insert(name: string) {
    const el = bodyRef.current;
    const token = `{${name}}`;
    if (!el) return setForm((f) => ({ ...f, body: f.body + token }));
    const start = el.selectionStart ?? form.body.length;
    const end = el.selectionEnd ?? start;
    setForm((f) => ({ ...f, body: f.body.slice(0, start) + token + f.body.slice(end) }));
  }

  async function act(kind: "save" | "reset" | "test") {
    setBusy(kind);
    try {
      if (kind === "save") {
        await call(`${BASE}/${text.key}`, json("PUT", { ...form, cta_label: form.cta_label || null }));
        toast({ tone: "success", title: "Testo salvato", text: "Da adesso le email partono con questo testo." });
      } else if (kind === "reset") {
        if (!window.confirm("Tornare al testo predefinito? Le tue modifiche si perdono.")) return;
        await call(`${BASE}/${text.key}`, { method: "DELETE" });
        toast({ tone: "success", title: "Testo predefinito ripristinato" });
      } else {
        const res = await call<{ sent: boolean; to: string }>(`${BASE}/${text.key}/test`, json("POST", payload));
        toast(res.sent ? { tone: "success", title: `Prova inviata a ${res.to}` }
          : { tone: "error", title: "Email di prova non partita", text: "Controlla la configurazione SMTP (utente e password della casella)." });
      }
      if (kind !== "test") await queryClient.invalidateQueries({ queryKey: ["email-templates"] });
    } catch (e) {
      toast({ tone: "error", title: "Operazione non riuscita", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <div className="space-y-4">
        <Field label="Oggetto"><Input value={form.subject} maxLength={200} onChange={(e) => setForm((f) => ({ ...f, subject: e.target.value }))} /></Field>
        <Field label="Titolo nell'email"><Input value={form.heading} maxLength={200} onChange={(e) => setForm((f) => ({ ...f, heading: e.target.value }))} /></Field>
        <Field label="Testo" hint="Testo semplice: una riga vuota separa i paragrafi. ⟦…⟧ mostra un codice in grande.">
          <Textarea ref={bodyRef} rows={10} value={form.body} maxLength={8000} onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))} />
        </Field>
        {text.has_cta && <Field label="Bottone"><Input value={form.cta_label} maxLength={80} onChange={(e) => setForm((f) => ({ ...f, cta_label: e.target.value }))} /></Field>}
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-500">Segnaposto (tocca per inserirlo)</p>
          <div className="flex flex-wrap gap-2">
            {text.placeholders.map((p) => (
              <button key={p.name} type="button" onClick={() => insert(p.name)} title={`${p.description} — es. ${p.example}`}
                className="cursor-pointer rounded-full bg-ink-50 px-3 py-1 font-mono text-xs text-ink-700 ring-1 ring-ink-200 hover:bg-brand-50 hover:ring-brand-300">
                {`{${p.name}}`}
              </button>
            ))}
          </div>
          <ul className="mt-2 space-y-0.5 text-xs text-ink-500">
            {text.placeholders.map((p) => <li key={p.name}><code>{`{${p.name}}`}</code>: {p.description}</li>)}
          </ul>
        </div>
        <div className="flex flex-wrap gap-2 border-t border-ink-100 pt-4">
          <Button onClick={() => act("save")} loading={busy === "save"}>Salva</Button>
          <Button variant="secondary" onClick={() => act("test")} loading={busy === "test"}>✉️ Mandami una prova</Button>
          {text.customized && <Button variant="ghost" onClick={() => act("reset")} loading={busy === "reset"}>↺ Testo predefinito</Button>}
        </div>
      </div>
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-bold uppercase tracking-wide text-ink-500">Anteprima</p>
          <Select value={club} onChange={(e) => setClub(e.target.value)} className="w-64" aria-label="Marchio">
            <option value="">🌍 Marchio JudoArteVida</option>
            {(clubs.data ?? []).filter((c) => c.kind !== "JAV_COURSES").map((c) => <option key={c.id} value={c.id}>🏯 {c.name}</option>)}
          </Select>
        </div>
        {preview && <p className="rounded-xl bg-ink-50 px-3 py-2 text-sm"><span className="text-ink-500">Oggetto:</span> <strong>{preview.subject}</strong></p>}
        <div className="overflow-hidden rounded-3xl ring-1 ring-ink-200">
          {preview ? <iframe title="Anteprima email" srcDoc={preview.html} sandbox="" className="h-[720px] w-full bg-white" /> : <Skeleton className="h-[720px]" />}
        </div>
      </div>
    </div>
  );
}
