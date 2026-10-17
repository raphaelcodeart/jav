"use client";

import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { BeltBadge } from "@/components/ui/belt";
import { EmptyState } from "@/components/ui/empty-state";
import { Pagination } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { PersonMarks, usePersonKinds } from "@/components/club/person-marks";
import { whatsappUrl } from "@/components/site/social-icons";
import { clubGet, fullName, type AdminAthlete } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// La tabella atleti della segreteria (e del superadmin entrato nel club):
// l'anagrafe come la tiene il club — nº de sócio, licença FPJ, nascita, età
// federativa, género, contatto, encarregado — più cintura, piano,
// certificato e debito, con chi ha portato l'atleta nel club sotto il nome.
// Ordinamento dalle intestazioni, filtri rapidi e CSV lavorano su ciò che
// l'API ha restituito (la ricerca e lo stato, invece, li fa l'API).

type SortKey = "member" | "name" | "birth" | "fedAge" | "due";
type Quick = "all" | "debt" | "cert" | "license" | "noMember";

const PAGE = 25;
const A = (path: string) => `/admin${path}`;

function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** La licenza FPJ: valida, in scadenza (30 giorni), scaduta o assente. */
function licenseState(a: AdminAthlete, today: string): "ok" | "soon" | "expired" | "none" {
  if (!a.federation_number) return "none";
  if (!a.federation_expires_on) return "ok";
  if (a.federation_expires_on < today) return "expired";
  const soon = new Date(today);
  soon.setDate(soon.getDate() + 30);
  return a.federation_expires_on <= soon.toISOString().slice(0, 10) ? "soon" : "ok";
}

/** Il numero di sócio in ordine naturale: "9" prima di "10". */
function memberCompare(a: string | null, b: string | null) {
  if (!a) return b ? 1 : 0;
  if (!b) return -1;
  return a.localeCompare(b, undefined, { numeric: true });
}

