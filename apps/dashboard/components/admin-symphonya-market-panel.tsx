"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { useMarketplaceConfig } from "@/components/marketplace-rules-card";
import { ProductThumbnail } from "@/components/product-thumbnail";
import type {
  SymphonyaMarketAdminProductRead,
  SymphonyaMarketOrderRead,
  SymphonyaMarketProducerRead,
  SymphonyaMarketSettingsRead,
  SymphonyaFacets,
} from "@/lib/types";

/** «Marketplace SYMPHONYA» (Session 89, «Marketplace 6» per il cliente): il pannello del negozio
 *  di moda di lusso rifornito da Symphonya. Clone di admin-kappa-market-panel.tsx
 *  con tabelle e rotte sue, più il rifornimento: il feed «universal.csv» di
 *  Symphonya (o un CSV caricato a mano) porta tutto il catalogo, spento; il
 *  prezzo è costo × ricarico; si accende per marca o categoria; gli ordini
 *  si inseriscono a mano su symphonya.com con SKU ed EAN mostrati qui. */

const input =
  "w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500";
const label = "block text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-1";

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

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
    <div className="glass-card rounded-2xl p-5 border-white/10 light:border-slate-200 space-y-4">
      <div>
        <h3 className="text-sm font-bold text-white light:text-slate-900">{title}</h3>
        {subtitle && <p className="text-xs text-slate-400 light:text-slate-500 mt-0.5">{subtitle}</p>}
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

/** Session 88: i conti di un prodotto Symphonya per l'amministratore -- quanto
 *  lo paghiamo, a quanto lo vende il cliente, quanto ci resta. Con taglie a
 *  prezzi diversi si prende quella che rende meno, la stessa su cui il
 *  server calcola la percentuale JavCash «dal guadagno». Mai al cliente. */
/** Session 89: what the customer pays, always VAT included -- the stored
 *  price when it already has VAT (brand price), plus VAT when it comes from
 *  Symphonya's markup. Same as symphonya_market/service.py::customer_price_cents. */
function prezzoFinale(priceCents: number, negozio: SymphonyaMarketSettingsRead | undefined, iva: number): number {
  return negozio?.prices_include_vat ? priceCents : Math.floor((priceCents * (100 + iva) + 50) / 100);
}

function contiProdotto(p: SymphonyaMarketAdminProductRead, negozio: SymphonyaMarketSettingsRead | undefined, iva: number) {
  // La formula dell'utente (Session 89), la stessa del server
  // (symphonya_market/service.py::variant_gain_cents): guadagno = prezzo al
  // cliente senza IVA − prezzo a noi (così com'è, niente spedizione).
  const sped = 0;
  const conIva = true;
  const costoVero = (cost: number) => cost;
  const netto = (lordo: number) => Math.floor((lordo * 100 * 2 + (100 + iva)) / ((100 + iva) * 2));
  const vendibili = p.variants.filter((v) => v.cost_cents && v.price_cents > 0 && !v.below_cost);
  const conCosto = vendibili.length > 0 ? vendibili : p.variants.filter((v) => v.cost_cents && v.price_cents > 0);
  if (conCosto.length === 0) return null;
  const pubblico = (v: (typeof conCosto)[number]) => prezzoFinale(v.price_cents, negozio, iva);
  const guadagnoDi = (v: (typeof conCosto)[number]) => netto(pubblico(v)) - costoVero(v.cost_cents ?? 0);
  const peggiore = conCosto.reduce((a, b) => (guadagnoDi(b) / pubblico(b) < guadagnoDi(a) / pubblico(a) ? b : a));
  const costo = peggiore.cost_cents ?? 0;
  const guadagno = guadagnoDi(peggiore);
  return {
    costo,
    sped,
    conIva,
    costoVero: costoVero(costo),
    prezzo: pubblico(peggiore),
    prezzoNetto: netto(pubblico(peggiore)),
    suggerito: peggiore.suggested_price_cents,
    guadagno,
    margine: (guadagno * 100) / pubblico(peggiore),
    inPerdita: vendibili.length === 0,
  };
}

function percento(value: number): string {
  return `${value.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`;
}

// --- Impostazioni ----------------------------------------------------------

