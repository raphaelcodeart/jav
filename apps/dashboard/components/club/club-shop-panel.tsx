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
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// Lo shop del club (apps/api/app/domains/club/shop_router.py): la segreteria
// carica i prodotti del suo club (t-shirt, judogi, materiale) e gestisce gli
// ordini fatti nel suo shop. Le famiglie lo trovano nello Shop accanto a
// quello di JudoArteVida, con l'etichetta del club. `familyOrders` è
// l'elenco (in sola lettura) degli ordini dello shop di JudoArteVida.
// I prodotti del club si comprano dalla Loja (club/loja.py), un ordine con
// la sua quota per ogni articolo: qui si dice per chi sono (sesso, alta
// competizione, kit del club, nome stampato) e fino a che altezza va bene
// ogni taglia, che è da dove la Loja suggerisce quella giusta.

type Audience = "ALL" | "F" | "M";
interface Variant { id: string; label: string; price_cents: number; inventory: number | null; active: boolean; in_stock: boolean; max_height_cm: number | null }
interface Product {
  id: string; name: string; description: string; image_url: string | null; status: string; variants: Variant[];
  audience_sex: Audience; high_competition_only: boolean; club_kit: boolean; needs_name: boolean;
}
interface Order {
  id: string; number: string; order_code: string; customer_display_name: string; athlete_name: string | null;
  product_name: string; amount_cents: number; amount_due_cents: number; status: string; fulfillment_status: string;
  payment_method: string | null; payment_proof_uploaded_at: string | null; created_at: string; recipient_name: string | null;
  city: string | null; delivery_status: string | null;
}

const A = "/admin/shop";
const AUDIENCES: Audience[] = ["ALL", "F", "M"];
/** «150» → 150; vuoto o fuori misura → null (nessuna taglia suggerita). */
const heightCm = (v: string) => { const n = Number(v); return v.trim() && Number.isInteger(n) && n >= 50 && n <= 230 ? n : null; };

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
                <ProductBadges product={p} />
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

/** Per chi è un prodotto, in poche etichette: «Para todos» e senza regole non ne mostra nessuna. */
function ProductBadges({ product: p }: { product: Product }) {
  const { t } = useI18n();
  if (p.audience_sex === "ALL" && !p.high_competition_only && !p.club_kit && !p.needs_name) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {p.audience_sex !== "ALL" && <Badge tone="info">{t(p.audience_sex === "F" ? "lojaStaff.audience.F" : "lojaStaff.audience.M")}</Badge>}
      {p.high_competition_only && <Badge tone="accent">🏅 {t("lojaStaff.badge.highCompetition")}</Badge>}
      {p.club_kit && <Badge tone="brand">{t("lojaStaff.badge.kit")}</Badge>}
      {p.needs_name && <Badge tone="neutral">✍️ {t("lojaStaff.badge.name")}</Badge>}
    </div>
  );
}

