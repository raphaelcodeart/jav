"use client";

import { useEffect, useState } from "react";
import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { ProductRequestBanner } from "@/components/product-requests";
import type {
  CustomerRead,
  ShopProductPage,
  JavMarketProductRead,
  ProductCatalogRead,
  ShopKey,
} from "@/lib/types";
import { JavMarketProductModal } from "@/components/jav-market-product-modal";
import { useMarketplaceConfig } from "@/components/marketplace-rules-card";
import { ContractRequestWizard } from "@/components/contract-request-wizard";
import { ProductCheckoutModal } from "@/components/product-checkout-modal";
import { ProductDetailModal } from "@/components/product-detail-modal";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { computePrice, contractPrices, productAllowsCustomerKind, isRecurringProductType } from "@/lib/product-audience";
import { ShareMenu } from "@/components/share-buttons";
import { useShopCategories } from "@/components/shop-categories-card";

const PRODUCT_TYPE_LABELS: Record<string, string> = {
  SERVICE: "Servizio",
  DIGITAL: "Digitale",
  PHYSICAL: "Fisico",
  SUBSCRIPTION: "Abbonamento",
};

type ProductCategory = "INTERNAL" | "DROPSHIPPING" | "PARTNER";
// Not a real Product.category value -- the Shop («Fai la Spesa con Jav») is
// a separate table/domain (jav_market), shown here as one more tab so a
// customer sees no difference. Only ever added to the tab bar when
// showShopTab is passed (see CustomerProductsPanelProps below).
type ShopTab = ProductCategory | "JAV_MARKET";

const CATEGORY_TABS: { key: ProductCategory; label: string }[] = [
  { key: "INTERNAL", label: "Jav" },
  { key: "PARTNER", label: "Prodotti Partner" },
  // A UI label only -- the DROPSHIPPING category key is unchanged in the
  // DB/API (see catalog/models.py::Product.category). "Fai la spesa con Jav
  // " is the title of the whole Shop since Session 68.
  { key: "DROPSHIPPING", label: "Offerte Jav" },
];

const ALL_CATEGORIES: ProductCategory[] = ["INTERNAL", "PARTNER", "DROPSHIPPING"];

// Session 73: ogni scheda dello Shop è uno shop a sé anche per le categorie.
// Il cliente non deve mai vedere la categoria di un altro shop, e questa
// tabella è l'unico punto in cui le due nomenclature si incontrano.
const SHOP_KEY_BY_TAB: Record<ShopTab, ShopKey> = {
  INTERNAL: "internal",
  PARTNER: "partner",
  DROPSHIPPING: "dropshipping",
  JAV_MARKET: "jav_market",
};

/** The logged-in customer's own record -- needed for two things the catalog
    could not previously get right: which contracts they are allowed to
    activate, and whether their price carries VAT. 404 for a staff/promoter
    account with no customer record is a normal answer, not an error. */
async function fetchMyCustomerRecord(): Promise<CustomerRead | null> {
  const res = await fetch("/api/proxy/customers/me");
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Impossibile caricare la tua anagrafica.");
  return res.json();
}

/** Session 89: la vetrina dello Shop a pagine («Mostra altri prodotti»).
 *  Tutto il catalogo in una risposta non regge su un catalogo grande, quindi
 *  arriva `PAGE_SIZE` schede per volta e ricerca e categoria le filtra il
 *  server. `baseKey` è la chiave di sempre, così chi la invalida continua a
 *  funzionare. */
const PAGE_SIZE = 48;

function useShopPages<T>(
  baseKey: readonly string[],
  url: string,
  enabled: boolean,
  filters: { q: string; category: string | null },
) {
  const query = useInfiniteQuery({
    queryKey: [...baseKey, filters.q, filters.category],
    queryFn: async ({ pageParam }): Promise<ShopProductPage<T>> => {
      const params = new URLSearchParams({ offset: String(pageParam), limit: String(PAGE_SIZE) });
      if (filters.q) params.set("q", filters.q);
      if (filters.category) params.set("category_id", filters.category);
      const res = await fetch(`${url}?${params}`);
      if (!res.ok) {
        return { items: [], total: 0, shop_total: 0, offset: pageParam, limit: PAGE_SIZE, next_offset: null, category_ids: [] };
      }
      return res.json();
    },
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    enabled,
    // Cambiando ricerca resta la griglia di prima finché arriva la nuova.
    placeholderData: keepPreviousData,
  });
  const pages = query.data?.pages ?? [];
  return {
    items: pages.flatMap((page) => page.items),
    shopTotal: pages[0]?.shop_total ?? 0,
    total: pages.at(-1)?.total ?? 0,
    categoryIds: pages[0]?.category_ids ?? [],
    hasMore: query.hasNextPage,
    loadingMore: query.isFetchingNextPage,
    loadMore: () => query.fetchNextPage(),
  };
}

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

