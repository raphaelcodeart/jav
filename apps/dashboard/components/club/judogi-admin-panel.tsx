"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend } from "@/lib/club";
import { cn } from "@/lib/cn";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";
import {
  COLOR_SWATCH, JUDOGI_COLORS, KIMONO_TYPES, STATUS_TONE,
  type JudogiColor, type JudogiOrder, type JudogiPrice, type KimonoType, type OrderStatus,
} from "@/lib/judogi";

// La segreteria e i judogi (apps/api/app/domains/club/judogi.py): gli
// ordini (stati, CSV per il fornitore), il listino che il calcolatore usa e
// le due regole del club (personalizzazione obbligatoria, permuta).

const ORDERS_KEY = ["club", "admin", "judogi", "orders"];
const PRICES_KEY = ["club", "admin", "judogi", "prices"];

/** «Euro» scritti a mano → centesimi; null se non è un importo. */
function toCents(s: string): number | null {
  const clean = s.trim().replace(/\s/g, "").replace(",", ".");
  if (!/^\d+(\.\d{0,2})?$/.test(clean)) return null;
  return Math.round(Number(clean) * 100);
}

function euroInput(cents: number) {
  return (cents / 100).toFixed(2).replace(".", ",");
}

export function JudogiAdminPanel() {
  const { t } = useI18n();
  const [view, setView] = useState("orders");
  return (
    <div className="space-y-5">
      <Tabs value={view} onChange={setView} items={[
        { key: "orders", label: `📦 ${t("judo.admin.orders")}` },
        { key: "prices", label: `🏷️ ${t("judo.admin.prices")}` },
        { key: "settings", label: `⚙️ ${t("judo.admin.settings")}` },
      ]} />
      {view === "orders" && <Orders />}
      {view === "prices" && <Prices />}
      {view === "settings" && <Settings />}
    </div>
  );
}

// --- Ordini ------------------------------------------------------------------------------------

