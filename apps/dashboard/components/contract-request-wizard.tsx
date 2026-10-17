"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ContractDocumentsPanel, useRequestDocuments } from "@/components/contract-documents-panel";
import { ContractRequestPaymentPanel } from "@/components/contract-request-payment-panel";
import { FullScreenPanel } from "@/components/full-screen-panel";
import { ProductDetailModal } from "@/components/product-detail-modal";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";
import { contractPrices, isBusinessCustomer, productAllowsCustomerKind } from "@/lib/product-audience";
import { PROVINCES } from "@/lib/provinces";
import type {
  BirthplaceRead,
  ContractRequestDetailRead,
  ContractRequestPointRead,
  ProductCatalogRead,
} from "@/lib/types";

type Step = "data" | "documents" | "contracts" | "summary";

const STEPS: Step[] = ["data", "documents", "contracts", "summary"];

type T = ReturnType<typeof useI18n>["t"];

/** "Contratto 1", "Contratto 2": a contract's place in the pratica. */
function pointCode(t: T, point: { position?: number }): string {
  return point.position ? t("ctr.point.codeN", { n: point.position }) : t("ctr.point.code");
}

/** "1 contratto" / "3 contratti". */
function contractsCount(t: T, n: number): string {
  return n === 1 ? t("ctr.count.oneContract") : t("ctr.count.nContracts", { n });
}

/** Tetto sui contratti di una pratica (MAX_POINTS_PER_REQUEST lato API). */
const MAX_POINTS = 50;

const inputClass = "w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-brand-500";
const labelClass = " font-semibold text-slate-600 uppercase block";
const primaryButton =
  "rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-brand-500/20 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed";
const secondaryButton =
  "rounded-xl bg-slate-900/5 hover:bg-slate-900/10 px-4 py-2.5 text-xs font-semibold text-slate-700 transition cursor-pointer disabled:opacity-50";

