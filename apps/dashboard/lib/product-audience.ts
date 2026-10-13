/** Chi può comprare cosa, e quanto costa davvero.
 *
 * Mirrors `apps/api/app/domains/catalog/pricing.py`. The server is the
 * authority for both rules -- it filters nothing here that it does not also
 * reject there -- but the catalog has to know the same answer to avoid
 * showing a customer a contract they would then be refused.
 *
 * Keep the two in sync. If they ever disagree, the server wins.
 */

const PRIVATE = "PRIVATE";
const BUSINESS = "BUSINESS";
const BOTH = "BOTH";

/** `products.customer_type` used to hold PMI / ENERGY_INTENSIVE /
    SOLE_PROPRIETOR / CONDOMINIUM -- a vocabulary that never lined up with
    `customers.kind`, so nothing could compare the two. Old values collapse
    onto BUSINESS; anything unrecognized fails OPEN (visible to everyone),
    because a display filter quietly hiding a product from the whole catalog
    is far worse than showing one product too many. */
export function normalizeProductCustomerType(value: string | null | undefined): string {
  if (!value) return BOTH;
  const upper = value.trim().toUpperCase();
  if (upper === PRIVATE || upper === BUSINESS || upper === BOTH) return upper;
  if (["SOLE_PROPRIETOR", "PMI", "CONDOMINIUM", "ENERGY_INTENSIVE"].includes(upper)) return BUSINESS;
  return BOTH;
}

/** Deliberately NOT the same grouping as the one that decides whether a
    customer has a first/last name or a company name (where SOLE_PROPRIETOR
    counts as "private"): a ditta individuale has a person's name AND a
    P.IVA. Two different questions. */
export function isBusinessCustomer(customerKind: string | null | undefined): boolean {
  return ["SOLE_PROPRIETOR", "COMPANY", "CONDOMINIUM"].includes((customerKind ?? "").trim().toUpperCase());
}

export function productAllowsCustomerKind(
  productCustomerType: string | null | undefined,
  customerKind: string | null | undefined
): boolean {
  const normalized = normalizeProductCustomerType(productCustomerType);
  if (normalized === BOTH) return true;
  // Unknown customer kind (e.g. the catalog rendered before the customer
  // record has loaded) must not hide anything -- same fail-open rule.
  if (!customerKind) return true;
  if (normalized === BUSINESS) return isBusinessCustomer(customerKind);
  return !isBusinessCustomer(customerKind);
}

export type PriceBreakdown = {
  netCents: number;
  /** Percentage points (22), not a fraction. 0 for a private customer. */
  vatRate: number;
  vatCents: number;
  grossCents: number;
};

/** The business rule, stated by the business: a contract for a private
    individual carries no VAT; a contract for a business is priced net + VAT.
    The customer's status decides WHETHER VAT applies, the product only
    decides WHICH rate applies when it does.
 *
 * `customerKind` null means "we don't know who is looking yet" -- e.g. the
 * shop grid, where nobody is buying a contract. There the product's own rate
 * is shown, which is what the catalog always did.
 */
export function computePrice(
  netCents: number,
  productVatPercentage: number | null | undefined,
  customerKind: string | null | undefined,
  { assumeBusinessWhenUnknown = true }: { assumeBusinessWhenUnknown?: boolean } = {}
): PriceBreakdown {
  const rateApplies = customerKind == null ? assumeBusinessWhenUnknown : isBusinessCustomer(customerKind);
  const rate = rateApplies && productVatPercentage ? productVatPercentage : 0;
  // Round half-up on the cent, matching catalog/pricing.py::_vat_cents.
  const vatCents = rate > 0 && netCents > 0 ? Math.round((netCents * rate) / 100) : 0;
  return { netCents, vatRate: rate, vatCents, grossCents: netCents + vatCents };
}

/** Session 84: a contract has two prices, both computed server-side before
    VAT -- in one go (`contract_net_amount_cents`, the listed price) and in
    rate (`contract_instalments_net_amount_cents`, monthly price x months;
    null = the rate split the one-go price). 3 and 12 rate split the same
    total, like contracts/payment_plans.py::plan_gross_cents. Display only:
    what is charged comes from the prices frozen on the contract. */
export function contractPrices(
  v: {
    contract_net_amount_cents: number;
    contract_instalments_net_amount_cents?: number | null;
    vat_percentage: number | null;
  },
  customerKind: string | null | undefined,
  options: { assumeBusinessWhenUnknown?: boolean } = {}
): { oneGo: PriceBreakdown; instalments: PriceBreakdown; hasOwnInstalmentPrice: boolean; monthlyGrossCents: number } {
  const oneGo = computePrice(v.contract_net_amount_cents, v.vat_percentage, customerKind, options);
  const hasOwnInstalmentPrice = v.contract_instalments_net_amount_cents != null;
  const instalments = hasOwnInstalmentPrice
    ? computePrice(v.contract_instalments_net_amount_cents!, v.vat_percentage, customerKind, options)
    : oneGo;
  // Half-up on the cent, the same rounding as payment_plans.breakdown_for.
  return { oneGo, instalments, hasOwnInstalmentPrice, monthlyGrossCents: Math.round(instalments.grossCents / 12) };
}

