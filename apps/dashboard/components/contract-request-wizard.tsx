"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ContractDocumentsPanel, useRequestDocuments } from "@/components/contract-documents-panel";
import { ContractRequestPaymentPanel } from "@/components/contract-request-payment-panel";
import { FullScreenPanel } from "@/components/full-screen-panel";
import { ProductDetailModal } from "@/components/product-detail-modal";
import { friendlyApiError } from "@/lib/api-error";
import { ENERGY_POINT_LABELS, pointCode, pointsBreakdown } from "@/lib/contract-status";
import { contractPrices, formatEuroCents as euro, isBusinessCustomer, productAllowsCustomerKind } from "@/lib/product-audience";
import { PROVINCES } from "@/lib/provinces";
import type {
  BirthplaceRead,
  ContractRequestDetailRead,
  ContractRequestPointRead,
  ProductCatalogRead,
} from "@/lib/types";

type Step = "data" | "documents" | "contracts" | "summary";

const STEPS: { key: Step; label: string }[] = [
  { key: "data", label: "Dati" },
  { key: "documents", label: "Documenti" },
  { key: "contracts", label: "Contratti" },
  { key: "summary", label: "Riepilogo" },
];

/** Tetto sulla somma POD + PDR (MAX_POINTS_PER_REQUEST lato API). */
const MAX_POINTS = 50;
/** A POD (luce) takes only luce offers, a PDR (gas) only gas ones. */
const POINT_ENERGY: Record<"POD" | "PDR", string> = { POD: "ELECTRICITY", PDR: "GAS" };

function countsOf(points: ContractRequestPointRead[]): { pod: number; pdr: number } {
  const pdr = points.filter((p) => p.point_kind === "PDR").length;
  return { pod: points.length - pdr, pdr };
}

const inputClass = "w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500";
const labelClass = "text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block";
const primaryButton =
  "rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-orange-500/20 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed";
const secondaryButton =
  "rounded-xl bg-white/10 light:bg-slate-900/5 hover:bg-white/20 light:hover:bg-slate-900/10 px-4 py-2.5 text-xs font-semibold text-white light:text-slate-700 transition cursor-pointer disabled:opacity-50";

