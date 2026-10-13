"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { vatLineLabel } from "@/lib/product-audience";
import { AdminImportedProductsPanel } from "@/components/admin-imported-products-panel";
import { Pagination, usePagination } from "@/components/pagination";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { ProductCategoriesField, saveProductCategories, sameCategorySelection, ManageCategoriesButton } from "@/components/shop-categories-card";
import type {
  AliexpressCatalogPage,
  AliexpressCatalogProduct,
  AliexpressOrderRead,
  AliexpressProductAdminRead,
  AliexpressSettingsRead,
} from "@/lib/types";

type Tab = "orders" | "products" | "catalog" | "manual" | "settings";

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function money(amount: number | null | undefined, currency: string | null | undefined): string {
  if (amount === null || amount === undefined) return "—";
  return `${amount.toFixed(2)} ${currency ?? ""}`.trim();
}

/** Same formula as the server (aliexpress_dropshipping/pricing.py), to show a
 *  price while the administrator types; the server's figure is what counts. */
function salePriceCents(
  cost: number | null, price: number,
  rules: Pick<AliexpressSettingsRead, "currency_rate" | "price_basis" | "markup_fixed_cents" | "price_rounding" | "shipping_mode" | "shipping_minimum_cents">,
  markupPct: number,
): number {
  const base = rules.price_basis === "COST" && cost !== null && cost > 0 ? cost : price;
  let cents = base * Number(rules.currency_rate) * 100 * (1 + markupPct / 100) + Number(rules.markup_fixed_cents);
  if (rules.shipping_mode === "INCLUDED") cents += Number(rules.shipping_minimum_cents);
  const rounded = Math.ceil(Math.round(cents * 1e6) / 1e6);
  if (rules.price_rounding === "NONE") return rounded;
  const target = Number(rules.price_rounding);
  const euros = Math.floor(rounded / 100);
  return rounded % 100 <= target ? euros * 100 + target : (euros + 1) * 100 + target;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("it-IT", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** AliExpress has no admin page for an order, only the public page of the
 *  article: that is the one link worth offering. The server sends the real
 *  one when it has it; this is the fallback shape of an item link. */
function aliexpressItemUrl(url: string | null | undefined, productId: string | null | undefined): string | null {
  return url || (productId ? `https://www.aliexpress.com/item/${productId}.html` : null);
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

function postJson<T>(url: string, body?: unknown, method = "POST"): Promise<T> {
  return getJson<T>(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

const card = "glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70";
const input = "w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500";
const label = "block text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-1";
const btnPrimary = "px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50";
const btnGhost = "px-3 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-xs font-semibold text-slate-300 light:text-slate-600 transition cursor-pointer disabled:opacity-50";

function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{message}</div>;
}

/** Marketplace 3 -- AliExpress dropshipping API (Session 71).
 *
 *  Until now this shop was only the hand-made list of the old
 *  imported_products plugin: someone copied a product from AliExpress by
 *  hand and followed the order outside the application. It now works like
 *  the other two Marketplaces (admin-cj-panel.tsx, admin-shopify-panel.tsx):
 *  products are searched in the AliExpress catalog through the Dropshipping
 *  API, re-priced in euro with our markup, sold in the customer Shop with
 *  the checkout of every other Marketplace, then the paid order is placed at
 *  AliExpress and followed until delivery. The hand-made list stays here as
 *  its own tab -- what has already been sold that way must keep working --
 *  but it is no longer the main screen. Confirming bank transfers stays in
 *  the unified "Ordini".
 */
const APP_URL = (process.env.NEXT_PUBLIC_APP_URL || "https://jav.ecodo.ai").replace(/\/$/, "");

export function AdminAliexpressPanel() {
  const { data: settings } = useQuery({
    queryKey: ["admin", "aliexpress", "settings"],
    queryFn: () => getJson<AliexpressSettingsRead>("/api/proxy/aliexpress/settings"),
  });
  const [tab, setTab] = useState<Tab | null>(null);
  const configured = !!settings?.connected;
  const activeTab: Tab = tab ?? (settings && !configured ? "settings" : "orders");

  const tabs: { key: Tab; label: string }[] = [
    { key: "orders", label: "Ordini" },
    { key: "products", label: "Prodotti in vendita" },
    { key: "catalog", label: "Catalogo AliExpress" },
    { key: "manual", label: "Prodotti inseriti a mano" },
    { key: "settings", label: "Impostazioni" },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white light:text-slate-900">Prodotti AliExpress Dropshipping</h2>
          <p className="text-xs text-slate-400 light:text-slate-500 mt-0.5">
            Prodotti presi dal catalogo AliExpress e venduti nello Shop: cerca, importa, prezza, invia gli ordini ad AliExpress e seguili fino alla consegna.
          </p>
        </div>
        {settings && (
          <div className="flex flex-wrap gap-2 text-[11px] font-semibold">
            <span className={`px-2.5 py-1 rounded-full border ${settings.enabled ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-slate-500/10 border-slate-500/30 text-slate-400"}`}>
              {settings.enabled ? "Shop attivo" : "Shop spento"}
            </span>
            {settings.connected && (
              <span className="px-2.5 py-1 rounded-full border bg-white/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600">
                {settings.account_label ?? "Account collegato"}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer ${
              activeTab === t.key
                ? "bg-orange-600 border-orange-600 text-white"
                : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
            }`}
          >
            {t.label}
          </button>
        ))}
        <span className="ml-auto">
          <ManageCategoriesButton shops={[{ key: "aliexpress", label: "AliExpress" }]} />
        </span>
      </div>

      {activeTab === "settings" && (settings ? <SettingsForm settings={settings} /> : <div className={`${card} h-40 animate-pulse`} />)}
      {activeTab === "catalog" && <CatalogTab settings={settings} configured={configured} onImported={() => setTab("products")} />}
      {activeTab === "products" && (
        <>
          <ProductsTab settings={settings} />
        </>
      )}
      {activeTab === "orders" && <OrdersTab settings={settings} />}
      {activeTab === "manual" && <ManualTab />}
    </div>
  );
}

// --- Impostazioni -----------------------------------------------------------------------

function SettingsForm({ settings }: { settings: AliexpressSettingsRead }) {
  const queryClient = useQueryClient();
  const [appSecret, setAppSecret] = useState("");
  const [form, setForm] = useState<AliexpressSettingsRead>(settings);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<"connect" | "test" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const body = {
        app_key: form.app_key ?? "",
        enabled: form.enabled,
        currency_rate: Number(form.currency_rate),
        price_basis: form.price_basis,
        markup_percentage: Number(form.markup_percentage),
        markup_fixed_cents: Number(form.markup_fixed_cents),
        price_rounding: form.price_rounding,
        shipping_mode: form.shipping_mode,
        shipping_minimum_cents: Number(form.shipping_minimum_cents),
        shipping_days: form.shipping_days || null,
        ship_to_country: form.ship_to_country,
        target_currency: form.target_currency,
        target_language: form.target_language,
        default_credit_percentage: Number(form.default_credit_percentage),
        auto_forward: form.auto_forward,
        ...(appSecret.trim() ? { app_secret: appSecret.trim() } : {}),
      };
      const saved = await postJson<AliexpressSettingsRead>("/api/proxy/aliexpress/settings", body, "PATCH");
      setForm(saved);
      setAppSecret("");
      queryClient.setQueryData(["admin", "aliexpress", "settings"], saved);
      queryClient.invalidateQueries({ queryKey: ["admin", "aliexpress", "products"] });
      setNotice("Impostazioni salvate. Se hai cambiato i prezzi, tutti i prodotti sono già stati ricalcolati.");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  /** The consent page of the seller's account: AliExpress sends the code
   *  back to the Callback URL, where only the server -- which knows the App
   *  Secret -- turns it into a token. */
  async function connect() {
    setBusy("connect");
    setError(null);
    setNotice(null);
    try {
      const data = await getJson<{ url: string; callback_url: string }>("/api/proxy/aliexpress/oauth/authorize-url");
      window.open(data.url, "_blank", "noopener,noreferrer");
      setNotice("Autorizza l'account nella scheda che si è aperta, poi torna qui e premi “Verifica connessione”.");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  }


  /** L'interruttore della visibilità si applica subito: prima cambiava solo
      il modulo, e chi non premeva "Salva" restava convinto di aver acceso
      lo shop mentre i clienti continuavano a non vederlo (Session 72). */
  async function toggleEnabled(value: boolean) {
    setForm({ ...form, enabled: value });
    setError(null);
    setNotice(null);
    try {
      const saved = await postJson<AliexpressSettingsRead>("/api/proxy/aliexpress/settings", { enabled: value }, "PATCH");
      setForm(saved);
      queryClient.setQueryData(["admin", "aliexpress", "settings"], saved);
      setNotice(value ? "Shop acceso: i clienti lo vedono appena c'è almeno un prodotto in vendita." : "Shop spento: la scheda sparisce dallo Shop del cliente.");
    } catch (err: any) {
      setForm({ ...form, enabled: !value });
      setError(err.message);
    }
  }

  async function test() {
    setBusy("test");
    setError(null);
    setNotice(null);
    try {
      const saved = await postJson<AliexpressSettingsRead & { sample_categories?: string[] }>("/api/proxy/aliexpress/settings/test");
      setForm({ ...form, connected: saved.connected, account_label: saved.account_label, token_expires_at: saved.token_expires_at, last_connected_at: saved.last_connected_at });
      queryClient.setQueryData(["admin", "aliexpress", "settings"], saved);
      const categories = saved.sample_categories ?? [];
      setNotice(
        categories.length > 0
          ? `Connessione riuscita. Categorie lette da AliExpress: ${categories.join(", ")}.`
          : `Connessione riuscita: AliExpress ha risposto${saved.account_label ? ` per l'account "${saved.account_label}"` : ""}.`
      );
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  const sampleCents = salePriceCents(10, 10, form, Number(form.markup_percentage));
  const setNum = (key: keyof AliexpressSettingsRead) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value as unknown as number });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <div className={`${card} p-5 space-y-4`}>
        <h3 className="text-sm font-bold text-white light:text-slate-900">Collegamento all&apos;API Dropshipping di AliExpress</h3>
        <details className="rounded-xl border border-orange-500/20 bg-orange-500/5 p-3 text-xs text-slate-300 light:text-slate-600" open={!settings.connected}>
          <summary className="font-semibold cursor-pointer text-orange-400">Come collegare AliExpress (una volta sola)</summary>
          <ol className="list-decimal pl-5 mt-2 space-y-1">
            <li>Crea l&apos;app sul portale <span className="font-mono">openservice.aliexpress.com</span>, categoria <strong>Drop Shipping</strong>.</li>
            <li>Registra come <strong>Callback URL</strong>: <span className="font-mono break-all">{APP_URL}/api/aliexpress/oauth/callback</span> (esattamente così, senza barra finale).</li>
            <li>Nella pagina della console dell&apos;app copia <strong>App Key</strong> e <strong>App Secret</strong> qui sotto e premi <strong>Salva collegamento</strong>.</li>
            <li>Fai attivare all&apos;app il permesso <strong>DS (dropshipping)</strong>: finché non è concesso, il catalogo non risponde.</li>
            <li>Premi <strong>Collega AliExpress</strong>: si apre la pagina di consenso, autorizzi l&apos;account venditore e AliExpress ti riporta qui.</li>
            <li>Chiudi con <strong>Verifica connessione</strong>. Il token ha una scadenza: il server lo rinnova da solo finché l&apos;autorizzazione resta valida.</li>
          </ol>
        </details>
        <div>
          <span className={label}>App Key</span>
          <input className={input} autoComplete="off" value={form.app_key ?? ""} placeholder="es. 547960"
            onChange={(e) => setForm({ ...form, app_key: e.target.value })} />
        </div>
        <div>
          <span className={label}>App Secret</span>
          <input className={input} type="password" autoComplete="off" value={appSecret}
            placeholder={settings.app_secret_configured ? `Salvato (${settings.app_secret_hint}) — scrivi qui solo per cambiarlo` : "••••••••"}
            onChange={(e) => setAppSecret(e.target.value)} />
          <p className="text-[11px] text-slate-500 mt-1">Resta salvato sul server e non viene mai mostrato.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className={btnPrimary} disabled={saving} onClick={save}>Salva collegamento</button>
          <button className={btnGhost} disabled={busy !== null || !settings.app_secret_configured} onClick={connect}>
            {busy === "connect" ? "..." : settings.connected ? "Ricollega AliExpress" : "Collega AliExpress"}
          </button>
          <button className={btnGhost} disabled={busy !== null || !settings.connected} onClick={test}>
            {busy === "test" ? "Verifica..." : "Verifica connessione"}
          </button>
        </div>
        <p className="text-xs text-slate-400 light:text-slate-500">
          Stato: {settings.connected
            ? (
              <span className="text-emerald-400">
                account collegato{settings.account_label ? ` (${settings.account_label})` : ""}
                {settings.last_connected_at ? ` · ultima verifica ${formatDate(settings.last_connected_at)}` : ""}
                {settings.token_expires_at ? ` · token valido fino al ${formatDate(settings.token_expires_at)}` : ""}
              </span>
            )
            : <span className="text-amber-400">non ancora autorizzato</span>}
        </p>

        <div className="pt-4 border-t border-white/5 light:border-slate-200 space-y-3">
          <Switch checked={form.enabled} onChange={(v) => void toggleEnabled(v)}
            title="Shop visibile ai clienti" hint="Aggiunge la scheda del Marketplace nello Shop del cliente. La scheda compare solo quando c'è almeno un prodotto in vendita: se è accesa ma il catalogo è vuoto, il cliente non vede nulla. Il nome della scheda si cambia nella card “Regole dei Marketplace” qui sopra." />
          <Switch checked={form.auto_forward} onChange={(v) => setForm({ ...form, auto_forward: v })}
            title="Invio automatico ad AliExpress (consigliato)" hint="Appena il cliente ha pagato, l'ordine viene creato su AliExpress con l'indirizzo di consegna. Se qualcosa va storto si riprova da solo; se AliExpress lo rifiuta ricevi un avviso." />
        </div>
      </div>

      <div className={`${card} p-5 space-y-4`}>
        <h3 className="text-sm font-bold text-white light:text-slate-900">Prezzi e spedizione</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className={label}>Il prezzo parte da</span>
            <select className={input} value={form.price_basis}
              onChange={(e) => setForm({ ...form, price_basis: e.target.value as AliexpressSettingsRead["price_basis"] })}>
              <option value="COST">prezzo riservato al dropshipping</option>
              <option value="PRICE">prezzo di listino AliExpress</option>
            </select>
          </div>
          <div>
            <span className={label}>Cambio 1 {form.target_currency || "USD"} = EUR</span>
            <input className={input} inputMode="decimal" value={form.currency_rate} onChange={setNum("currency_rate")} />
          </div>
          <div>
            <span className={label}>Ricarico %</span>
            <input className={input} inputMode="numeric" value={form.markup_percentage} onChange={setNum("markup_percentage")} />
          </div>
          <div>
            <span className={label}>Ricarico fisso (€)</span>
            <input className={input} inputMode="decimal" value={(Number(form.markup_fixed_cents) / 100).toString()}
              onChange={(e) => setForm({ ...form, markup_fixed_cents: Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) })} />
          </div>
          <div>
            <span className={label}>Arrotondamento</span>
            <select className={input} value={form.price_rounding}
              onChange={(e) => setForm({ ...form, price_rounding: e.target.value as AliexpressSettingsRead["price_rounding"] })}>
              <option value="90">a ,90 (es. 12,90)</option>
              <option value="99">a ,99 (es. 12,99)</option>
              <option value="NONE">al centesimo</option>
            </select>
          </div>
          <div>
            <span className={label}>Spedizione</span>
            <select className={input} value={form.shipping_mode}
              onChange={(e) => setForm({ ...form, shipping_mode: e.target.value as AliexpressSettingsRead["shipping_mode"] })}>
              <option value="CUSTOMER_PAYS">la paga il cliente (costo reale, con un minimo)</option>
              <option value="INCLUDED">inclusa nel prezzo</option>
            </select>
          </div>
          <div>
            <span className={label}>Spesa di spedizione minima (€)</span>
            <input className={input} inputMode="decimal" value={(Number(form.shipping_minimum_cents) / 100).toString()}
              onChange={(e) => setForm({ ...form, shipping_minimum_cents: Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) })} />
            <span className="block text-[10px] text-slate-500 mt-1">
              {form.shipping_mode === "INCLUDED"
                ? "Con la spedizione inclusa questo importo entra nel prezzo di listino e al checkout non si addebita nulla."
                : Number(form.shipping_minimum_cents) === 0
                  ? "Nessun minimo: il cliente paga esattamente la spedizione che AliExpress chiede per quei prodotti, calcolata al checkout. Metti un importo qui sopra se vuoi che non scenda mai sotto una certa soglia."
                  : "Il cliente paga almeno questo importo. Se la spedizione reale di AliExpress costa di più, si addebita quella. Il minimo vale una volta per ordine, non per articolo; a zero non c'è minimo e si paga solo il costo reale."}
            </span>
          </div>
          <div>
            <span className={label}>Tempi di consegna (giorni)</span>
            <input className={input} value={form.shipping_days ?? ""} placeholder="es. 10-20" onChange={(e) => setForm({ ...form, shipping_days: e.target.value })} />
          </div>
          <div>
            <span className={label}>Paese di consegna</span>
            <input className={input} maxLength={2} value={form.ship_to_country}
              onChange={(e) => setForm({ ...form, ship_to_country: e.target.value.toUpperCase() })} />
            <span className="block text-[10px] text-slate-500 mt-1">Sigla a due lettere: IT.</span>
          </div>
          <div>
            <span className={label}>Valuta e lingua delle risposte</span>
            <div className="flex gap-2">
              <input className={input} maxLength={3} value={form.target_currency}
                onChange={(e) => setForm({ ...form, target_currency: e.target.value.toUpperCase() })} />
              <input className={input} maxLength={8} value={form.target_language}
                onChange={(e) => setForm({ ...form, target_language: e.target.value })} />
            </div>
            <span className="block text-[10px] text-slate-500 mt-1">Es. USD e IT: AliExpress traduce i titoli.</span>
          </div>
          <div className="col-span-2">
            <span className={label}>JavCash usabili sui nuovi prodotti (%)</span>
            <input className={input} inputMode="numeric" value={form.default_credit_percentage} onChange={setNum("default_credit_percentage")} />
            <span className="block text-[10px] text-slate-500 mt-1">
              30% consigliato, massimo {settings.max_credit_percentage}%: un prodotto dei Marketplace non si compra mai tutto in JavCash.
            </span>
          </div>
        </div>
        <div className="p-3 rounded-xl bg-orange-500/5 border border-orange-500/20 text-xs text-slate-300 light:text-slate-600">
          Esempio: un articolo che costa <strong>10 {form.target_currency || "USD"}</strong> sarà in vendita a{" "}
          <strong className="text-orange-400">{euro(sampleCents)}</strong>
          {form.shipping_mode === "CUSTOMER_PAYS" ? (Number(form.shipping_minimum_cents) === 0
              ? " + la spedizione reale di AliExpress, calcolata al checkout."
              : ` + spedizione reale AliExpress, minimo ${euro(Number(form.shipping_minimum_cents))}.`) : " (spedizione inclusa)."}{" "}
          È il prezzo pieno IVA inclusa, lo stesso con carta; con bonifico istantaneo il cliente ha lo sconto delle Regole dei Marketplace, che riduce il margine.
          <p className="text-[11px] text-slate-500 mt-1">
            Se un articolo non ha il prezzo riservato al dropshipping si parte dal suo listino. L&apos;arrotondamento è sempre per eccesso.
          </p>
        </div>
        <ErrorBox message={error} />
        {notice && <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">{notice}</div>}
        <button className={btnPrimary} disabled={saving} onClick={save}>{saving ? "Salvataggio..." : "Salva impostazioni"}</button>
      </div>
    </div>
  );
}

function Switch({ checked, onChange, title, hint }: { checked: boolean; onChange: (v: boolean) => void; title: string; hint: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className="flex items-start gap-3 text-left cursor-pointer w-full">
      <span className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${checked ? "bg-orange-600" : "bg-white/15 light:bg-slate-300"}`}>
        <span className={`inline-block rounded-full bg-white shadow transition-transform ${checked ? "translate-x-6" : "translate-x-1"}`} style={{ height: 18, width: 18 }} />
      </span>
      <span>
        <span className="block text-sm font-semibold text-white light:text-slate-900">{title}</span>
        <span className="block text-[11px] text-slate-500">{hint}</span>
      </span>
    </button>
  );
}

// --- Catalogo AliExpress -------------------------------------------------------------------

function CatalogTab({ settings, configured, onImported }: {
  settings: AliexpressSettingsRead | undefined; configured: boolean; onImported: () => void;
}) {
  const [keyword, setKeyword] = useState("");
  const [query, setQuery] = useState<{ keyword: string; cursor: string | null; page: number } | null>(null);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  // A search hit carries no SKU: the variants, and with them the real
  // prices, only arrive with the detail call. So the import window opens on
  // an id and waits for that answer.
  const [previewOf, setPreviewOf] = useState<AliexpressCatalogProduct | null>(null);

  const { data: results, error, isFetching } = useQuery({
    queryKey: ["admin", "aliexpress", "search", query],
    queryFn: () => {
      const q = query!;
      const params = new URLSearchParams();
      if (q.keyword) params.set("keyword", q.keyword);
      if (q.cursor) params.set("cursor", q.cursor);
      return getJson<AliexpressCatalogPage>(`/api/proxy/aliexpress/catalog/search?${params}`);
    },
    enabled: !!query,
    staleTime: 120_000,
  });

  const { data: preview, error: previewError } = useQuery({
    queryKey: ["admin", "aliexpress", "catalog-product", previewOf?.product_id],
    queryFn: () => getJson<AliexpressCatalogProduct>(
      `/api/proxy/aliexpress/catalog/product?product_id=${encodeURIComponent(previewOf!.product_id)}`
    ),
    enabled: !!previewOf,
    staleTime: 120_000,
    retry: false,
  });

  if (!configured) {
    return <p className={`${card} p-6 text-sm text-slate-400`}>Prima collega l&apos;account AliExpress in Impostazioni.</p>;
  }

  function goTo(page: number, list = cursors) {
    setQuery({ keyword: keyword.trim(), cursor: list[page] ?? null, page });
  }

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); if (!keyword.trim()) return; setCursors([null]); goTo(0, [null]); }} className={`${card} p-4 flex flex-col md:flex-row gap-3 md:items-end`}>
        <div className="flex-1">
          <span className={label}>Cerca su AliExpress (parola chiave, in inglese funziona meglio)</span>
          <input className={input} value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="es. cuffie, lampada, yoga" />
        </div>
        <button type="submit" className={btnPrimary} disabled={isFetching || !keyword.trim()}>{isFetching ? "..." : "Cerca"}</button>
      </form>

      <ErrorBox message={error ? (error as Error).message : null} />

      {!query && (
        <p className="text-sm text-slate-500 text-center py-10">
          Scrivi che cosa cercare tra gli articoli disponibili per il dropshipping: vedi subito il prezzo a cui li venderesti, poi aprine uno per importarlo.
        </p>
      )}

      {results && (
        <>
          {results.items.length === 0 && <p className="text-sm text-slate-500 text-center py-6">Nessun prodotto trovato.</p>}
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
            {results.items.map((item) => (
              <button key={item.product_id} type="button" onClick={() => setPreviewOf(item)}
                className={`${card} overflow-hidden text-left hover:border-orange-500/40 transition cursor-pointer`}>
                <div className="relative aspect-square bg-white">
                  <ProductThumbnail imageUrl={item.image_url} alt={item.title} className="w-full h-full object-cover" />
                  {item.already_imported && (
                    <span className="absolute top-1.5 left-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-500 text-white">Già importato</span>
                  )}
                </div>
                <div className="p-2.5">
                  <p className="text-[11px] text-slate-300 light:text-slate-700 line-clamp-2 min-h-[2rem]">{item.title}</p>
                  <div className="flex items-end justify-between mt-1.5">
                    <span className="text-[10px] text-slate-500">{item.evaluate_rate ?? item.vendor ?? ""}</span>
                    {item.min_price_cents !== null && <span className="text-sm font-bold text-orange-400">{euro(item.min_price_cents)}</span>}
                  </div>
                </div>
              </button>
            ))}
          </div>
          <div className="flex items-center justify-center gap-2">
            <button className={btnGhost} disabled={!query || query.page === 0 || isFetching} onClick={() => goTo((query?.page ?? 1) - 1)}>← Precedente</button>
            <button className={btnGhost} disabled={!results.next_cursor || isFetching}
              onClick={() => {
                const page = (query?.page ?? 0) + 1;
                const next = [...cursors.slice(0, page), results.next_cursor];
                setCursors(next);
                goTo(page, next);
              }}>Successiva →</button>
          </div>
        </>
      )}

      {previewOf && (
        preview ? (
          <ImportModal
            product={preview}
            alreadyImported={!!previewOf.already_imported}
            settings={settings}
            onClose={() => setPreviewOf(null)}
            onImported={() => { setPreviewOf(null); onImported(); }}
          />
        ) : (
          <LoadingModal
            title={previewOf.title}
            error={previewError ? (previewError as Error).message : null}
            onClose={() => setPreviewOf(null)}
          />
        )
      )}
    </div>
  );
}

/** While AliExpress is asked for the SKUs of the chosen article -- it takes
 *  a moment, and it can answer that there is nothing sellable. */
function LoadingModal({ title, error, onClose }: { title: string; error: string | null; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up space-y-4">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm font-semibold text-white light:text-slate-900 line-clamp-2">{title}</p>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400 cursor-pointer shrink-0" aria-label="Chiudi">✕</button>
        </div>
        {error ? <ErrorBox message={error} /> : <p className="text-sm text-slate-400">Lettura delle varianti da AliExpress...</p>}
      </div>
    </div>
  );
}

function ImportModal({ product, alreadyImported, settings, onClose, onImported }: {
  product: AliexpressCatalogProduct; alreadyImported: boolean;
  settings: AliexpressSettingsRead | undefined; onClose: () => void; onImported: () => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(product.title.slice(0, 255));
  const [description, setDescription] = useState(product.description_text);
  const [creditPct, setCreditPct] = useState(String(settings?.default_credit_percentage ?? 30));
  const generalMarkup = settings?.markup_percentage ?? 100;
  const [markup, setMarkup] = useState(String(generalMarkup));
  const markupValue = markup.trim() === "" || Number.isNaN(Number(markup)) ? generalMarkup : Number(markup);
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(product.variants.filter((v) => v.inventory === null || v.inventory > 0).map((v) => v.variant_id))
  );
  const [categoryIds, setCategoryIds] = useState<string[]>([]);
  const [activate, setActivate] = useState(true);
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const priceOf = (v: AliexpressCatalogProduct["variants"][number]) =>
    settings ? salePriceCents(v.cost_amount, v.source_price_amount, settings, markupValue) : v.price_cents;

  async function handleImport() {
    setLoading(true);
    setSubmitError(null);
    try {
      const created = await postJson<{ id: string }>("/api/proxy/aliexpress/products", {
        product_id: product.product_id,
        name: name.trim(),
        description,
        credit_discount_percentage: Number(creditPct),
        markup_percentage: markupValue === generalMarkup ? null : markupValue,
        variant_ids: Array.from(selected),
        activate,
      });
      await queryClient.invalidateQueries({ queryKey: ["admin", "aliexpress"] });
      // Le categorie scelte qui evitano il giro "importa, poi riapri e
      // assegna": un catalogo importato in blocco nasce già ordinato.
      if (categoryIds.length > 0) await saveProductCategories("aliexpress", created.id, categoryIds);
      onImported();
    } catch (err: any) {
      setSubmitError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const itemUrl = aliexpressItemUrl(product.product_url, product.product_id);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-4xl max-h-[92vh] overflow-y-auto glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white light:text-slate-900">Importa da AliExpress</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400 cursor-pointer" aria-label="Chiudi">✕</button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-5">
          <div className="md:col-span-2 space-y-3">
            <div className="aspect-square rounded-xl overflow-hidden bg-white border border-white/10">
              <ProductThumbnail imageUrl={product.images[0] ?? product.image_url} alt={product.title} className="w-full h-full object-contain" />
            </div>
            <div className="flex gap-1.5 overflow-x-auto">
              {product.images.slice(1, 8).map((src) => (
                <div key={src} className="w-12 h-12 shrink-0 rounded-md overflow-hidden bg-white">
                  <ProductThumbnail imageUrl={src} alt="" className="w-full h-full object-cover" />
                </div>
              ))}
            </div>
            <p className="text-xs text-slate-400 light:text-slate-500">
              {product.vendor ? `Venditore ${product.vendor} · ` : ""}
              {alreadyImported && <span className="text-emerald-400">già importato</span>}
            </p>
            {itemUrl && (
              <a className={btnGhost} href={itemUrl} target="_blank" rel="noopener noreferrer">Apri su AliExpress</a>
            )}
          </div>
          <div className="md:col-span-3 space-y-3">
            <div>
              <span className={label}>Nome in vendita (in italiano)</span>
              <input className={input} value={name} maxLength={255} onChange={(e) => setName(e.target.value)} />
              <p className="text-[10px] text-slate-500 mt-0.5">Originale: {product.title}</p>
            </div>
            <div>
              <span className={label}>Descrizione</span>
              <textarea className={`${input} min-h-[110px]`} value={description} maxLength={8000} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div>
              <span className={label}>Varianti da vendere</span>
              <div className="max-h-56 overflow-y-auto rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
                {product.variants.map((v) => (
                  <label key={v.variant_id} className={`flex items-center gap-3 px-3 py-2 text-xs cursor-pointer ${v.inventory === 0 ? "opacity-50" : ""}`}>
                    <input type="checkbox" checked={selected.has(v.variant_id)}
                      onChange={(e) => {
                        const next = new Set(selected);
                        if (e.target.checked) next.add(v.variant_id); else next.delete(v.variant_id);
                        setSelected(next);
                      }} />
                    <span className="flex-1 min-w-0 truncate text-slate-200 light:text-slate-800">{v.label}{v.sku ? ` · ${v.sku}` : ""}</span>
                    <span className="text-slate-500 shrink-0" title="prezzo dropshipping / listino">
                      {v.cost_amount !== null ? `ds ${money(v.cost_amount, product.currency)}` : `listino ${money(v.source_price_amount, product.currency)}`}
                    </span>
                    <span className="font-bold text-orange-400 shrink-0 w-16 text-right">{euro(priceOf(v))}</span>
                    <span className="text-slate-500 shrink-0 w-14 text-right">{v.inventory === null ? "∞" : `${v.inventory} pz`}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 items-end">
              <div>
                <span className={label}>Ricarico %</span>
                <input className={input} inputMode="numeric" value={markup} onChange={(e) => setMarkup(e.target.value)} />
              </div>
              <div>
                <span className={label}>JavCash usabili (%)</span>
                <input className={input} inputMode="numeric" value={creditPct} onChange={(e) => setCreditPct(e.target.value)} />
              </div>
              <label className="flex items-center gap-2 text-xs text-slate-300 light:text-slate-600 pb-2 cursor-pointer">
                <input type="checkbox" checked={activate} onChange={(e) => setActivate(e.target.checked)} />
                Metti subito in vendita
              </label>
            </div>
            <ProductCategoriesField shop="aliexpress" value={categoryIds} onChange={setCategoryIds} />
            <p className="text-[11px] text-slate-500 -mt-1">
              {markupValue === generalMarkup
                ? `Ricarico generale (${generalMarkup}%): se lo cambi in Impostazioni, questo prodotto si aggiorna.`
                : `Ricarico solo per questo prodotto (${markupValue}%).`}
              {" "}JavCash: massimo {settings?.max_credit_percentage ?? 99}%.
            </p>
            <ErrorBox message={submitError} />
            <button className={`${btnPrimary} w-full py-2.5`} disabled={loading || selected.size === 0 || !name.trim() || alreadyImported}
              onClick={handleImport}>
              {loading ? "Importazione..." : alreadyImported ? "Già importato" : `Importa ${selected.size} ${selected.size === 1 ? "variante" : "varianti"}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Prodotti in vendita ----------------------------------------------------------------------

function ProductsTab({ settings }: { settings: AliexpressSettingsRead | undefined }) {
  const queryClient = useQueryClient();
  const { data: products, error } = useQuery({
    queryKey: ["admin", "aliexpress", "products"],
    queryFn: () => getJson<AliexpressProductAdminRead[]>("/api/proxy/aliexpress/products"),
  });
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<AliexpressProductAdminRead | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const needle = search.trim().toLowerCase();
  const filtered = (products ?? []).filter((p) =>
    !needle || p.name.toLowerCase().includes(needle) || p.variants.some((v) => (v.sku ?? "").toLowerCase().includes(needle))
  );
  const pagination = usePagination(filtered);

  async function act(product: AliexpressProductAdminRead, action: "sync" | "toggle") {
    setBusyId(product.id);
    setActionError(null);
    try {
      if (action === "sync") await postJson(`/api/proxy/aliexpress/products/${product.id}/sync`);
      else await postJson(`/api/proxy/aliexpress/products/${product.id}`, { status: product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }, "PATCH");
      await queryClient.invalidateQueries({ queryKey: ["admin", "aliexpress", "products"] });
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <ErrorBox message={(error as Error).message} />;
  if (!products) return <div className={`${card} h-40 animate-pulse`} />;
  if (products.length === 0) {
    return <p className={`${card} p-8 text-center text-sm text-slate-400`}>Nessun prodotto ancora: importali da &ldquo;Catalogo AliExpress&rdquo;.</p>;
  }

  return (
    <div className="space-y-3">
      <input className={input} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca per nome o SKU..." />
      <ErrorBox message={actionError} />
      <div className={`${card} divide-y divide-white/5 light:divide-slate-200 overflow-hidden`}>
        {pagination.pageItems.map((p) => {
          const live = p.variants.filter((v) => v.active && v.available_in_store);
          const prices = live.map((v) => v.effective_price_cents);
          const soldOut = live.length > 0 && live.every((v) => v.inventory !== null && v.inventory <= 0);
          const itemUrl = aliexpressItemUrl(p.product_url, p.aliexpress_product_id);
          return (
            <div key={p.id} className="p-4 flex flex-wrap items-center gap-4">
              <div className="w-14 h-14 rounded-lg overflow-hidden bg-white shrink-0">
                <ProductThumbnail imageUrl={p.image_url} alt={p.name} className="w-full h-full object-cover" />
              </div>
              <div className="flex-1 min-w-[200px]">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-semibold text-white light:text-slate-900">{p.name}</p>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${p.status === "ACTIVE" ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-slate-500/10 border-slate-500/30 text-slate-400"}`}>
                    {p.status === "ACTIVE" ? "In vendita" : "Nascosto"}
                  </span>
                  {soldOut && <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-rose-500/10 border-rose-500/30 text-rose-400">Esaurito</span>}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  {prices.length ? (Math.min(...prices) === Math.max(...prices) ? euro(prices[0] ?? 0) : `${euro(Math.min(...prices))} – ${euro(Math.max(...prices))}`) : "—"}
                  {" "}· {p.variants.length} varianti · JavCash {p.credit_discount_percentage}% · {p.paid_orders} venduti
                </p>
                <p className="text-[10px] text-slate-500">
                  Aggiornato da AliExpress {formatDate(p.last_synced_at)}{p.markup_percentage !== null ? ` · ricarico ${p.markup_percentage}%` : ""}
                  {p.vendor ? ` · ${p.vendor}` : ""}
                </p>
                {p.sync_error && <p className="text-[11px] text-amber-400 mt-0.5">{p.sync_error}</p>}
              </div>
              <div className="flex flex-wrap gap-2">
                <button className={btnGhost} onClick={() => setEditing(p)}>Modifica</button>
                <button className={btnGhost} disabled={busyId === p.id} onClick={() => act(p, "sync")}>{busyId === p.id ? "..." : "Aggiorna da AliExpress"}</button>
                <button className={btnGhost} disabled={busyId === p.id} onClick={() => act(p, "toggle")}>{p.status === "ACTIVE" ? "Nascondi" : "Metti in vendita"}</button>
                {itemUrl && <a className={btnGhost} href={itemUrl} target="_blank" rel="noopener noreferrer">Apri su AliExpress</a>}
              </div>
            </div>
          );
        })}
      </div>
      <Pagination {...pagination} label="prodotti" />
      {editing && <EditProductModal product={editing} maxCredit={settings?.max_credit_percentage ?? 99} onClose={() => setEditing(null)} />}
    </div>
  );
}

function EditProductModal({ product, maxCredit, onClose }: { product: AliexpressProductAdminRead; maxCredit: number; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(product.name);
  const [description, setDescription] = useState(product.description);
  const [creditPct, setCreditPct] = useState(String(product.credit_discount_percentage));
  const [markup, setMarkup] = useState(product.markup_percentage === null ? "" : String(product.markup_percentage));
  const [image, setImage] = useState(product.image_url);
  const [variants, setVariants] = useState(product.variants);
  const [categoryIds, setCategoryIds] = useState<string[]>(product.category_ids ?? []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setLoading(true);
    setError(null);
    try {
      await postJson(`/api/proxy/aliexpress/products/${product.id}`, {
        name: name.trim(),
        description,
        image_url: image,
        credit_discount_percentage: Number(creditPct),
        markup_percentage: markup.trim() === "" ? null : Number(markup),
      }, "PATCH");
      for (const v of variants) {
        const original = product.variants.find((o) => o.id === v.id);
        if (!original) continue;
        if (original.active !== v.active || original.price_override_cents !== v.price_override_cents || original.label !== v.label) {
          await postJson(`/api/proxy/aliexpress/variants/${v.id}`, {
            active: v.active, label: v.label, price_override_cents: v.price_override_cents,
          }, "PATCH");
        }
      }
      // Solo se le spunte sono state davvero toccate: un salvataggio che non
      // riguarda le categorie non deve passare da questo endpoint.
      if (!sameCategorySelection(categoryIds, product.category_ids ?? [])) {
        await saveProductCategories("aliexpress", product.id, categoryIds);
        await queryClient.invalidateQueries({ queryKey: ["shop-categories", "aliexpress"] });
      }
      await queryClient.invalidateQueries({ queryKey: ["admin", "aliexpress", "products"] });
      onClose();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-3xl max-h-[92vh] overflow-y-auto glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-white light:text-slate-900">Modifica prodotto</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400 cursor-pointer" aria-label="Chiudi">✕</button>
        </div>
        <div>
          <span className={label}>Nome</span>
          <input className={input} value={name} maxLength={255} onChange={(e) => setName(e.target.value)} />
          {product.source_title && <p className="text-[10px] text-slate-500 mt-0.5">Su AliExpress: {product.source_title}</p>}
        </div>
        <div>
          <span className={label}>Descrizione</span>
          <textarea className={`${input} min-h-[120px]`} value={description} maxLength={8000} onChange={(e) => setDescription(e.target.value)} />
        </div>
        {product.images.length > 1 && (
          <div>
            <span className={label}>Foto principale</span>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {product.images.map((src) => (
                <button key={src} type="button" onClick={() => setImage(src)}
                  className={`w-14 h-14 shrink-0 rounded-lg overflow-hidden bg-white border-2 cursor-pointer ${image === src ? "border-orange-500" : "border-transparent"}`}>
                  <ProductThumbnail imageUrl={src} alt="" className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className={label}>JavCash usabili (%, max {maxCredit})</span>
            <input className={input} inputMode="numeric" value={creditPct} onChange={(e) => setCreditPct(e.target.value)} />
          </div>
          <div>
            <span className={label}>Ricarico % solo per questo prodotto</span>
            <input className={input} inputMode="numeric" value={markup} placeholder="vuoto = quello generale" onChange={(e) => setMarkup(e.target.value)} />
          </div>
        </div>
        <ProductCategoriesField shop="aliexpress" value={categoryIds} onChange={setCategoryIds} />
        <div>
          <span className={label}>Varianti</span>
          <div className="rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
            {variants.map((v, i) => (
              <div key={v.id} className={`flex flex-wrap items-center gap-3 px-3 py-2 text-xs ${!v.available_in_store ? "opacity-50" : ""}`}>
                <input type="checkbox" checked={v.active} title="In vendita"
                  onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, active: e.target.checked } : x)))} />
                <input className="flex-1 min-w-[120px] rounded-md glass-input px-2 py-1 text-xs" value={v.label}
                  onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                <span className="text-slate-500">{v.cost_amount !== null ? `ds ${v.cost_amount.toFixed(2)}` : `listino ${v.source_price_amount.toFixed(2)}`}</span>
                <span className="text-slate-400">auto {euro(v.price_cents)}</span>
                <input className="w-24 rounded-md glass-input px-2 py-1 text-xs" inputMode="decimal" placeholder="prezzo fisso €"
                  value={v.price_override_cents === null ? "" : (v.price_override_cents / 100).toFixed(2)}
                  onChange={(e) => {
                    const cents = e.target.value.trim() === "" ? null : Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) || null;
                    setVariants(variants.map((x, j) => (j === i ? { ...x, price_override_cents: cents } : x)));
                  }} />
                <span className="text-slate-500 w-14 text-right">{v.inventory === null ? "∞" : `${v.inventory} pz`}</span>
                {!v.available_in_store && <span className="text-rose-400">non più su AliExpress</span>}
              </div>
            ))}
          </div>
          <p className="text-[10px] text-slate-500 mt-1">Il prezzo fisso, se c&apos;è, sostituisce quello calcolato: non segue più il costo del fornitore.</p>
        </div>
        <ErrorBox message={error} />
        <div className="flex justify-end gap-2">
          <button className={btnGhost} onClick={onClose}>Annulla</button>
          <button className={btnPrimary} disabled={loading || !name.trim()} onClick={save}>{loading ? "Salvataggio..." : "Salva"}</button>
        </div>
      </div>
    </div>
  );
}

// --- Ordini ----------------------------------------------------------------------------------

type Badge = { label: string; className: string };

const TONE = {
  ok: "bg-emerald-500/10 border-emerald-500/30 text-emerald-400",
  info: "bg-sky-500/10 border-sky-500/30 text-sky-400",
  warn: "bg-amber-500/10 border-amber-500/30 text-amber-400",
  bad: "bg-rose-500/10 border-rose-500/30 text-rose-400",
  muted: "bg-white/5 border-white/10 light:border-slate-300 text-slate-400",
};

const CUSTOMER_PAYMENT: Record<string, Badge> = {
  AWAITING_PAYMENT: { label: "Cliente: da pagare", className: TONE.warn },
  PAID: { label: "Cliente: pagato", className: TONE.ok },
  CANCELLED: { label: "Annullato", className: TONE.bad },
};

const SUPPLIER_ORDER: Record<string, Badge> = {
  NOT_SENT: { label: "AliExpress: non creato", className: TONE.muted },
  SENDING: { label: "AliExpress: invio in corso", className: TONE.info },
  SENT: { label: "AliExpress: creato, in preparazione", className: TONE.info },
  SHIPPED: { label: "Spedito", className: TONE.info },
  DELIVERED: { label: "Consegnato", className: TONE.ok },
  ERROR: { label: "AliExpress: errore", className: TONE.bad },
  CANCELLED: { label: "Annullato su AliExpress", className: TONE.bad },
};

const ERROR_KIND: Record<string, string> = {
  TEMPORARY: "temporaneo, si riprova da solo",
  AUTHENTICATION: "token / permessi dell'app",
  VALIDATION: "dati rifiutati da AliExpress",
  FATAL: "da verificare",
};

const ORDER_FILTERS: { key: string; label: string; match: (o: AliexpressOrderRead) => boolean }[] = [
  { key: "send", label: "Da inviare ad AliExpress", match: (o) => o.status === "PAID" && ["NOT_SENT", "SENDING", "ERROR"].includes(o.fulfillment_status ?? "") },
  { key: "problems", label: "Problemi", match: (o) => o.status === "PAID" && ["ERROR", "CANCELLED"].includes(o.fulfillment_status ?? "") },
  { key: "unpaid", label: "Cliente non ha pagato", match: (o) => o.status === "AWAITING_PAYMENT" },
  { key: "moving", label: "In preparazione / in viaggio", match: (o) => ["SENT", "SHIPPED"].includes(o.fulfillment_status ?? "") },
  { key: "delivered", label: "Consegnati", match: (o) => o.fulfillment_status === "DELIVERED" },
  { key: "all", label: "Tutti", match: () => true },
];

function Pill({ badge }: { badge?: Badge }) {
  if (!badge) return null;
  return <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${badge.className}`}>{badge.label}</span>;
}

function OrdersTab({ settings }: { settings: AliexpressSettingsRead | undefined }) {
  const queryClient = useQueryClient();
  const { data: orders, error } = useQuery({
    queryKey: ["admin", "aliexpress", "orders"],
    queryFn: () => getJson<AliexpressOrderRead[]>("/api/proxy/aliexpress/orders"),
    refetchInterval: 60_000,
  });
  const [filter, setFilter] = useState("send");
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const active = ORDER_FILTERS.find((f) => f.key === filter) ?? ORDER_FILTERS[0]!;
  const needle = search.trim().toLowerCase();
  const filtered = (orders ?? []).filter(active.match).filter((o) =>
    !needle
    || o.id.slice(0, 8).toLowerCase().includes(needle)
    || o.product_name.toLowerCase().includes(needle)
    || o.customer_display_name.toLowerCase().includes(needle)
    || (o.aliexpress_order_id ?? "").toLowerCase().includes(needle)
    || (o.out_order_id ?? "").toLowerCase().includes(needle)
    || (o.tracking_number ?? "").toLowerCase().includes(needle)
  );
  const pagination = usePagination(filtered);

  async function act(order: AliexpressOrderRead, action: "forward" | "sync") {
    setBusyId(order.id);
    setActionError(null);
    try {
      const updated = await postJson<AliexpressOrderRead>(`/api/proxy/aliexpress/orders/${order.id}/${action}`);
      if (updated.forward_error && updated.fulfillment_status === "ERROR") setActionError(updated.forward_error);
      await queryClient.invalidateQueries({ queryKey: ["admin", "aliexpress", "orders"] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "orders"] });
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <ErrorBox message={(error as Error).message} />;
  if (!orders) return <div className={`${card} h-40 animate-pulse`} />;

  return (
    <div className="space-y-3">
      <p className="text-[11px] text-slate-500">
        I bonifici si confermano da <strong>Ordini</strong>, come per tutti gli acquisti. Qui: invio ad AliExpress e spedizione.
        {settings?.auto_forward ? " Invio automatico attivo: gli ordini pagati partono da soli." : " Invio automatico spento: usa “Crea su AliExpress”."}
      </p>
      <div className="flex flex-wrap gap-2">
        {ORDER_FILTERS.map((f) => {
          const count = orders.filter(f.match).length;
          return (
            <button key={f.key} onClick={() => setFilter(f.key)}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                filter === f.key ? "bg-orange-600 border-orange-600 text-white" : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
              }`}>
              {f.label} <span className="opacity-70">({count})</span>
            </button>
          );
        })}
      </div>
      <input className={input} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca per ordine, cliente, prodotto, numero AliExpress o tracking..." />
      <ErrorBox message={actionError} />

      {filtered.length === 0 ? (
        <p className={`${card} p-8 text-center text-sm text-slate-500`}>Nessun ordine qui.</p>
      ) : (
        <div className={`${card} divide-y divide-white/5 light:divide-slate-200 overflow-hidden`}>
          {pagination.pageItems.map((o) => {
            const customerPaid = o.status === "PAID";
            const canCreate = customerPaid && ["NOT_SENT", "ERROR"].includes(o.fulfillment_status ?? "") && !o.aliexpress_order_id;
            const itemUrl = aliexpressItemUrl(null, o.aliexpress_product_id);
            const open = openId === o.id;
            return (
              <div key={o.id} className={`p-4 ${o.fulfillment_status === "ERROR" ? "bg-rose-500/[0.04]" : ""}`}>
                <div className="flex flex-wrap items-start gap-4">
                  <div className="w-12 h-12 rounded-lg overflow-hidden bg-white shrink-0">
                    <ProductThumbnail imageUrl={o.product_image_url} alt="" className="w-full h-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-[240px]">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-white light:text-slate-900">{o.customer_display_name}</span>
                      <span className="text-xs text-slate-500 font-mono">#{o.id.slice(0, 8).toUpperCase()}</span>
                    </div>
                    <div className="flex items-center gap-1.5 flex-wrap mt-1">
                      <Pill badge={CUSTOMER_PAYMENT[o.status]} />
                      {customerPaid && <Pill badge={SUPPLIER_ORDER[o.fulfillment_status ?? ""]} />}
                    </div>
                    <p className="text-xs text-slate-400 light:text-slate-500 mt-1">
                      {o.product_name} · {o.variant_label} × {o.quantity} · cliente {euro(o.amount_cents - o.bank_transfer_discount_cents)}
                      {(o.vat_amount_cents ?? 0) > 0 && <> · {vatLineLabel(o.vat_percentage ?? 0)} {euro(o.vat_amount_cents!)}</>}
                      {o.supplier_cost_cents != null && <> · costo ≈ {euro(o.supplier_cost_cents)}</>}
                      {/* Session 76: la spedizione ha un margine suo -- si
                          addebita max(reale, minimo) -- e il suo costo ora
                          esce dal margine complessivo invece di restarci
                          dentro come se fosse guadagno. */}
                      {o.supplier_shipping_cents != null && (
                        <span className="text-slate-500">
                          {" "}· spedizione {euro(o.shipping_cents)} addebitati su {euro(o.supplier_shipping_cents)} reali
                          {o.shipping_margin_cents != null && (
                            <span className={o.shipping_margin_cents >= 0 ? "text-emerald-400" : "text-rose-400"}>
                              {" "}({o.shipping_margin_cents >= 0 ? "+" : ""}{euro(o.shipping_margin_cents)})
                            </span>
                          )}
                        </span>
                      )}
                      {o.estimated_margin_cents != null && (
                        <span className={o.estimated_margin_cents >= 0 ? "text-emerald-400" : "text-rose-400"}> · margine al netto di IVA, sconto e spedizione ≈ {euro(o.estimated_margin_cents)}</span>
                      )}
                    </p>
                    <p className="text-[11px] text-slate-500">
                      {formatDate(o.paid_at ?? o.created_at)} · {o.city} ({o.province})
                      {o.aliexpress_order_id && <> · AliExpress <span className="font-mono">{o.aliexpress_order_id}</span></>}
                      {o.tracking_number && <> · tracking <span className="font-mono">{o.tracking_number}</span></>}
                    </p>
                    {o.forward_error && o.fulfillment_status === "ERROR" && (
                      <p className="text-[11px] text-rose-400 mt-0.5">
                        {o.forward_error}{o.last_error_kind ? ` (${ERROR_KIND[o.last_error_kind] ?? o.last_error_kind})` : ""}
                      </p>
                    )}
                    {o.next_retry_at && o.fulfillment_status === "ERROR" && (
                      <p className="text-[11px] text-slate-500">Nuovo tentativo automatico {formatDate(o.next_retry_at)} · tentativi {o.attempt_count}</p>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2 sm:justify-end">
                    {canCreate && (
                      <button className={btnPrimary} disabled={busyId === o.id} onClick={() => act(o, "forward")}>
                        {busyId === o.id ? "Invio..." : o.fulfillment_status === "ERROR" ? "Riprova su AliExpress" : "Crea su AliExpress"}
                      </button>
                    )}
                    {o.aliexpress_order_id && o.fulfillment_status !== "DELIVERED" && (
                      <button className={btnGhost} disabled={busyId === o.id} onClick={() => act(o, "sync")}>Aggiorna stato</button>
                    )}
                    {itemUrl && <a className={btnGhost} href={itemUrl} target="_blank" rel="noopener noreferrer">Apri su AliExpress</a>}
                    {o.tracking_url && <a className={btnGhost} href={o.tracking_url} target="_blank" rel="noopener noreferrer">Traccia</a>}
                    <button className={btnGhost} onClick={() => setOpenId(open ? null : o.id)}>{open ? "Chiudi" : "Dettagli"}</button>
                  </div>
                </div>
                {open && (
                  <div className="mt-3 pt-3 border-t border-white/5 light:border-slate-200 grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-slate-400 light:text-slate-500">
                    <div className="space-y-0.5">
                      <p className="font-semibold text-slate-300 light:text-slate-700">Consegna</p>
                      <p>{o.recipient_name} · {o.recipient_phone}</p>
                      <p>{o.address_line1}{o.address_line2 ? `, ${o.address_line2}` : ""}</p>
                      <p>{o.postal_code} {o.city} ({o.province}) {o.country_code}</p>
                      <p>{o.shipping_days ?? "?"} giorni stimati</p>
                    </div>
                    <div className="space-y-0.5">
                      <p className="font-semibold text-slate-300 light:text-slate-700">Cliente</p>
                      <p>{o.quantity} × {euro(o.unit_price_cents)} + spedizione {euro(o.shipping_cents)} = {euro(o.amount_cents)}</p>
                      <p>
                        JavCash {euro(o.credit_applied_cents)} · in euro {euro(o.amount_due_cents)} ({o.payment_method === "CARD" ? "carta" : "bonifico"})
                        {o.bank_transfer_discount_cents > 0 && <> · sconto bonifico -{euro(o.bank_transfer_discount_cents)}</>}
                      </p>
                      <p>Pagato {formatDate(o.paid_at)}</p>
                    </div>
                    <div className="space-y-0.5">
                      <p className="font-semibold text-slate-300 light:text-slate-700">AliExpress</p>
                      <p>Ordine <span className="font-mono">{o.aliexpress_order_id ?? "—"}</span> · stato {o.aliexpress_order_status ?? "—"}</p>
                      <p>Nostro riferimento <span className="font-mono">{o.out_order_id ?? "—"}</span></p>
                      <p>Creato {formatDate(o.forwarded_at)} · tentativi {o.attempt_count ?? 0}</p>
                      {o.tracking_company && <p>Corriere {o.tracking_company}</p>}
                      <p>Ultimo controllo {formatDate(o.last_sync_at)}</p>
                      {o.shipped_at && <p>Spedito {formatDate(o.shipped_at)}</p>}
                      {o.delivered_at && <p>Consegnato {formatDate(o.delivered_at)}</p>}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      <Pagination {...pagination} label="ordini" />
    </div>
  );
}

// --- Prodotti inseriti a mano -----------------------------------------------------------------

/** The old "Acquisti Jav" plugin (Session 34), kept reachable: what
 *  was sold by hand before the API existed must keep working -- its orders,
 *  its JavCash, its history. New products go through "Catalogo AliExpress". */
function ManualTab() {
  return (
    <div className="space-y-4">
      <div className={`${card} p-4 text-xs text-slate-400 light:text-slate-500`}>
        Questa è la vecchia lista compilata a mano, prima del collegamento all&apos;API. Resta qui perché i prodotti già
        venduti così non devono sparire: si possono ancora nascondere o riattivare, e i loro ordini restano in
        &ldquo;Ordini&rdquo;. Per i prodotti nuovi usa <strong>Catalogo AliExpress</strong>: prezzi, disponibilità e
        spedizione si aggiornano da soli.
      </div>
      <AdminImportedProductsPanel />
    </div>
  );
}
