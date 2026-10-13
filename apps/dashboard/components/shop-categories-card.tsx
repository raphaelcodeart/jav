"use client";

import { useState } from "react";
import { FullScreenPanel } from "@/components/full-screen-panel";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { ShopCategoryRead, ShopKey } from "@/lib/types";

/** Categorie di uno shop (Session 73).
 *
 *  Ogni shop -- le tre sezioni del catalogo nostro e i tre Marketplace --
 *  ha le sue categorie, create qui dall'amministratore e usate dal cliente
 *  come filtro nello Shop. Una categoria appartiene a UNO shop: la stessa
 *  card, montata in ogni pannello, lavora sempre e solo sulle categorie
 *  dello shop selezionato, perché i cataloghi sono separati e mescolarli
 *  darebbe al cliente filtri che non filtrano niente.
 *
 *  La card è pensata per essere montata dove l'amministratore gestisce i
 *  prodotti di quello shop: vive accanto alla lista, non in una pagina a
 *  parte, così la categoria si crea nel momento in cui serve. */

async function fetchShopCategories(shop: ShopKey): Promise<ShopCategoryRead[]> {
  const res = await fetch(`/api/proxy/shop-categories?shop=${shop}`);
  if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile caricare le categorie."));
  return res.json();
}

/** Le categorie di uno shop, in ordine di posizione. Usata sia dal pannello
    admin sia dalle schede prodotto: una sola query condivisa per shop. */
export function useShopCategories(shop: ShopKey, enabled = true) {
  return useQuery({
    queryKey: ["shop-categories", shop],
    queryFn: () => fetchShopCategories(shop),
    enabled,
    staleTime: 60_000,
  });
}

/** Sostituisce in blocco le categorie di un prodotto dentro il suo shop.
    Chiamata dai form prodotto solo quando l'amministratore ha davvero
    toccato le spunte: un salvataggio che non riguarda le categorie non
    deve dipendere da questo endpoint. */
export async function saveProductCategories(
  shop: ShopKey,
  productId: string,
  categoryIds: string[]
): Promise<void> {
  const res = await fetch("/api/proxy/shop-categories/assignments", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ shop, product_id: productId, category_ids: categoryIds }),
  });
  if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile salvare le categorie del prodotto."));
}

/** Due liste di id sono la stessa scelta? L'ordine non conta: il server
    sostituisce l'insieme, non una sequenza. */
export function sameCategorySelection(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const left = [...a].sort();
  const right = [...b].sort();
  return left.every((id, i) => id === right[i]);
}

const cardClass = "glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70";
const inputClass = "w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500";
const ghostClass =
  "px-3 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-xs font-semibold text-slate-300 light:text-slate-600 transition cursor-pointer disabled:opacity-50";

export interface ShopCategoriesCardProps {
  /** Gli shop gestiti da questa card. Con più di uno compare un selettore
      interno: il catalogo nostro ha tre sezioni ma una sola pagina admin. */
  shops: { key: ShopKey; label: string }[];
}

/** Il bottone "Gestisci Categorie" (Session 74): sta in testa a ogni pagina
    shop, visibile da qualunque scheda, e apre la stessa gestione della card.
    Nasce da una richiesta esplicita dell'utente, che nella pagina Shop
    AliExpress non trovava dove intervenire sulle categorie: una card
    richiudibile in mezzo ai prodotti non si vede abbastanza. */