/** Un interruttore con titolo e spiegazione, come quello di «Piani e prezzi». */
function Switch({ checked, onChange, title, hint }: { checked: boolean; onChange: (v: boolean) => void; title: string; hint: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
      className="flex w-full cursor-pointer items-center justify-between gap-3 rounded-2xl bg-ink-50 px-4 py-3 text-left text-sm font-semibold text-ink-800 ring-1 ring-ink-200">
      <span>{title}<span className="block text-xs font-normal text-ink-500">{hint}</span></span>
      <span aria-hidden="true" className={cn("relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors motion-reduce:transition-none", checked ? "bg-brand-500" : "bg-ink-300")}>
        <span className={cn("absolute h-5 w-5 rounded-full bg-white shadow transition-all motion-reduce:transition-none", checked ? "right-0.5" : "left-0.5")} />
      </span>
    </button>
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
  const [audience, setAudience] = useState<Audience>(product?.audience_sex ?? "ALL");
  const [highOnly, setHighOnly] = useState(product?.high_competition_only ?? false);
  const [kit, setKit] = useState(product?.club_kit ?? false);
  const [needsName, setNeedsName] = useState(product?.needs_name ?? false);
  const [variants, setVariants] = useState(() => (product?.variants ?? []).map((v) => ({ id: v.id, label: v.label, price: (v.price_cents / 100).toFixed(2), stock: v.inventory == null ? "" : String(v.inventory), height: v.max_height_cm == null ? "" : String(v.max_height_cm), active: v.active })));
  const [fresh, setFresh] = useState<{ label: string; price: string; stock: string; height: string }[]>(product ? [] : [{ label: t("shopx.club.singleVariant"), price: "", stock: "", height: "" }]);
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
        .map((v) => ({ label: v.label.trim(), price_cents: cents(v.price), inventory: v.stock === "" ? null : Number(v.stock), max_height_cm: heightCm(v.height) }));
      const audienceBody = { audience_sex: audience, high_competition_only: highOnly, club_kit: kit, needs_name: needsName };
      if (product) {
        await clubSend(`${A}/products/${product.id}`, "PATCH", { name, description, image_url: image, status, ...audienceBody });
        for (const v of variants) {
          // max_height_cm sempre presente: null toglie l'altezza.
          await clubSend(`${A}/variants/${v.id}`, "PATCH", { label: v.label, price_cents: cents(v.price), inventory: v.stock === "" ? null : Number(v.stock), max_height_cm: heightCm(v.height), active: v.active });
        }
        for (const v of newOnes) await clubSend(`${A}/products/${product.id}/variants`, "POST", v);
      } else {
        await clubSend(`${A}/products`, "POST", { name, description, image_url: image, status, ...audienceBody, variants: newOnes });
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
        <section className="space-y-3 rounded-2xl p-4 ring-1 ring-ink-100">
          <p className="text-xs font-bold uppercase tracking-wide text-ink-500">{t("lojaStaff.product.forWhom")}</p>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t("lojaStaff.product.forWhom")}>
            {AUDIENCES.map((a) => (
              <button key={a} type="button" role="radio" aria-checked={audience === a} onClick={() => setAudience(a)}
                className={cn("min-h-11 cursor-pointer rounded-2xl px-4 text-sm font-bold ring-2 transition-colors motion-reduce:transition-none",
                  audience === a ? "bg-brand-500 text-white ring-brand-500" : "bg-white text-ink-900 ring-ink-100 hover:ring-ink-200")}>
                {t(`lojaStaff.audience.${a}` as "lojaStaff.audience.ALL")}
              </button>
            ))}
          </div>
          <Switch checked={highOnly} onChange={setHighOnly} title={t("lojaStaff.product.highOnly")} hint={t("lojaStaff.product.highOnlyHint")} />
          <Switch checked={kit} onChange={setKit} title={t("lojaStaff.product.kit")} hint={t("lojaStaff.product.kitHint")} />
          <Switch checked={needsName} onChange={setNeedsName} title={t("lojaStaff.product.needsName")} hint={t("lojaStaff.product.needsNameHint")} />
          {/* Quem vê este produto: lo stesso filtro della Loja (loja.py::product_visible), a parole */}
          <div className="rounded-2xl bg-ink-900 p-4 text-white">
            <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-accent-500">{t("lojaStaff.product.reachTitle")}</p>
            <p className="mt-1 text-sm leading-relaxed text-ink-200">
              {t(`lojaStaff.product.reach.${audience}` as "lojaStaff.product.reach.ALL")}{" "}
              {highOnly ? t("lojaStaff.product.reachHigh") : t("lojaStaff.product.reachAll")}
            </p>
          </div>
        </section>
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-500">{t("shopx.club.variantsTitle")}</p>
          <div className="space-y-2">
            <div className="hidden grid-cols-[1fr_100px_80px_96px_auto] gap-2 px-1 text-[11px] font-semibold text-ink-500 sm:grid" aria-hidden="true">
              <span>{t("shopx.club.variant")}</span><span>{t("shopx.club.priceEur")}</span><span>{t("shopx.club.piecesLabel")}</span><span>{t("lojaStaff.product.heightCol")}</span><span />
            </div>
            {variants.map((v, i) => (
              <div key={v.id} className="grid grid-cols-2 items-center gap-2 sm:grid-cols-[1fr_100px_80px_96px_auto]">
                <Input className="col-span-2 sm:col-span-1" value={v.label} onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} aria-label={t("shopx.club.variant")} />
                <Input value={v.price} inputMode="decimal" onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, price: e.target.value } : x))} aria-label={t("shopx.club.priceEur")} />
                <Input value={v.stock} inputMode="numeric" placeholder="∞" onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, stock: e.target.value } : x))} aria-label={t("shopx.club.piecesLabel")} />
                <Input value={v.height} inputMode="numeric" maxLength={3} placeholder={t("lojaStaff.product.heightPlaceholder")} onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, height: e.target.value.replace(/\D/g, "") } : x))} aria-label={t("lojaStaff.product.heightLabel")} />
                <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={v.active} onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, active: e.target.checked } : x))} />{t("shopx.club.variantActive")}</label>
              </div>
            ))}
            {fresh.map((v, i) => (
              <div key={`new-${i}`} className="grid grid-cols-2 items-center gap-2 sm:grid-cols-[1fr_100px_80px_96px_auto]">
                <Input className="col-span-2 sm:col-span-1" value={v.label} placeholder={t("shopx.club.variantPlaceholder")} onChange={(e) => setFresh((vs) => vs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} aria-label={t("shopx.club.variant")} />
                <Input value={v.price} inputMode="decimal" placeholder="€" onChange={(e) => setFresh((vs) => vs.map((x, j) => j === i ? { ...x, price: e.target.value } : x))} aria-label={t("shopx.club.priceEur")} />
                <Input value={v.stock} inputMode="numeric" placeholder={`∞ ${t("shopx.club.pieces")}`} onChange={(e) => setFresh((vs) => vs.map((x, j) => j === i ? { ...x, stock: e.target.value } : x))} aria-label={t("shopx.club.piecesLabel")} />
                <Input value={v.height} inputMode="numeric" maxLength={3} placeholder={t("lojaStaff.product.heightPlaceholder")} onChange={(e) => setFresh((vs) => vs.map((x, j) => j === i ? { ...x, height: e.target.value.replace(/\D/g, "") } : x))} aria-label={t("lojaStaff.product.heightLabel")} />
                <span className="text-xs text-ink-400">{t("shopx.club.variantNew")}</span>
              </div>
            ))}
            <Button size="sm" variant="ghost" onClick={() => setFresh((vs) => [...vs, { label: "", price: "", stock: "", height: "" }])}>＋ {t("shopx.club.variant")}</Button>
            <p className="text-xs text-ink-500">{t("lojaStaff.product.heightHint")}</p>
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
  // Gli ordini nuovi dei prodotti del club arrivano dalla Loja, tra le
  // «Encomendas da Loja» della sezione judogi: qui restano quelli di prima.
  const hint = <p className="rounded-2xl bg-accent-50 px-4 py-3 text-sm text-accent-900 ring-1 ring-accent-200">💡 {t("lojaStaff.shopOrdersHint")}</p>;
  if ((data ?? []).length === 0) return <div className="space-y-4">{hint}<EmptyState icon={<span className="text-3xl">📦</span>} title={t("shopx.club.noOrders")} /></div>;
  return (
    <div className="space-y-4">
      {hint}
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
