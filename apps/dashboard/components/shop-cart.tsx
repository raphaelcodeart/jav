"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { useMarketplaceConfig } from "@/components/marketplace-rules-card";
import type { CartRead, CartSectionRead, CartShop } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

/** Il carrello dello Shop (Session 75).
 *
 *  Un carrello solo per il cliente, diviso in sezioni per negozio: i quattro
 *  negozi hanno regole che si escludono a vicenda -- indirizzo e spedizione
 *  nei Marketplace, «riscuoti subito cashback» nel catalogo interno e mai nei
 *  Marketplace -- quindi righe di negozi diversi non possono finire nello
 *  stesso ordine. Il totale in cima è la somma; si paga una sezione per volta.
 *
 *  Qui dentro non si calcola nessun prezzo. Ogni operazione restituisce il
 *  carrello ricalcolato dal server, che è anche l'unico a sapere i listini:
 *  la finestra disegna quello che riceve. */

const CART_QUERY_KEY = ["carts", "mine"];

async function fetchCart(): Promise<CartRead> {
  const res = await fetch("/api/proxy/carts/mine");
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

export function useCart(enabled = true) {
  return useQuery({ queryKey: CART_QUERY_KEY, queryFn: fetchCart, enabled });
}

/** Le operazioni sul carrello. Ognuna risponde con il carrello intero, così
 *  la cache si aggiorna senza una seconda chiamata e senza mai ricostruire
 *  lato browser un totale che è del server. */
export function useCartActions() {
  const queryClient = useQueryClient();
  // Ogni rotta del carrello risponde con il carrello intero: si scrive in
  // cache quello, invece di rileggerlo con una seconda chiamata o di
  // ricostruire lato browser un totale che appartiene al server.
  const onSuccess = (cart: CartRead) => queryClient.setQueryData(CART_QUERY_KEY, cart);

  async function send(path: string, init: RequestInit): Promise<CartRead> {
    const res = await fetch(path, init);
    if (!res.ok) throw new Error(await friendlyApiError(res));
    return res.json();
  }
  const json = (body: unknown, method: string): RequestInit => ({
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const add = useMutation({
    mutationFn: ({ shop, variantId, quantity }: { shop: CartShop; variantId: string; quantity: number }) =>
      send(`/api/proxy/carts/mine/${shop}/items`, json({ variant_id: variantId, quantity }, "POST")),
    onSuccess,
  });
  const setQuantity = useMutation({
    mutationFn: ({ shop, itemId, quantity }: { shop: CartShop; itemId: string; quantity: number }) =>
      send(`/api/proxy/carts/mine/${shop}/items/${itemId}`, json({ quantity }, "PATCH")),
    onSuccess,
  });
  const remove = useMutation({
    mutationFn: ({ shop, itemId }: { shop: CartShop; itemId: string }) =>
      send(`/api/proxy/carts/mine/${shop}/items/${itemId}`, { method: "DELETE" }),
    onSuccess,
  });
  const clear = useMutation({
    mutationFn: ({ shop }: { shop: CartShop }) => send(`/api/proxy/carts/mine/${shop}`, { method: "DELETE" }),
    onSuccess,
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: CART_QUERY_KEY });
  return { add, setQuantity, remove, clear, invalidate };
}

/** L'icona in alto, con quanti articoli ci sono dentro. Non si nasconde da
 *  sola quando il carrello è vuoto: un carrello che sparisce è un carrello
 *  che il cliente non trova più quando gli serve. */
export function ShopCartButton({ onOpen }: { onOpen: () => void }) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const { data: cart } = useCart();
  const count = cart?.item_count ?? 0;
  return (
    <button
      onClick={onOpen}
      aria-label={count > 0 ? t("shopx.cart.ariaCount", { n: count }) : t("shopx.cart.ariaEmpty")}
      className="relative flex items-center gap-2 px-2.5 py-2 rounded-xl border border-slate-200 bg-slate-900/5 hover:bg-slate-900/10 transition cursor-pointer"
    >
      <svg className="w-5 h-5 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M3 3h2l.4 2M7 13h10l3-8H5.4M7 13L5.4 5M7 13l-2 5h13" />
        <circle cx="9" cy="20" r="1.5" />
        <circle cx="17" cy="20" r="1.5" />
      </svg>
      {count > 0 && (
        <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-brand-600 text-white text-[10px] font-bold flex items-center justify-center">
          {count > 99 ? "99+" : count}
        </span>
      )}
      {/* Il totale sparisce sotto i 640px: nella barra del telefono accanto a
          campanella, tema e menu non ci sta, e l'icona con il contatore basta
          a dire che c'e' qualcosa dentro. */}
      {cart && cart.total_cents > 0 && (
        <span className="hidden sm:inline text-xs font-semibold text-slate-900 tabular-nums">
          {euro(cart.total_cents)}
        </span>
      )}
    </button>
  );
}

function QuantityStepper({
  value, disabled, onChange,
}: { value: number; disabled: boolean; onChange: (next: number) => void }) {
  const { t } = useI18n();
  return (
    <div className="flex items-center rounded-lg border border-slate-200 overflow-hidden">
      <button
        onClick={() => onChange(value - 1)}
        disabled={disabled}
        aria-label={t("shopx.cart.decrease")}
        className="px-2 py-1 text-sm text-slate-600 hover:bg-slate-900/10 disabled:opacity-40 cursor-pointer"
      >
        −
      </button>
      <span className="px-2.5 text-xs font-semibold text-slate-900 tabular-nums">{value}</span>
      <button
        onClick={() => onChange(value + 1)}
        disabled={disabled}
        aria-label={t("shopx.cart.increase")}
        className="px-2 py-1 text-sm text-slate-600 hover:bg-slate-900/10 disabled:opacity-40 cursor-pointer"
      >
        +
      </button>
    </div>
  );
}

function CartSection({
  section, label, onCheckout,
}: { section: CartSectionRead; label: string; onCheckout: (shop: CartShop) => void }) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const { setQuantity, remove, clear } = useCartActions();
  const busy = setQuantity.isPending || remove.isPending || clear.isPending;

  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 bg-slate-900/5">
        <p className="text-xs font-bold text-slate-900">{label}</p>
        <button
          onClick={() => clear.mutate({ shop: section.shop })}
          disabled={busy}
          className="text-[11px] text-slate-500 hover:text-rose-400 disabled:opacity-40 cursor-pointer"
        >
          {t("shopx.cart.empty")}
        </button>
      </div>

      <div className="divide-y divide-slate-200">
        {section.items.map((line) => (
          <div key={line.cart_item_id} className="flex gap-3 p-3">
            <ProductThumbnail imageUrl={line.image_url} alt={line.product_name} className="w-14 h-14 rounded-lg shrink-0" />
            <div className="flex-1 min-w-0 space-y-1">
              <p className={`text-xs font-semibold truncate ${line.available ? " text-slate-900" : "text-slate-500 line-through"}`}>
                {line.product_name}
              </p>
              {line.variant_label && <p className="text-[11px] text-slate-500 truncate">{line.variant_label}</p>}
              {!line.available && (
                <p className="text-[11px] text-rose-400">{line.unavailable_reason ?? t("shopx.cart.unavailable")}</p>
              )}
              <div className="flex items-center gap-2 pt-0.5">
                <QuantityStepper
                  value={line.quantity}
                  disabled={busy || !line.available}
                  onChange={(next) =>
                    setQuantity.mutate({ shop: section.shop, itemId: line.cart_item_id, quantity: next })
                  }
                />
                <button
                  onClick={() => remove.mutate({ shop: section.shop, itemId: line.cart_item_id })}
                  disabled={busy}
                  className="text-[11px] text-slate-500 hover:text-rose-400 disabled:opacity-40 cursor-pointer"
                >
                  {t("shopx.cart.remove")}
                </button>
              </div>
            </div>
            <p className="text-xs font-bold text-slate-900 tabular-nums shrink-0">
              {line.available ? euro(line.line_total_cents) : "—"}
            </p>
          </div>
        ))}
      </div>

      <div className="p-3 space-y-1.5 bg-gradient-to-br from-brand-600/10 to-brand-400/5 border-t border-brand-500/20">
        <div className="flex justify-between text-slate-500">
          <span>{t("shopx.cart.items")}</span>
          <span className="tabular-nums">{euro(section.items_cents ?? 0)}</span>
        </div>
        <div className="flex justify-between text-slate-500">
          <span>{t("shopx.checkout.shipping")}</span>
          <span className="tabular-nums">
            {section.free_shipping ? t("shopx.checkout.free") : section.shipping_included || !section.shipping_cents ? t("shopx.checkout.included") : euro(section.shipping_cents)}
          </span>
        </div>
        {(section.free_shipping_missing_cents ?? 0) > 0 && (
          <p className="text-[11px] text-sky-400">
            {t("shopx.cart.freeShippingMissing", { amount: euro(section.free_shipping_missing_cents ?? 0) })}
          </p>
        )}
        <div className="flex justify-between items-center pt-1 border-t border-slate-300">
          <span className="text-xs font-bold text-slate-900">{t("shopx.cart.total")}</span>
          <span className="text-base font-extrabold text-brand-600 tabular-nums">{euro(section.amount_cents ?? 0)}</span>
        </div>
        {section.purchasable ? (
          <button
            onClick={() => onCheckout(section.shop)}
            className="w-full mt-1 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer"
          >
            {t("shopx.cart.goCheckout")}
          </button>
        ) : (
          <p className="mt-1 text-[11px] text-rose-400">
            {section.items.some((line) => !line.available)
              ? t("shopx.cart.removeUnavailable")
              : section.problems[0] ?? t("shopx.cart.notPayable")}
          </p>
        )}
      </div>
    </div>
  );
}

