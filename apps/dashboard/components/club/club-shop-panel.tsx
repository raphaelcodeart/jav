"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Pagination, usePaged } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

// Lo shop del club (apps/api/app/domains/club/shop_router.py): la segreteria
// carica i prodotti del suo club (t-shirt, judogi, materiale) e gestisce gli
// ordini fatti nel suo shop. Le famiglie lo trovano nello Shop accanto a
// quello di JudoArteVida, con l'etichetta del club. `familyOrders` è
// l'elenco (in sola lettura) degli ordini dello shop di JudoArteVida.

interface Variant { id: string; label: string; price_cents: number; inventory: number | null; active: boolean; in_stock: boolean }
interface Product { id: string; name: string; description: string; image_url: string | null; status: string; variants: Variant[] }
interface Order {
  id: string; number: string; order_code: string; customer_display_name: string; athlete_name: string | null;
  product_name: string; amount_cents: number; amount_due_cents: number; status: string; fulfillment_status: string;
  payment_method: string | null; payment_proof_uploaded_at: string | null; created_at: string; recipient_name: string | null;
  city: string | null; delivery_status: string | null;
}

const A = "/admin/shop";
const ORDER_TONE: Record<string, "warning" | "success" | "danger" | "neutral"> = {
  AWAITING_PAYMENT: "warning", PAID: "success", CANCELLED: "danger",
};

export function ClubShopPanel({ familyOrders }: { familyOrders: React.ReactNode }) {
  const { t } = useI18n();
  const [tab, setTab] = useState<"products" | "orders" | "jav">("products");
  return (
    <div className="space-y-5">
      <Tabs value={tab} onChange={(k) => setTab(k as typeof tab)} items={[
        { key: "products", label: `🏯 ${t("shopx.club.tabProducts")}` },
        { key: "orders", label: `📦 ${t("shopx.club.tabOrders")}` },
        { key: "jav", label: `🌍 ${t("shopx.club.tabJav")}` },
      ]} />
      {tab === "products" && <Products />}
      {tab === "orders" && <Orders />}
      {tab === "jav" && familyOrders}
    </div>
  );
}