function Impostazioni() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["admin", "symphonya-market", "settings"],
    queryFn: () => get<SymphonyaMarketSettingsRead>("/symphonya-market/settings"),
  });
  const [form, setForm] = useState<SymphonyaMarketSettingsRead | null>(null);
  const corrente = form ?? data ?? null;
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const salva = useMutation({
    mutationFn: (payload: Partial<SymphonyaMarketSettingsRead>) =>
      send<SymphonyaMarketSettingsRead>("/symphonya-market/settings", "PATCH", payload),
    onSuccess: (row) => {
      setForm(row);
      setMessage({ ok: true, text: "Impostazioni salvate." });
      queryClient.invalidateQueries({ queryKey: ["admin", "symphonya-market"] });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  if (!corrente) return <Card title="Impostazioni">Caricamento…</Card>;

  return (
    <Card
      title="Impostazioni del negozio"
      subtitle="Finché è spento, il cliente non vede la scheda nello Shop: sparisce da sola."
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div>
          <span className={label}>Stato</span>
          <select
            className={input}
            value={corrente.enabled ? "on" : "off"}
            onChange={(e) => setForm({ ...corrente, enabled: e.target.value === "on" })}
          >
            <option value="off">Spento</option>
            <option value="on">Acceso</option>
          </select>
        </div>
        <div>
          <span className={label}>Spedizione</span>
          <select
            className={input}
            value={corrente.shipping_mode}
            onChange={(e) =>
              setForm({ ...corrente, shipping_mode: e.target.value as SymphonyaMarketSettingsRead["shipping_mode"] })
            }
          >
            <option value="CUSTOMER_PAYS">la paga il cliente</option>
            <option value="INCLUDED">inclusa nel prezzo</option>
          </select>
        </div>
        <div>
          <span className={label}>Spese di spedizione (€)</span>
          <input
            className={input}
            inputMode="decimal"
            value={(corrente.shipping_flat_cents / 100).toString()}
            onChange={(e) => setForm({ ...corrente, shipping_flat_cents: centsFrom(e.target.value) })}
          />
          <span className="block text-[10px] text-slate-500 mt-1">
            {corrente.shipping_mode === "INCLUDED"
              ? "Inclusa nel prezzo: al checkout non si addebita nulla."
              : "Addebitate una volta per ordine, non per articolo."}
          </span>
        </div>
        <div>
          <span className={label}>Tempi di consegna</span>
          <input
            className={input}
            value={corrente.shipping_days ?? ""}
            placeholder="es. 3-5"
            onChange={(e) => setForm({ ...corrente, shipping_days: e.target.value })}
          />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={() =>
            salva.mutate({
              enabled: corrente.enabled, shipping_mode: corrente.shipping_mode,
              shipping_flat_cents: corrente.shipping_flat_cents, shipping_days: corrente.shipping_days,
            })
          }
          disabled={salva.isPending}
          className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {salva.isPending ? "Salvo…" : "Salva impostazioni"}
        </button>
        <Esito message={message} />
      </div>
    </Card>
  );
}

// --- Feed Symphonya (Session 88) --------------------------------------------

/** Da dove arriva il catalogo: l'URL del feed con la chiave (si scrive, non
 *  si rilegge mai), l'import automatico ogni tre ore, il ricarico sul costo
 *  e l'esito dell'ultimo import. «Aggiorna ora» e «Carica CSV» partono in
 *  background: finché l'esito non cambia, il riquadro si rilegge da solo. */
function FeedSymphonya() {
  const queryClient = useQueryClient();
  const [waiting, setWaiting] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: ["admin", "symphonya-market", "settings"],
    queryFn: () => get<SymphonyaMarketSettingsRead>("/symphonya-market/settings"),
    refetchInterval: waiting ? 4000 : false,
  });
  const [feedUrl, setFeedUrl] = useState("");
  const [markup, setMarkup] = useState<string | null>(null);
  const [credit, setCredit] = useState<string | null>(null);
  const [sped, setSped] = useState<string | null>(null);
  const [creditMode, setCreditMode] = useState<"FIXED" | "MARGIN" | null>(null);
  const [share, setShare] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // L'import è finito quando l'esito sulle impostazioni è cambiato rispetto a
  // quello letto al momento del clic: derivato qui, non sincronizzato con un
  // effetto.
  const lastSeen = data ? `${data.last_import_at ?? ""}` : "";
  const importing = waiting !== null && lastSeen === waiting;
  const markupValue = markup ?? String(data?.markup_percentage ?? 0);
  const creditValue = credit ?? String(data?.credit_percentage ?? 30);
  const creditModeValue = creditMode ?? data?.credit_mode ?? "FIXED";
  const shareValue = share ?? String(data?.credit_margin_share ?? 50);
  const spedValue = sped ?? ((data?.shipping_cost_cents ?? 500) / 100).toString();

  const salva = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      send<SymphonyaMarketSettingsRead>("/symphonya-market/settings", "PATCH", payload),
    onSuccess: () => {
      setFeedUrl("");
      setMarkup(null);
      setCredit(null);
      setCreditMode(null);
      setShare(null);
      setSped(null);
      setMessage({
        ok: true,
        text: "Salvato. Prezzi e percentuale JavCash si aggiornano su tutti i prodotti, tranne quelli personalizzati a mano.",
      });
      queryClient.invalidateQueries({ queryKey: ["admin", "symphonya-market"] });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  const aggiorna = useMutation({
    mutationFn: () => send("/symphonya-market/feed/import", "POST", {}),
    onSuccess: () => {
      setWaiting(lastSeen);
      setMessage({ ok: true, text: "Import avviato: di solito bastano pochi secondi, il primo può durare un minuto." });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  const carica = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch("/api/proxy/symphonya-market/feed/upload", { method: "POST", body });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return (await res.json()) as { products: number };
    },
    onSuccess: (r) => {
      setWaiting(lastSeen);
      setMessage({ ok: true, text: `File valido, ${r.products} prodotti: import avviato.` });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  if (!data) return <Card title="Feed Symphonya">Caricamento…</Card>;
  return (
    <Card
      title="Catalogo da Symphonya"
      subtitle="L'API di Symphonya porta tutto il catalogo (oltre 30.000 profumi e cosmetici), spento: accendi per marca o categoria qui sotto. Si aggiorna da solo ogni 3 ore."
    >
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="lg:col-span-2">
          <span className={label}>Chiave API di Symphonya</span>
          <input
            className={input}
            type="password"
            autoComplete="off"
            value={feedUrl}
            placeholder={data.feed_configured ? `Configurata ${data.feed_hint ?? ""} — incolla per cambiarla` : "La chiave del tuo account Symphonya (40 caratteri)"}
            onChange={(e) => setFeedUrl(e.target.value)}
          />
        </div>
        <div>
          <span className={label}>Ricarico sopra il prezzo di Symphonya (%)</span>
          <input className={input} inputMode="numeric" value={markupValue} onChange={(e) => setMarkup(e.target.value)} />
          <span className="block text-[10px] text-slate-500 mt-1">
            Il cliente paga il prezzo al pubblico consigliato da Symphonya (IVA inclusa; dove manca, il costo + 40% +
            IVA) più questo ricarico (0 = esattamente quello). Il nostro costo lo vedi solo tu.
          </span>
          {/* Session 88: la percentuale JavCash fissa per tutti, oppure calcolata
              su ogni prodotto da quanto ci guadagniamo. */}
          <span className={`${label} mt-3`}>JavCash pagabile</span>
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-xs text-slate-300 light:text-slate-700 cursor-pointer">
              <input type="radio" checked={creditModeValue === "FIXED"} onChange={() => setCreditMode("FIXED")} />
              Uguale per tutti:
              <input
                className={`${input} !w-16 !py-1`}
                inputMode="numeric"
                value={creditValue}
                disabled={creditModeValue !== "FIXED"}
                onChange={(e) => setCredit(e.target.value)}
              />
              %
            </label>
            <label className="flex items-center gap-2 text-xs text-slate-300 light:text-slate-700 cursor-pointer">
              <input type="radio" checked={creditModeValue === "MARGIN"} onChange={() => setCreditMode("MARGIN")} />
              Dal nostro guadagno, il
              <input
                className={`${input} !w-16 !py-1`}
                inputMode="numeric"
                value={shareValue}
                disabled={creditModeValue !== "MARGIN"}
                onChange={(e) => setShare(e.target.value)}
              />
              % del guadagno
            </label>
          </div>
          <span className="block text-[10px] text-slate-500 mt-1">
            {creditModeValue === "MARGIN"
              ? "Guadagno = prezzo al cliente senza IVA − prezzo a noi. Il cliente paga in JavCash fino a questa quota del guadagno, in % del prezzo IVA inclusa. Si ricalcola a ogni import, per difetto."
              : "Quanta parte del prezzo il cliente può pagare in JavCash, per tutti i prodotti Symphonya. Mai 100."}{" "}
            Un prodotto modificato a mano tiene la sua.
          </span>
        </div>
      </div>
      <label className="flex items-center gap-2 text-xs text-slate-300 light:text-slate-700 cursor-pointer">
        <input
          type="checkbox"
          checked={data.auto_import}
          onChange={(e) => salva.mutate({ auto_import: e.target.checked })}
        />
        Aggiorna da solo ogni 3 ore (costi, listino, scorte)
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() =>
            salva.mutate({
              ...(feedUrl.trim() ? { api_key: feedUrl.trim() } : {}),
              markup_percentage: Number(markupValue) || 0,
              credit_percentage: Math.min(99, Number(creditValue) || 0),
              credit_mode: creditModeValue,
              credit_margin_share: Math.min(100, Number(shareValue) || 0),
            })
          }
          disabled={salva.isPending}
          className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {salva.isPending ? "Salvo…" : "Salva"}
        </button>
        <button
          onClick={() => aggiorna.mutate()}
          disabled={!data.feed_configured || importing || aggiorna.isPending}
          className="px-4 py-2 rounded-xl border border-white/10 light:border-slate-300 text-xs font-semibold text-slate-200 light:text-slate-700 hover:bg-white/5 light:hover:bg-slate-900/5 cursor-pointer disabled:opacity-40"
        >
          {importing ? "Import in corso…" : "Aggiorna ora da Symphonya"}
        </button>
        <button
          onClick={() => fileRef.current?.click()}
          disabled={importing || carica.isPending}
          className="px-4 py-2 rounded-xl border border-white/10 light:border-slate-300 text-xs font-semibold text-slate-200 light:text-slate-700 hover:bg-white/5 light:hover:bg-slate-900/5 cursor-pointer disabled:opacity-40"
        >
          {carica.isPending ? "Controllo il file…" : "Carica un file JSON Symphonya"}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".json,application/json"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) carica.mutate(file);
            e.target.value = "";
          }}
        />
      </div>
      <Esito message={message} />
      {data.last_import_at && (
        <p className={`text-[11px] ${data.last_import_error ? "text-rose-400" : "text-slate-400 light:text-slate-500"}`}>
          Ultimo import {new Date(data.last_import_at).toLocaleString("it-IT")}:{" "}
          {data.last_import_error ?? data.last_import_summary}
        </p>
      )}
    </Card>
  );
}

/** Accendere 3.500 prodotti uno a uno non si fa: si accende una marca o una
 *  categoria intera. Ogni riga dice quanti prodotti ha e quanti sono accesi. */
