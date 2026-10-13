"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PhotoUpload } from "@/components/photo-upload";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { friendlyApiError } from "@/lib/api-error";
import { useMarketplaceConfig } from "@/components/marketplace-rules-card";
import { ProductCategoriesField, saveProductCategories, sameCategorySelection, ManageCategoriesButton } from "@/components/shop-categories-card";
import type { ProductCatalogRead, ProductRead, RankRead, ShopKey } from "@/lib/types";
import { isRecurringProductType } from "@/lib/product-audience";

const ENERGY_LABELS: Record<string, string> = {
  ELECTRICITY: "Luce",
  GAS: "Gas",
  DUAL_FUEL: "Dual Fuel",
};

const PRODUCT_TYPE_LABELS: Record<string, string> = {
  ENERGY_CONTRACT: "Contratto Energia",
  DIGITAL: "Digitale",
  PHYSICAL: "Fisico",
  SUBSCRIPTION: "Abbonamento",
};

// Who a product may be sold to. Three values, because the business question
// is genuinely binary-plus-both -- the old vocabulary (PMI, ENERGY_INTENSIVE,
// SOLE_PROPRIETOR) never lined up with `customers.kind` (COMPANY, ...), so
// nothing could compare the two and no product was ever actually filtered.
// Legacy values still parse server-side and collapse onto BUSINESS; see
// catalog/pricing.py.
const CUSTOMER_TYPE_LABELS: Record<string, string> = {
  BOTH: "Privati e aziende",
  PRIVATE: "Solo privati",
  BUSINESS: "Solo aziende / P.IVA",
};

const LEGACY_CUSTOMER_TYPE_LABELS: Record<string, string> = {
  SOLE_PROPRIETOR: "Solo aziende / P.IVA",
  PMI: "Solo aziende / P.IVA",
  CONDOMINIUM: "Solo aziende / P.IVA",
  ENERGY_INTENSIVE: "Solo aziende / P.IVA",
};

function customerTypeLabel(value: string): string {
  return CUSTOMER_TYPE_LABELS[value] ?? LEGACY_CUSTOMER_TYPE_LABELS[value] ?? value;
}

const CATEGORY_LABELS: Record<string, string> = {
  INTERNAL: "Interno Jav",
  DROPSHIPPING: "Fai la spesa con Jav",
  PARTNER: "Partner / collaboratore",
};

// Le tre sezioni del catalogo nostro sono tre shop distinti agli occhi delle
// categorie (Session 73): "Casa" delle Offerte Jav e "Casa" dei Partner sono
// due categorie diverse, perché sono due vetrine diverse per il cliente.
const SHOP_KEY_BY_CATEGORY: Record<string, ShopKey> = {
  INTERNAL: "internal",
  PARTNER: "partner",
  DROPSHIPPING: "dropshipping",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function euroToCents(value: string): number {
  const parsed = parseFloat(value.replace(",", "."));
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

function centsToEuroInput(cents: number): string {
  return (cents / 100).toFixed(2);
}

function commissionTokensToCents(tokens: Record<string, string>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [code, value] of Object.entries(tokens)) {
    if (value.trim()) out[code] = euroToCents(value);
  }
  return out;
}

function commissionTokensToEuro(tokens: Record<string, number>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [code, cents] of Object.entries(tokens)) {
    out[code] = centsToEuroInput(cents);
  }
  return out;
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti.");
  return res.json();
}

async function fetchRanks(): Promise<RankRead[]> {
  const res = await fetch("/api/proxy/commissions/ranks");
  if (!res.ok) throw new Error("Impossibile caricare le qualifiche.");
  return res.json();
}

interface ProductFormState {
  name: string;
  description: string;
  imageUrl: string;
  basePriceEuro: string;
  // Session 84: a contract's monthly rata (net of VAT), NOT basePrice / 12 --
  // paying in rate costs more. Empty = the rate split the one-go price.
  monthlyPriceEuro: string;
  initialFeeEuro: string;
  recurringFeeEuro: string;
  billingPeriod: string;
  vatPercentage: string;
  contractDurationMonths: string;
  // rank code -> gettone in EUR (string, same input pattern as the other money
  // fields) -- the personal token this product pays at that rank, see
  // catalog/models.py::ProductVersion.commission_tokens.
  commissionTokens: Record<string, string>;
  // 0-100, string for the same reason every other numeric field here is a
  // string (lets the input hold "" while the user is typing). Only
  // meaningful when the product's category isn't INTERNAL -- see
  // catalog/service.py::_clamp_credit_discount.
  creditDiscountPercentage: string;
  // Whether "riscuoti subito cashback" is offerable at checkout for this
  // product -- same INTERNAL-forced-off rule as creditDiscountPercentage,
  // see catalog/service.py::_clamp_cashback_enabled.
  cashbackEnabled: boolean;
  // INTERNAL-only counterparts of the two above. 0-100: how much of a paid
  // contract's GROSS (VAT included) comes back as JavCash, automatically
  // and with no surcharge -- see catalog/service.py::_clamp_contract_cashback.
  contractCashbackPercentage: string;
  // A one-off bonus for the promoter who ORIGINALLY brought the customer in.
  // A value an admin sets per product, never a price comparison in code.
  firstReferrerBonusEnabled: boolean;
  firstReferrerBonusEuro: string;
  // Le categorie dello Shop a cui il prodotto appartiene dentro la propria
  // sezione. Non stanno sulla ProductVersion: si salvano con una chiamata
  // loro (PUT /shop-categories/assignments), e solo se toccate.
  categoryIds: string[];
}

