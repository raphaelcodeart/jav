"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";
import { ProductThumbnail } from "@/components/product-thumbnail";
import {
  BulkAssign,
  CategoryList,
  ProductCategoriesField,
  sameCategorySelection,
  saveProductCategories,
  useShopCategories,
} from "@/components/shop-categories-card";
import type {
  JavMarketAdminProductRead,
  JavMarketOrderRead,
  JavMarketProducerRead,
  JavMarketSettingsRead,
  JavMarketSupplierDispatchRead,
  JavMarketSupplierDraft,
  JavMarketSupplierQueue,
} from "@/lib/types";

/** «Fai la Spesa con Jav» (Session 79): il pannello con cui
 *  l'amministratore costruisce il negozio.
 *
 *  Tre cose, nell'ordine in cui servono: le impostazioni (acceso, spese di
 *  spedizione), le **aziende produttrici** e i prodotti. Le aziende vengono
 *  prima dei prodotti di proposito -- un prodotto le può scegliere da un
 *  elenco, e chi compila la scheda una volta non la riscrive per ogni
 *  articolo.
 *
 *  Qui non c'è nessun fornitore da collegare via API: niente OAuth, niente
 *  sync, niente ricarico su un costo. Il prezzo lo scrive chi carica il
 *  prodotto ed è già quello di vendita.
 *
 *  Ottobre 2026: le aziende sono i **fornitori** a cui partono gli ordini.
 *  Un prodotto ha il suo fornitore oppure eredita quello della categoria
 *  («Categorie e fornitori»), e «Fornitori da avvisare» raccoglie gli
 *  ordini pagati di ciascun fornitore in un'email sola, da rileggere e
 *  correggere prima dell'invio. Chi è il fornitore lo decide il server
 *  (`resolve_suppliers`): qui si mostra e basta. */

const input =
  "w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-brand-500";
const label = "block font-semibold text-slate-500 uppercase tracking-wide mb-1";