// Wallet credit is JavCash, never plain EUR -- see wallet-panel.tsx's
// identical helper.
function javCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} JavCash`;
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare il catalogo prodotti.");
  return res.json();
}

interface CustomerProductsPanelProps {
  /** When set, each card gets a "Condividi" button that copies a referral link
      pointing directly at that product -- promoter-only use case. */
  referralCode?: string;
  organizationId?: string;
  /** Which category tabs this instance shows -- lets the same component back
      both "Contratti Jav" (INTERNAL only) and "Shop" (PARTNER +
      DROPSHIPPING) without duplicating the catalog grid/cards. Defaults to
      all three, matching the original single-Shop-page behavior (used by the
      promoter's "Condividi" view, which still shares every category). */
  visibleCategories?: ProductCategory[];
  /** The logged-in account's own email, used only to pre-fill (never lock)
      the activation wizard's editable Email field. */
  accountEmail?: string;
  /** Opt-in only -- appends the Shop tab («Fai la Spesa con Jav») to the
      tab bar. Every existing caller (INTERNAL-only
      Home catalog, the promoter "Condividi" view) omits this and keeps
      behaving exactly as before. */
  showShopTab?: boolean;
  /** Quando c'e', sopra la ricerca compare il riquadro «Non hai trovato ciò
      che cercavi?» (richieste di prodotto). E' la funzione che porta il
      cliente a «Le mie richieste»: senza una scheda dove leggere le
      risposte, il riquadro non ha senso, per questo lo accende lei. */
  onOpenProductRequests?: () => void;
}

export function CustomerProductsPanel({
  referralCode,
  organizationId,
  visibleCategories = ALL_CATEGORIES,
  accountEmail,
  showShopTab = false,
  onOpenProductRequests,
}: CustomerProductsPanelProps = {}) {
  const queryClient = useQueryClient();
  const { data: products, isLoading, error } = useQuery({
    queryKey: ["customer", "products"],
    queryFn: fetchProducts,
  });
  const { data: marketplaceConfig } = useMarketplaceConfig();
  // Session 78: il prezzo esposto e' l'imponibile, l'IVA si aggiunge al
  // checkout. Il "+ IVA" accanto al prezzo e' cio' che evita al cliente la
  // sorpresa del 22% al momento di pagare.
  const marketplaceVatPercentage = marketplaceConfig?.vat_percentage ?? 0;
  const marketplaceLabels = marketplaceConfig?.labels ?? { jav_market: "Fai la Spesa con Jav" };
  const [shopTarget, setShopTarget] = useState<JavMarketProductRead | null>(null);
  // Only the contract catalog depends on who is looking -- the shop grid
  // sells the same products to everyone -- so this is not fetched at all
  // unless an INTERNAL tab is on screen.
  const needsCustomerKind = visibleCategories.includes("INTERNAL");
  const { data: myCustomer } = useQuery({
    queryKey: ["customer", "me", "record"],
    queryFn: fetchMyCustomerRecord,
    enabled: needsCustomerKind,
  });
  const customerKind = myCustomer?.kind ?? null;

  const [activeCategory, setActiveCategory] = useState<ShopTab>(visibleCategories[0] ?? "INTERNAL");
  // Gli strumenti per navigare lo shop scelto (Session 73): la categoria e
  // la ricerca lavorano insieme, e cambiano solo la griglia -- mai il
  // checkout, mai una scheda prodotto.
  const [search, setSearch] = useState("");
  const [chosenCategoryId, setChosenCategoryId] = useState<string | null>(null);

  // Session 89: lo Shop arriva a pagine (useShopPages). La ricerca e la
  // categoria valgono solo per il negozio aperto e partono quando il
  // cliente smette di scrivere, non a ogni lettera.
  const [pagedSearch, setPagedSearch] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setPagedSearch(search.trim()), 350);
    return () => clearTimeout(timer);
  }, [search]);
  const pagedFilters = (tab: ShopTab) =>
    activeCategory === tab ? { q: pagedSearch, category: chosenCategoryId } : { q: "", category: null };
  // Session 79: «Fai la Spesa con Jav». Un negozio spento risponde vuoto e
  // la sua scheda sparisce da sola.
  const javMarketShop = useShopPages<JavMarketProductRead>(
    ["customer", "jav-market", "products"], "/api/proxy/jav-market/products/mine/page", showShopTab,
    pagedFilters("JAV_MARKET"),
  );
  const pagedShops: Partial<Record<ShopTab, ReturnType<typeof useShopPages<unknown>>>> = {
    JAV_MARKET: javMarketShop,
  };
  const [checkoutTarget, setCheckoutTarget] = useState<{ versionId: string; name: string } | null>(null);
  const [detailTarget, setDetailTarget] = useState<ProductCatalogRead | null>(null);
  const [activationTarget, setActivationTarget] = useState<ProductCatalogRead | null>(null);

  // "I miei Contratti" and Home show only the Jav packages: a
  // showcase since Session 55 -- activation happens only through the pratica.
  const contractsOnly = !referralCode && visibleCategories.length === 1 && visibleCategories[0] === "INTERNAL";

  // Session 72: each own-catalog section can be renamed and switched off by
  // the administrator ("Sezioni dello Shop"). The switch applies to the Shop's
  // tab bar; a page that asks for one category on purpose (the home showcase
  // of the contracts) keeps showing it.
  const sectionConfig = marketplaceConfig?.sections;
  const sectionKeyOf: Record<ProductCategory, "internal" | "partner" | "dropshipping"> = {
    INTERNAL: "internal",
    PARTNER: "partner",
    DROPSHIPPING: "dropshipping",
  };
  const onlyOneCategoryAsked = visibleCategories.length === 1;
  const visibleTabs: { key: ShopTab; label: string }[] = [
    ...CATEGORY_TABS.filter((tab) => visibleCategories.includes(tab.key))
      .filter((tab) => onlyOneCategoryAsked || (sectionConfig?.[sectionKeyOf[tab.key]]?.enabled ?? true))
      .map((tab) => ({ key: tab.key, label: sectionConfig?.[sectionKeyOf[tab.key]]?.label ?? tab.label })),
    ...(showShopTab && javMarketShop.shopTotal > 0
      ? [{ key: "JAV_MARKET" as ShopTab, label: marketplaceLabels.jav_market }]
      : []),
  ];

  // A section switched off (or a Shop that ran out of products) must
  // never leave the Shop showing an empty body: fall back to the first tab
  // that actually exists, derived during render, never synced in an effect.
  const activeTab: ShopTab = visibleTabs.some((t) => t.key === activeCategory)
    ? activeCategory
    : visibleTabs[0]?.key ?? activeCategory;

  const shopCards: JavMarketProductRead[] = showShopTab && activeTab === "JAV_MARKET" ? javMarketShop.items : [];

  const activeProducts = (products ?? []).filter(
    (p) => p.status === "ACTIVE" && p.current_version && p.current_version.status === "ACTIVE"
  );
  const shopCatalog = activeProducts
    .filter((p) => p.category === activeTab)
    // A customer is only offered the contracts their own tipologia may
    // activate. Enforcement is server-side too (contracts/service.py) --
    // this is so nobody is shown a card that would then be refused. Applies
    // only to contracts: the shop sells the same products to everyone. Fails
    // open while the customer record is still loading.
    .filter((p) => p.category !== "INTERNAL" || productAllowsCustomerKind(p.customer_type, customerKind));

  // Le categorie dello shop scelto -- e solo di quello. La chiamata è
  // tollerante: se il catalogo non ha ancora categorie (o la risposta non
  // arriva) lo Shop resta esattamente quello di prima, senza barra.
  const shopKey = SHOP_KEY_BY_TAB[activeTab];
  // La vetrina dei pacchetti in Home non è una vetrina da esplorare: tre
  // card e un pulsante. Gli strumenti di navigazione servono nello Shop.
  const navigable = !contractsOnly;
  const { data: shopCategories } = useShopCategories(shopKey, navigable);

  // Tutte le categorie attive di questo shop, anche quelle ancora senza
  // prodotti: sono l'indice del negozio, e il cliente deve vedere che cosa
  // ci si vende (richiesta esplicita dell'utente). Quelle vuote restano
  // visibili ma spente all'aspetto, e chi le apre legge perché è vuota.
  const categoryIdsInShop = new Set<string>([
    ...shopCatalog.flatMap((p) => p.category_ids ?? []),
    ...shopCards.flatMap((p) => p.category_ids ?? []),
    // Lo Shop arriva a pagine: le categorie piene le conosce il server, non
    // le pagine già caricate.
    ...(pagedShops[activeTab]?.categoryIds ?? []),
  ]);
  const categoryChips = (shopCategories ?? []).filter((c) => c.active);
  // Derivata durante il render: cambiando shop la categoria scelta non
  // esiste più, e il filtro deve semplicemente sparire.
  const activeCategoryId = categoryChips.some((c) => c.id === chosenCategoryId) ? chosenCategoryId : null;

  const needle = search.trim().toLowerCase();
  const filtering = needle !== "" || activeCategoryId !== null;
  function matchesSearch(name: string, description?: string | null): boolean {
    return !needle || name.toLowerCase().includes(needle) || (description ?? "").toLowerCase().includes(needle);
  }
  function matchesCategory(categoryIds: string[] | undefined): boolean {
    return activeCategoryId === null || (categoryIds ?? []).includes(activeCategoryId);
  }
  /** Torna alla vetrina piena: è la via d'uscita dal risultato vuoto. */
  function showEverything() {
    setSearch("");
    setChosenCategoryId(null);
  }

  const catalog = shopCatalog.filter(
    (p) => matchesSearch(p.current_version!.name, p.current_version!.description) && matchesCategory(p.category_ids)
  );
  const shopCardsShown = shopCards.filter(
    (p) => matchesSearch(p.name, p.description) && matchesCategory(p.category_ids)
  );

  /** The referral link for one product: lands the recipient on registration
      with this promoter's code and this product already selected. */
  function productLink(productId: string, productName: string): string {
    if (!referralCode || typeof window === "undefined") return "";
    const url = new URL(`/r/${referralCode}`, window.location.origin);
    if (organizationId) url.searchParams.set("org", organizationId);
    url.searchParams.set("product", productId);
    url.searchParams.set("product_name", productName);
    return url.toString();
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-500 gap-2">
        <svg className="animate-spin h-5 w-5 text-brand-600" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <span>Caricamento catalogo...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
        Impossibile caricare il catalogo prodotti.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">
          {contractsOnly ? "I pacchetti Jav" : showShopTab && !referralCode ? "Fai la spesa con Jav" : "Prodotti & Servizi"}
        </h3>
        <p className="text-xs text-slate-500">
          {referralCode
            ? "Condividi un'offerta con un cliente: il link lo porta dritto alla registrazione, già associato a te."
            : contractsOnly
              ? "Apri “Dettagli” per leggere ogni pacchetto. Per attivarli usa “Attiva nuovo contratto”: una pratica può contenere uno o più contratti."
              : showShopTab
                ? "Usa il tuo JavCash nello Shop, con consegna a casa."
                : "Le iscrizioni, i corsi e gli abbonamenti disponibili per il tuo profilo."}
        </p>
      </div>


      {/* La scelta dello shop è la prima cosa che fa il cliente: pulsanti
          grandi e tappabili, non linguette. Due per riga sul telefono. */}
      {visibleTabs.length > 1 && (
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {visibleTabs.map((tab) => {
          const count = tab.key === "JAV_MARKET"
            ? javMarketShop.shopTotal
            : activeProducts.filter((p) => p.category === tab.key).length;
          const chosen = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              aria-pressed={chosen}
              onClick={() => {
                setActiveCategory(tab.key);
                // Cambiando negozio si riparte dalla vetrina piena: la
                // ricerca e la categoria di prima erano di un altro shop.
                showEverything();
              }}
              className={`rounded-2xl border p-4 sm:p-5 text-left transition-all duration-200 cursor-pointer active:scale-[0.98] ${
                chosen
                  ? "bg-gradient-to-br from-brand-600 to-brand-400 border-brand-500 text-white shadow-lg shadow-brand-500/20"
                  : "glass-card border-slate-200 bg-white/70 hover:border-brand-500/40 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-brand-500/10"
              }`}
            >
              <span className={`block text-sm sm:text-base font-bold leading-snug ${chosen ? "text-slate-900" : " text-slate-900"}`}>
                {tab.label}
              </span>
              <span className={`block text-[11px] mt-1 ${chosen ? "text-white/80" : " text-slate-500"}`}>
                {count > 0 ? `${count} ${count === 1 ? "prodotto" : "prodotti"}` : "Nessun prodotto"}
              </span>
            </button>
          );
        })}
      </div>
      )}

      {onOpenProductRequests && (
        <ProductRequestBanner searchText={search} onOpenRequests={onOpenProductRequests} />
      )}

      {/* Ricerca e categorie del solo shop scelto: si compongono, e insieme
          decidono la griglia qui sotto. */}
      {navigable && (
        <div className="space-y-3">
          <div className="relative">
            <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
            </svg>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Cerca un prodotto per nome o descrizione..."
              aria-label="Cerca un prodotto in questo negozio"
              className="w-full rounded-xl glass-input pl-10 pr-10 py-3 text-sm focus:border-brand-500"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                aria-label="Cancella la ricerca"
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-lg text-slate-400 hover:text-slate-900 cursor-pointer"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {categoryChips.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                aria-pressed={activeCategoryId === null}
                onClick={() => setChosenCategoryId(null)}
                className={`px-3.5 py-2 rounded-full text-xs font-semibold border transition cursor-pointer ${
                  activeCategoryId === null
                    ? "bg-brand-600 border-brand-600 text-white"
                    : " bg-slate-900/5 border-slate-300 text-slate-600 hover:bg-slate-100"
                }`}
              >
                Tutte
              </button>
              {categoryChips.map((c) => {
                const empty = !categoryIdsInShop.has(c.id);
                return (
                  <button
                    key={c.id}
                    type="button"
                    aria-pressed={activeCategoryId === c.id}
                    onClick={() => setChosenCategoryId(c.id)}
                    title={empty ? "Nessun prodotto in questa categoria, per ora" : undefined}
                    className={`px-3.5 py-2 rounded-full text-xs font-semibold border transition cursor-pointer ${
                      activeCategoryId === c.id
                        ? "bg-brand-600 border-brand-600 text-white"
                        : empty
                          ? " bg-slate-900/5 border-slate-200 text-slate-500 hover:bg-slate-100"
                          : " bg-slate-900/5 border-slate-300 text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    {c.name}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {catalog.length === 0 && shopCardsShown.length === 0 ? (
        filtering ? (
          // Vuoto perché lo stiamo filtrando noi, non perché il negozio sia
          // vuoto: la differenza va detta, e con una via d'uscita.
          <div className="text-center py-12 space-y-3">
            <p className="text-sm text-slate-500">
              Nessun prodotto corrisponde alla ricerca in questo negozio.
            </p>
            <button
              type="button"
              onClick={showEverything}
              className="px-4 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white shadow-lg shadow-brand-500/20 transition cursor-pointer"
            >
              Mostra tutti
            </button>
          </div>
        ) : (
          <p className="text-sm text-slate-500 text-center py-12">
            {activeTab === "INTERNAL"
              ? "Nessun prodotto disponibile al momento. Contatta il tuo promoter di riferimento per maggiori informazioni."
              : "Nessun prodotto in questa categoria al momento."}
          </p>
        )
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {catalog.map((p, i) => {
            const v = p.current_version!;
            const typeLabel = PRODUCT_TYPE_LABELS[p.product_type] ?? p.product_type;
            const purchasable = !referralCode && p.category !== "INTERNAL";
            // A Jav package opens its details (Session 55): it is
            // read here, and activated through "Attiva nuovo contratto".
            const readable = p.category === "INTERNAL";
            const openable = purchasable || readable;
            const maxCreditCents = Math.round((v.base_price_cents * v.credit_discount_percentage) / 100);
            return (
              <div
                key={p.id}
                style={{ animationDelay: `${Math.min(i, 8) * 60}ms` }}
                className="group animate-slide-up glass-card rounded-2xl overflow-hidden border-slate-200 bg-white/70 hover:border-brand-500/40 hover:-translate-y-1.5 hover:shadow-2xl hover:shadow-brand-500/10 transition-all duration-300"
              >
                <button
                  type="button"
                  onClick={() => openable && setDetailTarget(p)}
                  disabled={!openable}
                  className={`relative block w-full h-48 overflow-hidden ${openable ? "cursor-pointer" : "cursor-default"}`}
                >
                  <ProductThumbnail
                    imageUrl={v.image_url}
                    alt={v.name}
                    className="w-full h-full object-cover transition-transform duration-500 ease-out group-hover:scale-110"
                    iconClassName="w-12 h-12 text-brand-600/40"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-slate-950/70 via-transparent to-transparent" />
                  <div className="absolute top-3 left-3 flex flex-wrap gap-1.5">
                    <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-950/70 backdrop-blur-sm text-slate-900 border border-slate-200 shadow-lg">
                      {typeLabel}
                    </span>
                  </div>
                  {p.category !== "INTERNAL" && v.credit_discount_percentage > 0 && (
                    <div className="absolute top-3 right-3">
                      <span className="px-2.5 py-1 rounded-full text-[10px] font-extrabold bg-gradient-to-r from-emerald-500 to-emerald-400 text-white shadow-lg shadow-emerald-500/30">
                        -{v.credit_discount_percentage}% in JavCash
                      </span>
                    </div>
                  )}
                  {purchasable && (
                    <div className="absolute inset-0 flex items-center justify-center bg-slate-950/0 group-hover:bg-slate-950/30 transition-colors duration-300">
                      <span className="opacity-0 group-hover:opacity-100 translate-y-1 group-hover:translate-y-0 transition-all duration-300 px-3 py-1.5 rounded-lg bg-white/90 text-slate-900 text-[11px] font-bold shadow-lg">
                        Vedi dettagli
                      </span>
                    </div>
                  )}
                </button>
                <div className="p-5">
                  <h4
                    onClick={() => openable && setDetailTarget(p)}
                    className={`text-base font-semibold text-slate-900 mb-1 leading-snug ${openable ? "cursor-pointer hover:text-brand-600 transition" : ""}`}
                  >
                    {v.name}
                  </h4>
                  {v.description && (
                    <p className="text-xs text-slate-500 mb-4 line-clamp-2">{v.description}</p>
                  )}

                  <div className="flex items-end justify-between gap-3 pt-4 border-t border-slate-200">
                    <div>
                      <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Prezzo</p>
                      <div className="flex items-baseline gap-1">
                        <span className="text-2xl font-extrabold text-slate-900 tabular-nums">{euro(v.base_price_cents)}</span>
                        <span className="text-[11px] text-slate-500">{isRecurringProductType(p.product_type) ? "unica soluzione" : ""}</span>
                      </div>
                      {p.category === "INTERNAL" && isRecurringProductType(p.product_type) && (
                        // Session 84: the rate have their own price, not the one above / 12.
                        <p className=" text-slate-500 mt-0.5">
                          oppure 12 rate da{" "}
                          {euro(contractPrices(v, customerKind, { assumeBusinessWhenUnknown: false }).monthlyGrossCents)}
                        </p>
                      )}
                      {(() => {
                        // A contract for a private customer carries no VAT at
                        // all -- this card used to add it unconditionally, so a
                        // privato was quoted 22% more than they would ever be
                        // charged. On the shop grid (no customer kind in play)
                        // the product's own rate is shown, as before.
                        const price = computePrice(
                          v.base_price_cents,
                          v.vat_percentage,
                          p.category === "INTERNAL" ? customerKind : null
                        );
                        if (price.vatCents <= 0) {
                          return p.category === "INTERNAL" && customerKind ? (
                            <p className="text-[10px] text-slate-500 mt-0.5">IVA non applicata</p>
                          ) : null;
                        }
                        return (
                          <p className="text-[10px] text-slate-500 mt-0.5">
                            + IVA {price.vatRate}% ({euro(price.grossCents)} tot.)
                          </p>
                        );
                      })()}
                      {v.initial_fee_cents > 0 && (
                        <p className="text-[10px] text-slate-500 mt-0.5">
                          + {euro(v.initial_fee_cents)} attivazione
                        </p>
                      )}
                    </div>
                    {p.category !== "INTERNAL" && maxCreditCents > 0 && (
                      <div className="text-right">
                        <p className="text-[10px] font-semibold text-emerald-500 uppercase tracking-wide">JavCash usabili</p>
                        <p className="text-lg font-extrabold text-emerald-400 tabular-nums">{javCash(maxCreditCents)}</p>
                      </div>
                    )}
                  </div>

                  {referralCode && (
                    // A menu, not a row: these are cards in a grid, and five
                    // pills per card would crowd out the product itself.
                    <ShareMenu
                      url={productLink(p.id, v.name)}
                      text={`Ti consiglio "${v.name}" di Jav:`}
                      title={v.name}
                      heading={`Condividi "${v.name}"`}
                      buttonClassName="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-600 text-xs font-semibold transition cursor-pointer"
                    />
                  )}
                  {purchasable && (
                    <button
                      onClick={() => setDetailTarget(p)}
                      className="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 text-white text-xs font-bold shadow-lg shadow-brand-500/20 transition-all duration-200 cursor-pointer active:scale-[0.98]"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 11H4L5 9z" />
                      </svg>
                      Vedi dettagli e acquista
                    </button>
                  )}
                  {readable && (
                    <button
                      onClick={() => setDetailTarget(p)}
                      className="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-slate-900/5 hover:bg-slate-900/10 border border-slate-300 text-slate-800 text-xs font-bold transition-all duration-200 cursor-pointer active:scale-[0.98]"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Dettagli
                    </button>
                  )}
                </div>
              </div>
            );
          })}
          {shopCardsShown.map((p, i) => {
            const maxCreditCents = Math.round((p.min_price_cents * p.credit_discount_percentage) / 100);
            return (
              <div
                key={`shop-${p.id}`}
                style={{ animationDelay: `${Math.min(catalog.length + i, 8) * 60}ms` }}
                className="group animate-slide-up glass-card rounded-2xl overflow-hidden border-slate-200 bg-white/70 hover:border-brand-500/40 hover:-translate-y-1.5 hover:shadow-2xl hover:shadow-brand-500/10 transition-all duration-300"
              >
                <button
                  type="button"
                  onClick={() => {
                    if (!referralCode) setShopTarget(p);
                  }}
                  className="relative block w-full h-48 overflow-hidden cursor-pointer bg-white"
                >
                  <ProductThumbnail
                    imageUrl={p.image_url}
                    alt={p.name}
                    className="w-full h-full object-cover transition-transform duration-500 ease-out group-hover:scale-110"
                    iconClassName="w-12 h-12 text-brand-600/40"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-slate-950/70 via-transparent to-transparent" />
                  <div className="absolute top-3 left-3 flex flex-wrap gap-1.5">
                    <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-950/70 backdrop-blur-sm text-slate-900 border border-slate-200 shadow-lg">
                      {p.shipping_days ? `Consegna ${p.shipping_days} gg` : "Spedito a casa"}
                    </span>
                  </div>
                  {p.credit_discount_percentage > 0 && (
                    <div className="absolute top-3 right-3">
                      <span className="px-2.5 py-1 rounded-full text-[10px] font-extrabold bg-gradient-to-r from-emerald-500 to-emerald-400 text-white shadow-lg shadow-emerald-500/30">
                        -{p.credit_discount_percentage}% in JavCash
                      </span>
                    </div>
                  )}
                  {!p.in_stock && (
                    <span className="absolute inset-x-0 bottom-0 py-1.5 text-center text-[11px] font-bold bg-slate-900/85 text-slate-900">Esaurito</span>
                  )}
                  <div className="absolute inset-0 flex items-center justify-center bg-slate-950/0 group-hover:bg-slate-950/30 transition-colors duration-300">
                    <span className="opacity-0 group-hover:opacity-100 translate-y-1 group-hover:translate-y-0 transition-all duration-300 px-3 py-1.5 rounded-lg bg-white/90 text-slate-900 text-[11px] font-bold shadow-lg">
                      Vedi dettagli
                    </span>
                  </div>
                </button>
                <div className="p-5">
                  <h4
                    onClick={() => setShopTarget(p)}
                    className="text-base font-semibold text-slate-900 mb-1 leading-snug cursor-pointer hover:text-brand-600 transition line-clamp-2"
                  >
                    {p.name}
                  </h4>
                  {p.description && (
                    <p className="text-xs text-slate-500 mb-4 line-clamp-2">{p.description}</p>
                  )}
                  <div className="flex items-end justify-between gap-3 pt-4 border-t border-slate-200">
                    <div>
                      <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
                        {p.min_price_cents !== p.max_price_cents ? "Prezzo da" : "Prezzo"}
                      </p>
                      <span className="text-2xl font-extrabold text-slate-900 tabular-nums">{euro(p.min_price_cents)}</span>
                      <p className="text-[10px] text-slate-500 mt-0.5">
                        {marketplaceVatPercentage > 0 ? "+ IVA · " : ""}
                        {p.shipping_included ? "Spedizione inclusa" : "+ spedizione"}
                      </p>
                      {/* The price shown is the full one; bank transfer takes a discount off. */}
                      {p.bank_transfer_discount_percentage > 0 && (
                        <p className=" font-semibold text-slate-900 mt-0.5">
                          Con bonifico istantaneo -{p.bank_transfer_discount_percentage}%:{" "}
                          <span className="tabular-nums">
                            {euro(p.min_price_cents - Math.floor((p.min_price_cents * p.bank_transfer_discount_percentage + 50) / 100))}
                          </span>
                        </p>
                      )}
                    </div>
                    {maxCreditCents > 0 && (
                      <div className="text-right">
                        <p className="text-[10px] font-semibold text-emerald-500 uppercase tracking-wide">JavCash usabili</p>
                        <p className="text-lg font-extrabold text-emerald-400 tabular-nums">{javCash(maxCreditCents)}</p>
                      </div>
                    )}
                  </div>
                  {referralCode ? (
                    // Il promoter condivide, non compra per conto d'altri:
                    // il link porta alla registrazione col suo codice.
                    <ShareMenu
                      url={productLink(p.id, p.name)}
                      text={`Ti consiglio "${p.name}" nello shop di Jav:`}
                      title={p.name}
                      heading={`Condividi "${p.name}"`}
                      buttonClassName="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-600 text-xs font-semibold transition cursor-pointer"
                    />
                  ) : (
                    <button
                      onClick={() => setShopTarget(p)}
                      className="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 text-white text-xs font-bold shadow-lg shadow-brand-500/20 transition-all duration-200 cursor-pointer active:scale-[0.98]"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 11H4L5 9z" />
                      </svg>
                      Vedi dettagli e acquista
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {(() => {
        // «Mostra altri prodotti» per lo Shop, che arriva a pagine.
        const paged = pagedShops[activeTab];
        if (!paged || paged.items.length === 0) return null;
        return (
          <div className="flex flex-col items-center gap-2 pt-2">
            {paged.hasMore && (
              <p className=" text-slate-500 tabular-nums">
                {paged.items.length.toLocaleString("it-IT")} di {paged.total.toLocaleString("it-IT")} prodotti
              </p>
            )}
            {paged.hasMore && (
              <button
                type="button"
                onClick={() => paged.loadMore()}
                disabled={paged.loadingMore}
                className="px-5 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white shadow-lg shadow-brand-500/20 transition cursor-pointer disabled:opacity-60"
              >
                {paged.loadingMore ? "Caricamento…" : "Mostra altri prodotti"}
              </button>
            )}
          </div>
        );
      })()}

      {detailTarget && (
        <ProductDetailModal
          product={detailTarget}
          customerKind={detailTarget.category === "INTERNAL" ? customerKind : undefined}
          ctaLabel={
            detailTarget.category !== "INTERNAL"
              ? "Acquista ora"
              : referralCode
                ? "Chiudi"
                : "Attiva nuovo contratto"
          }
          onClose={() => setDetailTarget(null)}
          onBuy={(versionId, name) => {
            const target = detailTarget;
            setDetailTarget(null);
            if (target.category !== "INTERNAL") setCheckoutTarget({ versionId, name });
            // The same pratica as the button at the top of "I miei
            // Contratti", with this package already chosen for every contract.
            else if (!referralCode) setActivationTarget(target);
          }}
        />
      )}

      {checkoutTarget && (
        <ProductCheckoutModal
          productVersionId={checkoutTarget.versionId}
          productName={checkoutTarget.name}
          onClose={() => setCheckoutTarget(null)}
        />
      )}

      {shopTarget && (
        <JavMarketProductModal product={shopTarget} onClose={() => setShopTarget(null)} />
      )}

      {activationTarget && (
        // Starting from a package opens a new pratica with that package
        // already chosen for every contract of it (Session 52) -- one or
        // ten, changeable one by one.
        <ContractRequestWizard
          initialProduct={activationTarget}
          customerKind={customerKind}
          accountEmail={accountEmail}
          holder={{
            firstName: myCustomer?.first_name,
            lastName: myCustomer?.last_name,
            pec: myCustomer?.pec,
            fiscalCode: myCustomer?.fiscal_code,
          }}
          onClose={() => {
            setActivationTarget(null);
            queryClient.invalidateQueries({ queryKey: ["contract-requests"] });
          }}
        />
      )}
    </div>
  );
}