const EMPTY_FORM: ProductFormState = {
  name: "",
  description: "",
  imageUrl: "",
  basePriceEuro: "",
  monthlyPriceEuro: "",
  initialFeeEuro: "0",
  recurringFeeEuro: "0",
  billingPeriod: "MONTHLY",
  vatPercentage: "10",
  contractDurationMonths: "12",
  commissionTokens: {},
  creditDiscountPercentage: "0",
  cashbackEnabled: false,
  contractCashbackPercentage: "0",
  firstReferrerBonusEnabled: false,
  firstReferrerBonusEuro: "0",
  categoryIds: [],
};

function ProductFormFields({
  form,
  onChange,
  ranks,
  category,
  productType,
}: {
  form: ProductFormState;
  onChange: (patch: Partial<ProductFormState>) => void;
  ranks: RankRead[];
  /** Whether the "sconto in crediti" field is usable -- INTERNAL products
      (Jav's own supply) are never discountable in wallet credits, see
      docs/cashback-partner-invoices-plan.md. */
  category: string;
  /** ENERGY_CONTRACT / SUBSCRIPTION are contracts: one-go price + monthly price. */
  productType: string;
}) {
  const isContract = isRecurringProductType(productType);
  return (
    <>
      <div className="space-y-1">
        <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome</label>
        <input required value={form.name} onChange={(e) => onChange({ name: e.target.value })}
          className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
      </div>

      <div className="space-y-1">
        <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Descrizione</label>
        <textarea rows={2} value={form.description} onChange={(e) => onChange({ description: e.target.value })}
          placeholder="Descrizione visibile ai clienti nel marketplace..."
          className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500 resize-none" />
      </div>

      <div className="space-y-1">
        <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Foto prodotto (URL immagine)</label>
        <div className="flex items-center gap-3">
          {form.imageUrl && (
            // eslint-disable-next-line @next/next/no-img-element -- externally-hosted, variable-source image (URL or uploaded)
            <img src={form.imageUrl} alt="" className="w-12 h-12 rounded-lg object-cover border border-white/10 light:border-slate-200 shrink-0" />
          )}
          <input value={form.imageUrl} onChange={(e) => onChange({ imageUrl: e.target.value })}
            placeholder="https://..."
            className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
        </div>
      </div>

      <ProductCategoriesField
        shop={SHOP_KEY_BY_CATEGORY[category] ?? "internal"}
        value={form.categoryIds}
        onChange={(categoryIds) => onChange({ categoryIds })}
      />

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">
            {isContract ? "Prezzo unica soluzione (EUR)" : "Prezzo base (EUR)"}
          </label>
          <input required inputMode="decimal" value={form.basePriceEuro} onChange={(e) => onChange({ basePriceEuro: e.target.value })}
            placeholder={isContract ? "149.00" : "18.00"}
            className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
          {isContract && (
            <p className="text-[10px] text-slate-500">L&apos;intero contratto pagato in una volta, IVA esclusa.</p>
          )}
        </div>
        {isContract && (
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Prezzo mensile (EUR)</label>
            <input inputMode="decimal" value={form.monthlyPriceEuro} onChange={(e) => onChange({ monthlyPriceEuro: e.target.value })}
              placeholder="18.30"
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
            <p className="text-[10px] text-slate-500">
              La rata di chi paga a rate, IVA esclusa: il totale a rate è questo × i mesi del contratto (anche in 3 rate).
              Compilato, lo sconto per il pagamento unico di Impostazioni non si applica più a questo pacchetto.
              Vuoto = le rate dividono il prezzo in unica soluzione, e lo sconto resta.
            </p>
          </div>
        )}
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Aliquota IVA (%)</label>
          <input inputMode="decimal" value={form.vatPercentage} onChange={(e) => onChange({ vatPercentage: e.target.value })}
            placeholder="10"
            className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Fee iniziale (EUR)</label>
          <input inputMode="decimal" value={form.initialFeeEuro} onChange={(e) => onChange({ initialFeeEuro: e.target.value })}
            className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Fee ricorrente (EUR)</label>
          <input inputMode="decimal" value={form.recurringFeeEuro} onChange={(e) => onChange({ recurringFeeEuro: e.target.value })}
            className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Periodicità fatturazione</label>
          <select value={form.billingPeriod} onChange={(e) => onChange({ billingPeriod: e.target.value })}
            className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
            <option value="MONTHLY">Mensile</option>
            <option value="QUARTERLY">Trimestrale</option>
            <option value="ANNUAL">Annuale</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Durata contratto (mesi)</label>
          <input inputMode="numeric" value={form.contractDurationMonths}
            onChange={(e) => onChange({ contractDurationMonths: e.target.value })}
            placeholder="Vuoto = nessun rinnovo"
            className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
          <p className="text-[10px] text-slate-500">Lascia vuoto per prodotti senza rinnovo (digitali, fisici, acquisti una tantum).</p>
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">
          Sconto pagabile in crediti (%)
        </label>
        {category === "INTERNAL" ? (
          <p className="text-[10px] text-slate-500">
            Non disponibile per i prodotti Interno Jav -- pagabili solo in bonifico.
          </p>
        ) : (
          <>
            <input
              inputMode="numeric"
              value={form.creditDiscountPercentage}
              onChange={(e) => onChange({ creditDiscountPercentage: e.target.value })}
              placeholder="0"
              className="w-full max-w-[140px] rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
            />
            <p className="text-[10px] text-slate-500">
              Quanta parte del prezzo un cliente può pagare con i crediti wallet nel checkout -- il resto resta bonifico.
            </p>
          </>
        )}
      </div>

      <div className="space-y-1">
        <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">
          Cashback al checkout
        </label>
        {category === "INTERNAL" ? (
          <p className="text-[10px] text-slate-500">
            Non disponibile per i prodotti Interno Jav.
          </p>
        ) : (
          <>
            <label className="flex items-center gap-2.5 text-xs text-slate-300 light:text-slate-600 cursor-pointer">
              <input
                type="checkbox"
                checked={form.cashbackEnabled}
                onChange={(e) => onChange({ cashbackEnabled: e.target.checked })}
                className="w-4 h-4 rounded border-white/20 accent-orange-500"
              />
              Abilita &ldquo;riscuoti subito cashback&rdquo; per questo prodotto
            </label>
            <p className="text-[10px] text-slate-500">
              Se attivo, il cliente può scegliere in fase di acquisto di pagare il {" "}
              <span className="font-mono">5%</span> in più per ricevere l&apos;intero importo pagato (100% + 5%)
              accreditato subito come JavCash sul suo wallet, una volta confermato il pagamento.
            </p>
          </>
        )}
      </div>

      {category === "INTERNAL" && (
        <>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">
              Cashback automatico sul contratto (%)
            </label>
            <input
              inputMode="numeric"
              value={form.contractCashbackPercentage}
              onChange={(e) => onChange({ contractCashbackPercentage: e.target.value })}
              placeholder="0"
              className="w-full max-w-[140px] rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
            />
            <p className="text-[10px] text-slate-500">
              Percentuale dell&apos;importo totale pagato (IVA inclusa) che torna al cliente come JavCash
              quando il contratto risulta pagato. <strong>Automatico e senza il 5% aggiuntivo</strong>: sui
              servizi Jav e sulla formazione il cliente non paga nulla in più per ottenere il credito,
              a differenza del riscatto fatture dei partner esterni. <span className="font-mono">0</span> = nessun
              cashback.
            </p>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">
              Bonus a chi porta il cliente
            </label>
            <label className="flex items-center gap-2.5 text-xs text-slate-300 light:text-slate-600 cursor-pointer">
              <input
                type="checkbox"
                checked={form.firstReferrerBonusEnabled}
                onChange={(e) => onChange({ firstReferrerBonusEnabled: e.target.checked })}
                className="w-4 h-4 rounded border-white/20 accent-orange-500"
              />
              Riconosci un bonus extra al primo promoter che ha portato il cliente
            </label>
            {form.firstReferrerBonusEnabled && (
              <div className="flex items-center gap-2 pt-1">
                <input
                  inputMode="decimal"
                  value={form.firstReferrerBonusEuro}
                  onChange={(e) => onChange({ firstReferrerBonusEuro: e.target.value })}
                  placeholder="25.00"
                  className="w-full max-w-[140px] rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
                />
                <span className="text-xs text-slate-500">EUR</span>
              </div>
            )}
            <p className="text-[10px] text-slate-500">
              Si aggiunge alla provvigione normale, non la sostituisce, e viene pagato{" "}
              <strong>una sola volta per contratto</strong> al promoter che ha portato il cliente in Jav
              &mdash; mai a tutta la rete e mai al promoter che si limita a compilare il contratto,
              se è una persona diversa.
            </p>
          </div>
        </>
      )}

      <div className="space-y-1 pt-2 border-t border-white/5 light:border-slate-200">
        <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">
          Gettone provvigionale per grado (EUR)
        </label>
        <p className="text-[10px] text-slate-500 mb-2">
          Quanto guadagna il promoter per un contratto di QUESTO prodotto, in base al proprio grado.
          Determina anche la differenza imprenditoriale riconosciuta agli sponsor superiori.
        </p>
        <div className="grid grid-cols-3 gap-2">
          {[...ranks].sort((a, b) => a.level - b.level).map((r) => (
            <div key={r.id} className="space-y-0.5">
              <label className="text-[10px] text-slate-400 light:text-slate-500 font-mono block">{r.code}</label>
              <input
                inputMode="decimal"
                value={form.commissionTokens[r.code] ?? ""}
                onChange={(e) =>
                  onChange({ commissionTokens: { ...form.commissionTokens, [r.code]: e.target.value } })
                }
                placeholder="0.00"
                className="w-full rounded-lg glass-input px-2 py-1.5 text-xs focus:border-orange-500"
              />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

export function AdminProductsPanel() {
  const queryClient = useQueryClient();
  const { data: products, error: loadError } = useQuery({
    queryKey: ["admin", "products"],
    queryFn: fetchProducts,
  });
  const { data: ranks = [] } = useQuery({
    queryKey: ["admin", "ranks"],
    queryFn: fetchRanks,
  });
  // Session 86: a RETIRED product is out of the catalog for good -- kept in
  // the database only because orders or contracts point at it -- so the
  // list hides it unless asked.
  const [showRetired, setShowRetired] = useState(false);
  const retiredCount = (products ?? []).filter((p) => p.status === "RETIRED").length;
  const listedProducts = products?.filter((p) => showRetired || p.status !== "RETIRED");

  const [showCreate, setShowCreate] = useState(false);
  const [isDuplicating, setIsDuplicating] = useState(false);
  const [code, setCode] = useState("");
  const [productType, setProductType] = useState("ENERGY_CONTRACT");
  const [energyType, setEnergyType] = useState("ELECTRICITY");
  const [customerType, setCustomerType] = useState("BOTH");
  const [category, setCategory] = useState("INTERNAL");
  const [createForm, setCreateForm] = useState<ProductFormState>(EMPTY_FORM);
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editingProduct, setEditingProduct] = useState<ProductCatalogRead | null>(null);
  // Lives on the Product, not the ProductVersion, so it is saved by its own
  // PATCH below. Until now it could only be set at creation and never
  // corrected -- and nothing read it anyway.
  const [editCustomerType, setEditCustomerType] = useState("BOTH");
  // Session 89: the internal code is a Product field too (LUCE-COPY-COPY
  // after two duplicates), renamed by the same PATCH.
  const [editCode, setEditCode] = useState("");
  const [editForm, setEditForm] = useState<ProductFormState>(EMPTY_FORM);
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Le sezioni dello Shop sono rinominabili (Session 72): il selettore delle
  // categorie deve chiamarle come le chiama il cliente, non con i nomi fissi.
  const { data: marketplaceConfig } = useMarketplaceConfig();
  const shopsForCategories: { key: ShopKey; label: string }[] = [
    { key: "internal", label: marketplaceConfig?.sections.internal.label ?? "Interno Jav" },
    { key: "partner", label: marketplaceConfig?.sections.partner.label ?? "Partner / collaboratore" },
    { key: "dropshipping", label: marketplaceConfig?.sections.dropshipping.label ?? "Fai la spesa con Jav" },
  ];

  const [deletingProduct, setDeletingProduct] = useState<ProductCatalogRead | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function openDuplicate(product: ProductCatalogRead) {
    const v = product.current_version;
    setCode(`${product.code}-COPY`);
    setProductType(product.product_type);
    setEnergyType(product.energy_type ?? "ELECTRICITY");
    setCustomerType(product.customer_type);
    setCategory(product.category);
    setCreateForm({
      name: v ? `${v.name} (copia)` : "",
      description: v?.description ?? "",
      imageUrl: v?.image_url ?? "",
      basePriceEuro: v ? centsToEuroInput(v.base_price_cents) : "",
      monthlyPriceEuro: v?.monthly_price_cents != null ? centsToEuroInput(v.monthly_price_cents) : "",
      initialFeeEuro: v ? centsToEuroInput(v.initial_fee_cents) : "0",
      recurringFeeEuro: v ? centsToEuroInput(v.recurring_fee_cents) : "0",
      billingPeriod: v?.billing_period ?? "MONTHLY",
      vatPercentage: v?.vat_percentage != null ? String(v.vat_percentage) : "",
      contractDurationMonths: v?.contract_duration_months != null ? String(v.contract_duration_months) : "",
      commissionTokens: v ? commissionTokensToEuro(v.commission_tokens) : {},
      creditDiscountPercentage: v ? String(v.credit_discount_percentage) : "0",
      cashbackEnabled: v?.cashback_enabled ?? false,
      contractCashbackPercentage: v ? String(v.contract_cashback_percentage) : "0",
      firstReferrerBonusEnabled: v?.first_referrer_bonus_enabled ?? false,
      firstReferrerBonusEuro: v ? centsToEuroInput(v.first_referrer_bonus_cents) : "0",
      categoryIds: product.category_ids ?? [],
    });
    setCreateError(null);
    setIsDuplicating(true);
    setShowCreate(true);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code,
          product_type: productType,
          energy_type: productType === "ENERGY_CONTRACT" ? energyType : null,
          customer_type: customerType,
          category,
          name: createForm.name,
          description: createForm.description,
          image_url: createForm.imageUrl.trim() || null,
          base_price_cents: euroToCents(createForm.basePriceEuro),
          monthly_price_cents: isRecurringProductType(productType) && createForm.monthlyPriceEuro.trim()
            ? euroToCents(createForm.monthlyPriceEuro)
            : null,
          initial_fee_cents: euroToCents(createForm.initialFeeEuro),
          recurring_fee_cents: euroToCents(createForm.recurringFeeEuro),
          billing_period: createForm.billingPeriod,
          vat_percentage: createForm.vatPercentage.trim() ? parseFloat(createForm.vatPercentage) : null,
          contract_duration_months: createForm.contractDurationMonths.trim()
            ? parseInt(createForm.contractDurationMonths, 10)
            : null,
          commission_tokens: commissionTokensToCents(createForm.commissionTokens),
          credit_discount_percentage: category === "INTERNAL" ? 0 : (parseInt(createForm.creditDiscountPercentage, 10) || 0),
          cashback_enabled: category === "INTERNAL" ? false : createForm.cashbackEnabled,
          // Mirror of the clamps in catalog/service.py -- the server enforces
          // these regardless, this just keeps the request honest.
          contract_cashback_percentage: category === "INTERNAL" ? (parseInt(createForm.contractCashbackPercentage, 10) || 0) : 0,
          first_referrer_bonus_enabled: category === "INTERNAL" && createForm.firstReferrerBonusEnabled,
          first_referrer_bonus_cents: category === "INTERNAL" ? euroToCents(createForm.firstReferrerBonusEuro) : 0,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));

      // Le categorie non stanno sulla ProductVersion: si assegnano dopo, e
      // solo se ne è stata scelta almeno una, così un catalogo senza
      // categorie non dipende affatto da questo endpoint.
      const created: ProductRead = await res.json();
      if (createForm.categoryIds.length > 0 && created?.id) {
        const shop = SHOP_KEY_BY_CATEGORY[category] ?? "internal";
        await saveProductCategories(shop, created.id, createForm.categoryIds);
        await queryClient.invalidateQueries({ queryKey: ["shop-categories", shop] });
      }

      setShowCreate(false);
      setIsDuplicating(false);
      setCode("");
      setCreateForm(EMPTY_FORM);
      await queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare il prodotto.");
    } finally {
      setCreateLoading(false);
    }
  }

  function openEdit(product: ProductCatalogRead) {
    const v = product.current_version;
    setEditForm({
      name: v?.name ?? "",
      description: v?.description ?? "",
      imageUrl: v?.image_url ?? "",
      basePriceEuro: v ? centsToEuroInput(v.base_price_cents) : "",
      monthlyPriceEuro: v?.monthly_price_cents != null ? centsToEuroInput(v.monthly_price_cents) : "",
      initialFeeEuro: v ? centsToEuroInput(v.initial_fee_cents) : "0",
      recurringFeeEuro: v ? centsToEuroInput(v.recurring_fee_cents) : "0",
      billingPeriod: v?.billing_period ?? "MONTHLY",
      vatPercentage: v?.vat_percentage != null ? String(v.vat_percentage) : "",
      contractDurationMonths: v?.contract_duration_months != null ? String(v.contract_duration_months) : "",
      commissionTokens: v ? commissionTokensToEuro(v.commission_tokens) : {},
      creditDiscountPercentage: v ? String(v.credit_discount_percentage) : "0",
      cashbackEnabled: v?.cashback_enabled ?? false,
      contractCashbackPercentage: v ? String(v.contract_cashback_percentage) : "0",
      firstReferrerBonusEnabled: v?.first_referrer_bonus_enabled ?? false,
      firstReferrerBonusEuro: v ? centsToEuroInput(v.first_referrer_bonus_cents) : "0",
      categoryIds: product.category_ids ?? [],
    });
    setEditCustomerType(
      ["PRIVATE", "BUSINESS", "BOTH"].includes(product.customer_type) ? product.customer_type : "BUSINESS"
    );
    setEditCode(product.code);
    setEditError(null);
    setEditingProduct(product);
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editingProduct?.current_version) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const res = await fetch(`/api/proxy/products/versions/${editingProduct.current_version.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: editForm.name,
          description: editForm.description,
          image_url: editForm.imageUrl.trim() || null,
          base_price_cents: euroToCents(editForm.basePriceEuro),
          // Sent even when empty: an explicit null clears it on the server.
          monthly_price_cents: isRecurringProductType(editingProduct.product_type) && editForm.monthlyPriceEuro.trim()
            ? euroToCents(editForm.monthlyPriceEuro)
            : null,
          initial_fee_cents: euroToCents(editForm.initialFeeEuro),
          recurring_fee_cents: euroToCents(editForm.recurringFeeEuro),
          vat_percentage: editForm.vatPercentage.trim() ? parseFloat(editForm.vatPercentage) : null,
          contract_duration_months: editForm.contractDurationMonths.trim()
            ? parseInt(editForm.contractDurationMonths, 10)
            : null,
          commission_tokens: commissionTokensToCents(editForm.commissionTokens),
          credit_discount_percentage: editingProduct.category === "INTERNAL" ? 0 : (parseInt(editForm.creditDiscountPercentage, 10) || 0),
          cashback_enabled: editingProduct.category === "INTERNAL" ? false : editForm.cashbackEnabled,
          contract_cashback_percentage: editingProduct.category === "INTERNAL" ? (parseInt(editForm.contractCashbackPercentage, 10) || 0) : 0,
          first_referrer_bonus_enabled: editingProduct.category === "INTERNAL" && editForm.firstReferrerBonusEnabled,
          first_referrer_bonus_cents: editingProduct.category === "INTERNAL" ? euroToCents(editForm.firstReferrerBonusEuro) : 0,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));

      // Audience and code are Product fields, not ProductVersion ones --
      // second call, and only with what actually changed, so an unrelated
      // edit never writes to the product row.
      const productChanges: Record<string, string> = {};
      if (editCustomerType !== editingProduct.customer_type) productChanges.customer_type = editCustomerType;
      if (editCode.trim() && editCode.trim() !== editingProduct.code) productChanges.code = editCode.trim();
      if (Object.keys(productChanges).length > 0) {
        const audienceRes = await fetch(`/api/proxy/products/${editingProduct.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(productChanges),
        });
        if (!audienceRes.ok) throw new Error(await friendlyApiError(audienceRes));
      }

      // Stesso criterio della creazione: si tocca l'endpoint delle categorie
      // solo se le spunte sono cambiate davvero.
      if (!sameCategorySelection(editForm.categoryIds, editingProduct.category_ids ?? [])) {
        const shop = SHOP_KEY_BY_CATEGORY[editingProduct.category] ?? "internal";
        await saveProductCategories(shop, editingProduct.id, editForm.categoryIds);
        await queryClient.invalidateQueries({ queryKey: ["shop-categories", shop] });
      }

      setEditingProduct(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
    } catch (err: any) {
      setEditError(err.message || "Impossibile salvare le modifiche.");
    } finally {
      setEditLoading(false);
    }
  }

  async function handleDeleteProduct() {
    if (!deletingProduct) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/proxy/products/${deletingProduct.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile eliminare il prodotto."));
      setDeletingProduct(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
    } catch (err: any) {
      setDeleteError(err.message || "Impossibile eliminare il prodotto.");
    } finally {
      setDeleteLoading(false);
    }
  }

  const deleteConfirmModal = deletingProduct && (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
        <h3 className="text-lg font-bold text-white light:text-slate-900 mb-2">Elimina prodotto</h3>
        <p className="text-xs text-slate-400 light:text-slate-500 mb-4">
          Stai per eliminare definitivamente il prodotto{" "}
          <span className="font-semibold text-slate-300 light:text-slate-700">
            &quot;{deletingProduct.current_version?.name ?? deletingProduct.code}&quot;
          </span>{" "}
          e tutte le sue versioni. L&apos;operazione non può essere annullata. Se il prodotto ha contratti
          associati, l&apos;eliminazione verrà rifiutata: in quel caso puoi solo disattivarlo.
        </p>
        {deleteError && <p className="text-xs text-rose-400 mb-3">{deleteError}</p>}
        <div className="flex justify-end gap-3">
          <button
            onClick={() => { setDeletingProduct(null); setDeleteError(null); }}
            className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer"
          >
            Annulla
          </button>
          <button
            onClick={handleDeleteProduct}
            disabled={deleteLoading}
            className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
          >
            {deleteLoading ? "Eliminazione..." : "Elimina definitivamente"}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400 light:text-slate-500">
          Cataloghi luce, gas, dual fuel ed Energia Circolare venduti in marketplace.
        </p>
        <button
          onClick={() => {
            setCode("");
            setProductType("ENERGY_CONTRACT");
            setEnergyType("ELECTRICITY");
            setCustomerType("PRIVATE");
            setCategory("INTERNAL");
            setCreateForm(EMPTY_FORM);
            setCreateError(null);
            setIsDuplicating(false);
            setShowCreate(true);
          }}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer shrink-0"
        >
          + Nuovo Prodotto
        </button>
      </div>

      {loadError && <p className="text-sm text-rose-400">Impossibile caricare i prodotti.</p>}

      {/* Un bottone solo per le tre sezioni: sono tre shop distinti, ma una
          pagina sola, e un selettore dentro la finestra costa meno di tre
          card uguali. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ManageCategoriesButton shops={shopsForCategories} />
        {retiredCount > 0 && (
          <label className="flex items-center gap-2 text-xs text-slate-400 light:text-slate-500 cursor-pointer">
            <input
              type="checkbox"
              checked={showRetired}
              onChange={(e) => setShowRetired(e.target.checked)}
              className="w-4 h-4 rounded border-white/20 accent-orange-500"
            />
            Mostra ritirati ({retiredCount})
          </label>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {listedProducts === undefined ? (
          <p className="text-sm text-slate-500 col-span-full text-center py-8">Caricamento...</p>
        ) : listedProducts.length === 0 ? (
          <p className="text-sm text-slate-500 col-span-full text-center py-8">Nessun prodotto nel catalogo.</p>
        ) : (
          listedProducts.map((p) => (
            <div key={p.id} className="glass-card rounded-2xl overflow-hidden border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
              <div className="h-32 overflow-hidden relative">
                <ProductThumbnail
                  imageUrl={p.current_version?.image_url}
                  alt={p.current_version?.name ?? p.code}
                  iconClassName="w-10 h-10 text-orange-400/40"
                />
                <div className="absolute top-2 right-2 flex items-center gap-1.5">
                  <button
                    onClick={() => openDuplicate(p)}
                    className="p-1.5 rounded-lg bg-slate-950/70 hover:bg-slate-950/90 text-white transition cursor-pointer"
                    title="Duplica prodotto"
                    disabled={!p.current_version}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </button>
                  <button
                    onClick={() => openEdit(p)}
                    className="p-1.5 rounded-lg bg-slate-950/70 hover:bg-slate-950/90 text-white transition cursor-pointer"
                    title="Modifica prodotto"
                    disabled={!p.current_version}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </button>
                  <button
                    onClick={() => { setDeletingProduct(p); setDeleteError(null); }}
                    className="p-1.5 rounded-lg bg-slate-950/70 hover:bg-rose-600 text-white transition cursor-pointer"
                    title="Elimina prodotto"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
              <div className="p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 text-amber-400 border-amber-500/20">
                    {p.product_type === "ENERGY_CONTRACT"
                      ? (p.energy_type ? ENERGY_LABELS[p.energy_type] ?? p.energy_type : "Energia")
                      : PRODUCT_TYPE_LABELS[p.product_type] ?? p.product_type}
                  </span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                    p.status === "ACTIVE"
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                      : "bg-slate-500/10 light:bg-slate-200/50 text-slate-400 light:text-slate-500 border-slate-500/20 light:border-slate-300"
                  }`}>
                    {p.status === "RETIRED" ? "Ritirato" : p.status}
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-white light:text-slate-900 mb-0.5">
                  {p.current_version?.name ?? p.code}
                </h4>
                <p className="font-mono text-[10px] text-slate-500 mb-2">{p.code}</p>
                {p.current_version?.description && (
                  <p className="text-xs text-slate-400 light:text-slate-500 mb-3 line-clamp-2">
                    {p.current_version.description}
                  </p>
                )}
                <div className="flex items-center gap-1.5 mb-2 flex-wrap">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600">
                    {CATEGORY_LABELS[p.category] ?? p.category}
                  </span>
                  {p.category !== "INTERNAL" && p.current_version && p.current_version.credit_discount_percentage > 0 && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                      {p.current_version.credit_discount_percentage}% in JavCash
                    </span>
                  )}
                  {p.category !== "INTERNAL" && p.current_version?.cashback_enabled && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-orange-500/10 text-orange-400 border-orange-500/20">
                      Cashback attivo
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400 light:text-slate-500">
                    Target: {customerTypeLabel(p.customer_type)}
                  </span>
                  {p.current_version && (
                    <span className="text-right">
                      <span className="block text-sm font-bold text-orange-400">
                        {euro(p.current_version.base_price_cents)}
                      </span>
                      {p.current_version.monthly_price_cents != null && (
                        <span className="block text-[10px] text-slate-400">a rate {euro(p.current_version.monthly_price_cents)}/mese</span>
                      )}
                      {p.current_version.vat_percentage != null && (
                        <span className="block text-[10px] text-slate-500">+ IVA {p.current_version.vat_percentage}%</span>
                      )}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">
                {isDuplicating ? "Duplica Prodotto" : "Nuovo Prodotto"}
              </h3>
              <button onClick={() => { setShowCreate(false); setIsDuplicating(false); }}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {isDuplicating && (
              <p className="text-xs text-slate-400 light:text-slate-500 -mt-2 mb-4">
                Tutti i campi sono precompilati dal prodotto originale, incluso il gettone per grado. Cambia almeno il codice prima di salvare.
              </p>
            )}

            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice</label>
                <input required value={code} onChange={(e) => setCode(e.target.value)} placeholder="Es: LUCE-PMI-01"
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-orange-500" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Tipo Prodotto</label>
                  <select value={productType} onChange={(e) => setProductType(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                    {Object.entries(PRODUCT_TYPE_LABELS).map(([code2, label]) => (
                      <option key={code2} value={code2}>{label}</option>
                    ))}
                  </select>
                </div>
                {productType === "ENERGY_CONTRACT" && (
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Tipo Energia</label>
                    <select value={energyType} onChange={(e) => setEnergyType(e.target.value)}
                      className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                      {Object.entries(ENERGY_LABELS).map(([code2, label]) => (
                        <option key={code2} value={code2}>{label}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cliente Target</label>
                  <select value={customerType} onChange={(e) => setCustomerType(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                    {Object.entries(CUSTOMER_TYPE_LABELS).map(([code2, label]) => (
                      <option key={code2} value={code2}>{label}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Categoria</label>
                  <select value={category} onChange={(e) => setCategory(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                    {Object.entries(CATEGORY_LABELS).map(([code2, label]) => (
                      <option key={code2} value={code2}>{label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <ProductFormFields form={createForm} onChange={(patch) => setCreateForm((f) => ({ ...f, ...patch }))} ranks={ranks} category={category} productType={productType} />

              {createError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{createError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => { setShowCreate(false); setIsDuplicating(false); }}
                  className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={createLoading}
                  className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {createLoading ? "Creazione..." : isDuplicating ? "Crea Copia" : "Crea Prodotto"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingProduct && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">Modifica Prodotto</h3>
              <button onClick={() => setEditingProduct(null)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p className="font-mono text-[10px] text-slate-500 mb-4">{editingProduct.code}</p>

            {editingProduct.current_version && (
              <div className="mb-5 pb-5 border-b border-white/5 light:border-slate-200">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block mb-2">Carica foto</label>
                <PhotoUpload
                  currentUrl={editForm.imageUrl || null}
                  uploadPath={`products/versions/${editingProduct.current_version.id}/photo`}
                  onUploaded={(url) => {
                    setEditForm((f) => ({ ...f, imageUrl: url }));
                    queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
                  }}
                  alt={editingProduct.current_version.name}
                  size={72}
                />
              </div>
            )}

            <form onSubmit={handleEditSave} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice</label>
                <input
                  required
                  maxLength={64}
                  value={editCode}
                  onChange={(e) => setEditCode(e.target.value)}
                  placeholder="Es: LUCE-PRIVATI-12"
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-orange-500"
                />
                <p className="text-[10px] text-slate-500">
                  Codice interno del prodotto: il cliente non lo vede. Deve essere diverso da quello degli altri prodotti.
                </p>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">
                  Cliente Target
                </label>
                <select
                  value={editCustomerType}
                  onChange={(e) => setEditCustomerType(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
                >
                  {Object.entries(CUSTOMER_TYPE_LABELS).map(([code2, label]) => (
                    <option key={code2} value={code2}>{label}</option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-500">
                  Chi può attivare questo contratto. Un cliente vede in catalogo solo i contratti compatibili
                  con la propria tipologia &mdash; e il controllo è anche lato server, non solo grafico.
                </p>
              </div>

              <ProductFormFields form={editForm} onChange={(patch) => setEditForm((f) => ({ ...f, ...patch }))} ranks={ranks} category={editingProduct?.category ?? "INTERNAL"} productType={editingProduct?.product_type ?? "ENERGY_CONTRACT"} />

              {editError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{editError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setEditingProduct(null)}
                  className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={editLoading}
                  className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {editLoading ? "Salvataggio..." : "Salva Modifiche"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {deleteConfirmModal}
    </div>
  );
}