async function fetchRequest(id: string): Promise<ContractRequestDetailRead> {
  const res = await fetch(`/api/proxy/contract-requests/${id}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("products fetch failed");
  return res.json();
}

/** Where a pratica picks up when reopened: the first thing still to do. */
function resumeStepFor(request: ContractRequestDetailRead): Step {
  if (request.status !== "DRAFT") return "summary";
  if (!request.street || request.points.length === 0) return "data";
  if ((request.documents_blocking ?? []).length > 0) return "documents";
  if (request.points_without_package > 0) return "contracts";
  return "summary";
}

type AddressValue = { street: string; city: string; province: string; postal_code: string };

/** "Attiva nuovo contratto": the pratica di attivazione (Sessions 52-53).
 *
 *  Everything is asked once, at the start -- holder, PEC, IBAN, address --
 *  together with "quanti contratti vuoi attivare?". The pratica is created
 *  with that many contracts already there; after the identity documents,
 *  each one only needs the offer to activate. Each becomes its own contract
 *  -- its own review, its own commissions -- while documents and payment are
 *  dealt with once.
 *
 *  Everything is saved as it is filled in, so closing halfway loses nothing
 *  and "Riprendi" reopens exactly here.
 *
 *  Used by the customer for themselves, and by a promoter for one of their
 *  customers (`customer` set): the promoter does everything except pay,
 *  which the customer does from their own account. */
export function ContractRequestWizard({
  requestId: initialRequestId,
  initialStep,
  initialProduct,
  customer,
  producerAgentId,
  customerKind,
  accountEmail,
  holder,
  onClose,
}: {
  requestId?: string;
  initialStep?: "documents" | "packages" | "summary";
  /** The contract the customer started from in the catalog: pre-chosen for
      every contract of the pratica, freely changed one by one later. */
  initialProduct?: ProductCatalogRead | null;
  /** Promoter mode: the customer this pratica is for. */
  customer?: {
    id: string;
    kind: string | null;
    email: string | null;
    firstName?: string | null;
    lastName?: string | null;
    pec?: string | null;
    fiscalCode?: string | null;
  };
  /** Staff only (Session 66): the promoter this pratica is attributed to. */
  producerAgentId?: string | null;
  customerKind?: string | null;
  accountEmail?: string;
  holder?: { firstName?: string | null; lastName?: string | null; pec?: string | null; fiscalCode?: string | null };
  onClose: () => void;
}) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const queryClient = useQueryClient();
  const promoterMode = Boolean(customer);
  const [requestId, setRequestId] = useState<string | null>(initialRequestId ?? null);
  const [chosenStep, setChosenStep] = useState<Step | null>(
    initialStep === "packages" ? "contracts" : initialStep ?? (initialRequestId ? null : "data")
  );
  const [preview, setPreview] = useState<{ product: ProductCatalogRead; pointId: string | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  // Session 89: the fiscal code does not match the data -- a warning, not a
  // block: the data is saved, and "Continua comunque" goes on.
  const [fiscalWarning, setFiscalWarning] = useState<string[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const { data: request, error: loadError } = useQuery({
    queryKey: ["contract-request", requestId],
    queryFn: () => fetchRequest(requestId!),
    enabled: Boolean(requestId),
  });
  const { data: products } = useQuery({ queryKey: ["customer", "products"], queryFn: fetchProducts });

  const kind = request?.customer_kind ?? customer?.kind ?? customerKind ?? null;
  const packages = (products ?? [])
    .filter(
      (p) =>
        p.category === "INTERNAL" &&
        p.status === "ACTIVE" &&
        p.current_version?.status === "ACTIVE" &&
        productAllowsCustomerKind(p.customer_type, kind)
    )
    // Dal più economico al più caro (0, 303,78, 425,78), come chiesto.
    .sort(
      (a, b) =>
        a.current_version!.base_price_cents - b.current_version!.base_price_cents ||
        a.current_version!.name.localeCompare(b.current_version!.name, fmt.tag)
    );
  const step: Step | null = chosenStep ?? (request ? resumeStepFor(request) : null);

  function goTo(next: Step) {
    setActionError(null);
    setChosenStep(next);
  }

  /** Every mutation returns the whole pratica: it replaces the cached copy,
      so the screen never shows a half-updated mix of old and new. */
  async function mutate(label: string, path: string, init: RequestInit): Promise<ContractRequestDetailRead | null> {
    setBusy(label);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/contract-requests${path}`, {
        ...init,
        headers: init.body ? { "Content-Type": "application/json" } : undefined,
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const detail = (await res.json()) as ContractRequestDetailRead;
      queryClient.setQueryData(["contract-request", detail.id], detail);
      queryClient.invalidateQueries({ queryKey: ["contract-requests"] });
      queryClient.invalidateQueries({ queryKey: ["customer", "contracts"] });
      return detail;
    } catch (err: any) {
      setActionError(err.message || t("common.failed"));
      return null;
    } finally {
      setBusy(null);
    }
  }

  const customerName = [customer?.firstName, customer?.lastName].filter(Boolean).join(" ") || t("ctr.wiz.theCustomer");
  const title = promoterMode
    ? requestId
      ? t("ctr.wiz.praticaFor", { name: request?.holder_name || customerName })
      : t("ctr.wiz.newPraticaFor", { name: customerName })
    : request
      ? t("ctr.wiz.praticaCode", { code: request.code })
      : t("ctr.wiz.activateNew");
  const liveTotal = (request?.points ?? []).reduce((sum, p) => sum + (p.gross_amount_cents ?? 0), 0);
  const isDraft = !request || request.status === "DRAFT";

  return (
    <FullScreenPanel
      eyebrow={request ? t("ctr.wiz.praticaCode", { code: request.code }) : t("ctr.wiz.activateNew")}
      title={title}
      onClose={onClose}
      subtitle={
        <div className="space-y-2">
          <div className="flex items-center gap-1 overflow-x-auto pb-0.5">
            {STEPS.map((key, i) => {
              const current = key === step;
              // Past the documents only once identity, bill (and visura /
              // P.IVA for a business) are in -- a draft only: a sent
              // pratica is just being looked at.
              const documentsDone = !isDraft || (request?.documents_blocking ?? []).length === 0;
              const reachable =
                key === "data" ||
                (Boolean(requestId) && (key === "documents" || documentsDone));
              return (
                <button
                  key={key}
                  onClick={() => reachable && goTo(key)}
                  disabled={!reachable}
                  className={`flex items-center gap-1.5 px-2 py-1 rounded-lg shrink-0 transition ${
                    current ? "bg-brand-600/15" : reachable ? "hover:bg-slate-100 cursor-pointer" : "opacity-50"
                  }`}
                >
                  <span
                    className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                      current ? "bg-brand-600 text-white" : " bg-slate-900/10 text-slate-400"
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span className={`text-[11px] font-semibold ${current ? " text-slate-900" : "text-slate-500"}`}>
                    {t(`ctr.wiz.step.${key}`)}
                  </span>
                </button>
              );
            })}
          </div>
          {request && request.points.length > 0 && (
            <p className=" text-slate-500">
              {contractsCount(t, request.points.length)}
              {liveTotal > 0 && <> · {t("ctr.log.total")} <strong className="text-brand-600 tabular-nums">{euro(liveTotal)}</strong></>}
            </p>
          )}
        </div>
      }
    >
      {loadError && <p className="text-sm text-rose-400">{(loadError as Error).message}</p>}
      {actionError && (
        <div className="mb-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{actionError}</div>
      )}
      {step === null && !loadError && <div className="h-40 rounded-2xl bg-slate-900/5 animate-pulse" />}

      {step === "data" && fiscalWarning && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 space-y-2">
          <p className="text-xs font-semibold text-amber-700">
            {t("ctr.wiz.fiscalWarnTitle")}
          </p>
          <ul className="list-disc pl-5 text-xs text-amber-800 space-y-0.5">
            {fiscalWarning.map((p) => <li key={p}>{p}</li>)}
          </ul>
          <p className=" text-slate-600">
            {t("ctr.wiz.fiscalWarnBody")}
          </p>
          <button
            type="button"
            onClick={() => {
              setFiscalWarning(null);
              goTo("documents");
            }}
            className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-xs font-semibold text-white transition cursor-pointer"
          >
            {t("ctr.pfc.continueAnyway")}
          </button>
        </div>
      )}

      {step === "data" && (
        <DataStep
          key={request?.id ?? "new"}
          request={request}
          defaults={{
            firstName: customer?.firstName ?? holder?.firstName ?? "",
            lastName: customer?.lastName ?? holder?.lastName ?? "",
            email: customer?.email ?? accountEmail ?? "",
            pec: customer?.pec ?? holder?.pec ?? "",
            fiscalCode: customer?.fiscalCode ?? holder?.fiscalCode ?? "",
          }}
          promoterMode={promoterMode}
          customerKind={customer?.kind ?? customerKind ?? null}
          busy={busy === "data"}
          onSubmit={async (body, count) => {
            if (request && request.status !== "DRAFT") {
              goTo("documents");
              return;
            }
            let detail: ContractRequestDetailRead | null;
            if (!request) {
              detail = await mutate("data", "", {
                method: "POST",
                body: JSON.stringify({
                  ...body,
                  points_count: count,
                  customer_id: customer?.id ?? null,
                  producer_agent_id: producerAgentId ?? null,
                  product_version_id: initialProduct?.current_version?.id ?? null,
                }),
              });
            } else {
              detail = await mutate("data", `/${request.id}`, { method: "PATCH", body: JSON.stringify(body) });
              if (detail && detail.points.length !== count) {
                detail = await mutate("data", `/${request.id}/points-count`, {
                  method: "PUT",
                  body: JSON.stringify({ count }),
                });
              }
            }
            if (detail) {
              setRequestId(detail.id);
              if (detail.fiscal_code_problems.length > 0) {
                setFiscalWarning(detail.fiscal_code_problems);
                return;
              }
              setFiscalWarning(null);
              goTo("documents");
            }
          }}
        />
      )}

      {step === "documents" && request && (
        <div className="space-y-5">
          <div>
            <h3 className="text-sm font-bold text-slate-900">{t("ctr.pfc.flow.documents")}</h3>
            <p className="text-xs text-slate-500 mt-1">
              {t("ctr.wiz.docsIntro", { contracts: contractsCount(t, request.points.length) })}
            </p>
          </div>
          <ContractDocumentsPanel requestId={request.id} />
          {isDraft && (request.documents_blocking ?? []).length > 0 && (
            <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-700 text-xs">
              {t("ctr.wiz.docsBlocking")} <strong>{request.documents_blocking.join(", ")}</strong>.
            </div>
          )}
          <div className="flex gap-2">
            <button onClick={() => goTo("data")} className={secondaryButton}>{t("ctr.wiz.backData")}</button>
            <button
              onClick={() => goTo("contracts")}
              disabled={isDraft && (request.documents_blocking ?? []).length > 0}
              className={`flex-1 ${primaryButton}`}
            >
              {t("ctr.wiz.continueOffers")}
            </button>
          </div>
        </div>
      )}

      {step === "contracts" && request && (
        <ContractsStep
          request={request}
          packages={packages}
          kind={kind}
          busy={busy}
          onPreview={(product, pointId) => setPreview({ product, pointId })}
          onChoose={(pointId, versionId) =>
            mutate(`package-${pointId}`, `/${request.id}/points/${pointId}/product`, {
              method: "PUT",
              body: JSON.stringify({ product_version_id: versionId }),
            })
          }
          onChooseForAll={(versionId) =>
            mutate("package-all", `/${request.id}/product`, {
              method: "PUT",
              body: JSON.stringify({ product_version_id: versionId }),
            })
          }
          onBack={() => goTo("documents")}
          onNext={() => goTo("summary")}
        />
      )}

      {step === "summary" && request && (
        <SummaryStep
          request={request}
          promoterMode={promoterMode}
          busy={busy}
          onChooseContracts={() => goTo("contracts")}
          onGoToDocuments={() => goTo("documents")}
          onSaveNotes={(notes) =>
            mutate("notes", `/${request.id}/notes`, { method: "PUT", body: JSON.stringify({ notes }) })
          }
          onSubmit={() => mutate("submit", `/${request.id}/submit`, { method: "POST" })}
          onCancelDraft={async () => {
            if (!window.confirm(t("ctr.wiz.confirmDeleteDraft"))) return;
            const detail = await mutate("cancel", `/${request.id}/cancel`, { method: "POST" });
            if (detail) onClose();
          }}
          onClose={onClose}
        />
      )}

      {preview && (
        <ProductDetailModal
          product={preview.product}
          customerKind={kind}
          ctaLabel={
            preview.pointId
              ? t("ctr.wiz.chooseForThis")
              : t("common.close")
          }
          onClose={() => setPreview(null)}
          onBuy={async (versionId) => {
            const target = preview.pointId;
            setPreview(null);
            if (target && request && isDraft) {
              await mutate(`package-${target}`, `/${request.id}/points/${target}/product`, {
                method: "PUT",
                body: JSON.stringify({ product_version_id: versionId }),
              });
            }
          }}
        />
      )}
    </FullScreenPanel>
  );
}

