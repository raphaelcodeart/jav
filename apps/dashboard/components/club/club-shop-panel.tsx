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
  const [tab, setTab] = useState<"products" | "orders" | "jav">("products");
  return (
    <div className="space-y-5">
      <Tabs value={tab} onChange={(k) => setTab(k as typeof tab)} items={[
        { key: "products", label: "🏯 Prodotti del club" },
        { key: "orders", label: "📦 Ordini del club" },
        { key: "jav", label: "🌍 Ordini Shop JudoArteVida" },
      ]} />
      {tab === "products" && <Products />}
      {tab === "orders" && <Orders />}
      {tab === "jav" && familyOrders}
    </div>
  );
}

function Products() {
  const { fmt } = useI18n();
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "shop", "products"], queryFn: () => clubGet<Product[]>(`${A}/products`) });
  const [editing, setEditing] = useState<Product | "new" | null>(null);
  const paged = usePaged(data ?? [], 12);
  if (isLoading) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-ink-600">
          I prodotti del tuo club compaiono nello Shop delle tue famiglie, con l&apos;etichetta del club, accanto allo shop di JudoArteVida. Si pagano con bonifico all&apos;IBAN del club (Impostazioni) e gli ordini li gestisci qui.
        </p>
        <Button onClick={() => setEditing("new")}>＋ Nuovo prodotto</Button>
      </div>
      {(data ?? []).length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🛍️</span>} title="Lo shop del club è vuoto" text="Aggiungi la t-shirt del club, il judogi con il logo, il materiale." action={<Button onClick={() => setEditing("new")}>Aggiungi il primo prodotto</Button>} />
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
                  <Badge tone={p.status === "ACTIVE" ? "success" : "neutral"} dot>{p.status === "ACTIVE" ? "In vendita" : "Nascosto"}</Badge>
                </div>
                <p className="text-sm text-ink-600">{p.variants.map((v) => `${v.label} ${fmt.euro(v.price_cents)}`).join(" · ")}</p>
                <Button size="sm" variant="secondary" onClick={() => setEditing(p)}>✎ Modifica</Button>
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
  const toast = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState(product?.name ?? "");
  const [description, setDescription] = useState(product?.description ?? "");
  const [image, setImage] = useState<string | null>(product?.image_url ?? null);
  const [status, setStatus] = useState(product?.status ?? "ACTIVE");
  const [variants, setVariants] = useState(() => (product?.variants ?? []).map((v) => ({ id: v.id, label: v.label, price: (v.price_cents / 100).toFixed(2), stock: v.inventory == null ? "" : String(v.inventory), active: v.active })));
  const [fresh, setFresh] = useState<{ label: string; price: string; stock: string }[]>(product ? [] : [{ label: "Unica", price: "", stock: "" }]);
  const [busy, setBusy] = useState(false);
  const cents = (v: string) => Math.round(Number(v.replace(",", ".")) * 100);

  async function upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    try {
      const { image_url } = await clubSend<{ image_url: string }>(`${A}/images`, "POST", form);
      setImage(image_url);
    } catch (e) {
      toast({ tone: "error", title: "Foto non caricata", text: (e as Error).message });
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
      toast({ tone: "success", title: "Prodotto salvato" });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: "Non salvato", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} size="lg" title={product ? "Modifica prodotto" : "Nuovo prodotto"}
      footer={<><Button variant="ghost" onClick={onClose}>Chiudi</Button><Button onClick={save} loading={busy} disabled={!name.trim() || (!product && !fresh.some((v) => cents(v.price) > 0))}>Salva</Button></>}>
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-[1fr_160px]">
          <Field label="Nome"><Input value={name} maxLength={255} onChange={(e) => setName(e.target.value)} placeholder="T-shirt do clube" /></Field>
          <Field label="Stato">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="ACTIVE">In vendita</option>
              <option value="INACTIVE">Nascosto</option>
            </Select>
          </Field>
        </div>
        <Field label="Descrizione"><Textarea rows={3} value={description} maxLength={8000} onChange={(e) => setDescription(e.target.value)} /></Field>
        <Field label="Foto" hint="JPG, PNG o WebP fino a 5 MB.">
          <div className="flex items-center gap-3">
            {image && (
              // eslint-disable-next-line @next/next/no-img-element -- anteprima
              <img src={image} alt="" className="h-16 w-16 rounded-xl object-cover ring-1 ring-ink-100" />
            )}
            <Input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); }} />
          </div>
        </Field>
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-500">Varianti (taglia, colore…) e prezzi</p>
          <div className="space-y-2">
            {variants.map((v, i) => (
              <div key={v.id} className="grid grid-cols-[1fr_110px_90px_auto] items-center gap-2">
                <Input value={v.label} onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} aria-label="Variante" />
                <Input value={v.price} inputMode="decimal" onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, price: e.target.value } : x))} aria-label="Prezzo €" />
                <Input value={v.stock} inputMode="numeric" placeholder="∞" onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, stock: e.target.value } : x))} aria-label="Pezzi" />
                <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={v.active} onChange={(e) => setVariants((vs) => vs.map((x, j) => j === i ? { ...x, active: e.target.checked } : x))} />attiva</label>
              </div>
            ))}
            {fresh.map((v, i) => (
              <div key={`new-${i}`} className="grid grid-cols-[1fr_110px_90px_auto] items-center gap-2">
                <Input value={v.label} placeholder="Es. M · Azul" onChange={(e) => setFresh((vs) => vs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} aria-label="Variante" />
                <Input value={v.price} inputMode="decimal" placeholder="€" onChange={(e) => setFresh((vs) => vs.map((x, j) => j === i ? { ...x, price: e.target.value } : x))} aria-label="Prezzo €" />
                <Input value={v.stock} inputMode="numeric" placeholder="∞ pezzi" onChange={(e) => setFresh((vs) => vs.map((x, j) => j === i ? { ...x, stock: e.target.value } : x))} aria-label="Pezzi" />
                <span className="text-xs text-ink-400">nuova</span>
              </div>
            ))}
            <Button size="sm" variant="ghost" onClick={() => setFresh((vs) => [...vs, { label: "", price: "", stock: "" }])}>＋ Variante</Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function Orders() {
  const { fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "shop", "orders"], queryFn: () => clubGet<Order[]>(`${A}/orders`) });
  const [busy, setBusy] = useState<string | null>(null);
  const paged = usePaged(data ?? [], 20);

  async function act(o: Order, action: "confirm-payment" | "ship" | "delivered" | "cancel") {
    let body: unknown;
    if (action === "cancel") {
      const reason = window.prompt("Perché annulli l'ordine?");
      if (!reason) return;
      body = { reason };
    } else if (action === "ship") {
      body = { tracking_number: null, tracking_url: null, tracking_company: null };
    }
    setBusy(o.id);
    try {
      await clubSend(`${A}/orders/${o.id}/${action}`, "POST", body);
      await queryClient.invalidateQueries({ queryKey: ["club", "admin", "shop", "orders"] });
      toast({ tone: "success", title: "Ordine aggiornato" });
    } catch (e) {
      toast({ tone: "error", title: "Operazione non riuscita", text: (e as Error).message });
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
      toast({ tone: "error", title: "Prova non disponibile", text: (e as Error).message });
    }
  }

  if (isLoading) return <Skeleton className="h-64" />;
  if ((data ?? []).length === 0) return <EmptyState icon={<span className="text-3xl">📦</span>} title="Ancora nessun ordine nello shop del club" />;
  return (
    <div className="space-y-4">
      <ul className="space-y-3">
        {paged.items.map((o) => (
          <li key={o.id} className="glass-card flex flex-wrap items-center gap-4 rounded-2xl p-4">
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-ink-900">{o.product_name}</p>
              <p className="text-xs text-ink-500">
                {o.order_code} · {fmt.shortDate(o.created_at)} · {o.customer_display_name}{o.athlete_name ? ` · per ${o.athlete_name}` : ""}
              </p>
            </div>
            <span className="font-display text-lg text-ink-900">{fmt.euro(o.amount_due_cents ?? o.amount_cents)}</span>
            <Badge tone={ORDER_TONE[o.status] ?? "neutral"} dot>{o.status === "AWAITING_PAYMENT" ? "Da pagare" : o.status === "PAID" ? "Pagato" : o.status === "CANCELLED" ? "Annullato" : o.status}</Badge>
            {o.status === "PAID" && <Badge tone="neutral">{o.fulfillment_status === "DELIVERED" ? "Consegnato" : o.fulfillment_status === "SHIPPED" ? "Spedito" : "Da preparare"}</Badge>}
            <div className="flex flex-wrap gap-2">
              {o.payment_proof_uploaded_at && <Button size="sm" variant="ghost" onClick={() => proof(o)}>🧾 Prova</Button>}
              {o.status === "AWAITING_PAYMENT" && <Button size="sm" loading={busy === o.id} onClick={() => act(o, "confirm-payment")}>✓ Pagamento ricevuto</Button>}
              {o.status === "PAID" && o.fulfillment_status !== "SHIPPED" && o.fulfillment_status !== "DELIVERED" && <Button size="sm" variant="secondary" loading={busy === o.id} onClick={() => act(o, "ship")}>🚚 Spedito</Button>}
              {o.status === "PAID" && o.fulfillment_status !== "DELIVERED" && <Button size="sm" variant="secondary" loading={busy === o.id} onClick={() => act(o, "delivered")}>📦 Consegnato</Button>}
              {o.status === "AWAITING_PAYMENT" && <Button size="sm" variant="ghost" className="text-rose-600" loading={busy === o.id} onClick={() => act(o, "cancel")}>Annulla</Button>}
            </div>
          </li>
        ))}
      </ul>
      <Pagination page={paged.page} pages={paged.pages} onChange={(p) => { paged.setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
    </div>
  );
}