function centsFrom(value: string): number {
  return Math.round((parseFloat(value.replace(",", ".")) || 0) * 100);
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api/proxy${path}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

async function send<T>(path: string, method: string, body: unknown): Promise<T> {
  const res = await fetch(`/api/proxy${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="glass-card rounded-2xl p-5 border-slate-200 space-y-4">
      <div>
        <h3 className="text-sm font-bold text-slate-900">{title}</h3>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

function Esito({ message }: { message: { ok: boolean; text: string } | null }) {
  if (!message) return null;
  return (
    <p className={`text-xs ${message.ok ? "text-emerald-400" : "text-rose-400"}`}>{message.text}</p>
  );
}

// --- Impostazioni ----------------------------------------------------------

function Impostazioni() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["admin", "jav-market", "settings"],
    queryFn: () => get<JavMarketSettingsRead>("/jav-market/settings"),
  });
  const [form, setForm] = useState<JavMarketSettingsRead | null>(null);
  const corrente = form ?? data ?? null;
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const salva = useMutation({
    mutationFn: (payload: Partial<JavMarketSettingsRead>) =>
      send<JavMarketSettingsRead>("/jav-market/settings", "PATCH", payload),
    onSuccess: (row) => {
      setForm(row);
      setMessage({ ok: true, text: t("mkt.jm.settingsSaved") });
      queryClient.invalidateQueries({ queryKey: ["admin", "jav-market"] });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  if (!corrente) return <Card title={t("mkt.jm.settings")}>{t("mkt.jm.loading")}</Card>;

  return (
    <Card
      title={t("mkt.jm.settingsTitle")}
      subtitle={t("mkt.jm.settingsSubtitle")}
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div>
          <span className={label}>{t("mkt.jm.state")}</span>
          <select
            className={input}
            value={corrente.enabled ? "on" : "off"}
            onChange={(e) => setForm({ ...corrente, enabled: e.target.value === "on" })}
          >
            <option value="off">{t("mkt.jm.off")}</option>
            <option value="on">{t("mkt.jm.on")}</option>
          </select>
        </div>
        <div>
          <span className={label}>{t("mkt.jm.shipping")}</span>
          <select
            className={input}
            value={corrente.shipping_mode}
            onChange={(e) =>
              setForm({ ...corrente, shipping_mode: e.target.value as JavMarketSettingsRead["shipping_mode"] })
            }
          >
            <option value="CUSTOMER_PAYS">{t("mkt.jm.shippingCustomerPays")}</option>
            <option value="INCLUDED">{t("mkt.jm.shippingIncluded")}</option>
          </select>
        </div>
        <div>
          <span className={label}>{t("mkt.jm.shippingCost")}</span>
          <input
            className={input}
            inputMode="decimal"
            value={(corrente.shipping_flat_cents / 100).toString()}
            onChange={(e) => setForm({ ...corrente, shipping_flat_cents: centsFrom(e.target.value) })}
          />
          <span className="block text-[10px] text-slate-500 mt-1">
            {corrente.shipping_mode === "INCLUDED"
              ? t("mkt.jm.shippingIncludedHint")
              : t("mkt.jm.shippingPerOrderHint")}
          </span>
        </div>
        <div>
          <span className={label}>{t("mkt.jm.minOrder")}</span>
          <input
            className={input}
            inputMode="decimal"
            value={((corrente.min_order_cents ?? 0) / 100).toString()}
            onChange={(e) => setForm({ ...corrente, min_order_cents: centsFrom(e.target.value) })}
          />
          <span className="block text-[10px] text-slate-500 mt-1">
            {t("mkt.jm.minOrderHint")}
          </span>
        </div>
        <div>
          <span className={label}>{t("mkt.jm.freeShipping")}</span>
          <input
            className={input}
            inputMode="decimal"
            value={((corrente.free_shipping_threshold_cents ?? 0) / 100).toString()}
            onChange={(e) => setForm({ ...corrente, free_shipping_threshold_cents: centsFrom(e.target.value) })}
          />
          <span className="block text-[10px] text-slate-500 mt-1">
            {t("mkt.jm.freeShippingHint")}
          </span>
        </div>
        <div>
          <span className={label}>{t("mkt.jm.forwarding")}</span>
          <select
            className={input}
            value={corrente.auto_forward ? "auto" : "manuale"}
            onChange={(e) => setForm({ ...corrente, auto_forward: e.target.value === "auto" })}
          >
            <option value="manuale">{t("mkt.jm.forwardManual")}</option>
            <option value="auto">{t("mkt.jm.forwardAuto")}</option>
          </select>
          <span className="block text-[10px] text-slate-500 mt-1">
            {corrente.auto_forward
              ? t("mkt.jm.forwardAutoHint")
              : t("mkt.jm.forwardManualHint")}
          </span>
        </div>
        <div>
          <span className={label}>{t("mkt.jm.deliveryTime")}</span>
          <input
            className={input}
            value={corrente.shipping_days ?? ""}
            placeholder={t("mkt.jm.deliveryTimePlaceholder")}
            onChange={(e) => setForm({ ...corrente, shipping_days: e.target.value })}
          />
        </div>
        <div className="sm:col-span-2">
          <span className={label}>{t("shopSuppliers.settingsFrom")}</span>
          <input
            className={input}
            type="email"
            value={corrente.supplier_email_from ?? ""}
            placeholder="info@judoartevida.com"
            onChange={(e) => setForm({ ...corrente, supplier_email_from: e.target.value })}
          />
          <span className="block text-[10px] text-slate-500 mt-1">{t("shopSuppliers.settingsFromHint")}</span>
        </div>
        <div className="sm:col-span-2">
          <span className={label}>{t("shopSuppliers.settingsSignature")}</span>
          <textarea
            className={`${input} min-h-[60px]`}
            value={corrente.supplier_email_signature ?? ""}
            placeholder={t("shopSuppliers.settingsSignaturePlaceholder")}
            onChange={(e) => setForm({ ...corrente, supplier_email_signature: e.target.value })}
          />
          <span className="block text-[10px] text-slate-500 mt-1">{t("shopSuppliers.settingsSignatureHint")}</span>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={() => salva.mutate(corrente)}
          disabled={salva.isPending}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {salva.isPending ? t("mkt.jm.saving") : t("mkt.jm.saveSettings")}
        </button>
        <Esito message={message} />
      </div>
    </Card>
  );
}

// --- Fornitori (le aziende produttrici) -----------------------------------

const PRODUTTORE_VUOTO = {
  name: "", description: "", website_url: "", vat_number: "", email: "", phone: "", address: "",
};

/** L'anagrafica dei fornitori: le aziende che fanno la merce e a cui
 *  partono gli ordini. Si chiamavano «aziende produttrici»; il nome è
 *  cambiato quando gli ordini hanno cominciato a partire per fornitore. */
function Produttori() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  // Dietro un pulsante come le categorie: le aziende si compilano una
  // volta e si toccano di rado, mentre i prodotti si caricano ogni giorno.
  const [aperto, setAperto] = useState(false);
  const { data: producers } = useQuery({
    queryKey: ["admin", "jav-market", "producers"],
    queryFn: () => get<JavMarketProducerRead[]>("/jav-market/producers"),
  });
  const [form, setForm] = useState({ ...PRODUTTORE_VUOTO });
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const crea = useMutation({
    mutationFn: () =>
      send<JavMarketProducerRead>("/jav-market/producers", "POST", {
        ...form,
        website_url: form.website_url || null,
        vat_number: form.vat_number || null,
        email: form.email || null,
        phone: form.phone || null,
        address: form.address || null,
      }),
    onSuccess: (p) => {
      setForm({ ...PRODUTTORE_VUOTO });
      setMessage({ ok: true, text: t("mkt.jm.supplierAdded", { name: p.name }) });
      queryClient.invalidateQueries({ queryKey: ["admin", "jav-market", "producers"] });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  const elenco = producers ?? [];
  if (!aperto) {
    return (
      <div className="glass-card rounded-2xl p-4 border-slate-200 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-bold text-slate-900">{t("shopSuppliers.registryTitle")}</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {elenco.length === 0
              ? t("shopSuppliers.registryEmpty")
              : t("shopSuppliers.registryCount", {
                  n: elenco.length,
                  names: `${elenco.slice(0, 3).map((p) => p.name).join(", ")}${elenco.length > 3 ? "…" : ""}`,
                })}
          </p>
        </div>
        <button
          onClick={() => setAperto(true)}
          className="px-4 py-2 rounded-xl border border-brand-500/40 text-xs font-semibold text-brand-600 hover:bg-brand-500/10 transition cursor-pointer shrink-0"
        >
          {t("shopSuppliers.registryManage")}
        </button>
      </div>
    );
  }

  return (
    <Card title={t("shopSuppliers.registryTitle")} subtitle={t("shopSuppliers.registrySubtitle")}>
      <button
        onClick={() => setAperto(false)}
        className=" font-semibold text-slate-500 hover:text-slate-900 cursor-pointer"
      >
        ← {t("common.close")}
      </button>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div className="sm:col-span-2">
          <span className={label}>{t("mkt.jm.companyName")}</span>
          <input className={input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <span className={label}>{t("mkt.jm.vatNumber")}</span>
          <input className={input} value={form.vat_number} onChange={(e) => setForm({ ...form, vat_number: e.target.value })} />
        </div>
        <div className="sm:col-span-3">
          <span className={label}>{t("mkt.jm.supplierDescription")}</span>
          <textarea
            className={`${input} min-h-[70px]`}
            value={form.description}
            placeholder={t("mkt.jm.supplierDescriptionPlaceholder")}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div>
          <span className={label}>{t("mkt.jm.website")}</span>
          <input className={input} value={form.website_url} placeholder="https://" onChange={(e) => setForm({ ...form, website_url: e.target.value })} />
        </div>
        <div>
          <span className={label}>{t("mkt.jm.orderEmail")}</span>
          <input className={input} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <span className="block text-[10px] text-slate-500 mt-1">
            {t("mkt.jm.orderEmailHint")}
          </span>
        </div>
        <div>
          <span className={label}>{t("mkt.jm.phone")}</span>
          <input className={input} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        </div>
        <div className="sm:col-span-3">
          <span className={label}>{t("mkt.jm.address")}</span>
          <input className={input} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={() => crea.mutate()}
          disabled={crea.isPending || form.name.trim().length === 0}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {crea.isPending ? t("mkt.jm.adding") : t("shopSuppliers.registryAdd")}
        </button>
        <Esito message={message} />
      </div>

      {elenco.length > 0 && (
        <div className="rounded-xl border border-slate-200 divide-y divide-slate-200">
          {elenco.map((p) => (
            <FornitoreRiga key={p.id} producer={p} />
          ))}
        </div>
      )}
    </Card>
  );
}

/** Una riga dell'anagrafica, che si apre in modifica sul posto: l'email
 *  di un fornitore si corregge qui, senza ricrearlo. */
function FornitoreRiga({ producer: p }: { producer: JavMarketProducerRead }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [bozza, setBozza] = useState<typeof PRODUTTORE_VUOTO & { active: boolean } | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const salva = useMutation({
    mutationFn: (body: typeof PRODUTTORE_VUOTO & { active: boolean }) =>
      send<JavMarketProducerRead>(`/jav-market/producers/${p.id}`, "PATCH", body),
    onSuccess: () => {
      setBozza(null);
      setMessage({ ok: true, text: t("shopSuppliers.registrySaved") });
      queryClient.invalidateQueries({ queryKey: ["admin", "jav-market"] });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  if (!bozza) {
    return (
      <div className="px-3 py-2 flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-slate-900">
            {p.name}
            {!p.active && <span className="ml-2 text-[10px] font-bold text-slate-400">{t("shopSuppliers.inactive")}</span>}
          </p>
          <p className="text-[11px] text-slate-500 truncate">
            {p.email ? p.email : <span className="text-amber-700">{t("mkt.jm.missingEmail")}</span>}
            {p.phone ? ` · ${p.phone}` : ""}
            {p.description ? ` · ${p.description}` : ""}
          </p>
          <Esito message={message} />
        </div>
        <button
          onClick={() => {
            setMessage(null);
            setBozza({
              name: p.name, description: p.description, website_url: p.website_url ?? "", vat_number: p.vat_number ?? "",
              email: p.email ?? "", phone: p.phone ?? "", address: p.address ?? "", active: p.active,
            });
          }}
          className="px-2.5 py-1 rounded-lg font-semibold border border-slate-300 text-slate-600 hover:bg-slate-100 cursor-pointer shrink-0"
        >
          {t("shopSuppliers.edit")}
        </button>
      </div>
    );
  }

  const campo = (key: keyof typeof PRODUTTORE_VUOTO, testo: string, span = "") => (
    <div className={span}>
      <span className={label}>{testo}</span>
      <input className={input} value={bozza[key]} onChange={(e) => setBozza({ ...bozza, [key]: e.target.value })} />
    </div>
  );
  return (
    <div className="px-3 py-3 space-y-3 bg-slate-900/[0.02]">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {campo("name", t("mkt.jm.companyName"), "sm:col-span-2")}
        {campo("vat_number", t("mkt.jm.vatNumber"))}
        {campo("email", t("mkt.jm.orderEmail"))}
        {campo("phone", t("mkt.jm.phone"))}
        {campo("website_url", t("mkt.jm.website"))}
        {campo("address", t("mkt.jm.address"), "sm:col-span-3")}
        <div className="sm:col-span-3">
          <span className={label}>{t("mkt.jm.supplierDescription")}</span>
          <textarea
            className={`${input} min-h-[60px]`}
            value={bozza.description}
            onChange={(e) => setBozza({ ...bozza, description: e.target.value })}
          />
        </div>
      </div>
      <label className="flex items-center gap-2 text-xs text-slate-700">
        <input type="checkbox" checked={bozza.active} onChange={(e) => setBozza({ ...bozza, active: e.target.checked })} />
        {t("shopSuppliers.registryActive")}
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => salva.mutate(bozza)}
          disabled={salva.isPending || !bozza.name.trim()}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {salva.isPending ? t("mkt.jm.saving") : t("mkt.jm.saveChanges")}
        </button>
        <button onClick={() => setBozza(null)} className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-slate-900/5 cursor-pointer">
          {t("common.cancel")}
        </button>
        <Esito message={message} />
      </div>
    </div>
  );
}

// --- Categorie e fornitori ---------------------------------------------------

/** Le categorie dello Shop gestite da qui, con il fornitore di ciascuna:
 *  i prodotti senza un fornitore loro prendono quello della categoria.
 *  Stessi componenti della gestione categorie degli altri shop
 *  (shop-categories-card.tsx), più la scelta del fornitore. */
function CategorieEFornitori() {
  const { t } = useI18n();
  const [aperto, setAperto] = useState(false);
  const { data: categories, error } = useShopCategories("jav_market");
  const { data: producers } = useQuery({
    queryKey: ["admin", "jav-market", "producers"],
    queryFn: () => get<JavMarketProducerRead[]>("/jav-market/producers"),
  });
  const elenco = categories ?? [];
  const collegate = elenco.filter((c) => c.producer_id).length;

  if (!aperto) {
    return (
      <div className="glass-card rounded-2xl p-4 border-slate-200 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-bold text-slate-900">{t("shopSuppliers.categoriesTitle")}</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {elenco.length === 0
              ? t("shopSuppliers.categoriesEmpty")
              : t("shopSuppliers.categoriesSummary", { n: elenco.length, linked: collegate })}
          </p>
        </div>
        <button
          onClick={() => setAperto(true)}
          className="px-4 py-2 rounded-xl border border-brand-500/40 text-xs font-semibold text-brand-600 hover:bg-brand-500/10 transition cursor-pointer shrink-0"
        >
          {t("shopSuppliers.categoriesManage")}
        </button>
      </div>
    );
  }

  return (
    <Card title={t("shopSuppliers.categoriesTitle")} subtitle={t("shopSuppliers.categoriesSubtitle")}>
      <button
        onClick={() => setAperto(false)}
        className=" font-semibold text-slate-500 hover:text-slate-900 cursor-pointer"
      >
        ← {t("common.close")}
      </button>
      {error && <p className="text-xs text-rose-400">{(error as Error).message}</p>}
      <CategoryList
        shop="jav_market"
        categories={categories}
        producers={(producers ?? []).map((p) => ({ id: p.id, name: p.name }))}
      />
      <BulkAssign shop="jav_market" categories={categories} />
    </Card>
  );
}

// --- Catalogo --------------------------------------------------------------

/** La foto del prodotto: si allega dal computer (finisce sul nostro server,
 *  POST /jav-market/images) oppure si incolla un URL come prima. In tutti e
 *  due i casi al form arriva solo un URL. */
function ImmagineProdotto({ value, onChange }: { value: string; onChange: (url: string) => void }) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function allega(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch("/api/proxy/jav-market/images", { method: "POST", body });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { image_url } = await res.json();
      onChange(image_url);
    } catch (err: unknown) {
      setError((err as Error).message || t("mkt.jm.uploadFailed"));
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="flex items-start gap-3">
      <div className="w-16 h-16 rounded-lg overflow-hidden border border-slate-200 shrink-0">
        <ProductThumbnail imageUrl={value || null} alt={t("mkt.jm.productPhoto")} iconClassName="w-7 h-7 text-brand-600/40" />
      </div>
      <div className="flex-1 min-w-0 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={allega} className="hidden" />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 cursor-pointer transition disabled:opacity-40"
          >
            {uploading ? t("mkt.jm.loading") : value ? t("mkt.jm.changePhoto") : t("mkt.jm.attachPhoto")}
          </button>
          {value && !uploading && (
            <button
              type="button"
              onClick={() => onChange("")}
              className="px-2 py-1.5 rounded-lg text-[11px] font-semibold text-rose-400 hover:bg-rose-500/10 cursor-pointer"
            >
              {t("mkt.jm.remove")}
            </button>
          )}
          <span className="text-[10px] text-slate-500">{t("mkt.jm.imageFormats")}</span>
        </div>
        <input
          className={input}
          placeholder={t("mkt.jm.imageUrlPlaceholder")}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        {error && <p className="text-[11px] text-rose-400">{error}</p>}
      </div>
    </div>
  );
}

type VarianteForm = { label: string; price: string; inventory: string };

const PRODOTTO_VUOTO = {
  name: "", description: "", image_url: "", credit_discount_percentage: "30", unit_cost: "",
  producer_id: "",
};

/** Session 87: il catalogo è un elenco da cercare e filtrare, e creare o
 *  modificare un prodotto apre una finestra sopra l'elenco. Prima il form
 *  di creazione stava sempre aperto in cima e quello di modifica compariva
 *  in fondo alla lista: con centinaia di prodotti
 *  bisognava scorrere tutto per arrivarci. */
type Editor = { mode: "create" } | { mode: "edit"; id: string };

function Catalogo() {
  const { t, fmt } = useI18n();
  const euro = (cents: number) => fmt.euro(cents);
  const queryClient = useQueryClient();
  const { data: products } = useQuery({
    queryKey: ["admin", "jav-market", "products"],
    queryFn: () => get<JavMarketAdminProductRead[]>("/jav-market/products"),
  });
  const { data: producers } = useQuery({
    queryKey: ["admin", "jav-market", "producers"],
    queryFn: () => get<JavMarketProducerRead[]>("/jav-market/producers"),
  });
  const [editor, setEditor] = useState<Editor | null>(null);
  const [cerca, setCerca] = useState("");
  const [stato, setStato] = useState<"TUTTI" | "ACTIVE" | "INACTIVE">("TUTTI");
  const [produttore, setProduttore] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const spegni = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "ACTIVE" | "INACTIVE" }) =>
      send<JavMarketAdminProductRead>(`/jav-market/products/${id}`, "PATCH", { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "jav-market", "products"] }),
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  const tutti = products ?? [];
  const testo = cerca.trim().toLowerCase();
  // Si cerca anche nella descrizione e negli sku: in un catalogo di abiti il codice
  // articolo sta nella descrizione e l'EAN è lo sku di ogni variante.
  const visibili = tutti.filter(
    (p) =>
      (stato === "TUTTI" || p.status === stato) &&
      (!produttore || p.supplier?.id === produttore) &&
      (!testo ||
        p.name.toLowerCase().includes(testo) ||
        p.description.toLowerCase().includes(testo) ||
        p.variants.some((v) => (v.sku ?? "").toLowerCase().includes(testo) || v.label.toLowerCase().includes(testo)))
  );
  const quanti = {
    TUTTI: tutti.length,
    ACTIVE: tutti.filter((p) => p.status === "ACTIVE").length,
    INACTIVE: tutti.filter((p) => p.status !== "ACTIVE").length,
  };
  // La finestra di modifica legge il prodotto dalla lista, non da una copia:
  // dopo un salvataggio mostra i prezzi nuovi senza doverla riaprire.
  const inModifica = editor?.mode === "edit" ? tutti.find((p) => p.id === editor.id) ?? null : null;

  return (
    <Card title={t("mkt.jm.catalogTitle")} subtitle={t("mkt.jm.catalogCount", { n: tutti.length })}>
      <div className="flex flex-col lg:flex-row gap-2 lg:items-center">
        <input
          className={`${input} lg:max-w-xs`}
          placeholder={t("mkt.jm.catalogSearch")}
          value={cerca}
          onChange={(e) => setCerca(e.target.value)}
        />
        <div className="flex flex-wrap gap-1.5">
          {(
            [
              ["TUTTI", t("mkt.jm.filterAll")],
              ["ACTIVE", t("mkt.jm.onSale")],
              ["INACTIVE", t("mkt.jm.filterOff")],
            ] as const
          ).map(([key, testoBottone]) => (
            <button
              key={key}
              onClick={() => setStato(key)}
              className={`px-2.5 py-1.5 rounded-lg text-[11px] font-semibold border cursor-pointer ${
                stato === key
                  ? "border-brand-500/50 bg-brand-500/15 text-brand-700"
                  : " border-slate-300 text-slate-600 hover:bg-slate-900/5"
              }`}
            >
              {testoBottone} ({quanti[key]})
            </button>
          ))}
        </div>
        {(producers ?? []).length > 1 && (
          <select className={`${input} lg:max-w-[12rem]`} value={produttore} onChange={(e) => setProduttore(e.target.value)}>
            <option value="">{t("mkt.jm.allSuppliers")}</option>
            {(producers ?? []).map((pr) => (
              <option key={pr.id} value={pr.id}>{pr.name}</option>
            ))}
          </select>
        )}
        <button
          onClick={() => setEditor({ mode: "create" })}
          className="lg:ml-auto px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer whitespace-nowrap"
        >
          {t("mkt.jm.newProductButton")}
        </button>
      </div>
      <Esito message={message} />

      {tutti.length === 0 ? (
        <p className="text-xs text-slate-500">{t("mkt.jm.catalogEmpty")}</p>
      ) : visibili.length === 0 ? (
        <p className="text-xs text-slate-500">{t("mkt.jm.catalogNoMatch")}</p>
      ) : (
        <>
          {visibili.length !== tutti.length && (
            <p className="text-[11px] text-slate-500">{t("mkt.jm.showingOf", { n: visibili.length, total: tutti.length })}</p>
          )}
          <div className="rounded-xl border border-slate-200 divide-y divide-slate-200">
            {visibili.map((p) => (
              <div key={p.id} className="flex items-center gap-3 p-3">
                <button
                  onClick={() => setEditor({ mode: "edit", id: p.id })}
                  className="flex items-center gap-3 min-w-0 flex-1 text-left cursor-pointer"
                >
                  <ProductThumbnail imageUrl={p.image_url} alt={p.name} className="w-11 h-11 rounded-lg object-cover shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-slate-900 truncate">{p.name}</p>
                    <p className="text-[11px] text-slate-500 truncate">
                      {p.supplier ? (
                        `${
                          p.supplier_source === "CATEGORY"
                            ? t("shopSuppliers.inheritedShort", {
                                name: p.supplier.name,
                                category: p.supplier_category_name ?? "",
                              })
                            : p.supplier.name
                        } · `
                      ) : (
                        <span className="text-amber-700">{t("shopSuppliers.noSupplierShort")} · </span>
                      )}
                      {p.variants.length === 1 ? t("mkt.jm.variantOne") : t("mkt.jm.variantMany", { n: p.variants.length })} ·{" "}
                      {euro(Math.min(...p.variants.map((v) => v.price_cents)))}
                      {p.variants.length > 1 &&
                        Math.max(...p.variants.map((v) => v.price_cents)) !== Math.min(...p.variants.map((v) => v.price_cents)) &&
                        ` – ${euro(Math.max(...p.variants.map((v) => v.price_cents)))}`}
                      {" "}· JavCash {p.credit_discount_percentage}%
                    </p>
                  </div>
                </button>
                <button
                  onClick={() => setEditor({ mode: "edit", id: p.id })}
                  className="px-2.5 py-1 rounded-lg font-semibold border border-slate-300 text-slate-600 hover:bg-slate-100 cursor-pointer"
                >
                  {t("mkt.jm.edit")}
                </button>
                <button
                  onClick={() => spegni.mutate({ id: p.id, status: p.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" })}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-bold border cursor-pointer ${
                    p.status === "ACTIVE"
                      ? "border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10"
                      : " border-slate-300 text-slate-500 hover:bg-slate-100"
                  }`}
                >
                  {p.status === "ACTIVE" ? t("mkt.jm.onSale") : t("mkt.jm.offProduct")}
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {editor?.mode === "create" && (
        <NuovoProdotto
          producers={producers ?? []}
          onClose={() => setEditor(null)}
          onCreated={(p) => {
            setEditor(null);
            setMessage({ ok: true, text: t("mkt.jm.productUploaded", { name: p.name }) });
          }}
        />
      )}
      {inModifica && (
        <ModificaProdotto
          key={inModifica.id}
          product={inModifica}
          producers={producers ?? []}
          onClose={() => setEditor(null)}
        />
      )}
    </Card>
  );
}