async function fetchRequest(id: string): Promise<ContractRequestDetailRead> {
  const res = await fetch(`/api/proxy/contract-requests/${id}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare il catalogo prodotti.");
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
 *  together with "quanti POD hai?" (luce) and "quanti PDR hai?" (gas). The
 *  pratica is created with those points already there; after the identity
 *  documents, each point only needs the contract to activate on it -- a POD
 *  chooses among luce offers only, a PDR among gas offers only. Each POD becomes its own contract -- its own
 *  review, its own commissions -- while documents and payment are dealt with
 *  once. No POD code is asked.
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
      every POD, freely changed per POD later. */
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
        a.current_version!.name.localeCompare(b.current_version!.name, "it")
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
      setActionError(err.message || "Operazione non riuscita.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  const customerName = [customer?.firstName, customer?.lastName].filter(Boolean).join(" ") || "il cliente";
  const title = promoterMode
    ? requestId
      ? `Pratica per ${request?.holder_name || customerName}`
      : `Nuova pratica per ${customerName}`
    : request
      ? `Pratica ${request.code}`
      : "Attiva nuovo contratto";
  const liveTotal = (request?.points ?? []).reduce((sum, p) => sum + (p.gross_amount_cents ?? 0), 0);
  const isDraft = !request || request.status === "DRAFT";

  return (
    <FullScreenPanel
      eyebrow={request ? `Pratica ${request.code}` : "Attiva nuovo contratto"}
      title={title}
      onClose={onClose}
      subtitle={
        <div className="space-y-2">
          <div className="flex items-center gap-1 overflow-x-auto pb-0.5">
            {STEPS.map((s, i) => {
              const current = s.key === step;
              // Past the documents only once identity, bill (and visura /
              // P.IVA for a business) are in -- a draft only: a sent
              // pratica is just being looked at.
              const documentsDone = !isDraft || (request?.documents_blocking ?? []).length === 0;
              const reachable =
                s.key === "data" ||
                (Boolean(requestId) && (s.key === "documents" || documentsDone));
              return (
                <button
                  key={s.key}
                  onClick={() => reachable && goTo(s.key)}
                  disabled={!reachable}
                  className={`flex items-center gap-1.5 px-2 py-1 rounded-lg shrink-0 transition ${
                    current ? "bg-orange-600/15" : reachable ? "hover:bg-white/5 cursor-pointer" : "opacity-50"
                  }`}
                >
                  <span
                    className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                      current ? "bg-orange-600 text-white" : "bg-white/10 light:bg-slate-900/10 text-slate-400"
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span className={`text-[11px] font-semibold ${current ? "text-white light:text-slate-900" : "text-slate-500"}`}>
                    {s.label}
                  </span>
                </button>
              );
            })}
          </div>
          {request && request.points.length > 0 && (
            <p className="text-[11px] text-slate-400 light:text-slate-500">
              {pointsBreakdown(request.points)}
              {liveTotal > 0 && <> · totale <strong className="text-orange-400 tabular-nums">{euro(liveTotal)}</strong></>}
            </p>
          )}
        </div>
      }
    >
      {loadError && <p className="text-sm text-rose-400">{(loadError as Error).message}</p>}
      {actionError && (
        <div className="mb-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{actionError}</div>
      )}
      {step === null && !loadError && <div className="h-40 rounded-2xl bg-white/5 light:bg-slate-900/5 animate-pulse" />}

      {step === "data" && fiscalWarning && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 space-y-2">
          <p className="text-xs font-semibold text-amber-300 light:text-amber-700">
            Attenzione: il codice fiscale non sembra tornare con i dati scritti
          </p>
          <ul className="list-disc pl-5 text-xs text-amber-200 light:text-amber-800 space-y-0.5">
            {fiscalWarning.map((p) => <li key={p}>{p}</li>)}
          </ul>
          <p className="text-[11px] text-slate-400 light:text-slate-600">
            I dati sono salvati. Controlla nome, cognome, data e luogo di nascita e il codice fiscale (nome e cognome
            invertiti?) e premi di nuovo «Continua», oppure vai avanti così.
          </p>
          <button
            type="button"
            onClick={() => {
              setFiscalWarning(null);
              goTo("documents");
            }}
            className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-xs font-semibold text-white transition cursor-pointer"
          >
            Continua comunque
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
          initialEnergy={initialProduct?.energy_type ?? null}
          busy={busy === "data"}
          onSubmit={async (body, counts) => {
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
                  pod_count: counts.pod,
                  pdr_count: counts.pdr,
                  customer_id: customer?.id ?? null,
                  producer_agent_id: producerAgentId ?? null,
                  product_version_id: initialProduct?.current_version?.id ?? null,
                }),
              });
            } else {
              detail = await mutate("data", `/${request.id}`, { method: "PATCH", body: JSON.stringify(body) });
              const now = detail ? countsOf(detail.points) : null;
              if (detail && now && (now.pod !== counts.pod || now.pdr !== counts.pdr)) {
                detail = await mutate("data", `/${request.id}/points-count`, {
                  method: "PUT",
                  body: JSON.stringify({ pod_count: counts.pod, pdr_count: counts.pdr }),
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
            <h3 className="text-sm font-bold text-white light:text-slate-900">Documenti</h3>
            <p className="text-xs text-slate-400 light:text-slate-500 mt-1">
              Si caricano una volta sola e valgono per tutti i punti della pratica ({pointsBreakdown(request.points)}).
              Ogni documento può avere più pagine: fotografa fronte e retro del documento e tutte le pagine della
              bolletta (fino a 20).
            </p>
          </div>
          <ContractDocumentsPanel requestId={request.id} />
          {isDraft && (request.documents_blocking ?? []).length > 0 && (
            <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">
              Per andare avanti carica almeno una pagina di: <strong>{request.documents_blocking.join(", ")}</strong>.
            </div>
          )}
          <div className="flex gap-2">
            <button onClick={() => goTo("data")} className={secondaryButton}>← Dati</button>
            <button
              onClick={() => goTo("contracts")}
              disabled={isDraft && (request.documents_blocking ?? []).length > 0}
              className={`flex-1 ${primaryButton}`}
            >
              Continua: scegli il contratto per ogni punto
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
          onMoveAddress={(pointId, address) =>
            mutate(`address-${pointId}`, `/${request.id}/points/${pointId}/address`, {
              method: "PATCH",
              body: JSON.stringify(address),
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
            if (!window.confirm("Eliminare questa pratica in bozza?")) return;
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
              ? `Scegli per questo ${request?.points.find((p) => p.id === preview.pointId)?.point_kind ?? "punto"}`
              : "Chiudi"
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

// --- 1. Dati: intestatario, indirizzo, quanti POD -------------------------------------

function AddressFields({ value, onChange }: { value: AddressValue; onChange: (value: AddressValue) => void }) {
  return (
    <>
      <div className="space-y-1">
        <label className={labelClass}>Indirizzo di fornitura</label>
        <input
          required
          value={value.street}
          onChange={(e) => onChange({ ...value, street: e.target.value })}
          placeholder="Via/Piazza e numero civico"
          className={inputClass}
        />
      </div>
      <div className="grid grid-cols-6 gap-2">
        <div className="col-span-3 space-y-1">
          <label className={labelClass}>Città</label>
          <input required value={value.city} onChange={(e) => onChange({ ...value, city: e.target.value })} className={inputClass} />
        </div>
        <div className="col-span-1 space-y-1">
          <label className={labelClass}>Prov.</label>
          <select
            required
            value={value.province}
            onChange={(e) => onChange({ ...value, province: e.target.value })}
            className="w-full rounded-xl glass-input px-1.5 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
          >
            <option value="" disabled>--</option>
            {PROVINCES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div className="col-span-2 space-y-1">
          <label className={labelClass}>CAP</label>
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
  const label = (p: BirthplaceRead) => `${p.name} (${p.foreign ? "estero" : p.province})`;

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
        placeholder="Comune, o Stato se all'estero"
        autoComplete="off"
        className={inputClass}
      />
      {open && !value && query.length >= 2 && (
        <div className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto rounded-xl border border-white/10 light:border-slate-200 bg-slate-900 light:bg-white shadow-xl">
          {options.length === 0 ? (
            <p className="px-3 py-2 text-xs text-slate-500">{isFetching ? "Cerco…" : "Nessun comune o Stato con questo nome"}</p>
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
                className="w-full text-left px-3 py-2 text-sm text-slate-200 light:text-slate-700 hover:bg-white/5 light:hover:bg-slate-900/5 cursor-pointer"
              >
                {label(p)}
                {!p.active && (
                  <span className="ml-1 text-[10px] text-slate-500">
                    comune soppresso{p.until ? ` nel ${p.until}` : ""}
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
  initialEnergy,
  busy,
  onSubmit,
}: {
  request: ContractRequestDetailRead | undefined;
  defaults: { firstName: string; lastName: string; email: string; pec: string; fiscalCode: string };
  promoterMode: boolean;
  /** The customer's own kind: what "Il contratto è per" starts from. */
  customerKind: string | null;
  /** Energy of the offer the customer started from in the catalog: a gas
      offer starts the pratica at 0 POD and 1 PDR. */
  initialEnergy: string | null;
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
    counts: { pod: number; pdr: number }
  ) => void;
}) {
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
  const [counts, setCounts] = useState<{ pod: number; pdr: number }>(() =>
    request && request.points.length > 0
      ? countsOf(request.points)
      : initialEnergy === "GAS"
        ? { pod: 0, pdr: 1 }
        : { pod: 1, pdr: 0 }
  );
  const total = counts.pod + counts.pdr;

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
          counts
        );
      }}
      className="space-y-4"
    >
      <fieldset disabled={readOnly} className="space-y-4">
        <div className="space-y-1">
          <label className={labelClass}>Il contratto è per</label>
          <select
            value={business ? businessKind : "PRIVATE"}
            onChange={(e) => setHolderKind(e.target.value)}
            className={`${inputClass} bg-slate-900 light:bg-white`}
          >
            <option value="PRIVATE">Privato</option>
            <option value={businessKind}>Azienda / Partita IVA</option>
          </select>
        </div>

        {business && (
          <div className="space-y-1">
            <label className={labelClass}>Ragione sociale</label>
            <input required value={companyName} onChange={(e) => setCompanyName(e.target.value)} autoComplete="organization" className={inputClass} />
          </div>
        )}

        <h3 className="text-sm font-bold text-white light:text-slate-900">
          {business ? "Legale rappresentante" : "Intestatario del contratto"}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className={labelClass}>Nome</label>
            <input required value={firstName} onChange={(e) => setFirstName(e.target.value)} autoComplete="given-name" className={inputClass} />
          </div>
          <div className="space-y-1">
            <label className={labelClass}>Cognome</label>
            <input required value={lastName} onChange={(e) => setLastName(e.target.value)} autoComplete="family-name" className={inputClass} />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className={labelClass}>Data di nascita</label>
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
            <label className={labelClass}>Luogo di nascita</label>
            <BirthplaceInput
              value={birthPlace}
              onChange={(place) => {
                setBirthPlace(place);
                if (place) setPlaceMissing(false);
              }}
            />
            {placeMissing && <p className="text-[10px] text-rose-400">Scegli il luogo dall&apos;elenco che compare mentre scrivi.</p>}
          </div>
        </div>
        <div className="space-y-1">
          <label className={labelClass}>
            {business ? "Codice fiscale del legale rappresentante" : "Codice fiscale"}
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
            Lo controlliamo con nome, cognome, data e luogo di nascita: se qualcosa non torna te lo diciamo subito.
          </p>
        </div>
        <div className="space-y-1">
          <label className={labelClass}>Email</label>
          <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="nome@esempio.it" className={inputClass} />
          <p className="text-[10px] text-slate-500">Email di riferimento per questi contratti, anche diversa da quella dell&apos;account.</p>
        </div>
        <div className="space-y-1">
          <label className={labelClass}>
            PEC{" "}
            {business ? (
              <span className="normal-case font-semibold text-orange-400">(obbligatoria per le aziende)</span>
            ) : (
              <span className="normal-case font-normal text-slate-500">(facoltativa)</span>
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
              Per un contratto aziendale servono sia l&apos;email sia la PEC: è dove l&apos;azienda riceve le comunicazioni ufficiali.
            </p>
          )}
        </div>
        <div className="space-y-1">
          <label className={labelClass}>
            IBAN per addebito{promoterMode && <span className="normal-case font-normal text-slate-500"> (facoltativo)</span>}
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
          <p className="text-[10px] text-slate-500">Potrai modificarlo in qualsiasi momento da “I miei Contratti”.</p>
        </div>

        <h3 className="text-sm font-bold text-white light:text-slate-900 pt-3">Punto di fornitura</h3>
        <AddressFields value={address} onChange={setAddress} />

        <div className="pt-3 border-t border-white/5 light:border-slate-200 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <PointCounter
              label="Quanti POD hai?"
              hint="Contatori della luce"
              value={counts.pod}
              max={MAX_POINTS - counts.pdr}
              onChange={(pod) => setCounts((c) => ({ ...c, pod }))}
            />
            <PointCounter
              label="Quanti PDR hai?"
              hint="Contatori del gas"
              value={counts.pdr}
              max={MAX_POINTS - counts.pod}
              onChange={(pdr) => setCounts((c) => ({ ...c, pdr }))}
            />
          </div>
          <p className="text-[10px] text-slate-500">
            Ogni POD e ogni PDR diventa un contratto a sé: tra poco sceglierai quale attivare su ciascuno — offerte
            luce per i POD, offerte gas per i PDR.
          </p>
          {total === 0 && <p className="text-xs text-amber-400">Serve almeno un POD o un PDR.</p>}
        </div>
      </fieldset>
      <button type="submit" disabled={busy || (!readOnly && total === 0)} className={`w-full ${primaryButton}`}>
        {busy
          ? "Salvataggio..."
          : readOnly
            ? "Continua"
            : `Continua con ${[counts.pod > 0 ? `${counts.pod} POD` : null, counts.pdr > 0 ? `${counts.pdr} PDR` : null]
                .filter(Boolean)
                .join(" e ") || "0 punti"}: documenti`}
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
    "w-10 h-10 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-300 text-lg font-bold text-white light:text-slate-900 hover:bg-white/10 cursor-pointer disabled:opacity-40";
  return (
    <div className="space-y-2 p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
      <div>
        <label className={labelClass}>{label}</label>
        <p className="text-[10px] text-slate-500">{hint}</p>
      </div>
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => onChange(Math.max(0, value - 1))} disabled={value <= 0} className={stepButton}>
          −
        </button>
        <input
          type="number"
          min={0}
          max={max}
          value={value}
          onChange={(e) => onChange(Math.min(max, Math.max(0, Number(e.target.value) || 0)))}
          className="w-20 text-center rounded-xl glass-input px-2 py-2.5 text-base font-bold tabular-nums focus:border-orange-500"
        />
        <button type="button" onClick={() => onChange(Math.min(max, value + 1))} disabled={value >= max} className={stepButton}>
          +
        </button>
      </div>
    </div>
  );
}

// --- 3. Un contratto per ogni POD --------------------------------------------------

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
  const v = product.current_version!;
  const prices = contractPrices(v, kind, { assumeBusinessWhenUnknown: false });
  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-xl border transition ${
        selected ? "bg-orange-500/10 border-orange-500/50" : "bg-white/5 light:bg-white border-white/10 light:border-slate-200"
      }`}
    >
      <button onClick={onChoose} disabled={disabled} className="flex items-center gap-3 flex-1 min-w-0 text-left cursor-pointer disabled:cursor-default">
        <span className={`w-4 h-4 rounded-full border-2 shrink-0 ${selected ? "border-orange-500 bg-orange-500" : "border-slate-500"}`} />
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-white light:text-slate-900 truncate">
            {v.name}
            {product.energy_type && ENERGY_POINT_LABELS[product.energy_type] && (
              <span className="ml-2 text-[10px] font-semibold text-slate-500 uppercase">{ENERGY_POINT_LABELS[product.energy_type]}</span>
            )}
          </span>
          {/* Session 84: the yearly price in evidence, and underneath the rate
              from the product's own monthly price -- never yearly / 12. */}
          <span className="block text-sm font-bold text-white light:text-slate-900 tabular-nums">
            {euro(prices.oneGo.grossCents)}
            <span className="ml-1 text-[11px] font-normal text-slate-400 light:text-slate-500">
              annuale, unica soluzione{prices.oneGo.vatCents > 0 ? " · IVA incl." : ""}
            </span>
          </span>
          <span className="block text-[11px] text-slate-400 light:text-slate-500 tabular-nums">
            oppure {euro(prices.monthlyGrossCents)} × 12 mesi = {euro(prices.instalments.grossCents)}
            {v.contract_cashback_percentage > 0 ? ` · cashback ${v.contract_cashback_percentage}%` : ""}
          </span>
          <span className="block text-[11px] font-bold text-amber-400 light:text-amber-700 mt-0.5">
            ATTENZIONE: scegli Klarna quando effettui il pagamento
          </span>
        </span>
      </button>
      <button onClick={onPreview} className="px-2.5 py-1 rounded-lg text-[11px] font-semibold text-orange-400 hover:bg-orange-500/10 cursor-pointer shrink-0">
        Anteprima
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
  onMoveAddress,
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
  onMoveAddress: (pointId: string, address: AddressValue) => Promise<ContractRequestDetailRead | null>;
  onBack: () => void;
  onNext: () => void;
}) {
  const editable = request.status === "DRAFT";
  const [openPoint, setOpenPoint] = useState<string | null>(null);
  const [movingPoint, setMovingPoint] = useState<string | null>(null);
  const missing = request.points.filter((p) => !p.product_version_id).length;
  // Un POD sceglie solo tra le offerte luce, un PDR solo tra quelle gas.
  const packagesFor = (kind: "POD" | "PDR") => packages.filter((p) => p.energy_type === POINT_ENERGY[kind]);
  const counts = countsOf(request.points);

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-bold text-white light:text-slate-900">Scegli il contratto per ogni punto</h3>
        <p className="text-xs text-slate-400 light:text-slate-500 mt-1">
          Ogni POD e ogni PDR è un contratto a sé: puoi scegliere contratti diversi. Per i POD trovi le offerte luce,
          per i PDR quelle gas. Apri “Anteprima” per leggerlo prima di sceglierlo.
        </p>
      </div>

      {editable &&
        (["POD", "PDR"] as const).map((kind) =>
          (kind === "POD" ? counts.pod : counts.pdr) > 1 && packagesFor(kind).length > 0 ? (
            <BulkChoice
              key={kind}
              kind={kind}
              packages={packagesFor(kind)}
              busy={busy === "package-all"}
              onApply={onChooseForAll}
            />
          ) : null
        )}

      <div className="space-y-4">
        {request.points.map((point) => (
          <div key={point.id} className="p-4 rounded-2xl border border-white/10 light:border-slate-200 bg-slate-950/40 light:bg-white/70 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-bold text-white light:text-slate-900">
                  {pointCode(point)}
                  {point.energy_type && ENERGY_POINT_LABELS[point.energy_type] && (
                    <span className="ml-2 text-[10px] font-semibold text-slate-500 uppercase">{ENERGY_POINT_LABELS[point.energy_type]}</span>
                  )}
                </p>
                <p className="text-[11px] text-slate-400 light:text-slate-500 truncate">
                  {[point.street, point.city].filter(Boolean).join(", ")}
                  {editable && (
                    <button
                      onClick={() => setMovingPoint(movingPoint === point.id ? null : point.id)}
                      className="ml-2 font-semibold text-orange-400 hover:text-orange-300 cursor-pointer"
                    >
                      {movingPoint === point.id ? "Annulla" : "Indirizzo diverso?"}
                    </button>
                  )}
                </p>
              </div>
              {point.gross_amount_cents != null && (
                <span className="text-sm font-bold text-orange-400 tabular-nums shrink-0">{euro(point.gross_amount_cents)}</span>
              )}
            </div>

            {movingPoint === point.id && (
              <MoveAddressForm
                point={point}
                busy={busy === `address-${point.id}`}
                onSubmit={async (address) => {
                  if (await onMoveAddress(point.id, address)) setMovingPoint(null);
                }}
              />
            )}

            {packagesFor(point.point_kind).length === 0 ? (
              <p className="text-xs text-amber-400">
                Nessuna offerta {point.point_kind === "PDR" ? "gas" : "luce"} disponibile al momento.
              </p>
            ) : (
              <div className="space-y-2">
                {packagesFor(point.point_kind).map((product) => (
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
                {point.product_version_id && !packagesFor(point.point_kind).some((p) => p.current_version!.id === point.product_version_id) && (
                  <p className="text-[11px] text-slate-400">Contratto scelto: {point.product_name}</p>
                )}
              </div>
            )}

            <div className="pt-2 border-t border-white/5 light:border-slate-200">
              <button
                onClick={() => setOpenPoint(openPoint === point.id ? null : point.id)}
                className="text-xs font-semibold text-slate-300 light:text-slate-600 hover:text-orange-400 cursor-pointer"
              >
                {openPoint === point.id ? "▾" : "▸"} Allegati di questo {point.point_kind} (bolletta, foto del contatore)
              </button>
              {openPoint === point.id && (
                <div className="mt-3">
                  <ContractDocumentsPanel contractId={point.id} onlyTypes={["UTILITY_BILL"]} />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <button onClick={onBack} className={secondaryButton}>← Documenti</button>
        <button onClick={onNext} className={`flex-1 ${primaryButton}`}>
          {missing > 0 ? `Continua (${missing} ${missing === 1 ? "punto" : "punti"} senza contratto)` : "Continua: riepilogo"}
        </button>
      </div>
    </div>
  );
}

function BulkChoice({
  kind,
  packages,
  busy,
  onApply,
}: {
  kind: "POD" | "PDR";
  packages: ProductCatalogRead[];
  busy: boolean;
  onApply: (versionId: string) => void;
}) {
  const [choice, setChoice] = useState("");
  return (
    <div className="flex flex-col sm:flex-row gap-2 p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
      <select
        value={choice}
        onChange={(e) => setChoice(e.target.value)}
        className="flex-1 rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 light:bg-white"
      >
        <option value="">
          Stessa offerta {kind === "PDR" ? "gas per tutti i PDR" : "luce per tutti i POD"}…
        </option>
        {packages.map((p) => (
          <option key={p.id} value={p.current_version!.id}>{p.current_version!.name}</option>
        ))}
      </select>
      <button onClick={() => choice && onApply(choice)} disabled={!choice || busy} className={secondaryButton}>
        {busy ? "Applicazione..." : `Applica a tutti i ${kind}`}
      </button>
    </div>
  );
}

function MoveAddressForm({
  point,
  busy,
  onSubmit,
}: {
  point: ContractRequestPointRead;
  busy: boolean;
  onSubmit: (address: AddressValue) => void;
}) {
  const [address, setAddress] = useState<AddressValue>({
    street: point.street ?? "",
    city: point.city ?? "",
    province: point.province ?? "",
    postal_code: point.postal_code ?? "",
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ ...address, province: address.province.toUpperCase() });
      }}
      className="space-y-2 p-3 rounded-xl border border-orange-500/25 bg-orange-500/5"
    >
      <AddressFields value={address} onChange={setAddress} />
      <button type="submit" disabled={busy} className="w-full rounded-xl bg-orange-600 hover:bg-orange-500 px-4 py-2 text-xs font-bold text-white cursor-pointer disabled:opacity-50">
        {busy ? "Salvataggio..." : `Salva l'indirizzo di questo ${point.point_kind}`}
      </button>
    </form>
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
  const { data: sharedDocs } = useRequestDocuments(request.id);
  const [notesText, setNotesText] = useState(request.notes ?? "");
  const sharedMissing = (sharedDocs?.required ?? []).filter((r) => r.required !== false && r.document === null).length;
  const pointsMissingDocs = request.points.filter((p) => p.documents_missing > 0).length;
  const total = request.points.reduce((sum, p) => sum + (p.gross_amount_cents ?? 0), 0);
  const isDraft = request.status === "DRAFT";

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-bold text-white light:text-slate-900">{isDraft ? "Riepilogo della pratica" : "Pratica inviata"}</h3>
        <p className="text-xs text-slate-400 light:text-slate-500 mt-1">
          {isDraft
            ? `Controlla i contratti scelti. Inviando la pratica si aprono ${request.points.length} ${
                request.points.length === 1 ? "contratto" : "contratti indipendenti"
              }, ognuno verificato e attivato per conto suo.`
            : "Ogni contratto viene verificato dall'amministrazione per conto suo e si attiva appena i suoi documenti sono approvati."}
        </p>
      </div>

      <div className="p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200 text-[11px] text-slate-400 light:text-slate-500">
        Intestatario: <strong className="text-slate-200 light:text-slate-800">{request.holder_name}</strong>
        {request.email ? ` · ${request.email}` : ""}
        {request.street ? ` · ${request.street}, ${request.postal_code} ${request.city} (${request.province})` : ""}
      </div>

      <div className="rounded-2xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200 overflow-hidden">
        {request.points.map((point) => (
          <div key={point.id} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white light:text-slate-900">{pointCode(point)}</p>
              <p className={`text-[11px] ${point.product_name ? "text-slate-400 light:text-slate-500" : "text-amber-400"}`}>
                {point.product_name ?? "Contratto non ancora scelto"}
                {point.street && point.street !== request.street ? ` · ${point.street}, ${point.city}` : ""}
              </p>
            </div>
            <span className="text-sm font-semibold text-white light:text-slate-900 tabular-nums shrink-0">
              {point.gross_amount_cents != null ? euro(point.gross_amount_cents) : "—"}
            </span>
          </div>
        ))}
        <div className="flex items-center justify-between gap-3 px-4 py-3 bg-white/5 light:bg-slate-900/5">
          <span className="text-sm font-bold text-white light:text-slate-900">Totale</span>
          <span className="text-base font-extrabold text-orange-400 tabular-nums">{euro(total)}</span>
        </div>
      </div>

      {(sharedMissing > 0 || pointsMissingDocs > 0) && (
        <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">
          Mancano ancora dei documenti
          {sharedMissing > 0 ? ` (${sharedMissing} d'identità)` : ""}
          {pointsMissingDocs > 0 ? ` (bolletta di ${pointsMissingDocs} ${pointsMissingDocs === 1 ? "punto" : "punti"})` : ""}. Puoi inviare e pagare lo stesso e
          caricarli dopo: ogni contratto si attiva quando i suoi documenti sono approvati.
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
              Carica i documenti obbligatori: {request.documents_blocking.join(", ")}
            </button>
          ) : request.points_without_package > 0 ? (
            <button onClick={onChooseContracts} className={`w-full ${primaryButton}`}>
              Scegli il contratto per i punti mancanti
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
                ? "Invio in corso..."
                : `Invia la pratica (${request.points.length} ${request.points.length === 1 ? "contratto" : "contratti"})`}
            </button>
          )}
          <button onClick={onCancelDraft} disabled={busy === "cancel"} className="w-full text-xs text-slate-500 hover:text-rose-400 py-2 cursor-pointer">
            Elimina questa bozza
          </button>
        </div>
      ) : promoterMode ? (
        <div className="space-y-3">
          <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">
            Pratica inviata. Il cliente può pagarla dal suo account, in “I miei Contratti”, anche prima che i documenti
            siano approvati.
          </div>
          <PaymentLinkBox requestId={request.id} holderName={request.holder_name} />
          <button onClick={onClose} className={`w-full ${secondaryButton}`}>Chiudi</button>
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
  const [copied, setCopied] = useState(false);
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const link = `${origin}/customer?pratica=${requestId}`;
  const message =
    `Ciao${holderName ? ` ${holderName.split(" ")[0]}` : ""}, la tua pratica Jav è pronta. ` +
    `Entra con la tua email e password da questo link e trovi subito il pagamento: ${link}`;

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
    <div className="p-4 rounded-2xl border-2 border-orange-500/50 bg-orange-500/10 space-y-3">
      <div>
        <p className="text-sm font-bold text-white light:text-slate-900">Manda questo link al tuo cliente</p>
        <p className="text-xs text-slate-300 light:text-slate-600 mt-1">
          Aprendolo fa il login con la sua email e password e si trova direttamente sul pagamento di questa pratica.
        </p>
      </div>
      <p className="px-3 py-2 rounded-lg bg-black/30 light:bg-white text-[11px] font-mono text-orange-300 light:text-orange-700 break-all select-all">
        {link}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <button onClick={copy} className={primaryButton}>
          {copied ? "Link copiato ✓" : "Copia link"}
        </button>
        <a
          href={`https://wa.me/?text=${encodeURIComponent(message)}`}
          target="_blank"
          rel="noopener noreferrer"
          className={`${secondaryButton} text-center`}
        >
          Invia su WhatsApp
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
  const [saved, setSaved] = useState(false);
  const editable = request.status === "DRAFT";

  if (!editable) {
    if (!request.notes) return null;
    return (
      <div className="p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
        <p className={labelClass}>Note per l&apos;amministrazione</p>
        <p className="text-sm text-slate-200 light:text-slate-700 whitespace-pre-wrap mt-1">{request.notes}</p>
      </div>
    );
  }
  const dirty = text.trim() !== (request.notes ?? "");
  return (
    <div className="space-y-1.5">
      <label className={labelClass}>
        Note per l&apos;amministrazione <span className="normal-case font-normal text-slate-500">(facoltative)</span>
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
            ? "Tutto quello che l'amministrazione deve sapere su questo cliente o su questa pratica…"
            : "Un messaggio per noi: orari in cui chiamarti, dettagli sulla fornitura…"
        }
        className={`${inputClass} resize-none`}
      />
      <p className="text-[10px] text-slate-500">
        {busy ? "Salvataggio…" : saved ? "Note salvate." : "Le legge l'amministrazione quando verifica la pratica."}
      </p>
    </div>
  );
}