/** Il pannello del carrello. Si apre da destra e resta sopra lo Shop: il
 *  cliente non perde la griglia da cui stava scegliendo. */
export function ShopCartPanel({
  open, onClose, onCheckout,
}: { open: boolean; onClose: () => void; onCheckout: (shop: CartShop) => void }) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const { data: cart, isLoading, error } = useCart(open);
  const { data: config } = useMarketplaceConfig();
  const labels: Record<CartShop, string> = {
    jav_market: config?.labels?.jav_market ?? t("shopx.cart.labelJavMarket"),
    catalog: config?.sections?.partner?.label ?? t("shopx.cart.labelPartner"),
  };
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
      <div className="relative w-full max-w-md h-full overflow-y-auto bg-white border-l border-slate-200 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900">{t("shopx.cart.title")}</h2>
          <button onClick={onClose} aria-label={t("common.close")} className="text-slate-500 hover:text-slate-900 cursor-pointer">
            ✕
          </button>
        </div>

        {isLoading && <p className="text-xs text-slate-500">{t("shopx.loading")}</p>}
        {error && <p className="text-xs text-rose-400">{(error as Error).message}</p>}

        {cart && cart.sections.length === 0 && (
          <div className="py-16 text-center space-y-2">
            <p className="text-sm text-slate-500">{t("shopx.cart.isEmpty")}</p>
            <p className="text-xs text-slate-500">{t("shopx.cart.isEmptyHint")}</p>
          </div>
        )}

        {cart && cart.sections.length > 0 && (
          <>
            {/* Più sezioni vuol dire più ordini e più spedizioni: meglio
                dirlo qui che farlo scoprire al secondo pagamento. */}
            {cart.sections.length > 1 && (
              <p className="text-[11px] text-slate-500 leading-relaxed">
                {t("shopx.cart.multiShop")}
              </p>
            )}
            <div className="space-y-3">
              {cart.sections.map((section) => (
                <CartSection
                  key={section.cart_id}
                  section={section}
                  label={labels[section.shop]}
                  onCheckout={onCheckout}
                />
              ))}
            </div>
            <div className="flex justify-between items-center pt-2 border-t border-slate-200">
              <span className="text-xs text-slate-500">{t("shopx.cart.cartTotal")}</span>
              <span className="text-lg font-extrabold text-slate-900 tabular-nums">
                {euro(cart.total_cents)}
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