/** La finestra comune a creazione e modifica: sopra l'elenco, con la sua
 *  barra fissa in alto, così il pulsante per chiudere resta a portata anche
 *  su un prodotto con cento varianti. */
function Finestra({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full sm:max-w-3xl max-h-[92vh] overflow-y-auto rounded-t-3xl sm:rounded-2xl border border-slate-200 bg-white shadow-2xl animate-scale-up">
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-5 py-3 border-b border-slate-200 bg-white/95 backdrop-blur">
          <h3 className="text-sm font-bold text-slate-900 truncate">{title}</h3>
          <button
            onClick={onClose}
            aria-label={t("common.close")}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-900 hover:bg-slate-900/5 cursor-pointer"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="p-5 space-y-4">{children}</div>
      </div>
    </div>
  );
}

function NuovoProdotto({ producers, onClose, onCreated }: {
  producers: JavMarketProducerRead[];
  onClose: () => void;
  onCreated: (p: JavMarketAdminProductRead) => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ ...PRODOTTO_VUOTO });
  const [variants, setVariants] = useState<VarianteForm[]>([{ label: "Unica", price: "", inventory: "" }]);
  const [categorie, setCategorie] = useState<string[]>([]);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const crea = useMutation({
    mutationFn: async () => {
      const creato = await send<JavMarketAdminProductRead>("/jav-market/products", "POST", {
        name: form.name,
        description: form.description,
        image_url: form.image_url || null,
        images: [],
        status: "ACTIVE",
        credit_discount_percentage: Number(form.credit_discount_percentage) || 0,
        unit_cost_cents: form.unit_cost ? centsFrom(form.unit_cost) : null,
        producer_id: form.producer_id || null,
        variants: variants.map((v) => ({
          label: v.label || "Unica",
          price_cents: centsFrom(v.price),
          inventory: v.inventory === "" ? null : Number(v.inventory),
        })),
      });
      // Le categorie stanno in un altro dominio: si salvano dopo, e solo
      // se ne è stata scelta qualcuna.
      if (categorie.length > 0) await saveProductCategories("jav_market", creato.id, categorie, t("mkt.cat.saveProductFailed"));
      return creato;
    },
    onSuccess: (p) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "jav-market", "products"] });
      queryClient.invalidateQueries({ queryKey: ["shop-categories", "jav_market"] });
      onCreated(p);
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  return (
    <Finestra title={t("mkt.jm.newProduct")} onClose={onClose}>
      <p className="text-[11px] text-slate-500">
        {t("mkt.jm.newProductHint")}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="sm:col-span-2">
          <span className={label}>{t("mkt.jm.nameRequired")}</span>
          <input className={input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <span className={label}>{t("shopSuppliers.productSupplierLabel")}</span>
          <select className={input} value={form.producer_id} onChange={(e) => setForm({ ...form, producer_id: e.target.value })}>
            <option value="">{t("shopSuppliers.productSupplierNone")}</option>
            {producers.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <span className="block text-[10px] text-slate-500 mt-1">
            {form.producer_id ? t("shopSuppliers.productSupplierOwn") : t("shopSuppliers.productSupplierMissing")}
          </span>
        </div>
        <div>
          <span className={label}>{t("mkt.jm.javcashMax")}</span>
          <input
            className={input}
            inputMode="numeric"
            value={form.credit_discount_percentage}
            onChange={(e) => setForm({ ...form, credit_discount_percentage: e.target.value })}
          />
          <span className="block text-[10px] text-slate-500 mt-1">{t("mkt.jm.javcashMaxHint")}</span>
        </div>
        <div className="sm:col-span-3">
          <span className={label}>{t("mkt.jm.description")}</span>
          <textarea
            className={`${input} min-h-[70px]`}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div>
          <span className={label}>{t("mkt.jm.unitCost")}</span>
          <input
            className={input}
            inputMode="decimal"
            value={form.unit_cost}
            onChange={(e) => setForm({ ...form, unit_cost: e.target.value })}
          />
          <span className="block text-[10px] text-slate-500 mt-1">{t("mkt.jm.unitCostHint")}</span>
        </div>
        <div className="sm:col-span-4">
          <span className={label}>{t("mkt.jm.image")}</span>
          <ImmagineProdotto value={form.image_url} onChange={(url) => setForm({ ...form, image_url: url })} />
        </div>
        <div className="sm:col-span-4">
          <ProductCategoriesField shop="jav_market" value={categorie} onChange={setCategorie} />
        </div>
      </div>

      <div className="space-y-2">
        <p className={label}>{t("mkt.jm.variants")}</p>
        {variants.map((v, i) => (
          <div key={i} className="grid grid-cols-1 sm:grid-cols-4 gap-2">
            <input
              className={input}
              placeholder={t("mkt.jm.variantLabelPlaceholder")}
              value={v.label}
              onChange={(e) => setVariants(variants.map((x, j) => (i === j ? { ...x, label: e.target.value } : x)))}
            />
            <input
              className={input}
              inputMode="decimal"
              placeholder={t("mkt.jm.pricePlaceholder")}
              value={v.price}
              onChange={(e) => setVariants(variants.map((x, j) => (i === j ? { ...x, price: e.target.value } : x)))}
            />
            <input
              className={input}
              inputMode="numeric"
              placeholder={t("mkt.jm.stockPlaceholder")}
              value={v.inventory}
              onChange={(e) => setVariants(variants.map((x, j) => (i === j ? { ...x, inventory: e.target.value } : x)))}
            />
            {variants.length > 1 && (
              <button
                onClick={() => setVariants(variants.filter((_, j) => j !== i))}
                className="px-3 py-2 rounded-lg text-xs font-semibold text-rose-400 hover:bg-rose-500/10 cursor-pointer"
              >
                {t("mkt.jm.remove")}
              </button>
            )}
          </div>
        ))}
        <button
          onClick={() => setVariants([...variants, { label: "", price: "", inventory: "" }])}
          className="text-[11px] font-semibold text-brand-600 hover:text-brand-600 cursor-pointer"
        >
          {t("mkt.jm.addVariant")}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-slate-200">
        <button
          onClick={() => crea.mutate()}
          disabled={crea.isPending || !form.name.trim() || variants.every((v) => !v.price)}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {crea.isPending ? t("mkt.jm.uploading") : t("mkt.jm.uploadProduct")}
        </button>
        <button onClick={onClose} className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-slate-900/5 cursor-pointer">
          {t("common.cancel")}
        </button>
        <Esito message={message} />
      </div>
    </Finestra>
  );
}

function ModificaProdotto({ product, producers, onClose }: {
  product: JavMarketAdminProductRead;
  producers: JavMarketProducerRead[];
  onClose: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const invalida = () => queryClient.invalidateQueries({ queryKey: ["admin", "jav-market", "products"] });
  // I campi del prodotto sono una bozza: partono dal prodotto quando la
  // finestra si apre (il componente è montato con key=id) e si salvano con
  // «Salva modifiche». Prezzi e scorte invece si salvano campo per campo.
  const [bozza, setBozza] = useState({
    name: product.name,
    description: product.description,
    credit_discount_percentage: product.credit_discount_percentage,
    producer_id: product.producer_id,
    image_url: product.image_url,
  });
  const [categorie, setCategorie] = useState<string[]>(product.category_ids ?? []);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [filtroVarianti, setFiltroVarianti] = useState("");
  const [prezzoTutte, setPrezzoTutte] = useState("");

  const salva = useMutation({
    mutationFn: async () => {
      await send<JavMarketAdminProductRead>(`/jav-market/products/${product.id}`, "PATCH", {
        ...bozza,
        producer_id: bozza.producer_id || null,
        image_url: bozza.image_url || null,
      });
      if (!sameCategorySelection(categorie, product.category_ids ?? [])) {
        await saveProductCategories("jav_market", product.id, categorie, t("mkt.cat.saveProductFailed"));
      }
    },
    onSuccess: () => {
      invalida();
      queryClient.invalidateQueries({ queryKey: ["shop-categories", "jav_market"] });
      onClose();
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  const salvaVariante = useMutation({
    mutationFn: ({ id, price_cents, inventory }: { id: string; price_cents: number; inventory: number | null }) =>
      send(`/jav-market/variants/${id}`, "PATCH", { price_cents, inventory }),
    onSuccess: invalida,
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  // Un prezzo per tutte le varianti: in un catalogo di abiti un capo ha decine di
  // taglie e colori allo stesso prezzo, e scriverlo cento volte non è un
  // lavoro. A gruppi di dieci per non sommergere il server.
  const applicaATutte = useMutation({
    mutationFn: async (price_cents: number) => {
      const daFare = product.variants;
      for (let i = 0; i < daFare.length; i += 10) {
        await Promise.all(
          daFare.slice(i, i + 10).map((v) =>
            send(`/jav-market/variants/${v.id}`, "PATCH", { price_cents, inventory: v.inventory })
          )
        );
      }
      return daFare.length;
    },
    onSuccess: (n) => {
      setPrezzoTutte("");
      setMessage({ ok: true, text: t("mkt.jm.priceApplied", { n }) });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
    onSettled: invalida,
  });
  const cambiaStato = useMutation({
    mutationFn: () =>
      send<JavMarketAdminProductRead>(`/jav-market/products/${product.id}`, "PATCH", {
        status: product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE",
      }),
    onSuccess: invalida,
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  const filtro = filtroVarianti.trim().toLowerCase();
  const varianti = product.variants.filter(
    (v) => !filtro || v.label.toLowerCase().includes(filtro) || (v.sku ?? "").toLowerCase().includes(filtro)
  );
  const prezzoValido = centsFrom(prezzoTutte) > 0;

  return (
    <Finestra title={t("mkt.jm.editTitle", { name: product.name })} onClose={onClose}>
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`px-2 py-0.5 rounded-md text-[11px] font-bold ${
            product.status === "ACTIVE" ? "bg-emerald-500/15 text-emerald-400" : " bg-slate-900/5 text-slate-500"
          }`}
        >
          {product.status === "ACTIVE" ? t("mkt.jm.onSale") : t("mkt.jm.offHidden")}
        </span>
        <button
          onClick={() => cambiaStato.mutate()}
          disabled={cambiaStato.isPending}
          className="px-2.5 py-1 rounded-lg font-semibold border border-slate-300 text-slate-600 hover:bg-slate-100 cursor-pointer disabled:opacity-40"
        >
          {product.status === "ACTIVE" ? t("mkt.jm.turnOff") : t("mkt.jm.putOnSale")}
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="sm:col-span-2">
          <span className={label}>{t("mkt.jm.name")}</span>
          <input className={input} value={bozza.name} onChange={(e) => setBozza({ ...bozza, name: e.target.value })} />
        </div>
        <div>
          <span className={label}>{t("shopSuppliers.productSupplierLabel")}</span>
          <select
            className={input}
            value={bozza.producer_id ?? ""}
            onChange={(e) => setBozza({ ...bozza, producer_id: e.target.value || null })}
          >
            <option value="">{t("shopSuppliers.productSupplierNone")}</option>
            {producers.map((pr) => (
              <option key={pr.id} value={pr.id}>{pr.name}</option>
            ))}
          </select>
          <span className="block text-[10px] text-slate-500 mt-1">
            {bozza.producer_id
              ? t("shopSuppliers.productSupplierOwn")
              : product.supplier_source === "CATEGORY" && product.supplier
                ? t("shopSuppliers.productSupplierInherited", {
                    name: product.supplier.name,
                    category: product.supplier_category_name ?? "",
                  })
                : t("shopSuppliers.productSupplierMissing")}
          </span>
        </div>
        <div className="sm:col-span-2">
          <span className={label}>{t("mkt.jm.description")}</span>
          <textarea
            className={`${input} min-h-[70px]`}
            value={bozza.description}
            onChange={(e) => setBozza({ ...bozza, description: e.target.value })}
          />
        </div>
        <div>
          <span className={label}>{t("mkt.jm.javcashMax")}</span>
          <input
            className={input}
            inputMode="numeric"
            value={String(bozza.credit_discount_percentage)}
            onChange={(e) => setBozza({ ...bozza, credit_discount_percentage: Number(e.target.value) || 0 })}
          />
        </div>
      </div>
      <div>
        <span className={label}>{t("mkt.jm.mainImage")}</span>
        <ImmagineProdotto value={bozza.image_url ?? ""} onChange={(url) => setBozza({ ...bozza, image_url: url || null })} />
      </div>
      <ProductCategoriesField shop="jav_market" value={categorie} onChange={setCategorie} />
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => salva.mutate()}
          disabled={salva.isPending || !bozza.name.trim()}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {salva.isPending ? t("mkt.jm.saving") : t("mkt.jm.saveChanges")}
        </button>
        <button onClick={onClose} className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-slate-900/5 cursor-pointer">
          {t("common.cancel")}
        </button>
      </div>

      <div className="space-y-2 pt-4 border-t border-slate-200">
        <p className={label}>
          {t("mkt.jm.pricesStock")} · {product.variants.length === 1 ? t("mkt.jm.variantOne") : t("mkt.jm.variantMany", { n: product.variants.length })} ·{" "}
          {t("mkt.jm.savedOnBlur")}
        </p>
        {product.variants.length > 1 && (
          <div className="flex flex-wrap items-center gap-2 p-3 rounded-xl bg-slate-900/5">
            <span className=" text-slate-600">{t("mkt.jm.samePriceAll")}</span>
            <input
              className={`${input} max-w-[8rem]`}
              inputMode="decimal"
              placeholder={t("mkt.jm.pricePlaceholder")}
              value={prezzoTutte}
              onChange={(e) => setPrezzoTutte(e.target.value)}
            />
            <button
              onClick={() => applicaATutte.mutate(centsFrom(prezzoTutte))}
              disabled={!prezzoValido || applicaATutte.isPending}
              className="px-3 py-2 rounded-lg bg-brand-600 hover:bg-brand-500 text-[11px] font-semibold text-white cursor-pointer disabled:opacity-40"
            >
              {applicaATutte.isPending ? t("mkt.jm.applying") : t("mkt.jm.applyTo", { n: product.variants.length })}
            </button>
          </div>
        )}
        {product.variants.length > 8 && (
          <input
            className={input}
            placeholder={t("mkt.jm.variantSearch")}
            value={filtroVarianti}
            onChange={(e) => setFiltroVarianti(e.target.value)}
          />
        )}
        <div className="space-y-2">
          {varianti.map((v) => (
            // La key cambia con prezzo e scorta: dopo «Applica a tutte» i campi
            // ripartono dal valore salvato invece di tenere quello vecchio.
            <div key={`${v.id}-${v.price_cents}-${v.inventory}`} className="grid grid-cols-1 sm:grid-cols-[1fr_7rem_7rem] gap-2 items-center">
              <div className="flex items-center gap-2 min-w-0">
                {v.image_url && (
                  <ProductThumbnail imageUrl={v.image_url} alt="" className="w-8 h-8 rounded-md object-cover shrink-0" />
                )}
                <div className="min-w-0">
                  <p className="text-xs text-slate-700 truncate">{v.label}</p>
                  {v.sku && <p className="text-[10px] text-slate-500 truncate">{v.sku}</p>}
                </div>
              </div>
              <input
                className={input}
                inputMode="decimal"
                aria-label={t("mkt.jm.priceOf", { label: v.label })}
                defaultValue={(v.price_cents / 100).toString()}
                onBlur={(e) => {
                  const cents = centsFrom(e.target.value);
                  if (cents > 0 && cents !== v.price_cents) {
                    salvaVariante.mutate({ id: v.id, price_cents: cents, inventory: v.inventory });
                  }
                }}
              />
              <input
                className={input}
                inputMode="numeric"
                placeholder={t("mkt.jm.stock")}
                aria-label={t("mkt.jm.stockOf", { label: v.label })}
                defaultValue={v.inventory === null ? "" : String(v.inventory)}
                onBlur={(e) => {
                  const inventory = e.target.value === "" ? null : Number(e.target.value);
                  if (inventory !== v.inventory) {
                    salvaVariante.mutate({ id: v.id, price_cents: v.price_cents, inventory });
                  }
                }}
              />
            </div>
          ))}
          {varianti.length === 0 && <p className="text-xs text-slate-500">{t("mkt.jm.variantNoMatch")}</p>}
        </div>
      </div>
      <Esito message={message} />
    </Finestra>
  );
}


// --- Fornitori da avvisare ---------------------------------------------------

/** Ottobre 2026: gli ordini pagati raccolti per fornitore. Invece di un'email
 *  per ogni ordine, il fornitore ne riceve una sola con tutti i suoi --
 *  ognuno con il suo indirizzo di consegna -- che l'amministratore rilegge
 *  e può correggere prima di premere «Invia». Gli importi non ci sono mai:
 *  la lettera la scrive il server, e il fornitore non deve vedere i prezzi
 *  di vendita. */
function variante(label: string | null): string {
  return label && label !== "Unica" ? ` – ${label}` : "";
}

function FornitoriDaAvvisare() {
  const { t } = useI18n();
  const { data: queue, error } = useQuery({
    queryKey: ["admin", "jav-market", "supplier-queue"],
    queryFn: () => get<JavMarketSupplierQueue>("/jav-market/supplier-queue"),
  });
  const [bozzaDi, setBozzaDi] = useState<{ id: string; name: string } | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const fornitori = queue?.suppliers ?? [];
  const senzaFornitore = queue?.unassigned ?? [];

  return (
    <Card title={t("shopSuppliers.queueTitle")} subtitle={t("shopSuppliers.queueSubtitle")}>
      {error && <p className="text-xs text-rose-400">{(error as Error).message}</p>}
      <Esito message={message} />
      {!queue ? (
        <p className="text-xs text-slate-500">{t("shopSuppliers.loading")}</p>
      ) : fornitori.length === 0 ? (
        <p className="text-xs text-slate-500">{t("shopSuppliers.queueEmpty")}</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {fornitori.map((f) => (
            <div key={f.producer.id} className="rounded-xl border border-slate-200 p-4 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-bold text-slate-900 truncate">{f.producer.name}</p>
                  <p className="text-[11px] text-slate-500 truncate">
                    {f.producer.email ?? <span className="text-amber-700">{t("shopSuppliers.noEmail")}</span>}
                    {!f.producer.active && ` · ${t("shopSuppliers.inactive")}`}
                  </p>
                </div>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 text-amber-700 border-amber-500/20 shrink-0">
                  {t("shopSuppliers.queueCounts", { orders: f.order_count, pieces: f.piece_count })}
                </span>
              </div>
              <ul className="space-y-1">
                {f.orders.map((o) => (
                  <li key={o.id} className="text-[11px] text-slate-600">
                    <span className="font-semibold text-slate-800">#{o.order_code}</span> · {o.recipient_name}, {o.city}
                    {" — "}
                    {o.items.map((i) => `${i.quantity} × ${i.product_name}${variante(i.variant_label)}`).join(", ")}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => {
                  setMessage(null);
                  setBozzaDi({ id: f.producer.id, name: f.producer.name });
                }}
                className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer"
              >
                {t("shopSuppliers.prepareEmail")}
              </button>
            </div>
          ))}
        </div>
      )}

      {senzaFornitore.length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 space-y-1">
          <p className="text-xs font-semibold text-amber-800">
            {t("shopSuppliers.unassignedTitle", { n: senzaFornitore.length })}
          </p>
          <ul className="space-y-0.5">
            {senzaFornitore.map((u) => (
              <li key={u.item_id} className="text-[11px] text-amber-900">
                #{u.order_code} · {u.quantity} × {u.product_name}
                {variante(u.variant_label)}
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-amber-800">{t("shopSuppliers.unassignedHint")}</p>
        </div>
      )}

      <StoricoInvii />

      {bozzaDi && (
        <PreparaEmail
          producer={bozzaDi}
          onClose={() => setBozzaDi(null)}
          onSent={(text) => {
            setBozzaDi(null);
            setMessage({ ok: true, text });
          }}
        />
      )}
    </Card>
  );
}

function PreparaEmail({ producer, onClose, onSent }: {
  producer: { id: string; name: string };
  onClose: () => void;
  onSent: (text: string) => void;
}) {
  const { t } = useI18n();
  // Sempre fresca all'apertura (gcTime 0) e mai ricaricata sotto le mani di
  // chi sta correggendo il testo (niente refetch al ritorno sulla finestra).
  const { data: draft, error } = useQuery({
    queryKey: ["admin", "jav-market", "supplier-draft", producer.id],
    queryFn: () => get<JavMarketSupplierDraft>(`/jav-market/supplier-queue/${producer.id}/draft`),
    gcTime: 0,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  return (
    <Finestra title={t("shopSuppliers.modalTitle", { name: producer.name })} onClose={onClose}>
      {error ? (
        <p className="text-xs text-rose-400">{(error as Error).message}</p>
      ) : !draft ? (
        <p className="text-xs text-slate-500">{t("shopSuppliers.loading")}</p>
      ) : (
        // key: i campi partono dalla bozza, senza un effetto che li sincronizzi.
        <ModificaEmail key={draft.item_ids.join(",")} draft={draft} onClose={onClose} onSent={onSent} />
      )}
    </Finestra>
  );
}

function ModificaEmail({ draft, onClose, onSent }: {
  draft: JavMarketSupplierDraft;
  onClose: () => void;
  onSent: (text: string) => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [to, setTo] = useState(draft.to_email);
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body_text);
  const [errore, setErrore] = useState<string | null>(null);

  const invia = useMutation({
    mutationFn: () =>
      send(`/jav-market/supplier-queue/${draft.producer_id}/send`, "POST", {
        to_email: to.trim(),
        subject: subject.trim(),
        body_text: body,
        item_ids: draft.item_ids,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "jav-market"] });
      onSent(t("shopSuppliers.sent", { name: draft.producer_name, email: to.trim() }));
    },
    onError: (err: unknown) => {
      setErrore((err as Error).message);
      // Se nel frattempo gli ordini sono partiti, la coda sotto lo deve dire.
      queryClient.invalidateQueries({ queryKey: ["admin", "jav-market", "supplier-queue"] });
    },
  });

  return (
    <>
      <p className="text-[11px] text-slate-500">
        {t("shopSuppliers.includedOrders", {
          n: draft.order_codes.length,
          codes: draft.order_codes.map((c) => `#${c}`).join(", "),
        })}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <span className={label}>{t("shopSuppliers.fromLabel")}</span>
          <p className="text-xs text-slate-700 py-2">{draft.from_email || t("shopSuppliers.fromDefault")}</p>
        </div>
        <div>
          <span className={label}>{t("shopSuppliers.toLabel")}</span>
          <input className={input} type="email" value={to} onChange={(e) => setTo(e.target.value)} />
          {!draft.to_email && (
            <span className="block text-[10px] text-amber-700 mt-1">{t("shopSuppliers.toMissing")}</span>
          )}
        </div>
        <div className="sm:col-span-2">
          <span className={label}>{t("shopSuppliers.subjectLabel")}</span>
          <input className={input} value={subject} maxLength={255} onChange={(e) => setSubject(e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <span className={label}>{t("shopSuppliers.bodyLabel")}</span>
          <textarea
            className={`${input} min-h-[320px] leading-relaxed`}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <span className="block text-[10px] text-slate-500 mt-1">{t("shopSuppliers.bodyHint")}</span>
        </div>
      </div>
      {errore && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-500 text-xs">{errore}</div>
      )}
      <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-slate-200">
        <button
          onClick={() => {
            setErrore(null);
            invia.mutate();
          }}
          disabled={invia.isPending || !to.trim() || !subject.trim() || !body.trim()}
          className="px-5 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {invia.isPending ? t("shopSuppliers.sending") : t("shopSuppliers.send")}
        </button>
        <button onClick={onClose} className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-slate-900/5 cursor-pointer">
          {t("shopSuppliers.cancel")}
        </button>
        {body !== draft.body_text && (
          <button
            onClick={() => setBody(draft.body_text)}
            className="text-[11px] font-semibold text-brand-600 cursor-pointer"
          >
            {t("shopSuppliers.resetText")}
          </button>
        )}
      </div>
    </>
  );
}

/** Lo storico: a chi è partito cosa e quando, con il testo esatto. */
function StoricoInvii() {
  const { t, fmt } = useI18n();
  const [aperto, setAperto] = useState(false);
  const [espanso, setEspanso] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: ["admin", "jav-market", "supplier-dispatches"],
    queryFn: () => get<JavMarketSupplierDispatchRead[]>("/jav-market/supplier-dispatches"),
    enabled: aperto,
  });

  return (
    <div className="pt-3 border-t border-slate-200 space-y-2">
      <button onClick={() => setAperto(!aperto)} className="text-xs font-semibold text-brand-600 cursor-pointer">
        {aperto ? t("shopSuppliers.historyHide") : t("shopSuppliers.historyShow")}
      </button>
      {aperto &&
        (!data ? (
          <p className="text-xs text-slate-500">{t("shopSuppliers.loading")}</p>
        ) : data.length === 0 ? (
          <p className="text-xs text-slate-500">{t("shopSuppliers.historyEmpty")}</p>
        ) : (
          <div className="rounded-xl border border-slate-200 divide-y divide-slate-200">
            {data.map((d) => (
              <div key={d.id} className="px-3 py-2">
                <button
                  onClick={() => setEspanso(espanso === d.id ? null : d.id)}
                  className="w-full text-left cursor-pointer"
                >
                  <p className="text-xs text-slate-800">
                    <span className="font-semibold">{d.producer_name}</span>
                    {" · "}
                    {fmt.date(new Date(d.sent_at), {
                      day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
                    })}
                    {d.to_email ? ` · ${d.to_email}` : ""}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    {d.subject} · {t("shopSuppliers.historyCounts", { orders: d.order_count, pieces: d.piece_count })}
                    {d.order_codes.length > 0 && ` (${d.order_codes.map((c) => `#${c}`).join(", ")})`}
                    {" · "}
                    {t.dyn(`shopSuppliers.source.${d.source}`, d.source)}
                    {d.sent_by_email ? ` · ${d.sent_by_email}` : ""}
                  </p>
                </button>
                {espanso === d.id && d.body_text && (
                  <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-slate-900/5 p-3 text-[11px] text-slate-700 font-sans">
                    {d.body_text}
                  </pre>
                )}
              </div>
            ))}
          </div>
        ))}
    </div>
  );
}

// --- Ordini ----------------------------------------------------------------

/** Session 88: gli ordini del negozio con tutto quello che serve per evaderli
 *  -- cosa ha comprato il cliente (variante compresa), se ha pagato, dove
 *  spedire, le sue note -- e le azioni nell'ordine in cui servono: conferma
 *  del bonifico, l'invio per email alle aziende che producono, spedito con il tracking (il cliente riceve
 *  l'email), consegnato. Prima questo riquadro mostrava solo nome e totale, e
 *  l'indirizzo non si vedeva da nessuna parte. */
type FiltroOrdini = "DA_SPEDIRE" | "DA_PAGARE" | "SPEDITI" | "ANNULLATI" | "TUTTI";

function faseOrdine(o: JavMarketOrderRead): FiltroOrdini {
  if (o.status === "CANCELLED") return "ANNULLATI";
  if (o.status === "AWAITING_PAYMENT") return "DA_PAGARE";
  return o.shipped_at || o.delivered_at ? "SPEDITI" : "DA_SPEDIRE";
}

function Ordini() {
  const { t } = useI18n();
  const { data: orders } = useQuery({
    queryKey: ["admin", "jav-market", "orders"],
    queryFn: () => get<JavMarketOrderRead[]>("/jav-market/orders"),
  });
  const [filtro, setFiltro] = useState<FiltroOrdini>("DA_SPEDIRE");
  const tutti = orders ?? [];
  const conteggio = (f: FiltroOrdini) => (f === "TUTTI" ? tutti.length : tutti.filter((o) => faseOrdine(o) === f).length);
  const visibili = filtro === "TUTTI" ? tutti : tutti.filter((o) => faseOrdine(o) === filtro);

  return (
    <Card title={t("mkt.jm.ordersTitle")} subtitle={t("mkt.jm.ordersSubtitle")}>
      <div className="flex flex-wrap gap-1.5">
        {(
          [
            ["DA_SPEDIRE", t("mkt.jm.filterToShip")],
            ["DA_PAGARE", t("mkt.jm.awaitingPayment")],
            ["SPEDITI", t("mkt.jm.filterShipped")],
            ["ANNULLATI", t("mkt.jm.filterCancelled")],
            ["TUTTI", t("mkt.jm.filterAll")],
          ] as const
        ).map(([key, testo]) => (
          <button
            key={key}
            onClick={() => setFiltro(key)}
            className={`px-2.5 py-1.5 rounded-lg text-[11px] font-semibold border cursor-pointer ${
              filtro === key
                ? "border-brand-500/50 bg-brand-500/15 text-brand-700"
                : " border-slate-300 text-slate-600 hover:bg-slate-900/5"
            }`}
          >
            {testo} ({conteggio(key)})
          </button>
        ))}
      </div>
      {visibili.length === 0 ? (
        <p className="text-xs text-slate-500">{t("mkt.jm.ordersEmpty")}</p>
      ) : (
        <div className="space-y-3">
          {visibili.map((o) => (
            <OrdineCard key={o.id} order={o} />
          ))}
        </div>
      )}
    </Card>
  );
}

function OrdineCard({ order: o }: { order: JavMarketOrderRead }) {
  const { t, fmt } = useI18n();
  const euro = (cents: number) => fmt.euro(cents);
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [spedizione, setSpedizione] = useState<{ tracking_company: string; tracking_number: string; tracking_url: string } | null>(null);
  const [annulla, setAnnulla] = useState<string | null>(null);
  // Tutto il pannello, non solo gli ordini: pagare o mandare un ordine
  // cambia anche «Fornitori da avvisare».
  const invalida = () => queryClient.invalidateQueries({ queryKey: ["admin", "jav-market"] });
  const azione = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown; ok: string }) =>
      send<JavMarketOrderRead>(`/jav-market/orders/${o.id}/${path}`, "POST", body ?? {}),
    onSuccess: (_r, vars) => {
      setMessage({ ok: true, text: vars.ok });
      setSpedizione(null);
      setAnnulla(null);
      invalida();
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  const fase = faseOrdine(o);
  const extra = o as JavMarketOrderRead & { tracking_company?: string | null };

  return (
    <div className="rounded-xl border border-slate-200 p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-bold text-slate-900">
            #{o.order_code} · {o.customer_display_name}
          </p>
          <p className="text-[11px] text-slate-500">
            {fmt.date(new Date(o.created_at), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
            {" · "}{t("mkt.jm.totalLower")} {euro(o.amount_cents)}
            {o.credit_applied_cents > 0 && ` (${t("mkt.jm.ofWhichJavCash", { amount: euro(o.credit_applied_cents) })})`}
            {" · "}{t("mkt.jm.bankTransferLower")}
          </p>
        </div>
        <span
          className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
            fase === "DA_SPEDIRE"
              ? "bg-amber-500/10 text-amber-700 border-amber-500/20"
              : fase === "SPEDITI"
                ? "bg-sky-500/10 text-sky-400 border-sky-500/20"
                : fase === "DA_PAGARE"
                  ? "bg-slate-50 text-slate-400 border-slate-200"
                  : "bg-rose-500/10 text-rose-400 border-rose-500/20"
          }`}
        >
          {fase === "DA_SPEDIRE"
            ? t("mkt.jm.paidToShip")
            : fase === "SPEDITI"
              ? o.delivered_at ? t("mkt.jm.delivered") : t("mkt.jm.shipped")
              : fase === "DA_PAGARE"
                ? t("mkt.jm.awaitingPayment")
                : t("mkt.jm.cancelled")}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-lg bg-slate-900/5 p-3 space-y-1">
          <p className={label}>{t("mkt.jm.whatBought")}</p>
          {(o.items ?? []).map((i) => (
            <div key={i.id} className="text-xs text-slate-700">
              <span className="font-semibold">{i.quantity} ×</span> {i.product_name}
              {i.variant_label && i.variant_label !== "Unica" ? ` — ${i.variant_label}` : ""}
              <span className="text-slate-500"> · {euro(i.line_total_cents)}</span>
              {(i as { producer_name?: string | null }).producer_name && (
                <span className="text-slate-500"> · {(i as { producer_name?: string | null }).producer_name}</span>
              )}
            </div>
          ))}
          <p className="text-[11px] text-slate-500 pt-1">
            {t("mkt.jm.goods")} {euro(o.items_cents)} · {t("mkt.jm.shippingLower")} {euro(o.shipping_cents)}
            {(o.vat_amount_cents ?? 0) > 0 && ` · ${t("mkt.jm.vat")} ${euro(o.vat_amount_cents ?? 0)}`}
          </p>
        </div>
        <div className="rounded-lg bg-slate-900/5 p-3 space-y-1">
          <p className={label}>{t("mkt.jm.whereShip")}</p>
          <p className="text-xs text-slate-800 select-all leading-relaxed">
            {o.recipient_name}
            <br />
            {o.address_line1}
            {o.address_line2 ? `, ${o.address_line2}` : ""}
            <br />
            {o.postal_code} {o.city} ({o.province})
          </p>
          {o.recipient_phone && <p className="text-[11px] text-slate-400">{t("mkt.jm.tel")} {o.recipient_phone}</p>}
          {o.note && <p className=" text-amber-700">{t("mkt.jm.customerNote")}: {o.note}</p>}
          {(o.tracking_number || extra.tracking_company) && (
            <p className="text-[11px] text-sky-400">
              {extra.tracking_company ? `${extra.tracking_company} · ` : ""}
              {o.tracking_url ? (
                <a href={o.tracking_url} target="_blank" rel="noopener noreferrer" className="underline">
                  {o.tracking_number ?? t("mkt.jm.tracking")}
                </a>
              ) : (
                o.tracking_number
              )}
            </p>
          )}
        </div>
      </div>
      {o.status === "PAID" && (o.forwarded_at || o.forward_error) && (
        <p className={`text-[11px] ${o.forward_error ? "text-amber-700" : "text-slate-400"}`}>
          {o.forwarded_at && `${t("mkt.jm.forwardedOn", { date: new Date(o.forwarded_at).toLocaleString(fmt.tag) })} `}
          {o.forward_error && t("mkt.jm.toFix", { error: o.forward_error })}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {o.status === "AWAITING_PAYMENT" && o.payment_method === "BANK_TRANSFER" && (
          <button
            onClick={() => azione.mutate({ path: "confirm-payment", ok: t("mkt.jm.okPaid") })}
            disabled={azione.isPending}
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 cursor-pointer disabled:opacity-40"
          >
            {t("mkt.jm.confirmTransfer")}
          </button>
        )}
        {/* Solo se resta qualcosa da mandare: le righe già partite (da qui o
            da «Fornitori da avvisare») non ripartono. */}
        {o.status === "PAID" && !o.shipped_at && (o.supplier_pending_count ?? 1) > 0 && (
          <button
            onClick={() => azione.mutate({ path: "forward", ok: t("mkt.jm.okForwarded") })}
            disabled={azione.isPending}
            className="px-3 py-1.5 rounded-lg font-semibold border border-slate-300 text-slate-700 hover:bg-slate-100 cursor-pointer disabled:opacity-40"
          >
            {o.forwarded_at ? t("shopSuppliers.forwardRemaining") : t("mkt.jm.forwardByEmail")}
          </button>
        )}
        {fase === "DA_SPEDIRE" && (
          <button
            onClick={() => setSpedizione(spedizione ? null : { tracking_company: "", tracking_number: "", tracking_url: "" })}
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-brand-600 hover:bg-brand-500 text-white cursor-pointer"
          >
            {t("mkt.jm.markShipped")}
          </button>
        )}
        {o.shipped_at && !o.delivered_at && o.status === "PAID" && (
          <button
            onClick={() => azione.mutate({ path: "delivered", ok: t("mkt.jm.okDelivered") })}
            disabled={azione.isPending}
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold border border-sky-500/30 text-sky-400 hover:bg-sky-500/10 cursor-pointer disabled:opacity-40"
          >
            {t("mkt.jm.markDelivered")}
          </button>
        )}
        {o.status === "AWAITING_PAYMENT" && (
          <button
            onClick={() => setAnnulla(annulla === null ? "" : null)}
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold border border-rose-500/30 text-rose-400 hover:bg-rose-500/10 cursor-pointer"
          >
            {t("mkt.jm.cancelOrder")}
          </button>
        )}
      </div>

      {spedizione && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 items-end">
          <div>
            <span className={label}>{t("mkt.jm.carrier")}</span>
            <input className={input} placeholder={t("mkt.jm.carrierPlaceholder")} value={spedizione.tracking_company}
              onChange={(e) => setSpedizione({ ...spedizione, tracking_company: e.target.value })} />
          </div>
          <div>
            <span className={label}>{t("mkt.jm.trackingNumber")}</span>
            <input className={input} value={spedizione.tracking_number}
              onChange={(e) => setSpedizione({ ...spedizione, tracking_number: e.target.value })} />
          </div>
          <div>
            <span className={label}>{t("mkt.jm.trackingLink")}</span>
            <input className={input} placeholder="https://…" value={spedizione.tracking_url}
              onChange={(e) => setSpedizione({ ...spedizione, tracking_url: e.target.value })} />
          </div>
          <button
            onClick={() => azione.mutate({ path: "ship", body: spedizione, ok: t("mkt.jm.okShipped") })}
            disabled={azione.isPending}
            className="px-3 py-2 rounded-lg text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white cursor-pointer disabled:opacity-40"
          >
            {azione.isPending ? t("mkt.jm.saving") : t("mkt.jm.confirmShipping")}
          </button>
        </div>
      )}
      {annulla !== null && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[200px]">
            <span className={label}>{t("mkt.jm.cancelReason")}</span>
            <input className={input} value={annulla} onChange={(e) => setAnnulla(e.target.value)} autoFocus />
          </div>
          <button
            onClick={() => azione.mutate({ path: "cancel", body: { reason: annulla }, ok: t("mkt.jm.okCancelled") })}
            disabled={azione.isPending || !annulla.trim()}
            className="px-3 py-2 rounded-lg text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white cursor-pointer disabled:opacity-40"
          >
            {t("mkt.jm.confirmCancel")}
          </button>
        </div>
      )}
      <Esito message={message} />
    </div>
  );
}

export function AdminJavMarketPanel() {
  return (
    <div className="space-y-6">
      <Impostazioni />
      <Produttori />
      <CategorieEFornitori />
      <Catalogo />
      <FornitoriDaAvvisare />
      <Ordini />
    </div>
  );
}