function AccendiInBlocco() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["admin", "symphonya-market", "facets"],
    queryFn: () => get<SymphonyaFacets>("/symphonya-market/facets"),
  });
  const [tab, setTab] = useState<"brands" | "subcategories">("brands");
  const [cerca, setCerca] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const cambia = useMutation({
    mutationFn: (payload: { status: "ACTIVE" | "INACTIVE"; producer_id?: string; subcategory?: string; what: string }) =>
      send<{ updated: number }>("/symphonya-market/products/bulk-status", "POST", {
        status: payload.status, producer_id: payload.producer_id, subcategory: payload.subcategory,
      }).then((r) => ({ ...r, ...payload })),
    onSuccess: (r) => {
      setMessage({
        ok: true,
        text: `${r.what}: ${r.updated} prodotti ${r.status === "ACTIVE" ? "accesi" : "spenti"}.`,
      });
      queryClient.invalidateQueries({ queryKey: ["admin", "symphonya-market"] });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  const testo = cerca.trim().toLowerCase();
  const righe = (tab === "brands" ? data?.brands ?? [] : data?.subcategories ?? [])
    .map((r) => ({
      key: "id" in r ? r.id : r.key,
      name: r.name,
      products: r.products,
      active: r.active,
      isBrand: "id" in r,
    }))
    .filter((r) => !testo || r.name.toLowerCase().includes(testo));

  return (
    <Card title="Accendi e spegni in blocco" subtitle="Per marca o per categoria. I prodotti nuovi arrivano sempre spenti.">
      <div className="flex flex-wrap items-center gap-2">
        {(
          [
            ["brands", `Marche (${data?.brands.length ?? 0})`],
            ["subcategories", `Categorie (${data?.subcategories.length ?? 0})`],
          ] as const
        ).map(([key, text]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-2.5 py-1.5 rounded-lg text-[11px] font-semibold border cursor-pointer ${
              tab === key
                ? "border-orange-500/50 bg-orange-500/15 text-orange-300 light:text-orange-700"
                : "border-white/10 light:border-slate-300 text-slate-400 light:text-slate-600 hover:bg-white/5"
            }`}
          >
            {text}
          </button>
        ))}
        <input className={`${input} max-w-xs`} placeholder="Cerca…" value={cerca} onChange={(e) => setCerca(e.target.value)} />
      </div>
      <Esito message={message} />
      <div className="max-h-80 overflow-y-auto rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
        {righe.map((r) => (
          <div key={r.key} className="flex items-center gap-3 px-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-white light:text-slate-900 truncate">{r.name}</p>
              <p className="text-[11px] text-slate-500">
                {r.products} prodotti · {r.active} accesi
              </p>
            </div>
            <button
              onClick={() =>
                cambia.mutate({
                  status: "ACTIVE", what: r.name,
                  ...(r.isBrand ? { producer_id: r.key } : { subcategory: r.key }),
                })
              }
              disabled={cambia.isPending || r.active === r.products}
              className="px-2.5 py-1 rounded-lg text-[11px] font-bold border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 cursor-pointer disabled:opacity-30"
            >
              Accendi tutti
            </button>
            <button
              onClick={() =>
                cambia.mutate({
                  status: "INACTIVE", what: r.name,
                  ...(r.isBrand ? { producer_id: r.key } : { subcategory: r.key }),
                })
              }
              disabled={cambia.isPending || r.active === 0}
              className="px-2.5 py-1 rounded-lg text-[11px] font-semibold border border-white/10 light:border-slate-300 text-slate-400 hover:bg-white/5 cursor-pointer disabled:opacity-30"
            >
              Spegni tutti
            </button>
          </div>
        ))}
        {righe.length === 0 && <p className="px-3 py-3 text-xs text-slate-500">Niente da mostrare: fai prima un import da Symphonya.</p>}
      </div>
    </Card>
  );
}

// --- Marchi (le «aziende produttrici» del clone) ---------------------------------------------------

const PRODUTTORE_VUOTO = {
  name: "", description: "", website_url: "", vat_number: "", email: "", phone: "", address: "",
};

function Produttori() {
  const queryClient = useQueryClient();
  // Dietro un pulsante come le categorie: le aziende si compilano una
  // volta e si toccano di rado, mentre i prodotti si caricano ogni giorno.
  const [aperto, setAperto] = useState(false);
  const { data: producers } = useQuery({
    queryKey: ["admin", "symphonya-market", "producers"],
    queryFn: () => get<SymphonyaMarketProducerRead[]>("/symphonya-market/producers"),
  });
  const [form, setForm] = useState({ ...PRODUTTORE_VUOTO });
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const crea = useMutation({
    mutationFn: () =>
      send<SymphonyaMarketProducerRead>("/symphonya-market/producers", "POST", {
        ...form,
        website_url: form.website_url || null,
        vat_number: form.vat_number || null,
        email: form.email || null,
        phone: form.phone || null,
        address: form.address || null,
      }),
    onSuccess: (p) => {
      setForm({ ...PRODUTTORE_VUOTO });
      setMessage({ ok: true, text: `«${p.name}» aggiunta.` });
      queryClient.invalidateQueries({ queryKey: ["admin", "symphonya-market", "producers"] });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  if (!aperto) {
    return (
      <div className="glass-card rounded-2xl p-4 border-white/10 light:border-slate-200 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-bold text-white light:text-slate-900">Marchi</h3>
          <p className="text-xs text-slate-400 light:text-slate-500 mt-0.5">
            {(producers ?? []).length === 0
              ? "Nessuna marca ancora: arrivano da sole con il primo import da Symphonya."
              : `${(producers ?? []).length} in elenco: ${(producers ?? []).slice(0, 3).map((p) => p.name).join(", ")}${(producers ?? []).length > 3 ? "…" : ""}`}
          </p>
        </div>
        <button
          onClick={() => setAperto(true)}
          className="px-4 py-2 rounded-xl border border-orange-500/40 text-xs font-semibold text-orange-400 hover:bg-orange-500/10 transition cursor-pointer shrink-0"
        >
          Gestisci marchi
        </button>
      </div>
    );
  }

  return (
    <Card
      title="Marchi"
      subtitle="Chi fa la merce. L'email è quella a cui mandiamo l'ordine quando il cliente paga."
    >
      <button
        onClick={() => setAperto(false)}
        className="text-[11px] font-semibold text-slate-400 light:text-slate-500 hover:text-white light:hover:text-slate-900 cursor-pointer"
      >
        ← Chiudi
      </button>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div className="sm:col-span-2">
          <span className={label}>Nome del marchio *</span>
          <input className={input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <span className={label}>Partita IVA</span>
          <input className={input} value={form.vat_number} onChange={(e) => setForm({ ...form, vat_number: e.target.value })} />
        </div>
        <div className="sm:col-span-3">
          <span className={label}>Descrizione (la legge il cliente)</span>
          <textarea
            className={`${input} min-h-[70px]`}
            value={form.description}
            placeholder="Chi sono, cosa producono, dove."
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div>
          <span className={label}>Sito</span>
          <input className={input} value={form.website_url} placeholder="https://" onChange={(e) => setForm({ ...form, website_url: e.target.value })} />
        </div>
        <div>
          <span className={label}>Email per gli ordini</span>
          <input className={input} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <span className="block text-[10px] text-slate-500 mt-1">
            È qui che arriva l&apos;ordine quando il cliente paga. Senza, l&apos;ordine non si può inviare.
          </span>
        </div>
        <div>
          <span className={label}>Telefono</span>
          <input className={input} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        </div>
        <div className="sm:col-span-3">
          <span className={label}>Sede</span>
          <input className={input} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={() => crea.mutate()}
          disabled={crea.isPending || form.name.trim().length === 0}
          className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {crea.isPending ? "Aggiungo…" : "Aggiungi marchio"}
        </button>
        <Esito message={message} />
      </div>

      {(producers ?? []).length > 0 && (
        <div className="rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
          {(producers ?? []).map((p) => (
            <div key={p.id} className="px-3 py-2">
              <p className="text-xs font-semibold text-white light:text-slate-900">{p.name}</p>
              <p className="text-[11px] text-slate-500 truncate">
                {p.email ? p.email : <span className="text-amber-400">manca l&apos;email: gli ordini non partiranno</span>}
                {p.description ? ` · ${p.description}` : ""}
              </p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// --- Catalogo --------------------------------------------------------------

/** La foto del prodotto: si allega dal computer (finisce sul nostro server,
 *  POST /symphonya-market/images) oppure si incolla un URL come prima. In tutti e
 *  due i casi al form arriva solo un URL. */
function ImmagineProdotto({ value, onChange }: { value: string; onChange: (url: string) => void }) {
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
      const res = await fetch("/api/proxy/symphonya-market/images", { method: "POST", body });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { image_url } = await res.json();
      onChange(image_url);
    } catch (err: unknown) {
      setError((err as Error).message || "Caricamento fallito. Riprova.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="flex items-start gap-3">
      <div className="w-16 h-16 rounded-lg overflow-hidden border border-white/10 light:border-slate-200 shrink-0">
        <ProductThumbnail imageUrl={value || null} alt="Foto prodotto" iconClassName="w-7 h-7 text-orange-400/40" />
      </div>
      <div className="flex-1 min-w-0 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={allega} className="hidden" />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 cursor-pointer transition disabled:opacity-40"
          >
            {uploading ? "Caricamento…" : value ? "Cambia foto" : "Allega foto"}
          </button>
          {value && !uploading && (
            <button
              type="button"
              onClick={() => onChange("")}
              className="px-2 py-1.5 rounded-lg text-[11px] font-semibold text-rose-400 hover:bg-rose-500/10 cursor-pointer"
            >
              Togli
            </button>
          )}
          <span className="text-[10px] text-slate-500">JPG, PNG, WebP o GIF, max 5 MB.</span>
        </div>
        <input
          className={input}
          placeholder="…oppure incolla l'URL di un'immagine"
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
 *  in fondo alla lista: con centinaia di prodotti (Marketplace SYMPHONYA ne ha 249)
 *  bisognava scorrere tutto per arrivarci. */
type Editor = { mode: "create" } | { mode: "edit"; id: string };

function Catalogo() {
  const queryClient = useQueryClient();
  const { data: products } = useQuery({
    queryKey: ["admin", "symphonya-market", "products"],
    queryFn: () => get<SymphonyaMarketAdminProductRead[]>("/symphonya-market/products"),
  });
  const { data: producers } = useQuery({
    queryKey: ["admin", "symphonya-market", "producers"],
    queryFn: () => get<SymphonyaMarketProducerRead[]>("/symphonya-market/producers"),
  });
  const [editor, setEditor] = useState<Editor | null>(null);
  const [cerca, setCerca] = useState("");
  const [stato, setStato] = useState<"TUTTI" | "ACTIVE" | "INACTIVE">("TUTTI");
  const [produttore, setProduttore] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  // Symphonya porta migliaia di prodotti: se ne disegnano cento alla volta.
  const [limite, setLimite] = useState(100);
  const { data: negozio } = useQuery({
    queryKey: ["admin", "symphonya-market", "settings"],
    queryFn: () => get<SymphonyaMarketSettingsRead>("/symphonya-market/settings"),
  });
  const { data: marketplaceConfig } = useMarketplaceConfig();
  const iva = marketplaceConfig?.vat_percentage ?? 0;

  const spegni = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "ACTIVE" | "INACTIVE" }) =>
      send<SymphonyaMarketAdminProductRead>(`/symphonya-market/products/${id}`, "PATCH", { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "symphonya-market", "products"] }),
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  const tutti = products ?? [];
  const testo = cerca.trim().toLowerCase();
  // Si cerca anche nella descrizione e negli sku: nel Marketplace SYMPHONYA il codice
  // articolo sta nella descrizione e l'EAN è lo sku di ogni variante.
  const visibili = tutti.filter(
    (p) =>
      (stato === "TUTTI" || p.status === stato) &&
      (!produttore || p.producer_id === produttore) &&
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
    <Card title="Prodotti in catalogo" subtitle={`${tutti.length} prodotti.`}>
      <div className="flex flex-col lg:flex-row gap-2 lg:items-center">
        <input
          className={`${input} lg:max-w-xs`}
          placeholder="Cerca per nome, codice o EAN…"
          value={cerca}
          onChange={(e) => setCerca(e.target.value)}
        />
        <div className="flex flex-wrap gap-1.5">
          {(
            [
              ["TUTTI", "Tutti"],
              ["ACTIVE", "In vendita"],
              ["INACTIVE", "Spenti"],
            ] as const
          ).map(([key, testoBottone]) => (
            <button
              key={key}
              onClick={() => setStato(key)}
              className={`px-2.5 py-1.5 rounded-lg text-[11px] font-semibold border cursor-pointer ${
                stato === key
                  ? "border-orange-500/50 bg-orange-500/15 text-orange-300 light:text-orange-700"
                  : "border-white/10 light:border-slate-300 text-slate-400 light:text-slate-600 hover:bg-white/5 light:hover:bg-slate-900/5"
              }`}
            >
              {testoBottone} ({quanti[key]})
            </button>
          ))}
        </div>
        {(producers ?? []).length > 1 && (
          <select className={`${input} lg:max-w-[12rem]`} value={produttore} onChange={(e) => setProduttore(e.target.value)}>
            <option value="">Tutti i marchi</option>
            {(producers ?? []).map((pr) => (
              <option key={pr.id} value={pr.id}>{pr.name}</option>
            ))}
          </select>
        )}
        <button
          onClick={() => setEditor({ mode: "create" })}
          className="lg:ml-auto px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer whitespace-nowrap"
        >
          + Nuovo prodotto
        </button>
      </div>
      <Esito message={message} />

      {tutti.length === 0 ? (
        <p className="text-xs text-slate-500">Nessun prodotto ancora. Premi «+ Nuovo prodotto» per caricarne uno.</p>
      ) : visibili.length === 0 ? (
        <p className="text-xs text-slate-500">Nessun prodotto corrisponde alla ricerca.</p>
      ) : (
        <>
          {visibili.length !== tutti.length && (
            <p className="text-[11px] text-slate-500">Ne mostro {visibili.length} su {tutti.length}.</p>
          )}
          <div className="rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
            {visibili.slice(0, limite).map((p) => (
              <div key={p.id} className="flex items-center gap-3 p-3">
                <button
                  onClick={() => setEditor({ mode: "edit", id: p.id })}
                  className="flex items-center gap-3 min-w-0 flex-1 text-left cursor-pointer"
                >
                  <ProductThumbnail imageUrl={p.image_url} alt={p.name} className="w-11 h-11 rounded-lg object-cover shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-white light:text-slate-900 truncate">{p.name}</p>
                    <p className="text-[11px] text-slate-500 truncate">
                      {p.producer?.name ? `${p.producer.name} · ` : ""}
                      {p.variants.length} {p.variants.length === 1 ? "variante" : "varianti"}
                      {p.missing_from_feed && " · non più su Symphonya"}
                    </p>
                    {(() => {
                      const c = contiProdotto(p, negozio, iva);
                      return c ? (
                        <p className="text-[11px] text-slate-400 light:text-slate-600 truncate">
                          A noi <strong>{euro(c.costo)}</strong>
                          {c.costoVero !== c.costo && <> (con sped.{c.conIva ? " e IVA" : ""} {euro(c.costoVero)})</>} · Al
                          pubblico <strong>{euro(c.prezzo)}</strong>
                          {c.conIva ? " IVA incl." : ""} · Guadagno{" "}
                          <strong className={c.guadagno > 0 ? "text-emerald-400 light:text-emerald-700" : "text-rose-400"}>
                            {euro(c.guadagno)}
                          </strong>{" "}
                          ({percento(c.margine)}) · JavCash <strong className="text-orange-400">{p.credit_discount_percentage}%</strong>
                          {c.inPerdita && <span className="text-rose-400 font-semibold"> · in perdita: non in vendita</span>}
                        </p>
                      ) : (
                        <p className="text-[11px] text-slate-500 truncate">
                          {euro(Math.min(...p.variants.map((v) => v.price_cents)))} · JavCash {p.credit_discount_percentage}%
                        </p>
                      );
                    })()}
                  </div>
                </button>
                <button
                  onClick={() => setEditor({ mode: "edit", id: p.id })}
                  className="px-2.5 py-1 rounded-lg text-[11px] font-semibold border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10 cursor-pointer"
                >
                  Modifica
                </button>
                <button
                  onClick={() => spegni.mutate({ id: p.id, status: p.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" })}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-bold border cursor-pointer ${
                    p.status === "ACTIVE"
                      ? "border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10"
                      : "border-white/10 light:border-slate-300 text-slate-500 hover:bg-white/5"
                  }`}
                >
                  {p.status === "ACTIVE" ? "In vendita" : "Spento"}
                </button>
              </div>
            ))}
          </div>
          {visibili.length > limite && (
            <button
              onClick={() => setLimite(limite + 100)}
              className="w-full py-2 rounded-xl border border-white/10 light:border-slate-300 text-xs font-semibold text-slate-300 light:text-slate-600 hover:bg-white/5 cursor-pointer"
            >
              Mostra altri {Math.min(100, visibili.length - limite)} (di {visibili.length - limite})
            </button>
          )}
        </>
      )}

      {editor?.mode === "create" && (
        <NuovoProdotto
          producers={producers ?? []}
          onClose={() => setEditor(null)}
          onCreated={(p) => {
            setEditor(null);
            setMessage({ ok: true, text: `«${p.name}» caricato.` });
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
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full sm:max-w-3xl max-h-[92vh] overflow-y-auto rounded-t-3xl sm:rounded-2xl border border-white/10 light:border-slate-200 bg-slate-950 light:bg-white shadow-2xl animate-scale-up">
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-5 py-3 border-b border-white/10 light:border-slate-200 bg-slate-950/95 light:bg-white/95 backdrop-blur">
          <h3 className="text-sm font-bold text-white light:text-slate-900 truncate">{title}</h3>
          <button
            onClick={onClose}
            aria-label="Chiudi"
            className="p-1.5 rounded-lg text-slate-400 hover:text-white light:hover:text-slate-900 hover:bg-white/10 light:hover:bg-slate-900/5 cursor-pointer"
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
  producers: SymphonyaMarketProducerRead[];
  onClose: () => void;
  onCreated: (p: SymphonyaMarketAdminProductRead) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ ...PRODOTTO_VUOTO });
  const [variants, setVariants] = useState<VarianteForm[]>([{ label: "Unica", price: "", inventory: "" }]);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const crea = useMutation({
    mutationFn: () =>
      send<SymphonyaMarketAdminProductRead>("/symphonya-market/products", "POST", {
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
      }),
    onSuccess: (p) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "symphonya-market", "products"] });
      onCreated(p);
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  return (
    <Finestra title="Nuovo prodotto" onClose={onClose}>
      <p className="text-[11px] text-slate-500">
        Serve almeno una variante con il suo prezzo: un prodotto senza varianti non sarebbe comprabile.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="sm:col-span-2">
          <span className={label}>Nome *</span>
          <input className={input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <span className={label}>Marchio</span>
          <select className={input} value={form.producer_id} onChange={(e) => setForm({ ...form, producer_id: e.target.value })}>
            <option value="">— nessuno —</option>
            {producers.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <div>
          <span className={label}>JavCash max (%)</span>
          <input
            className={input}
            inputMode="numeric"
            value={form.credit_discount_percentage}
            onChange={(e) => setForm({ ...form, credit_discount_percentage: e.target.value })}
          />
          <span className="block text-[10px] text-slate-500 mt-1">Mai 100: è la regola dei Marketplace.</span>
        </div>
        <div className="sm:col-span-3">
          <span className={label}>Descrizione</span>
          <textarea
            className={`${input} min-h-[70px]`}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div>
          <span className={label}>Costo per noi (€)</span>
          <input
            className={input}
            inputMode="decimal"
            value={form.unit_cost}
            onChange={(e) => setForm({ ...form, unit_cost: e.target.value })}
          />
          <span className="block text-[10px] text-slate-500 mt-1">Serve solo al margine, mai mostrato.</span>
        </div>
        <div className="sm:col-span-4">
          <span className={label}>Immagine</span>
          <ImmagineProdotto value={form.image_url} onChange={(url) => setForm({ ...form, image_url: url })} />
        </div>
      </div>

      <div className="space-y-2">
        <p className={label}>Varianti</p>
        {variants.map((v, i) => (
          <div key={i} className="grid grid-cols-1 sm:grid-cols-4 gap-2">
            <input
              className={input}
              placeholder="Etichetta (es. Tester)"
              value={v.label}
              onChange={(e) => setVariants(variants.map((x, j) => (i === j ? { ...x, label: e.target.value } : x)))}
            />
            <input
              className={input}
              inputMode="decimal"
              placeholder="Prezzo €"
              value={v.price}
              onChange={(e) => setVariants(variants.map((x, j) => (i === j ? { ...x, price: e.target.value } : x)))}
            />
            <input
              className={input}
              inputMode="numeric"
              placeholder="Scorta (vuoto = illimitata)"
              value={v.inventory}
              onChange={(e) => setVariants(variants.map((x, j) => (i === j ? { ...x, inventory: e.target.value } : x)))}
            />
            {variants.length > 1 && (
              <button
                onClick={() => setVariants(variants.filter((_, j) => j !== i))}
                className="px-3 py-2 rounded-lg text-xs font-semibold text-rose-400 hover:bg-rose-500/10 cursor-pointer"
              >
                Togli
              </button>
            )}
          </div>
        ))}
        <button
          onClick={() => setVariants([...variants, { label: "", price: "", inventory: "" }])}
          className="text-[11px] font-semibold text-orange-400 hover:text-orange-300 cursor-pointer"
        >
          + Aggiungi variante
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-white/10 light:border-slate-200">
        <button
          onClick={() => crea.mutate()}
          disabled={crea.isPending || !form.name.trim() || variants.every((v) => !v.price)}
          className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {crea.isPending ? "Carico…" : "Carica prodotto"}
        </button>
        <button onClick={onClose} className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-white/5 light:hover:bg-slate-900/5 cursor-pointer">
          Annulla
        </button>
        <Esito message={message} />
      </div>
    </Finestra>
  );
}

function ModificaProdotto({ product, producers, onClose }: {
  product: SymphonyaMarketAdminProductRead;
  producers: SymphonyaMarketProducerRead[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const invalida = () => queryClient.invalidateQueries({ queryKey: ["admin", "symphonya-market", "products"] });
  const { data: negozio } = useQuery({
    queryKey: ["admin", "symphonya-market", "settings"],
    queryFn: () => get<SymphonyaMarketSettingsRead>("/symphonya-market/settings"),
  });
  const { data: marketplaceConfig } = useMarketplaceConfig();
  const negozioIva = marketplaceConfig?.vat_percentage ?? 0;
  // I campi del prodotto sono una bozza: partono dal prodotto quando la
  // finestra si apre (il componente è montato con key=id) e si salvano con
  // «Salva modifiche». Prezzi e scorte invece si salvano campo per campo.
  const [bozza, setBozza] = useState({
    name: product.name,
    description: product.description,
    credit_discount_percentage: product.credit_discount_percentage,
    producer_id: product.producer_id,
    image_url: product.image_url,
    markup_percentage: product.markup_percentage,
  });
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [filtroVarianti, setFiltroVarianti] = useState("");
  const [prezzoTutte, setPrezzoTutte] = useState("");

  const salva = useMutation({
    mutationFn: () =>
      send<SymphonyaMarketAdminProductRead>(`/symphonya-market/products/${product.id}`, "PATCH", {
        ...bozza,
        producer_id: bozza.producer_id || null,
        image_url: bozza.image_url || null,
      }),
    onSuccess: () => {
      invalida();
      onClose();
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  const salvaVariante = useMutation({
    mutationFn: ({ id, price_cents, inventory }: { id: string; price_cents: number; inventory: number | null }) =>
      send(`/symphonya-market/variants/${id}`, "PATCH", { price_cents, inventory }),
    onSuccess: invalida,
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  // Un prezzo per tutte le varianti: nel Marketplace SYMPHONYA un capo ha decine di
  // taglie e colori allo stesso prezzo, e scriverlo cento volte non è un
  // lavoro. A gruppi di dieci per non sommergere il server.
  const applicaATutte = useMutation({
    mutationFn: async (price_cents: number) => {
      const daFare = product.variants;
      for (let i = 0; i < daFare.length; i += 10) {
        await Promise.all(
          daFare.slice(i, i + 10).map((v) =>
            send(`/symphonya-market/variants/${v.id}`, "PATCH", { price_cents, inventory: v.inventory })
          )
        );
      }
      return daFare.length;
    },
    onSuccess: (n) => {
      setPrezzoTutte("");
      setMessage({ ok: true, text: `Prezzo applicato a ${n} varianti.` });
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
    onSettled: invalida,
  });
  const usaQuellaDelNegozio = useMutation({
    mutationFn: () => send(`/symphonya-market/products/${product.id}`, "PATCH", { credit_locked: false }),
    onSuccess: () => {
      invalida();
      onClose();
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  const sbloccaPrezzo = useMutation({
    mutationFn: (id: string) => send(`/symphonya-market/variants/${id}`, "PATCH", { price_locked: false }),
    onSuccess: invalida,
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  const cambiaStato = useMutation({
    mutationFn: () =>
      send<SymphonyaMarketAdminProductRead>(`/symphonya-market/products/${product.id}`, "PATCH", {
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
    <Finestra title={`Modifica «${product.name}»`} onClose={onClose}>
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`px-2 py-0.5 rounded-md text-[11px] font-bold ${
            product.status === "ACTIVE" ? "bg-emerald-500/15 text-emerald-400" : "bg-white/5 light:bg-slate-900/5 text-slate-500"
          }`}
        >
          {product.status === "ACTIVE" ? "In vendita" : "Spento: il cliente non lo vede"}
        </span>
        <button
          onClick={() => cambiaStato.mutate()}
          disabled={cambiaStato.isPending}
          className="px-2.5 py-1 rounded-lg text-[11px] font-semibold border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10 cursor-pointer disabled:opacity-40"
        >
          {product.status === "ACTIVE" ? "Spegni" : "Metti in vendita"}
        </button>
      </div>

      {/* Session 88: i conti del prodotto, chiari, solo per l'amministratore. */}
      {(() => {
        const c = contiProdotto(product, negozio, negozioIva);
        if (!c) return null;
        return (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="rounded-xl bg-white/5 light:bg-slate-900/5 p-3">
              <p className={label}>Prezzo a noi</p>
              <p className="text-base font-extrabold text-white light:text-slate-900 tabular-nums">{euro(c.costo)}</p>
              <p className="text-[10px] text-slate-500">
                quanto lo paghiamo a Symphonya
              </p>
            </div>
            <div className="rounded-xl bg-white/5 light:bg-slate-900/5 p-3">
              <p className={label}>Prezzo al pubblico</p>
              <p className="text-base font-extrabold text-white light:text-slate-900 tabular-nums">{euro(c.prezzo)}</p>
              <p className="text-[10px] text-slate-500">
                {negozio?.prices_include_vat
                  ? "IVA inclusa, prezzo consigliato da Symphonya"
                  : "IVA inclusa: prezzo di Symphonya (ricarico) + IVA"}
                {` · senza IVA ${euro(c.prezzoNetto)}`}
              </p>
            </div>
            <div className={`rounded-xl p-3 ${c.guadagno > 0 ? "bg-emerald-500/10" : "bg-rose-500/10"}`}>
              <p className={label}>Guadagno</p>
              <p className={`text-base font-extrabold tabular-nums ${c.guadagno > 0 ? "text-emerald-400 light:text-emerald-700" : "text-rose-400"}`}>
                {euro(c.guadagno)}
              </p>
              <p className="text-[10px] text-slate-500">
                {c.inPerdita
                  ? "in perdita: non in vendita"
                  : `${euro(c.prezzoNetto)} − ${euro(c.costo)} · ${percento(c.margine)} del prezzo`}
              </p>
            </div>
            <div className="rounded-xl bg-orange-500/10 p-3">
              <p className={label}>JavCash pagabile</p>
              <p className="text-base font-extrabold text-orange-400 tabular-nums">{product.credit_discount_percentage}%</p>
              <p className="text-[10px] text-slate-500">
                fino a {euro(Math.floor((c.prezzo * product.credit_discount_percentage) / 100))}
                {product.credit_locked
                  ? " · scelta a mano"
                  : negozio?.credit_mode === "MARGIN"
                    ? ` · il ${negozio.credit_margin_share}% del guadagno`
                    : " · quella del negozio"}
              </p>
            </div>
          </div>
        );
      })()}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="sm:col-span-2">
          <span className={label}>Nome</span>
          <input className={input} value={bozza.name} onChange={(e) => setBozza({ ...bozza, name: e.target.value })} />
        </div>
        <div>
          <span className={label}>Marchio</span>
          <select
            className={input}
            value={bozza.producer_id ?? ""}
            onChange={(e) => setBozza({ ...bozza, producer_id: e.target.value || null })}
          >
            <option value="">— nessuno —</option>
            {producers.map((pr) => (
              <option key={pr.id} value={pr.id}>{pr.name}</option>
            ))}
          </select>
        </div>
        <div className="sm:col-span-2">
          <span className={label}>Descrizione</span>
          <textarea
            className={`${input} min-h-[70px]`}
            value={bozza.description}
            onChange={(e) => setBozza({ ...bozza, description: e.target.value })}
          />
        </div>
        <div>
          <span className={label}>JavCash pagabile (%)</span>
          <input
            className={input}
            inputMode="numeric"
            value={String(bozza.credit_discount_percentage)}
            onChange={(e) =>
              setBozza({ ...bozza, credit_discount_percentage: Math.min(99, Number(e.target.value) || 0) })
            }
          />
          {/* Session 88: diversa da quella del negozio = personalizzata, e il
              cambio per tutti non la tocca più. */}
          <span className="block text-[10px] text-slate-500 mt-1">
            {product.credit_locked ? (
              <>
                Personalizzata per questo prodotto.{" "}
                <button
                  type="button"
                  onClick={() => usaQuellaDelNegozio.mutate()}
                  className="font-semibold text-orange-400 hover:text-orange-300 cursor-pointer"
                >
                  {negozio?.credit_mode === "MARGIN"
                    ? "Torna al calcolo dal guadagno"
                    : `Usa quella del negozio${negozio ? ` (${negozio.credit_percentage}%)` : ""}`}
                </button>
              </>
            ) : negozio?.credit_mode === "MARGIN" ? (
              `Calcolata dal guadagno (il ${negozio.credit_margin_share}% del margine): cambiala qui per personalizzarla.`
            ) : (
              `Quella del negozio${negozio ? ` (${negozio.credit_percentage}%)` : ""}: cambiala qui per personalizzarla.`
            )}
          </span>
        </div>
        <div>
          <span className={label}>Ricarico di questo prodotto (%)</span>
          <input
            className={input}
            inputMode="numeric"
            placeholder="quello del negozio"
            value={bozza.markup_percentage === null ? "" : String(bozza.markup_percentage)}
            onChange={(e) =>
              setBozza({ ...bozza, markup_percentage: e.target.value.trim() === "" ? null : Number(e.target.value) || 0 })
            }
          />
          <span className="block text-[10px] text-slate-500 mt-1">Vuoto = quello del negozio.</span>
        </div>
        {product.source_url && (
          <div className="flex items-end">
            <a href={product.source_url} target="_blank" rel="noopener noreferrer" className="text-[11px] font-semibold text-orange-400 hover:text-orange-300">
              Vedi su Symphonya →
            </a>
          </div>
        )}
      </div>
      <div>
        <span className={label}>Immagine principale</span>
        <ImmagineProdotto value={bozza.image_url ?? ""} onChange={(url) => setBozza({ ...bozza, image_url: url || null })} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => salva.mutate()}
          disabled={salva.isPending || !bozza.name.trim()}
          className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
        >
          {salva.isPending ? "Salvo…" : "Salva modifiche"}
        </button>
        <button onClick={onClose} className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-white/5 light:hover:bg-slate-900/5 cursor-pointer">
          Annulla
        </button>
      </div>

      <div className="space-y-2 pt-4 border-t border-white/10 light:border-slate-200">
        <p className={label}>
          Prezzi e scorte · {product.variants.length} {product.variants.length === 1 ? "variante" : "varianti"} · si
          salvano uscendo dal campo
        </p>
        {product.variants.length > 1 && (
          <div className="flex flex-wrap items-center gap-2 p-3 rounded-xl bg-white/5 light:bg-slate-900/5">
            <span className="text-[11px] text-slate-400 light:text-slate-600">Stesso prezzo per tutte le varianti:</span>
            <input
              className={`${input} max-w-[8rem]`}
              inputMode="decimal"
              placeholder="Prezzo €"
              value={prezzoTutte}
              onChange={(e) => setPrezzoTutte(e.target.value)}
            />
            <button
              onClick={() => applicaATutte.mutate(centsFrom(prezzoTutte))}
              disabled={!prezzoValido || applicaATutte.isPending}
              className="px-3 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-[11px] font-semibold text-white cursor-pointer disabled:opacity-40"
            >
              {applicaATutte.isPending ? "Applico…" : `Applica a ${product.variants.length}`}
            </button>
          </div>
        )}
        {product.variants.length > 8 && (
          <input
            className={input}
            placeholder="Cerca un prodotto (nome, EAN)…"
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
                  <p className="text-xs text-slate-300 light:text-slate-700 truncate">
                    {v.label}
                    {!v.available_in_store && <span className="text-rose-400"> · non più disponibile su Symphonya</span>}
                    {v.below_cost && <span className="text-rose-400"> · in perdita: non in vendita</span>}
                  </p>
                  <p className="text-[10px] text-slate-500 truncate">
                    {v.sku}
                    {v.cost_cents ? ` · a noi ${euro(v.cost_cents)}` : ""}
                    {v.cost_cents ? ` · al pubblico ${euro(prezzoFinale(v.price_cents, negozio, negozioIva))} IVA incl.` : ""}
                    {v.cost_cents
                      ? (() => {
                          const lordo = prezzoFinale(v.price_cents, negozio, negozioIva);
                          const netto = Math.floor((lordo * 100 * 2 + (100 + negozioIva)) / ((100 + negozioIva) * 2));
                          return ` · guadagno ${euro(netto - v.cost_cents)}`;
                        })()
                      : ""}
                    {v.suggested_price_cents && v.suggested_price_cents !== v.price_cents
                      ? ` · suggerito ${euro(v.suggested_price_cents)}`
                      : ""}
                    {v.price_locked && (
                      <>
                        {" · prezzo scritto a mano "}
                        <button
                          type="button"
                          onClick={() => sbloccaPrezzo.mutate(v.id)}
                          className="font-semibold text-orange-400 hover:text-orange-300 cursor-pointer"
                        >
                          torna al ricarico
                        </button>
                      </>
                    )}
                  </p>
                </div>
              </div>
              <input
                className={input}
                inputMode="decimal"
                aria-label={`Prezzo ${v.label}`}
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
                placeholder="Scorta"
                aria-label={`Scorta ${v.label}`}
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
          {varianti.length === 0 && <p className="text-xs text-slate-500">Nessuna variante corrisponde.</p>}
        </div>
      </div>
      <Esito message={message} />
    </Finestra>
  );
}


// --- Ordini ----------------------------------------------------------------

/** Session 88: gli ordini del negozio con tutto quello che serve per evaderli
 *  -- cosa ha comprato il cliente (variante compresa), se ha pagato, dove
 *  spedire, le sue note -- e le azioni nell'ordine in cui servono: conferma
 *  del bonifico, l'inserimento a mano su symphonya.com (SKU ed EAN sono qui), spedito con il tracking (il cliente riceve
 *  l'email), consegnato. Prima questo riquadro mostrava solo nome e totale, e
 *  l'indirizzo non si vedeva da nessuna parte. */
type FiltroOrdini = "DA_SPEDIRE" | "DA_PAGARE" | "SPEDITI" | "ANNULLATI" | "TUTTI";

function faseOrdine(o: SymphonyaMarketOrderRead): FiltroOrdini {
  if (o.status === "CANCELLED") return "ANNULLATI";
  if (o.status === "AWAITING_PAYMENT") return "DA_PAGARE";
  return o.shipped_at || o.delivered_at ? "SPEDITI" : "DA_SPEDIRE";
}

function Ordini() {
  const { data: orders } = useQuery({
    queryKey: ["admin", "symphonya-market", "orders"],
    queryFn: () => get<SymphonyaMarketOrderRead[]>("/symphonya-market/orders"),
  });
  const [filtro, setFiltro] = useState<FiltroOrdini>("DA_SPEDIRE");
  const tutti = orders ?? [];
  const conteggio = (f: FiltroOrdini) => (f === "TUTTI" ? tutti.length : tutti.filter((o) => faseOrdine(o) === f).length);
  const visibili = filtro === "TUTTI" ? tutti : tutti.filter((o) => faseOrdine(o) === filtro);

  return (
    <Card title="Ordini" subtitle="Un ordine pagato si inserisce a mano su symphonya.com con SKU ed EAN mostrati qui, poi si segna spedito con il tracking: il cliente riceve un'email a ogni passaggio.">
      <div className="flex flex-wrap gap-1.5">
        {(
          [
            ["DA_SPEDIRE", "Da spedire"],
            ["DA_PAGARE", "In attesa di pagamento"],
            ["SPEDITI", "Spediti"],
            ["ANNULLATI", "Annullati"],
            ["TUTTI", "Tutti"],
          ] as const
        ).map(([key, testo]) => (
          <button
            key={key}
            onClick={() => setFiltro(key)}
            className={`px-2.5 py-1.5 rounded-lg text-[11px] font-semibold border cursor-pointer ${
              filtro === key
                ? "border-orange-500/50 bg-orange-500/15 text-orange-300 light:text-orange-700"
                : "border-white/10 light:border-slate-300 text-slate-400 light:text-slate-600 hover:bg-white/5 light:hover:bg-slate-900/5"
            }`}
          >
            {testo} ({conteggio(key)})
          </button>
        ))}
      </div>
      {visibili.length === 0 ? (
        <p className="text-xs text-slate-500">Nessun ordine in questo stato.</p>
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

function OrdineCard({ order: o }: { order: SymphonyaMarketOrderRead }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [spedizione, setSpedizione] = useState<{ tracking_company: string; tracking_number: string; tracking_url: string } | null>(null);
  const [annulla, setAnnulla] = useState<string | null>(null);
  const invalida = () => queryClient.invalidateQueries({ queryKey: ["admin", "symphonya-market", "orders"] });
  const azione = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown; ok: string }) =>
      send<SymphonyaMarketOrderRead>(`/symphonya-market/orders/${o.id}/${path}`, "POST", body ?? {}),
    onSuccess: (_r, vars) => {
      setMessage({ ok: true, text: vars.ok });
      setSpedizione(null);
      setAnnulla(null);
      invalida();
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  const fase = faseOrdine(o);
  const extra = o as SymphonyaMarketOrderRead & { tracking_company?: string | null };

  return (
    <div className="rounded-xl border border-white/10 light:border-slate-200 p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-bold text-white light:text-slate-900">
            #{o.order_code} · {o.customer_display_name}
          </p>
          <p className="text-[11px] text-slate-500">
            {new Date(o.created_at).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
            {" · "}totale {euro(o.amount_cents)}
            {o.credit_applied_cents > 0 && ` (di cui ${euro(o.credit_applied_cents)} in JavCash)`}
            {" · "}
            {o.payment_method === "CARD" ? "carta" : "bonifico"}
          </p>
        </div>
        <span
          className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
            fase === "DA_SPEDIRE"
              ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
              : fase === "SPEDITI"
                ? "bg-sky-500/10 text-sky-400 border-sky-500/20"
                : fase === "DA_PAGARE"
                  ? "bg-white/5 text-slate-400 border-white/10"
                  : "bg-rose-500/10 text-rose-400 border-rose-500/20"
          }`}
        >
          {fase === "DA_SPEDIRE"
            ? "Pagato · da spedire"
            : fase === "SPEDITI"
              ? o.delivered_at ? "Consegnato" : "Spedito"
              : fase === "DA_PAGARE"
                ? "In attesa di pagamento"
                : "Annullato"}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-lg bg-white/5 light:bg-slate-900/5 p-3 space-y-1">
          <p className={label}>Cosa ha comprato</p>
          {(o.items ?? []).map((i) => (
            <div key={i.id} className="text-xs text-slate-300 light:text-slate-700">
              <span className="font-semibold">{i.quantity} ×</span> {i.product_name}
              {i.variant_label && i.variant_label !== "Unica" ? ` — ${i.variant_label}` : ""}
              <span className="text-slate-500"> · {euro(i.line_total_cents)}</span>
              <span className="block text-[11px] text-slate-500">
                SKU <span className="font-mono select-all">{i.supplier_sku ?? "—"}</span>
                {i.barcode && (
                  <>
                    {" "}· EAN <span className="font-mono select-all">{i.barcode}</span>
                  </>
                )}
                {i.supplier_url && (
                  <>
                    {" "}·{" "}
                    <a href={i.supplier_url} target="_blank" rel="noopener noreferrer" className="text-orange-400 hover:text-orange-300">
                      apri su Symphonya →
                    </a>
                  </>
                )}
              </span>
            </div>
          ))}
          <p className="text-[11px] text-slate-500 pt-1">
            Merce {euro(o.items_cents)} · spedizione {euro(o.shipping_cents)}
            {(o.vat_amount_cents ?? 0) > 0 && ` · IVA ${euro(o.vat_amount_cents ?? 0)}`}
          </p>
        </div>
        <div className="rounded-lg bg-white/5 light:bg-slate-900/5 p-3 space-y-1">
          <p className={label}>Dove spedire</p>
          <p className="text-xs text-slate-200 light:text-slate-800 select-all leading-relaxed">
            {o.recipient_name}
            <br />
            {o.address_line1}
            {o.address_line2 ? `, ${o.address_line2}` : ""}
            <br />
            {o.postal_code} {o.city} ({o.province})
          </p>
          {o.recipient_phone && <p className="text-[11px] text-slate-400">Tel. {o.recipient_phone}</p>}
          {o.note && <p className="text-[11px] text-amber-300 light:text-amber-700">Nota del cliente: {o.note}</p>}
          {(o.tracking_number || extra.tracking_company) && (
            <p className="text-[11px] text-sky-400">
              {extra.tracking_company ? `${extra.tracking_company} · ` : ""}
              {o.tracking_url ? (
                <a href={o.tracking_url} target="_blank" rel="noopener noreferrer" className="underline">
                  {o.tracking_number ?? "tracking"}
                </a>
              ) : (
                o.tracking_number
              )}
            </p>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {o.status === "AWAITING_PAYMENT" && o.payment_method === "BANK_TRANSFER" && (
          <button
            onClick={() => azione.mutate({ path: "confirm-payment", ok: "Bonifico confermato: ordine pagato." })}
            disabled={azione.isPending}
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 cursor-pointer disabled:opacity-40"
          >
            Conferma bonifico ricevuto
          </button>
        )}
        {o.status === "AWAITING_PAYMENT" && o.payment_method === "CARD" && (
          <span className="text-[11px] text-slate-500">In attesa della conferma di Stripe.</span>
        )}
        {fase === "DA_SPEDIRE" && (
          <button
            onClick={() => setSpedizione(spedizione ? null : { tracking_company: "", tracking_number: "", tracking_url: "" })}
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-orange-600 hover:bg-orange-500 text-white cursor-pointer"
          >
            Segna come spedito
          </button>
        )}
        {o.shipped_at && !o.delivered_at && o.status === "PAID" && (
          <button
            onClick={() => azione.mutate({ path: "delivered", ok: "Segnato come consegnato: il cliente ha ricevuto l'email." })}
            disabled={azione.isPending}
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold border border-sky-500/30 text-sky-400 hover:bg-sky-500/10 cursor-pointer disabled:opacity-40"
          >
            Segna come consegnato
          </button>
        )}
        {o.status === "AWAITING_PAYMENT" && (
          <button
            onClick={() => setAnnulla(annulla === null ? "" : null)}
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold border border-rose-500/30 text-rose-400 hover:bg-rose-500/10 cursor-pointer"
          >
            Annulla ordine
          </button>
        )}
      </div>

      {spedizione && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 items-end">
          <div>
            <span className={label}>Corriere</span>
            <input className={input} placeholder="es. BRT" value={spedizione.tracking_company}
              onChange={(e) => setSpedizione({ ...spedizione, tracking_company: e.target.value })} />
          </div>
          <div>
            <span className={label}>Numero di tracking</span>
            <input className={input} value={spedizione.tracking_number}
              onChange={(e) => setSpedizione({ ...spedizione, tracking_number: e.target.value })} />
          </div>
          <div>
            <span className={label}>Link di tracciamento</span>
            <input className={input} placeholder="https://…" value={spedizione.tracking_url}
              onChange={(e) => setSpedizione({ ...spedizione, tracking_url: e.target.value })} />
          </div>
          <button
            onClick={() => azione.mutate({ path: "ship", body: spedizione, ok: "Segnato come spedito: il cliente ha ricevuto l'email con il tracking." })}
            disabled={azione.isPending}
            className="px-3 py-2 rounded-lg text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white cursor-pointer disabled:opacity-40"
          >
            {azione.isPending ? "Salvo…" : "Conferma spedizione"}
          </button>
        </div>
      )}
      {annulla !== null && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[200px]">
            <span className={label}>Motivo dell&apos;annullamento</span>
            <input className={input} value={annulla} onChange={(e) => setAnnulla(e.target.value)} autoFocus />
          </div>
          <button
            onClick={() => azione.mutate({ path: "cancel", body: { reason: annulla }, ok: "Ordine annullato: i JavCash usati tornano al cliente." })}
            disabled={azione.isPending || !annulla.trim()}
            className="px-3 py-2 rounded-lg text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white cursor-pointer disabled:opacity-40"
          >
            Conferma annullamento
          </button>
        </div>
      )}
      <Esito message={message} />
    </div>
  );
}

export function AdminSymphonyaMarketPanel() {
  return (
    <div className="space-y-6">
      <Impostazioni />
      <FeedSymphonya />
      <AccendiInBlocco />
      <Catalogo />
      <Ordini />
      <Produttori />
    </div>
  );
}