function Products() {
  const { t, fmt } = useI18n();
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "shop", "products"], queryFn: () => clubGet<Product[]>(`${A}/products`) });
  const [editing, setEditing] = useState<Product | "new" | null>(null);
  const paged = usePaged(data ?? [], 12);
  if (isLoading) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-ink-600">
          {t("shopx.club.intro")}
        </p>
        <Button onClick={() => setEditing("new")}>＋ {t("shopx.club.newProduct")}</Button>
      </div>
      {(data ?? []).length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🛍️</span>} title={t("shopx.club.emptyTitle")} text={t("shopx.club.emptyText")} action={<Button onClick={() => setEditing("new")}>{t("shopx.club.addFirst")}</Button>} />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {paged.items.map((p) => (
            <li key={p.id} className="glass-card overflow-hidden rounded-3xl">
              <div className="h-40 bg-ink-50">
                {p.image_url
                  // eslint-disable-next-line @next/next/no-img-element -- foto caricata dal club
                  ? <img src={p.image_url} alt="" className="h-full w-full object-cover" />
                  : <div className="flex h-full items-center justify-center text-5xl">🛍️</div>}
              </div>
              <div className="space-y-2 p-4">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold text-ink-900">{p.name}</p>
                  <Badge tone={p.status === "ACTIVE" ? "success" : "neutral"} dot>{p.status === "ACTIVE" ? t("shopx.club.onSale") : t("shopx.club.hidden")}</Badge>
                </div>
                <p className="text-sm text-ink-600">{p.variants.map((v) => `${v.label} ${fmt.euro(v.price_cents)}`).join(" · ")}</p>
                <Button size="sm" variant="secondary" onClick={() => setEditing(p)}>✎ {t("shopx.club.edit")}</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <Pagination page={paged.page} pages={paged.pages} onChange={(p) => { paged.setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
      {editing && <ProductModal product={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ProductModal({ product, onClose }: { product: Product | null; onClose: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState(product?.name ?? "");
  const [description, setDescription] = useState(product?.description ?? "");
  const [image, setImage] = useState<string | null>(product?.image_url ?? null);
  const [status, setStatus] = useState(product?.status ?? "ACTIVE");
  const [variants, setVariants] = useState(() => (product?.variants ?? []).map((v) => ({ id: v.id, label: v.label, price: (v.price_cents / 100).toFixed(2), stock: v.inventory == null ? "" : String(v.inventory), active: v.active })));
  const [fresh, setFresh] = useState<{ label: string; price: string; stock: string }[]>(product ? [] : [{ label: t("shopx.club.singleVariant"), price: "", stock: "" }]);
  const [busy, setBusy] = useState(false);
  const cents = (v: string) => Math.round(Number(v.replace(",", ".")) * 100);

  async function upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    try {
      const { image_url } = await clubSend<{ image_url: string }>(`${A}/images`, "POST", form);
      setImage(image_url);
    } catch (e) {
      toast({ tone: "error", title: t("shopx.club.photoFailed"), text: (e as Error).message });
    }
  }

  async function save() {
    setBusy(true);
    try {
      const newOnes = fresh.filter((v) => v.label.trim() && cents(v.price) > 0)
        .map((v) => ({ label: v.label.trim(), price_cents: cents(v.price), inventory: v.stock === "" ? null : Number(v.stock) }));
      if (product) {
        await clubSend(`${A}/products/${product.id}`, "PATCH", { name, description, image_url: image, status });
        for (const v of variants) {
          await clubSend(`${A}/variants/${v.id}`, "PATCH", { label: v.label, price_cents: cents(v.price), inventory: v.stock === "" ? null : Number(v.stock), active: v.active });
        }
        for (const v of newOnes) await clubSend(`${A}/products/${product.id}/variants`, "POST", v);
      } else {
        await clubSend(`${A}/products`, "POST", { name, description, image_url: image, status, variants: newOnes });
      }
      await queryClient.invalidateQueries({ queryKey: ["club", "admin", "shop"] });
      toast({ tone: "success", title: t("shopx.club.saved") });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: t("shopx.club.notSaved"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} size="lg" title={product ? t("shopx.club.editProduct") : t("shopx.club.newProduct")}
      footer={<><Button variant="ghost" onClick={onClose}>{t("common.close")}</Button><Button onClick={save} loading={busy} disabled={!name.trim() || (!product && !fresh.some((v) => cents(v.price) > 0))}>{t("common.save")}</Button></>}>
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-[1fr_160px]">
          <Field label={t("shopx.club.name")}><Input value={name} maxLength={255} onChange={(e) => setName(e.target.value)} placeholder={t("shopx.club.namePlaceholder")} /></Field>
          <Field label={t("shopx.club.status")}>
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="ACTIVE">{t("shopx.club.onSale")}</option>
              <option value="INACTIVE">{t("shopx.club.hidden")}</option>
            </Select>
          </Field>
        </div>
        <Field label={t("shopx.club.description")}><Textarea rows={3} value={description} maxLength={8000} onChange={(e) => setDescription(e.target.value)} /></Field>
        <Field label={t("shopx.club.photo")} hint={t("shopx.club.photoHint")}>
          <div className="flex items-center gap-3">
            {image && (
              // eslint-disable-next-line @next/next/no-img-element -- anteprima
              <img src={image} alt="" className="h-16 w-16 rounded-xl object-cover ring-1 ring-ink-100" />
            )}
            <Input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); }} />
          </div>
        </Field>
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-500">{t("shopx.club.variantsTitle")}</p>
          <div className="space-y-2">
            {variants.map((v, i) => (
              <div key={v.id} className="grid grid-cols-[1fr_110px_90px_auto] items-center gap-2">
                <Input value={v.label} onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} aria-label={t("shopx.club.variant")} />
                <Input value={v.price} inputMode="decimal" onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, price: e.target.value } : x))} aria-label={t("shopx.club.priceEur")} />
                <Input value={v.stock} inputMode="numeric" placeholder="∞" onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, stock: e.target.value } : x))} aria-label={t("shopx.club.piecesLabel")} />
                <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={v.active} onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, active: e.target.checked } : x))} />{t("shopx.club.variantActive")}</label>
              </div>
            ))}
            {fresh.map((v, i) => (
              <div key={`new-${i}`} className="grid grid-cols-[1fr_110px_90px_auto] items-center gap-2">
                <Input value={v.label} placeholder={t("shopx.club.variantPlaceholder")} onChange={(e) => setFresh((vs) => vs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} aria-label={t("shopx.club.variant")} />
                <Input value={v.price} inputMode="decimal" placeholder="€" onChange={(e) => setFresh((vs) => vs.map((x, j) => j === i ? { ...x, price: e.target.value } : x))} aria-label={t("shopx.club.priceEur")} />
                <Input value={v.stock} inputMode="numeric" placeholder={`∞ ${t("shopx.club.pieces")}`} onChange={(e) => setFresh((vs) => vs.map((x, j) => j === i ? { ...x, stock: e.target.value } : x))} aria-label={t("shopx.club.piecesLabel")} />
                <span className="text-xs text-ink-400">{t("shopx.club.variantNew")}</span>
              </div>
            ))}
            <Button size="sm" variant="ghost" onClick={() => setFresh((vs) => [...vs, { label: "", price: "", stock: "" }])}>＋ {t("shopx.club.variant")}</Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function Orders() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "shop", "orders"], queryFn: () => clubGet<Order[]>(`${A}/orders`) });
  const [busy, setBusy] = useState<string | null>(null);
  const paged = usePaged(data ?? [], 20);

  async function act(o: Order, action: "confirm-payment" | "ship" | "delivered" | "cancel") {
    let body: unknown;
    if (action === "cancel") {
      const reason = window.prompt(t("shopx.club.cancelReason"));
      if (!reason) return;
      body = { reason };
    } else if (action === "ship") {
      body = { tracking_number: null, tracking_url: null, tracking_company: null };
    }
    setBusy(o.id);
    try {
      await clubSend(`${A}/orders/${o.id}/${action}`, "POST", body);
      await queryClient.invalidateQueries({ queryKey: ["club", "admin", "shop", "orders"] });
      toast({ tone: "success", title: t("shopx.club.orderUpdated") });
    } catch (e) {
      toast({ tone: "error", title: t("common.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function proof(o: Order) {
    const win = window.open("", "_blank");
    try {
      const { url } = await clubGet<{ url: string }>(`${A}/orders/${o.id}/payment-proof-url`);
      if (win) win.location.replace(url); else window.location.assign(url);
    } catch (e) {
      win?.close();
      toast({ tone: "error", title: t("shopx.club.proofUnavailable"), text: (e as Error).message });
    }
  }

  if (isLoading) return <Skeleton className="h-64" />;
  if ((data ?? []).length === 0) return <EmptyState icon={<span className="text-3xl">📦</span>} title={t("shopx.club.noOrders")} />;
  return (
    <div className="space-y-4">
      <ul className="space-y-3">
        {paged.items.map((o) => (
          <li key={o.id} className="glass-card flex flex-wrap items-center gap-4 rounded-2xl p-4">
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-ink-900">{o.product_name}</p>
              <p className="text-xs text-ink-500">
                {o.order_code} · {fmt.shortDate(o.created_at)} · {o.customer_display_name}{o.athlete_name ? ` · ${t("shopx.forAthlete", { name: o.athlete_name })}` : ""}
              </p>
            </div>
            <span className="font-display text-lg text-ink-900">{fmt.euro(o.amount_due_cents ?? o.amount_cents)}</span>
            <Badge tone={ORDER_TONE[o.status] ?? "neutral"} dot>{t.dyn(`shopx.club.orderStatus.${o.status}`, o.status)}</Badge>
            {o.status === "PAID" && <Badge tone="neutral">{o.fulfillment_status === "DELIVERED" ? t("shopx.club.delivered") : o.fulfillment_status === "SHIPPED" ? t("shopx.club.shipped") : t("shopx.club.toPrepare")}</Badge>}
            <div className="flex flex-wrap gap-2">
              {o.payment_proof_uploaded_at && <Button size="sm" variant="ghost" onClick={() => proof(o)}>🧾 {t("shopx.club.proof")}</Button>}
              {o.status === "AWAITING_PAYMENT" && <Button size="sm" loading={busy === o.id} onClick={() => act(o, "confirm-payment")}>✓ {t("shopx.club.paymentReceived")}</Button>}
              {o.status === "PAID" && o.fulfillment_status !== "SHIPPED" && o.fulfillment_status !== "DELIVERED" && <Button size="sm" variant="secondary" loading={busy === o.id} onClick={() => act(o, "ship")}>🚚 {t("shopx.club.shipped")}</Button>}
              {o.status === "PAID" && o.fulfillment_status !== "DELIVERED" && <Button size="sm" variant="secondary" loading={busy === o.id} onClick={() => act(o, "delivered")}>📦 {t("shopx.club.delivered")}</Button>}
              {o.status === "AWAITING_PAYMENT" && <Button size="sm" variant="ghost" className="text-rose-600" loading={busy === o.id} onClick={() => act(o, "cancel")}>{t("common.cancel")}</Button>}
            </div>
          </li>
        ))}
      </ul>
      <Pagination page={paged.page} pages={paged.pages} onChange={(p) => { paged.setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
    </div>
  );
}