function SortTh({ k, sort, onSort, children, className }: {
  k: SortKey; sort: { key: SortKey; dir: 1 | -1 }; onSort: (k: SortKey) => void; children: React.ReactNode; className?: string;
}) {
  const on = sort.key === k;
  return (
    <th className={cn("whitespace-nowrap px-2.5 py-2.5 text-left font-semibold", className)} aria-sort={on ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => onSort(k)} className={cn("inline-flex cursor-pointer items-center gap-1 uppercase tracking-wider hover:text-ink-900", on && "text-brand-700")}>
        {children}
        <span aria-hidden="true" className={cn("text-[10px]", !on && "opacity-30")}>{on && sort.dir === -1 ? "▼" : "▲"}</span>
      </button>
    </th>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return <th className={cn("whitespace-nowrap px-2.5 py-2.5 text-left font-semibold uppercase tracking-wider", className)}>{children}</th>;
}

export function AthletesTable({ onOpen }: { onOpen: (a: AdminAthlete) => void }) {
  const { t, fmt } = useI18n();
  const kinds = usePersonKinds();
  const [q, setQ] = useState("");
  const query = useDeferredValue(q.trim());
  const [status, setStatus] = useState("ACTIVE");
  const [quick, setQuick] = useState<Quick>("all");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "name", dir: 1 });
  const [page, setPage] = useState(1);
  const qs = new URLSearchParams({ ...(query ? { q: query } : {}), ...(status ? { status } : {}) }).toString();
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["club", "admin", "athletes", qs],
    queryFn: () => clubGet<AdminAthlete[]>(A(`/athletes?${qs}`)),
    placeholderData: (prev) => prev,
  });
  const today = todayIso();

  const counts = useMemo(() => {
    const rows = data ?? [];
    return {
      all: rows.length,
      debt: rows.filter((a) => a.due_cents > 0).length,
      cert: rows.filter((a) => a.certificate.status !== "VALID").length,
      license: rows.filter((a) => licenseState(a, today) !== "ok").length,
      noMember: rows.filter((a) => !a.member_number).length,
    };
  }, [data, today]);

  const rows = useMemo(() => {
    const list = (data ?? []).filter((a) =>
      quick === "all" ? true
      : quick === "debt" ? a.due_cents > 0
      : quick === "cert" ? a.certificate.status !== "VALID"
      : quick === "license" ? licenseState(a, today) !== "ok"
      : !a.member_number);
    const by: Record<SortKey, (x: AdminAthlete, y: AdminAthlete) => number> = {
      member: (x, y) => memberCompare(x.member_number ?? null, y.member_number ?? null),
      name: (x, y) => `${x.last_name} ${x.first_name}`.localeCompare(`${y.last_name} ${y.first_name}`),
      birth: (x, y) => x.birth_date.localeCompare(y.birth_date),
      fedAge: (x, y) => (x.federal_age ?? x.season_age) - (y.federal_age ?? y.season_age),
      due: (x, y) => x.due_cents - y.due_cents,
    };
    return [...list].sort((x, y) => by[sort.key](x, y) * sort.dir || by.name(x, y));
  }, [data, quick, sort, today]);

  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const current = Math.min(page, pages);
  const shown = rows.slice((current - 1) * PAGE, current * PAGE);

  function sortBy(key: SortKey) {
    setSort((s) => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : 1 }));
    setPage(1);
  }

  function exportCsv() {
    const head = [t("athTable.member"), t("athTable.license"), t("athTable.licenseUntil"), t("athTable.name"),
      t("athTable.birth"), t("athTable.fedAge"), t("athTable.gender"), t("athTable.belt"), t("athTable.plan"),
      t("athTable.guardian"), "Email", t("athTable.contact"), t("athTable.invitedBy"), t("athTable.certificate"), t("athTable.due")];
    const lines = rows.map((a) => [
      a.member_number ?? "", a.federation_number ?? "", a.federation_expires_on ?? "", fullName(a), a.birth_date,
      String(a.federal_age ?? a.season_age), a.sex, a.belt?.label ?? "", a.plan?.name ?? "",
      a.guardian_name ?? "", a.guardian_email ?? "", a.guardian_phone ?? "",
      a.invited_by ? a.invited_by.name : t("athTable.byClub"),
      t.dyn(`athTable.cert.${a.certificate.status}`, a.certificate.status), (a.due_cents / 100).toFixed(2),
    ]);
    const csv = [head, ...lines].map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(";")).join("\r\n");
    const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `atletas-${today}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const QUICK: { key: Quick; icon: string; label: string }[] = [
    { key: "all", icon: "👥", label: t("athTable.quickAll") },
    { key: "debt", icon: "💶", label: t("athTable.quickDebt") },
    { key: "cert", icon: "🩺", label: t("athTable.quickCert") },
    { key: "license", icon: "🪪", label: t("athTable.quickLicense") },
    { key: "noMember", icon: "#️⃣", label: t("athTable.quickNoMember") },
  ];

  return (
    <div className="space-y-4">
      {/* Ricerca, stato, CSV */}
      <div className="flex flex-col gap-3 rounded-3xl bg-white p-3 shadow-soft ring-1 ring-ink-900/5 sm:flex-row sm:items-center">
        <label className="relative min-w-0 flex-1">
          <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true">🔎</span>
          <input type="search" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }}
            placeholder={t("athTable.search")} aria-label={t("athTable.search")}
            className="h-11 w-full rounded-2xl bg-ink-50 pl-11 pr-4 text-sm text-ink-900 ring-1 ring-ink-900/5 placeholder:text-ink-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-300" />
          {isFetching && <span className="absolute right-4 top-1/2 h-3 w-3 -translate-y-1/2 animate-spin rounded-full border-2 border-brand-300 border-t-transparent" aria-hidden="true" />}
        </label>
        <div className="flex gap-2">
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label={t("athTable.status")}
            className="h-11 rounded-2xl bg-ink-50 px-3 text-sm font-semibold text-ink-800 ring-1 ring-ink-900/5 focus:outline-none focus:ring-2 focus:ring-brand-300">
            <option value="ACTIVE">{t("athTable.statusActive")}</option>
            <option value="SUSPENDED">{t("athTable.statusSuspended")}</option>
            <option value="LEFT">{t("athTable.statusLeft")}</option>
            <option value="">{t("athTable.statusAll")}</option>
          </select>
          <button type="button" onClick={exportCsv} disabled={rows.length === 0}
            className="inline-flex h-11 shrink-0 cursor-pointer items-center gap-2 rounded-2xl bg-ink-900 px-4 text-sm font-semibold text-white transition hover:bg-ink-800 disabled:opacity-40">
            ⬇ CSV
          </button>
        </div>
      </div>

      {/* Filtri rapidi */}
      <div className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none]">
        {QUICK.map((f) => (
          <button key={f.key} type="button" onClick={() => { setQuick(f.key); setPage(1); }} aria-pressed={quick === f.key}
            className={cn("inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold ring-1 transition",
              quick === f.key ? "bg-brand-600 text-white ring-brand-600 shadow-brand" : "bg-white text-ink-700 ring-ink-200 hover:ring-ink-300")}>
            <span aria-hidden="true">{f.icon}</span>{f.label}
            <span className={cn("rounded-full px-1.5 text-xs tabular-nums", quick === f.key ? "bg-white/20" : "bg-ink-100 text-ink-500")}>{counts[f.key]}</span>
          </button>
        ))}
      </div>

      {isLoading ? <Skeleton className="h-96" /> : rows.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🥋</span>} title={t("athTable.empty")} text={t("athTable.emptyText")} />
      ) : (
        <div className="overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/5">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[68rem] text-sm">
              <thead className="bg-ink-50/80 text-[11px] text-ink-500">
                <tr>
                  <Th className="w-20">{t("athTable.role")}</Th>
                  <SortTh k="member" sort={sort} onSort={sortBy}>{t("athTable.memberShort")}</SortTh>
                  <Th>{t("athTable.license")}</Th>
                  <SortTh k="name" sort={sort} onSort={sortBy} className="sticky left-0 z-10 bg-ink-50 shadow-[6px_0_8px_-6px_rgba(15,23,42,0.15)]">{t("athTable.name")}</SortTh>
                  <SortTh k="birth" sort={sort} onSort={sortBy}>{t("athTable.birth")}</SortTh>
                  <SortTh k="fedAge" sort={sort} onSort={sortBy}>{t("athTable.fedAge")}</SortTh>
                  <Th>{t("athTable.gender")}</Th>
                  <Th>{t("athTable.belt")} · {t("athTable.plan")}</Th>
                  <Th>{t("athTable.guardian")}</Th>
                  <Th>{t("athTable.contact")}</Th>
                  <Th>{t("athTable.certificate")}</Th>
                  <SortTh k="due" sort={sort} onSort={sortBy} className="text-right">{t("athTable.due")}</SortTh>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {shown.map((a) => {
                  const lic = licenseState(a, today);
                  const roles = kinds.athlete(a.id);
                  const wa = a.guardian_phone ? whatsappUrl(a.guardian_phone) : null;
                  const cert = a.certificate.status;
                  return (
                    <tr key={a.id} onClick={() => onOpen(a)} className="group cursor-pointer transition-colors hover:bg-brand-50/40">
                      {/* Che cosa è nel club: atleta, genitore, treinador… */}
                      <td className="px-2.5 py-2.5 align-middle">
                        <PersonMarks kinds={roles.length ? roles : ["ATHLETE"]} size="md" className="flex-wrap" />
                      </td>
                      <td className="px-2.5 py-2.5 font-mono text-xs font-semibold text-ink-700">
                        {a.member_number ? `#${a.member_number}` : <span className="text-ink-300">—</span>}
                      </td>
                      <td className="px-2.5 py-2.5">
                        {a.federation_number ? (
                          <span className="block">
                            <span className="font-mono text-xs font-semibold text-ink-800">{a.federation_number}</span>
                            <span className={cn("mt-0.5 block text-[11px] font-semibold",
                              lic === "expired" ? "text-rose-600" : lic === "soon" ? "text-amber-600" : "text-emerald-600")}>
                              {lic === "expired" ? "⛔ " : lic === "soon" ? "⏳ " : "✓ "}
                              {a.federation_expires_on ? fmt.shortDate(a.federation_expires_on) : t("athTable.licenseValid")}
                            </span>
                          </span>
                        ) : <Badge tone="warning">{t("athTable.licenseNone")}</Badge>}
                      </td>
                      <td className="sticky left-0 z-10 bg-white px-2.5 py-2.5 shadow-[6px_0_8px_-6px_rgba(15,23,42,0.15)] group-hover:bg-brand-50">
                        <span className="flex items-center gap-3">
                          {a.photo_url ? (
                            // eslint-disable-next-line @next/next/no-img-element -- foto della scheda
                            <img src={a.photo_url} alt="" className="h-9 w-9 shrink-0 rounded-full object-cover ring-2 ring-white shadow" />
                          ) : (
                            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-xs font-bold text-white shadow">
                              {a.first_name.slice(0, 1)}{a.last_name.slice(0, 1)}
                            </span>
                          )}
                          <span className="min-w-0 max-w-[15rem]">
                            <span className="block truncate font-semibold text-ink-900 group-hover:text-brand-700">{a.last_name}, {a.first_name}</span>
                            {/* Chi l'ha portato nel club. */}
                            <span className="mt-0.5 flex items-center gap-1 text-[11px] text-ink-500">
                              {a.invited_by?.kind === "PERSON" ? (
                                <>🤝 {t("athTable.invitedBy")}: <span className="font-semibold text-ink-700">{a.invited_by.name}</span>
                                  <PersonMarks kinds={kinds.user(a.invited_by.user_id)} className="scale-90" /></>
                              ) : a.invited_by?.kind === "WRITTEN" ? (
                                <>✍️ {t("athTable.invitedBy")}: <span className="font-semibold text-ink-700">{a.invited_by.name}</span></>
                              ) : <>🏯 {t("athTable.byClub")}</>}
                            </span>
                          </span>
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-2.5 py-2.5 tabular-nums">{fmt.shortDate(a.birth_date)}</td>
                      <td className="px-2.5 py-2.5">
                        <span className="inline-flex h-8 min-w-8 items-center justify-center rounded-xl bg-ink-900 px-2 font-display text-sm text-white" title={t("athTable.fedAgeHint")}>
                          {a.federal_age ?? a.season_age}
                        </span>
                      </td>
                      <td className="px-2.5 py-2.5">
                        <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold",
                          a.sex === "F" ? "bg-pink-50 text-pink-700 ring-1 ring-pink-200" : "bg-sky-50 text-sky-700 ring-1 ring-sky-200")}>
                          {a.sex === "F" ? "♀" : "♂"} {a.sex === "F" ? t("athTable.female") : t("athTable.male")}
                        </span>
                      </td>
                      <td className="px-2.5 py-2.5">
                        <span className="block" title={a.belt?.label ?? ""}><BeltBadge belt={a.belt} size="sm" showLabel={false} /></span>
                        <span className="mt-1 block max-w-[10rem] truncate text-[11px] text-ink-600">
                          {a.plan?.name ?? <Badge tone="warning">{t("athTable.noPlan")}</Badge>}
                          {a.plan_locked && <span title={t("athTable.planLocked")} className="ml-1">🔒</span>}
                        </span>
                      </td>
                      <td className="px-2.5 py-2.5">
                        {a.is_self ? <span className="text-xs font-semibold text-ink-500">{t("athTable.self")}</span> : (
                          <span className="block max-w-[11rem]">
                            <span className="block truncate text-sm font-semibold text-ink-800">{a.guardian_name ?? "—"}</span>
                            <span className="block truncate text-[11px] text-ink-500">{a.guardian_email ?? ""}</span>
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-2.5 py-2.5" onClick={(e) => e.stopPropagation()}>
                        {a.guardian_phone ? (
                          <span className="flex items-center gap-1.5">
                            <a href={`tel:${a.guardian_phone.replace(/\s+/g, "")}`} className="text-xs font-semibold text-ink-800 hover:text-brand-700">{a.guardian_phone}</a>
                            {wa && <a href={wa} target="_blank" rel="noopener noreferrer" title="WhatsApp" className="flex h-6 w-6 items-center justify-center rounded-full bg-[#25D366] text-[11px] text-white">✆</a>}
                          </span>
                        ) : a.guardian_email ? (
                          <a href={`mailto:${a.guardian_email}`} className="text-xs text-brand-700 hover:underline">✉️ Email</a>
                        ) : <span className="text-ink-300">—</span>}
                      </td>
                      <td className="px-2.5 py-2.5">
                        <Badge tone={cert === "VALID" ? "success" : cert === "EXPIRING" ? "warning" : cert === "EXPIRED" ? "danger" : "neutral"} dot>
                          {t.dyn(`athTable.cert.${cert}`, cert)}
                        </Badge>
                      </td>
                      <td className="whitespace-nowrap px-2.5 py-2.5 text-right font-semibold tabular-nums">
                        {a.due_cents > 0 ? <span className={a.overdue_count ? "text-rose-600" : "text-ink-900"}>{fmt.euro(a.due_cents)}</span> : <span className="text-emerald-600">✓</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="border-t border-ink-100 px-4 py-2.5 text-xs text-ink-500">{t("athTable.count", { n: rows.length })}</p>
        </div>
      )}
      <Pagination page={current} pages={pages} onChange={(p) => { setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
    </div>
  );
}