/** Mirrors catalog/pricing.py::RECURRING_PRODUCT_TYPES. Only these are sold
    as a canone per period; a PHYSICAL/DIGITAL product is a one-off price,
    whatever billing period its version happens to carry (the admin form
    defaults every version to MONTHLY). */
export function isRecurringProductType(productType: string | null | undefined): boolean {
  return ["ENERGY_CONTRACT", "SUBSCRIPTION"].includes((productType ?? "").toUpperCase());
}

export function formatEuroCents(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

// --- Marketplace: l'IVA sta DENTRO il prezzo (Session 74) -------------------
//
// Un contratto si quota al netto e l'IVA gli si somma sopra (computePrice,
// qui sopra). Nei Marketplace è l'esatto contrario: il prezzo esposto è il
// prezzo finale -- in Italia a un consumatore si mostra solo quello -- e
// l'IVA è già compresa. Quindi non si aggiunge niente: si scorpora.
//
// Mirrors the server, which freezes `vat_amount_cents` on the order: the
// taxable base is what is really charged for the goods, i.e. the amount
// minus the bank-transfer discount (a discount lowers the price, so it
// lowers the VAT). JavCash does NOT lower it: spending it is a way of
// paying, not a cheaper price.

/** L'IVA contenuta in un importo lordo, mezzo centesimo per eccesso.
 *
 *  `taxableGrossCents` è l'imponibile lordo: importo - sconto bonifico.
 *  Serve solo all'anteprima delle finestre di acquisto, quando l'ordine non
 *  esiste ancora; appena esiste si legge `vat_amount_cents` dall'ordine,
 *  che è congelato e ha l'ultima parola. */
export function includedVatCents(taxableGrossCents: number, vatPercentage: number | null | undefined): number {
  const rate = vatPercentage ?? 0;
  if (taxableGrossCents <= 0 || rate <= 0) return 0;
  // lordo × aliquota / (100 + aliquota), mezzo centesimo per eccesso.
  // Stessa aritmetica intera di rules.py::vat_included_cents -- floor((2n +
  // d) / 2d) arrotonda n/d per eccesso senza mai passare da un decimale
  // binario: l'anteprima e l'ordine devono dare lo stesso centesimo.
  const denominator = 100 + rate;
  return Math.floor((2 * taxableGrossCents * rate + denominator) / (2 * denominator));
}

/** "IVA 22%": la riga dell'IVA nel riepilogo, uguale in ogni finestra e
 *  elenco. Dalla Session 76 e' asciutta, perche' sta nell'elenco insieme
 *  alle altre voci; che il prezzo sia gia' comprensivo di IVA resta scritto
 *  accanto al prezzo stesso, dove serve al cliente per sapere che non ci
 *  saranno sorprese al checkout (Codice del Consumo artt. 14-15). */
/** L'IVA da **aggiungere** a un imponibile, come rules.vat_added_cents:
 *  net x pct / 100, mezzo centesimo per eccesso. Anteprima soltanto -- sul
 *  preventivo il server manda la sua, e sull'ordine e' congelata. */
export function addedVatCents(netCents: number, vatPercentage: number | null | undefined): number {
  const rate = vatPercentage ?? 0;
  if (netCents <= 0 || rate <= 0) return 0;
  return Math.floor((2 * netCents * rate + 100) / 200);
}

export function vatLineLabel(vatPercentage: number): string {
  // "già compresa nei prezzi" e non "di cui IVA": dalla Session 76 la riga
  // sta nell'elenco sopra il totale, dove le altre voci si sommano, e va
  // detto che questa no. Serve anche per il caso che "di cui" renderebbe
  // incomprensibile: pagando gran parte dell'ordine in JavCash, l'IVA
  // contenuta nei prezzi può superare l'importo ancora da pagare.
  // Solo "IVA 22%": nell'elenco del preventivo la riga sta fra le altre voci
  // e una spiegazione lunga la rendeva più pesante da leggere, non più
  // chiara. Che l'IVA sia dentro i prezzi e non aggiunta resta scritto in
  // marketplaces/rules.py e nel riepilogo dell'ordine.
  return `IVA ${vatPercentage.toLocaleString("it-IT", { maximumFractionDigits: 2 })}%`;
}
