"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { ProductThumbnail } from "@/components/product-thumbnail";
import type {
  KappaMarketAdminProductRead,
  KappaMarketOrderRead,
  KappaMarketProducerRead,
  KappaMarketSettingsRead,
} from "@/lib/types";

/** Marketplace 5 «Market Kappa» (Session 87): il pannello con cui
 *  l'amministratore costruisce il negozio di Kappa e Robe di Kappa. È il
 *  clone di admin-jav-market-panel.tsx, con tabelle e rotte sue.
 *
 *  Tre cose, nell'ordine in cui servono: le impostazioni (acceso, spese di
 *  spedizione), i **marchi** (nel database sono le «aziende produttrici»
 *  del clone) e i prodotti. I marchi vengono prima dei prodotti di
 *  proposito -- un prodotto li sceglie da un elenco, e chi compila la
 *  scheda una volta non la riscrive per ogni articolo.
 *
 *  Qui non c'è nessun fornitore da collegare: niente OAuth, niente sync,
 *  niente ricarico su un costo. Il prezzo lo scrive chi carica il prodotto
 *  ed è già quello di vendita. */

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

// --- Impostazioni ----------------------------------------------------------

function Impostazioni() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["admin", "kappa-market", "settings"],
    queryFn: () => get<KappaMarketSettingsRead>("/kappa-market/settings"),
  });
  const [form, setForm] = useState<KappaMarketSettingsRead | null>(null);
  const corrente = form ?? data ?? null;
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const salva = useMutation({
    mutationFn: (payload: Partial<KappaMarketSettingsRead>) =>
      send<KappaMarketSettingsRead>("/kappa-market/settings", "PATCH", payload),
    onSuccess: (row) => {
      setForm(row);
      setMessage({ ok: true, text: "Impostazioni salvate." });
      queryClient.invalidateQueries({ queryKey: ["admin", "kappa-market"] });
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
              setForm({ ...corrente, shipping_mode: e.target.value as KappaMarketSettingsRead["shipping_mode"] })
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
          <span className={label}>Invio ai marchi</span>
          <select
            className={input}
            value={corrente.auto_forward ? "auto" : "manuale"}
            onChange={(e) => setForm({ ...corrente, auto_forward: e.target.value === "auto" })}
          >
            <option value="manuale">a mano, con il pulsante</option>
            <option value="auto">automatico al pagamento</option>
          </select>
          <span className="block text-[10px] text-slate-500 mt-1">
            {corrente.auto_forward
              ? "Appena il cliente paga, l'ordine parte da solo verso i marchi."
              : "L'ordine pagato aspetta che tu prema «Invia ai marchi»: una verifica umana prima di mandare una email a un'azienda vera."}
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
          onClick={() => salva.mutate(corrente)}
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
    queryKey: ["admin", "kappa-market", "producers"],
    queryFn: () => get<KappaMarketProducerRead[]>("/kappa-market/producers"),
  });
  const [form, setForm] = useState({ ...PRODUTTORE_VUOTO });
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const crea = useMutation({
    mutationFn: () =>
      send<KappaMarketProducerRead>("/kappa-market/producers", "POST", {
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
      queryClient.invalidateQueries({ queryKey: ["admin", "kappa-market", "producers"] });
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
              ? "Nessun marchio ancora (es. Kappa, Robe di Kappa). Servono per dire al cliente di che marca è il capo, e per mandare l'ordine a chi lo evade."
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
 *  POST /kappa-market/images) oppure si incolla un URL come prima. In tutti e
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
      const res = await fetch("/api/proxy/kappa-market/images", { method: "POST", body });
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
 *  in fondo alla lista: con centinaia di prodotti (Market Kappa ne ha 249)
 *  bisognava scorrere tutto per arrivarci. */
type Editor = { mode: "create" } | { mode: "edit"; id: string };

function Catalogo() {
  const queryClient = useQueryClient();
  const { data: products } = useQuery({
    queryKey: ["admin", "kappa-market", "products"],
    queryFn: () => get<KappaMarketAdminProductRead[]>("/kappa-market/products"),
  });
  const { data: producers } = useQuery({
    queryKey: ["admin", "kappa-market", "producers"],
    queryFn: () => get<KappaMarketProducerRead[]>("/kappa-market/producers"),
  });
  const [editor, setEditor] = useState<Editor | null>(null);
  const [cerca, setCerca] = useState("");
  const [stato, setStato] = useState<"TUTTI" | "ACTIVE" | "INACTIVE">("TUTTI");
  const [produttore, setProduttore] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const spegni = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "ACTIVE" | "INACTIVE" }) =>
      send<KappaMarketAdminProductRead>(`/kappa-market/products/${id}`, "PATCH", { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "kappa-market", "products"] }),
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  const tutti = products ?? [];
  const testo = cerca.trim().toLowerCase();
  // Si cerca anche nella descrizione e negli sku: nel Market Kappa il codice
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
            {visibili.map((p) => (
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
                      {p.variants.length} {p.variants.length === 1 ? "variante" : "varianti"} ·{" "}
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
  producers: KappaMarketProducerRead[];
  onClose: () => void;
  onCreated: (p: KappaMarketAdminProductRead) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ ...PRODOTTO_VUOTO });
  const [variants, setVariants] = useState<VarianteForm[]>([{ label: "Unica", price: "", inventory: "" }]);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const crea = useMutation({
    mutationFn: () =>
      send<KappaMarketAdminProductRead>("/kappa-market/products", "POST", {
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
      queryClient.invalidateQueries({ queryKey: ["admin", "kappa-market", "products"] });
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
              placeholder="Etichetta (es. Taglia M · Nero)"
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
  product: KappaMarketAdminProductRead;
  producers: KappaMarketProducerRead[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const invalida = () => queryClient.invalidateQueries({ queryKey: ["admin", "kappa-market", "products"] });
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
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [filtroVarianti, setFiltroVarianti] = useState("");
  const [prezzoTutte, setPrezzoTutte] = useState("");

  const salva = useMutation({
    mutationFn: () =>
      send<KappaMarketAdminProductRead>(`/kappa-market/products/${product.id}`, "PATCH", {
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
      send(`/kappa-market/variants/${id}`, "PATCH", { price_cents, inventory }),
    onSuccess: invalida,
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  // Un prezzo per tutte le varianti: nel Market Kappa un capo ha decine di
  // taglie e colori allo stesso prezzo, e scriverlo cento volte non è un
  // lavoro. A gruppi di dieci per non sommergere il server.
  const applicaATutte = useMutation({
    mutationFn: async (price_cents: number) => {
      const daFare = product.variants;
      for (let i = 0; i < daFare.length; i += 10) {
        await Promise.all(
          daFare.slice(i, i + 10).map((v) =>
            send(`/kappa-market/variants/${v.id}`, "PATCH", { price_cents, inventory: v.inventory })
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
  const cambiaStato = useMutation({
    mutationFn: () =>
      send<KappaMarketAdminProductRead>(`/kappa-market/products/${product.id}`, "PATCH", {
        status: product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE",
      }),
    onSuccess: invalida,
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });

  // Session 89: elimina davvero un prodotto mai ordinato. Il catalogo Kappa
  // non ha un import automatico, quindi non torna; uno già ordinato il
  // server lo rifiuta (va spento).
  const [confermaElimina, setConfermaElimina] = useState(false);
  const elimina = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/proxy/kappa-market/products/${product.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
    },
    onSuccess: () => {
      invalida();
      onClose();
    },
    onError: (err: unknown) => {
      setConfermaElimina(false);
      setMessage({ ok: false, text: (err as Error).message });
    },
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
        {!confermaElimina ? (
          <button
            onClick={() => setConfermaElimina(true)}
            className="ml-auto px-2.5 py-1 rounded-lg text-[11px] font-semibold border border-rose-500/30 text-rose-400 hover:bg-rose-500/10 cursor-pointer"
          >
            Elimina prodotto
          </button>
        ) : (
          <span className="ml-auto flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-rose-400">
              Eliminare «{product.name}» con le sue {product.variants.length} varianti? Non si può annullare.
            </span>
            <button
              onClick={() => elimina.mutate()}
              disabled={elimina.isPending}
              className="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-rose-600 hover:bg-rose-500 text-white cursor-pointer disabled:opacity-40"
            >
              {elimina.isPending ? "..." : "Sì, elimina"}
            </button>
            <button
              onClick={() => setConfermaElimina(false)}
              className="px-2.5 py-1 rounded-lg text-[11px] font-semibold border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 cursor-pointer"
            >
              No
            </button>
          </span>
        )}
      </div>

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
          <span className={label}>JavCash max (%)</span>
          <input
            className={input}
            inputMode="numeric"
            value={String(bozza.credit_discount_percentage)}
            onChange={(e) => setBozza({ ...bozza, credit_discount_percentage: Number(e.target.value) || 0 })}
          />
        </div>
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
            placeholder="Cerca una variante (taglia, colore, EAN)…"
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
                  <p className="text-xs text-slate-300 light:text-slate-700 truncate">{v.label}</p>
                  {v.sku && <p className="text-[10px] text-slate-500 truncate">{v.sku}</p>}
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
 *  del bonifico, l'invio per email a chi evade l'ordine, spedito con il tracking (il cliente riceve
 *  l'email), consegnato. Prima questo riquadro mostrava solo nome e totale, e
 *  l'indirizzo non si vedeva da nessuna parte. */
type FiltroOrdini = "DA_SPEDIRE" | "DA_PAGARE" | "SPEDITI" | "ANNULLATI" | "TUTTI";

function faseOrdine(o: KappaMarketOrderRead): FiltroOrdini {
  if (o.status === "CANCELLED") return "ANNULLATI";
  if (o.status === "AWAITING_PAYMENT") return "DA_PAGARE";
  return o.shipped_at || o.delivered_at ? "SPEDITI" : "DA_SPEDIRE";
}

function Ordini() {
  const { data: orders } = useQuery({
    queryKey: ["admin", "kappa-market", "orders"],
    queryFn: () => get<KappaMarketOrderRead[]>("/kappa-market/orders"),
  });
  const [filtro, setFiltro] = useState<FiltroOrdini>("DA_SPEDIRE");
  const tutti = orders ?? [];
  const conteggio = (f: FiltroOrdini) => (f === "TUTTI" ? tutti.length : tutti.filter((o) => faseOrdine(o) === f).length);
  const visibili = filtro === "TUTTI" ? tutti : tutti.filter((o) => faseOrdine(o) === filtro);

  return (
    <Card title="Ordini" subtitle="Un ordine pagato si manda per email a chi lo evade e si segna spedito con il tracking: il cliente riceve un'email a ogni passaggio.">
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

function OrdineCard({ order: o }: { order: KappaMarketOrderRead }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [spedizione, setSpedizione] = useState<{ tracking_company: string; tracking_number: string; tracking_url: string } | null>(null);
  const [annulla, setAnnulla] = useState<string | null>(null);
  const invalida = () => queryClient.invalidateQueries({ queryKey: ["admin", "kappa-market", "orders"] });
  const azione = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown; ok: string }) =>
      send<KappaMarketOrderRead>(`/kappa-market/orders/${o.id}/${path}`, "POST", body ?? {}),
    onSuccess: (_r, vars) => {
      setMessage({ ok: true, text: vars.ok });
      setSpedizione(null);
      setAnnulla(null);
      invalida();
    },
    onError: (err: unknown) => setMessage({ ok: false, text: (err as Error).message }),
  });
  const fase = faseOrdine(o);
  const extra = o as KappaMarketOrderRead & { tracking_company?: string | null };

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
              {(i as { producer_name?: string | null }).producer_name && (
                <span className="text-slate-500"> · {(i as { producer_name?: string | null }).producer_name}</span>
              )}
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
      {o.status === "PAID" && (o.forwarded_at || o.forward_error) && (
        <p className={`text-[11px] ${o.forward_error ? "text-amber-400" : "text-slate-400"}`}>
          {o.forwarded_at && `Inviato ai marchi il ${new Date(o.forwarded_at).toLocaleString("it-IT")}. `}
          {o.forward_error && `Da sistemare: ${o.forward_error}`}
        </p>
      )}
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
        {o.status === "PAID" && !o.shipped_at && (
          <button
            onClick={() => azione.mutate({ path: "forward", ok: "Ordine inviato per email ai marchi." })}
            disabled={azione.isPending}
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold border border-white/10 light:border-slate-300 text-slate-200 light:text-slate-700 hover:bg-white/5 cursor-pointer disabled:opacity-40"
          >
            {o.forwarded_at ? "Reinvia ai marchi" : "Invia ai marchi per email"}
          </button>
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

export function AdminKappaMarketPanel() {
  return (
    <div className="space-y-6">
      <Impostazioni />
      <Produttori />
      <Catalogo />
      <Ordini />
    </div>
  );
}