export function ManageCategoriesButton({ shops }: ShopCategoriesCardProps) {
  const [open, setOpen] = useState(false);
  const [selectedShop, setSelectedShop] = useState<ShopKey | null>(null);
  const shop: ShopKey = shops.some((s) => s.key === selectedShop)
    ? (selectedShop as ShopKey)
    : shops[0]?.key ?? "internal";
  const { data: categories, error } = useShopCategories(shop, open);
  const current = shops.find((s) => s.key === shop);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-white text-xs font-bold shadow-lg shadow-orange-500/20 transition-all duration-200 cursor-pointer active:scale-[0.98]"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h10" />
        </svg>
        Gestisci Categorie
      </button>
      {open && (
        <FullScreenPanel
          title="Categorie dello shop"
          subtitle={`Con queste il cliente filtra i prodotti${current ? ` di ${current.label}` : ""}. Eliminare una categoria non elimina i prodotti.`}
          onClose={() => setOpen(false)}
        >
          <div className="space-y-4">
            {shops.length > 1 && (
              <div className="flex flex-wrap gap-2">
                {shops.map((s) => (
                  <button
                    key={s.key}
                    type="button"
                    onClick={() => setSelectedShop(s.key)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                      shop === s.key
                        ? "bg-orange-600 border-orange-600 text-white"
                        : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            )}
            {error && <p className="text-xs text-rose-400">{(error as Error).message}</p>}
            <CategoryList key={shop} shop={shop} categories={categories} />
            <BulkAssign key={`bulk-${shop}`} shop={shop} categories={categories} />
          </div>
        </FullScreenPanel>
      )}
    </>
  );
}

export function ShopCategoriesCard({ shops }: ShopCategoriesCardProps) {
  const [open, setOpen] = useState(false);
  const [selectedShop, setSelectedShop] = useState<ShopKey | null>(null);
  // Derivato, mai sincronizzato: se le etichette cambiano (le sezioni dello
  // Shop sono rinominabili) lo shop scelto resta valido finché esiste.
  const shop: ShopKey = shops.some((s) => s.key === selectedShop)
    ? (selectedShop as ShopKey)
    : shops[0]?.key ?? "internal";

  const { data: categories, error } = useShopCategories(shop, open);

  return (
    <div className={cardClass}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex flex-wrap items-center justify-between gap-2 px-5 py-4 text-left cursor-pointer"
      >
        <span>
          <span className="block text-sm font-bold text-white light:text-slate-900">Categorie dello shop</span>
          <span className="block text-xs text-slate-400 light:text-slate-500 mt-0.5">
            Le categorie con cui il cliente filtra i prodotti di questo shop, sotto il pulsante dello shop.
          </span>
        </span>
        <span className="text-xs font-semibold text-orange-400">{open ? "Chiudi" : "Gestisci"}</span>
      </button>

      {open && (
        <div className="px-5 pb-5 pt-4 border-t border-white/5 light:border-slate-200 space-y-4">
          {shops.length > 1 && (
            <div className="flex flex-wrap gap-2">
              {shops.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => setSelectedShop(s.key)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                    shop === s.key
                      ? "bg-orange-600 border-orange-600 text-white"
                      : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          )}

          {error && <p className="text-xs text-rose-400">{(error as Error).message}</p>}

          {/* key: cambiando shop le bozze di modifica non hanno più senso. */}
          <CategoryList key={shop} shop={shop} categories={categories} />

          <BulkAssign key={`bulk-${shop}`} shop={shop} categories={categories} />
        </div>
      )}
    </div>
  );
}

function CategoryList({ shop, categories }: { shop: ShopKey; categories: ShopCategoryRead[] | undefined }) {
  const queryClient = useQueryClient();
  // Le modifiche in corso, per id: il valore mostrato è la bozza se c'è,
  // altrimenti quello del server. Niente useEffect di sincronizzazione.
  const [drafts, setDrafts] = useState<Record<string, { name?: string; position?: string }>>({});
  const [newName, setNewName] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<ShopCategoryRead | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["shop-categories", shop] });
  }

  async function patch(category: ShopCategoryRead, body: Record<string, unknown>) {
    setBusyId(category.id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/shop-categories/${category.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile salvare la categoria."));
      setDrafts((d) => {
        const next = { ...d };
        delete next[category.id];
        return next;
      });
      await refresh();
    } catch (err: any) {
      setActionError(err.message || "Impossibile salvare la categoria.");
    } finally {
      setBusyId(null);
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setActionError(null);
    try {
      const res = await fetch("/api/proxy/shop-categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // In fondo alla barra: una categoria nuova non deve scavalcare
        // quelle che il cliente è già abituato a vedere per prime.
        body: JSON.stringify({
          shop,
          name: newName.trim(),
          position: categories?.length ? Math.max(...categories.map((c) => c.position)) + 1 : 0,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile creare la categoria."));
      setNewName("");
      await refresh();
    } catch (err: any) {
      setActionError(err.message || "Impossibile creare la categoria.");
    } finally {
      setCreating(false);
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/proxy/shop-categories/${deleting.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile eliminare la categoria."));
      setDeleting(null);
      await refresh();
    } catch (err: any) {
      setDeleteError(err.message || "Impossibile eliminare la categoria.");
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {actionError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{actionError}</div>
      )}

      {categories === undefined ? (
        <p className="text-xs text-slate-500 py-2">Caricamento categorie...</p>
      ) : categories.length === 0 ? (
        <p className="text-xs text-slate-500 py-2">
          Nessuna categoria per questo shop. Aggiungine una qui sotto: finché non ce n&apos;è nessuna, il cliente vede
          tutti i prodotti senza filtri.
        </p>
      ) : (
        <div className="rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
          {categories.map((c) => {
            const draft = drafts[c.id] ?? {};
            const name = draft.name ?? c.name;
            const position = draft.position ?? String(c.position);
            const changed = name.trim() !== c.name || position.trim() !== String(c.position);
            return (
              <div key={c.id} className="flex flex-wrap items-center gap-2 px-3 py-2.5">
                <input
                  className="w-16 rounded-md glass-input px-2 py-1.5 text-xs text-center"
                  inputMode="numeric"
                  title="Ordine di comparsa"
                  value={position}
                  onChange={(e) => setDrafts({ ...drafts, [c.id]: { ...draft, position: e.target.value } })}
                />
                <input
                  className="flex-1 min-w-[140px] rounded-md glass-input px-2 py-1.5 text-sm"
                  maxLength={120}
                  value={name}
                  onChange={(e) => setDrafts({ ...drafts, [c.id]: { ...draft, name: e.target.value } })}
                />
                <span className="text-[11px] text-slate-500 w-20 text-right shrink-0">
                  {c.product_count} {c.product_count === 1 ? "prodotto" : "prodotti"}
                </span>
                {changed && (
                  <button
                    type="button"
                    className="px-3 py-1.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                    disabled={busyId === c.id || !name.trim()}
                    onClick={() =>
                      patch(c, {
                        name: name.trim(),
                        position: Number.isFinite(parseInt(position, 10)) ? parseInt(position, 10) : c.position,
                      })
                    }
                  >
                    {busyId === c.id ? "..." : "Salva"}
                  </button>
                )}
                <button
                  type="button"
                  className={ghostClass}
                  disabled={busyId === c.id}
                  onClick={() => patch(c, { active: !c.active })}
                  title={c.active ? "Nascondila al cliente" : "Rendila visibile al cliente"}
                >
                  {c.active ? "Visibile" : "Nascosta"}
                </button>
                <button
                  type="button"
                  className="px-3 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-rose-600 hover:text-white border border-white/10 light:border-slate-300 text-xs font-semibold text-slate-300 light:text-slate-600 transition cursor-pointer"
                  onClick={() => { setDeleting(c); setDeleteError(null); }}
                >
                  Elimina
                </button>
              </div>
            );
          })}
        </div>
      )}

      <form onSubmit={create} className="flex flex-wrap items-end gap-2">
        <label className="flex-1 min-w-[180px]">
          <span className="block text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-1">
            Nuova categoria
          </span>
          <input
            className={inputClass}
            maxLength={120}
            value={newName}
            placeholder="Es. Casa, Elettronica, Regali"
            onChange={(e) => setNewName(e.target.value)}
          />
        </label>
        <button
          type="submit"
          disabled={creating || !newName.trim()}
          className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-bold text-white transition cursor-pointer disabled:opacity-50"
        >
          {creating ? "..." : "Aggiungi categoria"}
        </button>
      </form>

      <p className="text-[11px] text-slate-500">
        Il numero a sinistra è l&apos;ordine in cui le categorie compaiono al cliente. Una categoria nascosta sparisce
        dai filtri dello Shop ma resta qui, con i suoi prodotti: i prodotti tornano semplicemente visibili senza filtro.
      </p>

      {deleting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
            <h3 className="text-lg font-bold text-white light:text-slate-900 mb-2">Elimina categoria</h3>
            <p className="text-xs text-slate-400 light:text-slate-500 mb-4">
              Stai per eliminare la categoria{" "}
              <span className="font-semibold text-slate-300 light:text-slate-700">&quot;{deleting.name}&quot;</span>.{" "}
              <strong className="text-slate-200 light:text-slate-800">
                I {deleting.product_count} prodotti che contiene non vengono eliminati
              </strong>
              : restano in vendita e semplicemente non appartengono più a nessuna categoria, finché non li assegni a
              un&apos;altra. Se ti serve solo toglierla dai filtri del cliente, usa &ldquo;Visibile / Nascosta&rdquo;.
            </p>
            {deleteError && <p className="text-xs text-rose-400 mb-3">{deleteError}</p>}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => { setDeleting(null); setDeleteError(null); }}
                className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer"
              >
                Annulla
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleteBusy}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
              >
                {deleteBusy ? "Eliminazione..." : "Elimina categoria"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Le spunte delle categorie dentro il form di un prodotto. Un prodotto può
    stare in più categorie o in nessuna, e vede solo quelle del suo shop. */
export function ProductCategoriesField({
  shop,
  value,
  onChange,
}: {
  shop: ShopKey;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const { data: categories, error } = useShopCategories(shop);

  function toggle(id: string) {
    onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
  }

  return (
    <div>
      <span className="block text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-1">
        Categorie nello Shop
      </span>
      {error ? (
        <p className="text-[11px] text-rose-400">{(error as Error).message}</p>
      ) : categories === undefined ? (
        <p className="text-[11px] text-slate-500">Caricamento categorie...</p>
      ) : categories.length === 0 ? (
        <p className="text-[11px] text-slate-500">
          Nessuna categoria per questo shop: creale nella card &ldquo;Categorie dello shop&rdquo;.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {categories.map((c) => {
            const checked = value.includes(c.id);
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => toggle(c.id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                  checked
                    ? "bg-orange-600 border-orange-600 text-white"
                    : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
                } ${c.active ? "" : "opacity-60"}`}
              >
                {checked ? "✓ " : ""}
                {c.name}
                {!c.active && " (nascosta)"}
              </button>
            );
          })}
        </div>
      )}
      <p className="text-[10px] text-slate-500 mt-1">
        Un prodotto può stare in più categorie o in nessuna. Le categorie non cambiano prezzo né disponibilità: servono
        solo al cliente per trovarlo.
      </p>
    </div>
  );
}


// --- Assegnazione in blocco -------------------------------------------------

/** Dove stanno i prodotti di ogni shop, per l'amministratore. Il vecchio
    plugin dei prodotti a mano vive dentro il Marketplace AliExpress, quindi
    le sue righe si assegnano alle stesse categorie. */
const PRODUCTS_ENDPOINT: Record<ShopKey, string[]> = {
  internal: ["/api/proxy/products"],
  partner: ["/api/proxy/products"],
  dropshipping: ["/api/proxy/products"],
  cj: ["/api/proxy/cj/products"],
  shopify: ["/api/proxy/shopify/products"],
  aliexpress: ["/api/proxy/aliexpress/products", "/api/proxy/imported-products/products"],
  jav_market: ["/api/proxy/jav-market/products"],
  kappa_market: ["/api/proxy/kappa-market/products"],
  vaitto_market: ["/api/proxy/vaitto-market/products"],
  symphonya_market: ["/api/proxy/symphonya-market/products"],
  soleil_market: ["/api/proxy/soleil-market/products"],
};

type AssignableProduct = { id: string; name: string; category_ids?: string[]; category?: string };

async function fetchAssignableProducts(shop: ShopKey): Promise<AssignableProduct[]> {
  const lists = await Promise.all(
    PRODUCTS_ENDPOINT[shop].map(async (url) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile caricare i prodotti."));
      return (await res.json()) as AssignableProduct[];
    })
  );
  const all = lists.flat();
  // Il catalogo nostro è una lista sola per tutte e tre le sezioni: qui
  // interessa solo quella dello shop scelto (Product.category).
  if (shop === "internal" || shop === "partner" || shop === "dropshipping") {
    return all.filter((p) => (p.category ?? "").toLowerCase() === shop);
  }
  return all;
}

/** Mettere in categoria i prodotti già importati, senza riaprirli uno per
    uno: si sceglie la categoria, si spuntano i prodotti e si aggiungono (o
    si tolgono). Serve soprattutto dopo un'importazione in blocco, quando i
    prodotti sono decine e le categorie arrivano dopo. */
function BulkAssign({ shop, categories }: { shop: ShopKey; categories: ShopCategoryRead[] | undefined }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [categoryId, setCategoryId] = useState("");
  const [search, setSearch] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const { data: products, error } = useQuery({
    queryKey: ["shop-categories", "assignable", shop],
    queryFn: () => fetchAssignableProducts(shop),
    enabled: open,
  });

  const category = (categories ?? []).find((c) => c.id === categoryId) ?? null;
  const visible = (products ?? []).filter(
    (p) => !search.trim() || p.name.toLowerCase().includes(search.trim().toLowerCase())
  );

  function toggle(id: string) {
    const next = new Set(picked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setPicked(next);
  }

  /** `add` false = togli dalla categoria. Il server sostituisce l'insieme
      delle categorie di un prodotto, quindi unione/differenza si calcolano
      qui, partendo da quelle che il prodotto ha già. */
  async function apply(add: boolean) {
    if (!category || picked.size === 0) return;
    setBusy(true);
    setMessage(null);
    try {
      for (const product of (products ?? []).filter((p) => picked.has(p.id))) {
        const current = product.category_ids ?? [];
        const next = add
          ? Array.from(new Set([...current, category.id]))
          : current.filter((id) => id !== category.id);
        if (next.length === current.length && add) continue;
        await saveProductCategories(shop, product.id, next);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["shop-categories", shop] }),
        queryClient.invalidateQueries({ queryKey: ["shop-categories", "assignable", shop] }),
        queryClient.invalidateQueries({ queryKey: ["admin"] }),
      ]);
      setPicked(new Set());
      setMessage({
        ok: true,
        text: add
          ? `Aggiunti a “${category.name}”.`
          : `Tolti da “${category.name}”.`,
      });
    } catch (err: any) {
      setMessage({ ok: false, text: err.message || "Operazione non riuscita." });
    } finally {
      setBusy(false);
    }
  }

  if (!categories || categories.length === 0) return null;

  return (
    <div className="pt-4 border-t border-white/5 light:border-slate-200 space-y-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-xs font-semibold text-orange-400 cursor-pointer"
      >
        {open ? "Chiudi assegnazione in blocco" : "Assegna più prodotti a una categoria"}
      </button>
      {open && (
        <div className="space-y-3">
          {error && <p className="text-xs text-rose-400">{(error as Error).message}</p>}
          <div className="flex flex-wrap gap-2">
            <select
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              className="rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500"
            >
              <option value="">Scegli la categoria...</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.product_count})
                </option>
              ))}
            </select>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filtra i prodotti per nome..."
              className="flex-1 min-w-[180px] rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500"
            />
          </div>
          {!products ? (
            <p className="text-xs text-slate-500">Caricamento dei prodotti...</p>
          ) : visible.length === 0 ? (
            <p className="text-xs text-slate-500">Nessun prodotto da assegnare.</p>
          ) : (
            <div className="max-h-64 overflow-y-auto rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
              {visible.map((p) => (
                <label key={p.id} className="flex items-center gap-2 px-3 py-2 text-xs cursor-pointer">
                  <input type="checkbox" checked={picked.has(p.id)} onChange={() => toggle(p.id)} />
                  <span className="flex-1 truncate text-slate-200 light:text-slate-700">{p.name}</span>
                  {category && (p.category_ids ?? []).includes(category.id) && (
                    <span className="text-[10px] font-bold text-emerald-400">già dentro</span>
                  )}
                </label>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busy || !category || picked.size === 0}
              onClick={() => apply(true)}
              className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
            >
              {busy ? "Attendi..." : `Aggiungi alla categoria (${picked.size})`}
            </button>
            <button
              type="button"
              disabled={busy || !category || picked.size === 0}
              onClick={() => apply(false)}
              className="px-3 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold cursor-pointer disabled:opacity-50"
            >
              Togli dalla categoria
            </button>
            {message && <span className={`text-xs ${message.ok ? "text-emerald-400" : "text-rose-400"}`}>{message.text}</span>}
          </div>
        </div>
      )}
    </div>
  );
}