// --- 1. Dati: intestatario, indirizzo, quanti contratti -------------------------------

function AddressFields({ value, onChange }: { value: AddressValue; onChange: (value: AddressValue) => void }) {
  const { t } = useI18n();
  return (
    <>
      <div className="space-y-1">
        <label className={labelClass}>{t("ctr.f.address")}</label>
        <input
          required
          value={value.street}
          onChange={(e) => onChange({ ...value, street: e.target.value })}
          placeholder={t("ctr.wiz.streetPlaceholder")}
          className={inputClass}
        />
      </div>
      <div className="grid grid-cols-6 gap-2">
        <div className="col-span-3 space-y-1">
          <label className={labelClass}>{t("ctr.wiz.city")}</label>
          <input required value={value.city} onChange={(e) => onChange({ ...value, city: e.target.value })} className={inputClass} />
        </div>
        <div className="col-span-1 space-y-1">
          <label className={labelClass}>{t("ctr.wiz.province")}</label>
          <select
            required
            value={value.province}
            onChange={(e) => onChange({ ...value, province: e.target.value })}
            className="w-full rounded-xl glass-input px-1.5 py-2.5 text-sm bg-white focus:border-brand-500"
          >
            <option value="" disabled>--</option>
            {PROVINCES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div className="col-span-2 space-y-1">
          <label className={labelClass}>{t("ctr.wiz.postalCode")}</label>
          <input
            required
            minLength={5}
            maxLength={5}
            value={value.postal_code}
            onChange={(e) => onChange({ ...value, postal_code: e.target.value.replace(/\D/g, "") })}
            className={inputClass}
          />
        </div>
      </div>
    </>
  );
}

/** Session 89: «Luogo di nascita» -- a comune (also one since merged or
 *  suppressed: the fiscal code keeps its old code) or a foreign state,
 *  picked from what the server knows, because the fiscal code is checked
 *  against its Belfiore code. Typing again clears the choice. */
function BirthplaceInput({
  value,
  onChange,
}: {
  value: { code: string; label: string } | null;
  onChange: (value: { code: string; label: string } | null) => void;
}) {
  const { t } = useI18n();
  const [text, setText] = useState(value?.label ?? "");
  const [open, setOpen] = useState(false);
  const query = text.trim();
  const { data: options = [], isFetching } = useQuery({
    queryKey: ["birthplaces", query.toLowerCase()],
    queryFn: async (): Promise<BirthplaceRead[]> => {
      const res = await fetch(`/api/proxy/contract-requests/birthplaces?q=${encodeURIComponent(query)}`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
    enabled: open && !value && query.length >= 2,
    staleTime: 5 * 60_000,
  });
  const label = (p: BirthplaceRead) => `${p.name} (${p.foreign ? t("ctr.wiz.abroad") : p.province})`;

  return (
    <div className="relative">
      <input
        required
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={t("ctr.wiz.birthplacePlaceholder")}
        autoComplete="off"
        className={inputClass}
      />
      {open && !value && query.length >= 2 && (
        <div className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-xl">
          {options.length === 0 ? (
            <p className="px-3 py-2 text-xs text-slate-500">{isFetching ? t("ctr.wiz.searching") : t("ctr.wiz.noBirthplace")}</p>
          ) : (
            options.map((p) => (
              <button
                key={`${p.code}-${p.name}`}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onChange({ code: p.code, label: label(p) });
                  setText(label(p));
                  setOpen(false);
                }}
                className="w-full text-left px-3 py-2 text-sm text-slate-700 hover:bg-slate-900/5 cursor-pointer"
              >
                {label(p)}
                {!p.active && (
                  <span className="ml-1 text-[10px] text-slate-500">
                    {p.until ? t("ctr.wiz.suppressedIn", { year: p.until }) : t("ctr.wiz.suppressed")}
                  </span>
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function DataStep({
  request,
  defaults,
  promoterMode,
  customerKind,
  busy,
  onSubmit,
}: {
  request: ContractRequestDetailRead | undefined;
  defaults: { firstName: string; lastName: string; email: string; pec: string; fiscalCode: string };
  promoterMode: boolean;
  /** The customer's own kind: what "Il contratto è per" starts from. */
  customerKind: string | null;
  busy: boolean;
  onSubmit: (
    body: {
      holder_first_name: string;
      holder_last_name: string;
      email: string;
      pec: string | null;
      iban: string | null;
      holder_kind: string;
      company_name: string | null;
      legal_rep_fiscal_code: string | null;
      holder_fiscal_code: string | null;
      holder_birth_date: string | null;
      holder_birth_place_code: string | null;
    } & AddressValue,
    count: number
  ) => void;
}) {
  const { t } = useI18n();
  const readOnly = Boolean(request && request.status !== "DRAFT");
  // Session 85: privato or azienda is chosen here, per pratica. "Azienda"
  // keeps the customer's own business kind (ditta, condominio) when it has one.
  const businessKind = customerKind && isBusinessCustomer(customerKind) ? customerKind : "COMPANY";
  const [holderKind, setHolderKind] = useState(
    request?.customer_kind ?? (customerKind && isBusinessCustomer(customerKind) ? customerKind : "PRIVATE")
  );
  const business = isBusinessCustomer(holderKind);
  const [companyName, setCompanyName] = useState(request?.company_name ?? "");
  const [legalRepFiscalCode, setLegalRepFiscalCode] = useState(request?.legal_rep_fiscal_code ?? "");
  // Session 89: the private holder's CF (prefilled from the customer's own
  // when they are a person), and birth date and place of whoever signs.
  const [holderFiscalCode, setHolderFiscalCode] = useState(
    request?.holder_fiscal_code ?? (customerKind && isBusinessCustomer(customerKind) ? "" : defaults.fiscalCode)
  );
  const [birthDate, setBirthDate] = useState(request?.holder_birth_date ?? "");
  const [birthPlace, setBirthPlace] = useState<{ code: string; label: string } | null>(
    request?.holder_birth_place_code && request.holder_birth_place
      ? { code: request.holder_birth_place_code, label: request.holder_birth_place }
      : null
  );
  const [placeMissing, setPlaceMissing] = useState(false);
  const [firstName, setFirstName] = useState(request?.holder_first_name ?? defaults.firstName);
  const [lastName, setLastName] = useState(request?.holder_last_name ?? defaults.lastName);
  const [email, setEmail] = useState(request?.email ?? defaults.email);
  const [pec, setPec] = useState(request?.pec ?? defaults.pec);
  const [iban, setIban] = useState(request?.iban ?? "");
  const [address, setAddress] = useState<AddressValue>({
    street: request?.street ?? "",
    city: request?.city ?? "",
    province: request?.province ?? "",
    postal_code: request?.postal_code ?? "",
  });
  const [count, setCount] = useState(() => (request && request.points.length > 0 ? request.points.length : 1));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        // A place typed but not picked from the list has no code to check.
        if (!readOnly && !birthPlace) {
          setPlaceMissing(true);
          return;
        }
        onSubmit(
          {
            holder_first_name: firstName.trim(),
            holder_last_name: lastName.trim(),
            email: email.trim(),
            pec: pec.trim() || null,
            iban: iban.replace(/\s+/g, "").toUpperCase() || null,
            holder_kind: holderKind,
            company_name: business ? companyName.trim() || null : null,
            legal_rep_fiscal_code: business ? legalRepFiscalCode.replace(/\s+/g, "").toUpperCase() || null : null,
            holder_fiscal_code: business ? null : holderFiscalCode.replace(/\s+/g, "").toUpperCase() || null,
            holder_birth_date: birthDate || null,
            holder_birth_place_code: birthPlace?.code ?? null,
            ...address,
            province: address.province.toUpperCase(),
          },
          count
        );
      }}
      className="space-y-4"
    >
      <fieldset disabled={readOnly} className="space-y-4">
        <div className="space-y-1">
          <label className={labelClass}>{t("ctr.wiz.contractFor")}</label>
          <select
            value={business ? businessKind : "PRIVATE"}
            onChange={(e) => setHolderKind(e.target.value)}
            className={`${inputClass} bg-white`}
          >
            <option value="PRIVATE">{t("ctr.kind.PRIVATE")}</option>
            <option value={businessKind}>{t("ctr.wiz.businessOption")}</option>
          </select>
        </div>

        {business && (
          <div className="space-y-1">
            <label className={labelClass}>{t("ctr.create.companyName")}</label>
            <input required value={companyName} onChange={(e) => setCompanyName(e.target.value)} autoComplete="organization" className={inputClass} />
          </div>
        )}

        <h3 className="text-sm font-bold text-slate-900">
          {business ? t("ctr.f.legalRep") : t("ctr.wiz.contractHolder")}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className={labelClass}>{t("ctr.wiz.firstName")}</label>
            <input required value={firstName} onChange={(e) => setFirstName(e.target.value)} autoComplete="given-name" className={inputClass} />
          </div>
          <div className="space-y-1">
            <label className={labelClass}>{t("ctr.wiz.lastName")}</label>
            <input required value={lastName} onChange={(e) => setLastName(e.target.value)} autoComplete="family-name" className={inputClass} />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className={labelClass}>{t("ctr.wiz.birthDate")}</label>
            <input
              required
              type="date"
              value={birthDate}
              min="1900-01-01"
              max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setBirthDate(e.target.value)}
              autoComplete="bday"
              className={inputClass}
            />
          </div>
          <div className="space-y-1">
            <label className={labelClass}>{t("ctr.wiz.birthPlace")}</label>
            <BirthplaceInput
              value={birthPlace}
              onChange={(place) => {
                setBirthPlace(place);
                if (place) setPlaceMissing(false);
              }}
            />
            {placeMissing && <p className="text-[10px] text-rose-400">{t("ctr.wiz.pickFromList")}</p>}
          </div>
        </div>
        <div className="space-y-1">
          <label className={labelClass}>
            {business ? t("ctr.wiz.legalRepFiscalCode") : t("ctr.f.fiscalCode")}
          </label>
          <input
            required
            value={business ? legalRepFiscalCode : holderFiscalCode}
            onChange={(e) =>
              (business ? setLegalRepFiscalCode : setHolderFiscalCode)(e.target.value.replace(/\s+/g, "").toUpperCase())
            }
            minLength={16}
            maxLength={16}
            placeholder="RSSMRA80A01H501U"
            className={`${inputClass} font-mono tracking-wide`}
          />
          <p className="text-[10px] text-slate-500">
            {t("ctr.wiz.fiscalCodeHint")}
          </p>
        </div>
        <div className="space-y-1">
          <label className={labelClass}>Email</label>
          <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("ctr.wiz.emailPlaceholder")} className={inputClass} />
          <p className="text-[10px] text-slate-500">{t("ctr.wiz.emailHint")}</p>
        </div>
        <div className="space-y-1">
          <label className={labelClass}>
            PEC{" "}
            {business ? (
              <span className="normal-case font-semibold text-brand-600">{t("ctr.wiz.pecRequiredBusiness")}</span>
            ) : (
              <span className="normal-case font-normal text-slate-500">({t("common.optional").toLowerCase()})</span>
            )}
          </label>
          <input
            type="email"
            required={business}
            value={pec}
            onChange={(e) => setPec(e.target.value)}
            placeholder="nome@pec.it"
            className={inputClass}
          />
          {business && (
            <p className="text-[10px] text-slate-500">
              {t("ctr.wiz.pecHint")}
            </p>
          )}
        </div>
        <div className="space-y-1">
          <label className={labelClass}>
            {t("ctr.f.debitIban")}{promoterMode && <span className="normal-case font-normal text-slate-500"> ({t("common.optional").toLowerCase()})</span>}
          </label>
          <input
            required={!promoterMode}
            value={iban}
            onChange={(e) => setIban(e.target.value.toUpperCase())}
            placeholder="IT60 X054 2811 1010 0000 0123 456"
            minLength={15}
            maxLength={42}
            className={`${inputClass} font-mono tracking-wide`}
          />
          <p className="text-[10px] text-slate-500">{t("ctr.wiz.ibanHint")}</p>
        </div>

        <h3 className="text-sm font-bold text-ink-900 pt-3">{t("ctr.wiz.residence")}</h3>
        <AddressFields value={address} onChange={setAddress} />

        <div className="pt-3 border-t border-ink-200 space-y-3">
          <PointCounter
            label={t("ctr.wiz.howMany")}
            hint={t("ctr.wiz.howManyHint")}
            value={count}
            max={MAX_POINTS}
            onChange={(n) => setCount(Math.max(1, n))}
          />
        </div>
      </fieldset>
      <button type="submit" disabled={busy} className={`w-full ${primaryButton}`}>
        {busy
          ? t("ctr.wiz.saving")
          : readOnly
            ? t("ctr.wiz.continue")
            : t("ctr.wiz.continueWith", { contracts: contractsCount(t, count) })}
      </button>
    </form>
  );
}

function PointCounter({
  label,
  hint,
  value,
  max,
  onChange,
}: {
  label: string;
  hint: string;
  value: number;
  max: number;
  onChange: (value: number) => void;
}) {
  const stepButton =
    "w-10 h-10 rounded-xl bg-slate-900/5 border border-slate-300 text-lg font-bold text-slate-900 hover:bg-slate-100 cursor-pointer disabled:opacity-40";
  return (
    <div className="space-y-2 p-3 rounded-xl bg-slate-900/5 border border-slate-200">
      <div>
        <label className={labelClass}>{label}</label>
        <p className="text-[10px] text-slate-500">{hint}</p>
      </div>
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => onChange(Math.max(1, value - 1))} disabled={value <= 1} className={stepButton}>
          −
        </button>
        <input
          type="number"
          min={1}
          max={max}
          value={value}
          onChange={(e) => onChange(Math.min(max, Math.max(1, Number(e.target.value) || 1)))}
          className="w-20 text-center rounded-xl glass-input px-2 py-2.5 text-base font-bold tabular-nums focus:border-brand-500"
        />
        <button type="button" onClick={() => onChange(Math.min(max, value + 1))} disabled={value >= max} className={stepButton}>
          +
        </button>
      </div>
    </div>
  );
}

// --- 3. Un'offerta per ogni contratto --------------------------------------------

function PackageOption({
  product,
  kind,
  selected,
  disabled,
  onChoose,
  onPreview,
}: {
  product: ProductCatalogRead;
  kind: string | null;
  selected: boolean;
  disabled: boolean;
  onChoose: () => void;
  onPreview: () => void;
}) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const v = product.current_version!;
  const prices = contractPrices(v, kind, { assumeBusinessWhenUnknown: false });
  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-xl border transition ${
        selected ? "bg-brand-500/10 border-brand-500/50" : " bg-white border-slate-200"
      }`}
    >
      <button onClick={onChoose} disabled={disabled} className="flex items-center gap-3 flex-1 min-w-0 text-left cursor-pointer disabled:cursor-default">
        <span className={`w-4 h-4 rounded-full border-2 shrink-0 ${selected ? "border-brand-500 bg-brand-500" : "border-slate-500"}`} />
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-slate-900 truncate">
            {v.name}
          </span>
          {/* Session 84: the yearly price in evidence, and underneath the rate
              from the product's own monthly price -- never yearly / 12. */}
          <span className="block text-sm font-bold text-slate-900 tabular-nums">
            {euro(prices.oneGo.grossCents)}
            <span className="ml-1 font-normal text-slate-500">
              {t("ctr.wiz.yearlyOneGo")}{prices.oneGo.vatCents > 0 ? ` · ${t("ctr.wiz.vatIncl")}` : ""}
            </span>
          </span>
          <span className="block text-slate-500 tabular-nums">
            {t("ctr.wiz.orMonthly", { monthly: euro(prices.monthlyGrossCents), total: euro(prices.instalments.grossCents) })}
            {v.contract_cashback_percentage > 0 ? ` · ${t("ctr.wiz.cashbackPct", { pct: v.contract_cashback_percentage })}` : ""}
          </span>
        </span>
      </button>
      <button onClick={onPreview} className="px-2.5 py-1 rounded-lg text-[11px] font-semibold text-brand-600 hover:bg-brand-500/10 cursor-pointer shrink-0">
        {t("ctr.wiz.preview")}
      </button>
    </div>
  );
}

function ContractsStep({
  request,
  packages,
  kind,
  busy,
  onPreview,
  onChoose,
  onChooseForAll,
  onBack,
  onNext,
}: {
  request: ContractRequestDetailRead;
  packages: ProductCatalogRead[];
  kind: string | null;
  busy: string | null;
  onPreview: (product: ProductCatalogRead, pointId: string | null) => void;
  onChoose: (pointId: string, versionId: string) => void;
  onChooseForAll: (versionId: string) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const editable = request.status === "DRAFT";
  const [openPoint, setOpenPoint] = useState<string | null>(null);
  const missing = request.points.filter((p) => !p.product_version_id).length;

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-bold text-ink-900">{t("ctr.wiz.chooseOfferEach")}</h3>
        <p className="text-xs text-ink-500 mt-1">
          {t("ctr.wiz.chooseOfferHint")}
        </p>
      </div>

      {editable && request.points.length > 1 && packages.length > 0 && (
        <BulkChoice packages={packages} busy={busy === "package-all"} onApply={onChooseForAll} />
      )}

      <div className="space-y-4">
        {request.points.map((point) => (
          <div key={point.id} className="p-4 rounded-2xl border border-slate-200 bg-white/70 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-bold text-ink-900">{pointCode(t, point)}</p>
              </div>
              {point.gross_amount_cents != null && (
                <span className="text-sm font-bold text-brand-600 tabular-nums shrink-0">{euro(point.gross_amount_cents)}</span>
              )}
            </div>

            {packages.length === 0 ? (
              <p className="text-xs text-amber-700">{t("ctr.wiz.noOffers")}</p>
            ) : (
              <div className="space-y-2">
                {packages.map((product) => (
                  <PackageOption
                    key={product.id}
                    product={product}
                    kind={kind}
                    selected={point.product_version_id === product.current_version!.id}
                    disabled={!editable || busy === `package-${point.id}`}
                    onChoose={() => editable && onChoose(point.id, product.current_version!.id)}
                    onPreview={() => onPreview(product, editable ? point.id : null)}
                  />
                ))}
                {point.product_version_id && !packages.some((p) => p.current_version!.id === point.product_version_id) && (
                  <p className="text-[11px] text-slate-400">{t("ctr.wiz.chosenContract", { name: point.product_name ?? "" })}</p>
                )}
              </div>
            )}

            <div className="pt-2 border-t border-slate-200">
              <button
                onClick={() => setOpenPoint(openPoint === point.id ? null : point.id)}
                className="text-xs font-semibold text-slate-600 hover:text-brand-600 cursor-pointer"
              >
                {openPoint === point.id ? "▾" : "▸"} {t("ctr.wiz.thisAttachments")}
              </button>
              {openPoint === point.id && (
                <div className="mt-3">
                  <ContractDocumentsPanel contractId={point.id} />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <button onClick={onBack} className={secondaryButton}>{t("ctr.wiz.backDocuments")}</button>
        <button onClick={onNext} className={`flex-1 ${primaryButton}`}>
          {missing > 0 ? t("ctr.wiz.continueMissing", { contracts: contractsCount(t, missing) }) : t("ctr.wiz.continueSummary")}
        </button>
      </div>
    </div>
  );
}

function BulkChoice({
  packages,
  busy,
  onApply,
}: {
  packages: ProductCatalogRead[];
  busy: boolean;
  onApply: (versionId: string) => void;
}) {
  const { t } = useI18n();
  const [choice, setChoice] = useState("");
  return (
    <div className="flex flex-col sm:flex-row gap-2 p-3 rounded-xl bg-slate-900/5 border border-slate-200">
      <select
        value={choice}
        onChange={(e) => setChoice(e.target.value)}
        className="flex-1 rounded-xl glass-input px-3 py-2 text-xs bg-white"
      >
        <option value="">{t("ctr.wiz.sameOfferAll")}</option>
        {packages.map((p) => (
          <option key={p.id} value={p.current_version!.id}>{p.current_version!.name}</option>
        ))}
      </select>
      <button onClick={() => choice && onApply(choice)} disabled={!choice || busy} className={secondaryButton}>
        {busy ? t("ctr.wiz.applying") : t("ctr.wiz.applyAll")}
      </button>
    </div>
  );
}

// --- 4. Riepilogo, invio e pagamento --------------------------------------------------

function SummaryStep({
  request,
  promoterMode,
  busy,
  onChooseContracts,
  onGoToDocuments,
  onSaveNotes,
  onSubmit,
  onCancelDraft,
  onClose,
}: {
  request: ContractRequestDetailRead;
  promoterMode: boolean;
  busy: string | null;
  onChooseContracts: () => void;
  onGoToDocuments: () => void;
  onSaveNotes: (notes: string | null) => Promise<ContractRequestDetailRead | null>;
  onSubmit: () => void;
  onCancelDraft: () => void;
  onClose: () => void;
}) {
  const { t, fmt } = useI18n();
  const euro = fmt.euro;
  const { data: sharedDocs } = useRequestDocuments(request.id);
  const [notesText, setNotesText] = useState(request.notes ?? "");
  const sharedMissing = (sharedDocs?.required ?? []).filter((r) => r.required !== false && r.document === null).length;
  const pointsMissingDocs = request.points.filter((p) => p.documents_missing > 0).length;
  const total = request.points.reduce((sum, p) => sum + (p.gross_amount_cents ?? 0), 0);
  const isDraft = request.status === "DRAFT";

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-bold text-slate-900">{isDraft ? t("ctr.wiz.summaryTitle") : t("ctr.wiz.submittedTitle")}</h3>
        <p className="text-xs text-slate-500 mt-1">
          {isDraft
            ? request.points.length === 1
              ? t("ctr.wiz.summaryIntroOne")
              : t("ctr.wiz.summaryIntroMany", { n: request.points.length })
            : t("ctr.wiz.submittedIntro")}
        </p>
      </div>

      <div className="p-3 rounded-xl bg-slate-900/5 border border-slate-200 text-slate-500">
        {t("ctr.f.holder")}: <strong className=" text-slate-800">{request.holder_name}</strong>
        {request.email ? ` · ${request.email}` : ""}
        {request.street ? ` · ${request.street}, ${request.postal_code} ${request.city} (${request.province})` : ""}
      </div>

      <div className="rounded-2xl border border-slate-200 divide-y divide-slate-200 overflow-hidden">
        {request.points.map((point) => (
          <div key={point.id} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-slate-900">{pointCode(t, point)}</p>
              <p className={`text-[11px] ${point.product_name ? " text-slate-500" : "text-amber-700"}`}>
                {point.product_name ?? t("ctr.wiz.offerNotChosen")}
              </p>
            </div>
            <span className="text-sm font-semibold text-slate-900 tabular-nums shrink-0">
              {point.gross_amount_cents != null ? euro(point.gross_amount_cents) : "—"}
            </span>
          </div>
        ))}
        <div className="flex items-center justify-between gap-3 px-4 py-3 bg-slate-900/5">
          <span className="text-sm font-bold text-slate-900">{t("ctr.pay.total")}</span>
          <span className="text-base font-extrabold text-brand-600 tabular-nums">{euro(total)}</span>
        </div>
      </div>

      {(sharedMissing > 0 || pointsMissingDocs > 0) && (
        <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-700 text-xs">
          {t("ctr.wiz.docsStillMissing")}
          {sharedMissing > 0 ? ` (${t("ctr.wiz.nIdentity", { n: sharedMissing })})` : ""}
          {pointsMissingDocs > 0 ? ` (${t("ctr.wiz.attachmentsOf", { contracts: contractsCount(t, pointsMissingDocs) })})` : ""}.{" "}
          {t("ctr.wiz.docsLaterHint")}
        </div>
      )}

      <NotesBox
        request={request}
        promoterMode={promoterMode}
        busy={busy === "notes"}
        text={notesText}
        setText={setNotesText}
        onSave={onSaveNotes}
      />

      {isDraft ? (
        <div className="space-y-2">
          {(request.documents_blocking ?? []).length > 0 ? (
            <button onClick={onGoToDocuments} className={`w-full ${primaryButton}`}>
              {t("ctr.wiz.uploadRequired", { docs: request.documents_blocking.join(", ") })}
            </button>
          ) : request.points_without_package > 0 ? (
            <button onClick={onChooseContracts} className={`w-full ${primaryButton}`}>
              {t("ctr.wiz.chooseMissingOffers")}
            </button>
          ) : (
            <button
              onClick={async () => {
                // Notes typed but not yet saved go with the pratica, not lost.
                if (notesText.trim() !== (request.notes ?? "")) {
                  if (!(await onSaveNotes(notesText.trim() || null))) return;
                }
                onSubmit();
              }}
              disabled={busy === "submit" || busy === "notes"}
              className={`w-full ${primaryButton}`}
            >
              {busy === "submit"
                ? t("ctr.wiz.submitting")
                : t("ctr.wiz.submit", { contracts: contractsCount(t, request.points.length) })}
            </button>
          )}
          <button onClick={onCancelDraft} disabled={busy === "cancel"} className="w-full text-xs text-slate-500 hover:text-rose-400 py-2 cursor-pointer">
            {t("ctr.wiz.deleteDraft")}
          </button>
        </div>
      ) : promoterMode ? (
        <div className="space-y-3">
          <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">
            {t("ctr.wiz.submittedPromoter")}
          </div>
          <PaymentLinkBox requestId={request.id} holderName={request.holder_name} />
          <button onClick={onClose} className={`w-full ${secondaryButton}`}>{t("common.close")}</button>
        </div>
      ) : (
        <ContractRequestPaymentPanel requestId={request.id} />
      )}
    </div>
  );
}

/** Session 88: il link da mandare al cliente. Aprendolo, fa il login e si
 *  ritrova già sul pagamento di questa pratica (customer-client-page legge
 *  ?pratica=, il login torna alla pagina di partenza con ?next=): non deve
 *  cercarla fra i suoi contratti. Il link da solo non apre niente a nessuno --
 *  serve comunque la sua password, e la pratica si vede solo dal suo account. */
function PaymentLinkBox({ requestId, holderName }: { requestId: string; holderName: string | null }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const link = `${origin}/customer?pratica=${requestId}`;
  const message = holderName
    ? t("ctr.wiz.waMessageNamed", { name: holderName.split(" ")[0] ?? holderName, link })
    : t("ctr.wiz.waMessage", { link });

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      // Browser senza permesso per gli appunti: il link resta selezionabile a mano.
      setCopied(false);
    }
  }

  return (
    <div className="p-4 rounded-2xl border-2 border-brand-500/50 bg-brand-500/10 space-y-3">
      <div>
        <p className="text-sm font-bold text-slate-900">{t("ctr.wiz.sendLinkTitle")}</p>
        <p className="text-xs text-slate-600 mt-1">
          {t("ctr.wiz.sendLinkHint")}
        </p>
      </div>
      <p className="px-3 py-2 rounded-lg bg-white font-mono text-brand-700 break-all select-all">
        {link}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <button onClick={copy} className={primaryButton}>
          {copied ? t("ctr.wiz.linkCopied") : t("ctr.wiz.copyLink")}
        </button>
        <a
          href={`https://wa.me/?text=${encodeURIComponent(message)}`}
          target="_blank"
          rel="noopener noreferrer"
          className={`${secondaryButton} text-center`}
        >
          {t("ctr.wiz.sendWhatsApp")}
        </a>
      </div>
    </div>
  );
}

/** «Note per l'amministrazione» (Session 83): the customer's message and,
    above all, the promoter's -- who is filling this in for somebody and
    knows things the paperwork doesn't say. Staff read it in Pratiche. */
function NotesBox({
  request,
  promoterMode,
  busy,
  text,
  setText,
  onSave,
}: {
  request: ContractRequestDetailRead;
  promoterMode: boolean;
  busy: boolean;
  /** Owned by the summary, so "Invia la pratica" can save what was typed. */
  text: string;
  setText: (text: string) => void;
  onSave: (notes: string | null) => Promise<ContractRequestDetailRead | null>;
}) {
  const { t } = useI18n();
  const [saved, setSaved] = useState(false);
  const editable = request.status === "DRAFT";

  if (!editable) {
    if (!request.notes) return null;
    return (
      <div className="p-3 rounded-xl bg-slate-900/5 border border-slate-200">
        <p className={labelClass}>{t("ctr.adm.notesForAdmin")}</p>
        <p className="text-sm text-slate-700 whitespace-pre-wrap mt-1">{request.notes}</p>
      </div>
    );
  }
  const dirty = text.trim() !== (request.notes ?? "");
  return (
    <div className="space-y-1.5">
      <label className={labelClass}>
        {t("ctr.adm.notesForAdmin")} <span className="normal-case font-normal text-slate-500">({t("common.optional").toLowerCase()})</span>
      </label>
      <textarea
        rows={3}
        maxLength={2000}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setSaved(false);
        }}
        onBlur={async () => {
          if (dirty && (await onSave(text.trim() || null))) setSaved(true);
        }}
        placeholder={
          promoterMode
            ? t("ctr.wiz.notesPlaceholderPromoter")
            : t("ctr.wiz.notesPlaceholderCustomer")
        }
        className={`${inputClass} resize-none`}
      />
      <p className="text-[10px] text-slate-500">
        {busy ? t("ctr.wiz.savingEllipsis") : saved ? t("ctr.wiz.notesSaved") : t("ctr.wiz.notesHint")}
      </p>
    </div>
  );
}