function Orders() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<OrderStatus | "">("PENDING");
  const [q, setQ] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: [...ORDERS_KEY, status],
    queryFn: () => clubGet<JudogiOrder[]>(`/admin/judogi/orders${status ? `?status=${status}` : ""}`),
  });
  const [busy, setBusy] = useState<string | null>(null);
  const needle = q.trim().toLowerCase();
  const rows = (data ?? []).filter((o) => !needle || `${o.athlete_name} ${o.kimono_name} ${o.brand}`.toLowerCase().includes(needle));

  async function move(o: JudogiOrder, next: OrderStatus) {
    if (next === "CANCELLED" && !window.confirm(t("judo.admin.cancelConfirm"))) return;
    setBusy(o.id);
    try {
      await clubSend(`/admin/judogi/orders/${o.id}`, "PATCH", { status: next });
      await queryClient.invalidateQueries({ queryKey: ORDERS_KEY });
      toast({ tone: "success", title: t("judo.admin.moved", { status: t(`judo.status.${next}` as "judo.status.PENDING") }) });
    } catch (e) {
      toast({ tone: "error", title: t("judo.calc.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function setPrice(o: JudogiOrder) {
    const typed = window.prompt(t("judo.admin.pricePrompt"), "");
    if (typed == null) return;
    const cents = toCents(typed);
    if (cents == null) return;
    try {
      await clubSend(`/admin/judogi/orders/${o.id}`, "PATCH", { price_cents: cents });
      await queryClient.invalidateQueries({ queryKey: ORDERS_KEY });
    } catch (e) {
      toast({ tone: "error", title: t("judo.calc.failed"), text: (e as Error).message });
    }
  }

  async function csv() {
    const res = await fetch(`/api/proxy/club/admin/judogi/orders.csv${status ? `?status=${status}` : ""}`);
    if (!res.ok) {
      toast({ tone: "error", title: await friendlyApiError(res) });
      return;
    }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = "pedidos-judogi.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  const NEXT: Partial<Record<OrderStatus, OrderStatus>> = { PENDING: "IN_PREPARATION", IN_PREPARATION: "DELIVERED" };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 rounded-3xl bg-white p-2.5 shadow-soft ring-1 ring-ink-900/5">
        <div className="flex gap-1 overflow-x-auto rounded-2xl bg-ink-50 p-1">
          {(["PENDING", "IN_PREPARATION", "DELIVERED", "CANCELLED", ""] as const).map((s) => (
            <button key={s || "ALL"} type="button" onClick={() => setStatus(s)}
              className={cn("h-9 shrink-0 cursor-pointer rounded-xl px-3 text-sm font-semibold", status === s ? "bg-ink-900 text-white" : "text-ink-600 hover:bg-white")}>
              {s ? t(`judo.status.${s}` as "judo.status.PENDING") : t("judo.admin.all")}
            </button>
          ))}
        </div>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("judo.admin.search")} className="h-10 min-w-0 flex-1 sm:max-w-xs" aria-label={t("judo.admin.search")} />
        <Button variant="secondary" className="ml-auto" onClick={() => void csv()}>⬇ {t("judo.admin.csv")}</Button>
      </div>
      {isLoading ? <Skeleton className="h-64" /> : rows.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🥋</span>} title={t("judo.admin.noOrders")} />
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {rows.map((o) => (
            <li key={o.id} className="flex flex-col gap-3 rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
              <div className="flex items-start gap-3">
                <span className={cn("mt-1 h-8 w-8 shrink-0 rounded-full ring-2", o.color ? COLOR_SWATCH[o.color] : "bg-ink-100 ring-ink-200")} aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-ink-900">{o.athlete_name}</p>
                  <p className="text-sm text-ink-600">{t(`judo.type.${o.kimono_type}` as "judo.type.TRAINING")} · {o.brand} · {o.color_label} · <b>{o.size_cm} cm</b></p>
                  <p className="text-xs text-ink-500">✍️ «{o.kimono_name}» · {fmt.shortDate(o.created_at)}</p>
                </div>
                <Badge tone={STATUS_TONE[o.status]}>{t(`judo.status.${o.status}` as "judo.status.PENDING")}</Badge>
              </div>
              {o.trade_in && <p className="rounded-xl bg-emerald-50 px-3 py-1.5 text-xs text-emerald-800">♻️ {t("judo.admin.tradeIn", { what: `${o.trade_in.brand} ${o.trade_in.size_cm} cm`, amount: fmt.euro(o.trade_in.discount_cents) })}</p>}
              {o.notes && <p className="text-xs italic text-ink-600">“{o.notes}”</p>}
              <div className="flex flex-wrap items-center gap-2 border-t border-ink-100 pt-3">
                {o.price_cents != null ? <span className="font-display text-lg text-ink-900">{fmt.euro(o.price_cents)}</span> : (
                  <Button size="sm" variant="secondary" onClick={() => void setPrice(o)}>💶 {t("judo.admin.setPrice")}</Button>
                )}
                {o.fee_status && <Badge tone={o.fee_status === "PAID" ? "success" : "warning"}>{o.fee_status === "PAID" ? t("judo.orders.paid") : t("judo.orders.toPay")}</Badge>}
                <span className="ml-auto flex gap-1.5">
                  {NEXT[o.status] && <Button size="sm" loading={busy === o.id} onClick={() => void move(o, NEXT[o.status]!)}>→ {t(`judo.status.${NEXT[o.status]!}` as "judo.status.PENDING")}</Button>}
                  {o.status !== "CANCELLED" && o.status !== "DELIVERED" && <Button size="sm" variant="ghost" className="text-rose-700" disabled={busy === o.id} onClick={() => void move(o, "CANCELLED")}>{t("judo.admin.cancel")}</Button>}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --- Listino ------------------------------------------------------------------------------------

function Prices() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: PRICES_KEY, queryFn: () => clubGet<JudogiPrice[]>("/admin/judogi/prices") });
  const [type, setType] = useState<KimonoType>("TRAINING");
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [adding, setAdding] = useState<{ color: JudogiColor; brand: string; size: string; price: string }>({ color: "WHITE", brand: "", size: "", price: "" });
  const [busy, setBusy] = useState(false);

  const groups = useMemo(() => {
    const out = new Map<string, JudogiPrice[]>();
    for (const p of (data ?? []).filter((x) => x.kimono_type === type)) {
      const key = `${p.color}|${p.brand}`;
      out.set(key, [...(out.get(key) ?? []), p]);
    }
    return [...out.entries()];
  }, [data, type]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await queryClient.invalidateQueries({ queryKey: PRICES_KEY });
      await queryClient.invalidateQueries({ queryKey: ["club", "judogi"] });
    } catch (e) {
      toast({ tone: "error", title: t("judo.calc.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function save(p: JudogiPrice) {
    const cents = toCents(edits[p.id] ?? "");
    if (cents == null || cents === p.price_cents) return;
    await run(() => clubSend(`/admin/judogi/prices/${p.id}`, "PATCH", { price_cents: cents }));
    setEdits((e) => { const next = { ...e }; delete next[p.id]; return next; });
  }

  const addCents = toCents(adding.price);
  const addSize = Number(adding.size);

  if (isLoading) return <Skeleton className="h-64" />;
  if (!data?.length) {
    return (
      <EmptyState icon={<span className="text-3xl">🏷️</span>} title={t("judo.admin.noPrices")} text={t("judo.admin.noPricesText")}
        action={<Button loading={busy} onClick={() => void run(() => clubSend("/admin/judogi/prices/seed", "POST"))}>{t("judo.admin.seed")}</Button>} />
    );
  }
  return (
    <div className="space-y-4">
      <div className="flex gap-1 overflow-x-auto rounded-2xl bg-white p-1.5 shadow-soft ring-1 ring-ink-900/5">
        {KIMONO_TYPES.map((k) => (
          <button key={k} type="button" onClick={() => setType(k)}
            className={cn("h-10 shrink-0 cursor-pointer rounded-xl px-4 text-sm font-semibold", type === k ? "bg-brand-500 text-white" : "text-ink-600 hover:bg-ink-50")}>
            {t(`judo.type.${k}` as "judo.type.TRAINING")}
          </button>
        ))}
      </div>
      <p className="text-xs text-ink-500">{t("judo.admin.pricesHint")}</p>
      <div className="grid gap-3 xl:grid-cols-2">
        {groups.map(([key, rows]) => {
          const [color, brand] = key.split("|") as [JudogiColor, string];
          return (
            <section key={key} className="rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
              <h3 className="mb-3 flex items-center gap-2 font-semibold text-ink-900">
                <span className={cn("h-5 w-5 rounded-full ring-2", COLOR_SWATCH[color])} aria-hidden="true" />
                {brand} <span className="text-sm font-normal text-ink-500">· {t(`judo.color.${color}` as "judo.color.WHITE")}</span>
              </h3>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                {rows.map((p) => (
                  <div key={p.id} className={cn("rounded-xl bg-ink-50 p-2 ring-1 ring-ink-100", !p.active && "opacity-50")}>
                    <div className="mb-1 flex items-center justify-between text-xs font-bold text-ink-700">
                      {p.size_cm} cm
                      <button type="button" title={p.active ? t("judo.admin.disable") : t("judo.admin.enable")} aria-label={p.active ? t("judo.admin.disable") : t("judo.admin.enable")}
                        onClick={() => void run(() => clubSend(`/admin/judogi/prices/${p.id}`, "PATCH", { active: !p.active }))}
                        className="cursor-pointer text-ink-400 hover:text-ink-900">{p.active ? "●" : "○"}</button>
                    </div>
                    <Input inputMode="decimal" value={edits[p.id] ?? euroInput(p.price_cents)} aria-label={`${brand} ${p.size_cm}`}
                      onChange={(e) => setEdits((x) => ({ ...x, [p.id]: e.target.value }))} onBlur={() => void save(p)}
                      className={cn("h-9 text-right text-sm", edits[p.id] !== undefined && toCents(edits[p.id]!) == null && "ring-2 ring-rose-400")} />
                  </div>
                ))}
              </div>
            </section>
          );
        })}
      </div>
      <section className="rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
        <h3 className="mb-3 font-semibold text-ink-900">＋ {t("judo.admin.addPrice")}</h3>
        <div className="flex flex-wrap items-end gap-2">
          <Field label={t("judo.trade.color")}>
            <select className="h-10 rounded-xl border border-ink-200 bg-white px-3 text-sm" value={adding.color} onChange={(e) => setAdding({ ...adding, color: e.target.value as JudogiColor })}>
              {JUDOGI_COLORS.map((c) => <option key={c} value={c}>{t(`judo.color.${c}` as "judo.color.WHITE")}</option>)}
            </select>
          </Field>
          <Field label={t("judo.trade.brand")}><Input value={adding.brand} maxLength={60} onChange={(e) => setAdding({ ...adding, brand: e.target.value })} className="h-10 w-44" /></Field>
          <Field label={t("judo.trade.size")}><Input inputMode="numeric" value={adding.size} maxLength={3} onChange={(e) => setAdding({ ...adding, size: e.target.value.replace(/\D/g, "") })} className="h-10 w-24" /></Field>
          <Field label={t("judo.admin.price")}><Input inputMode="decimal" value={adding.price} onChange={(e) => setAdding({ ...adding, price: e.target.value })} className="h-10 w-28" placeholder="0,00" /></Field>
          <Button loading={busy} disabled={adding.brand.trim().length < 2 || addSize < 80 || addSize > 220 || addCents == null}
            onClick={() => void run(async () => {
              await clubSend("/admin/judogi/prices", "POST", { kimono_type: type, color: adding.color, brand: adding.brand.trim(), size_cm: addSize, price_cents: addCents });
              toast({ tone: "success", title: t("judo.admin.priceSaved", { amount: fmt.euro(addCents ?? 0) }) });
              setAdding({ ...adding, size: "", price: "" });
            })}>
            {t("common.save")}
          </Button>
        </div>
      </section>
    </div>
  );
}

// --- Impostazioni --------------------------------------------------------------------------------

function Settings() {
  const { data } = useQuery({ queryKey: ["club", "admin", "judogi", "settings"], queryFn: () => clubGet<{ customization_cents: number; trade_in_percent: number }>("/admin/judogi/settings") });
  if (!data) return <Skeleton className="h-40" />;
  return <SettingsForm key={`${data.customization_cents}-${data.trade_in_percent}`} initial={data} />;
}

function SettingsForm({ initial }: { initial: { customization_cents: number; trade_in_percent: number } }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [fee, setFee] = useState(euroInput(initial.customization_cents));
  const [pct, setPct] = useState(String(initial.trade_in_percent));
  const [busy, setBusy] = useState(false);
  const cents = toCents(fee);
  const percent = /^\d{1,3}$/.test(pct) && Number(pct) <= 100 ? Number(pct) : null;

  async function save() {
    setBusy(true);
    try {
      await clubSend("/admin/judogi/settings", "PUT", { customization_cents: cents, trade_in_percent: percent });
      await queryClient.invalidateQueries({ queryKey: ["club", "admin", "judogi", "settings"] });
      await queryClient.invalidateQueries({ queryKey: ["club", "judogi"] });
      toast({ tone: "success", title: t("judo.admin.settingsSaved") });
    } catch (e) {
      toast({ tone: "error", title: t("judo.calc.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="max-w-xl space-y-4 rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5">
      <Field label={t("judo.admin.customFee")} hint={t("judo.admin.customFeeHint")} htmlFor="jg-fee">
        <Input id="jg-fee" inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} className="w-36" />
      </Field>
      <Field label={t("judo.admin.tradePct")} hint={t("judo.admin.tradePctHint")} htmlFor="jg-pct">
        <Input id="jg-pct" inputMode="numeric" value={pct} maxLength={3} onChange={(e) => setPct(e.target.value.replace(/\D/g, ""))} className="w-24" />
      </Field>
      <Button loading={busy} disabled={cents == null || percent == null} onClick={() => void save()}>{t("common.save")}</Button>
    </section>
  );
}
