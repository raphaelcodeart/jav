/** Contract status labels and colours, shared by the pratica screens
    (Session 52). The older contract screens keep their own copies of the
    same table; these words must stay identical to theirs. */

export const CONTRACT_STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bozza",
  SUBMITTED: "Inviata",
  DOCUMENTS_PENDING: "Documenti mancanti",
  UNDER_REVIEW: "In revisione",
  APPROVED: "Approvata",
  PAYMENT_PENDING: "In attesa di pagamento",
  PAID: "Pagata",
  ACTIVATION_PENDING: "In attivazione",
  ACTIVE: "Attiva",
  SUSPENDED: "Sospesa",
  CANCELLED: "Cessata",
  EXPIRED: "Scaduta",
  RENEWED: "Rinnovata",
  REJECTED: "Respinta",
};

export function contractStatusBadge(status: string): string {
  switch (status) {
    case "ACTIVE":
    case "RENEWED":
      return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
    case "DRAFT":
      return "bg-slate-500/10 light:bg-slate-200/50 text-slate-400 light:text-slate-500 border-slate-500/20 light:border-slate-300";
    case "REJECTED":
    case "CANCELLED":
    case "SUSPENDED":
      return "bg-rose-500/10 text-rose-400 border-rose-500/20";
    case "UNDER_REVIEW":
      return "bg-sky-500/10 text-sky-400 border-sky-500/20";
    default:
      return "bg-amber-500/10 text-amber-400 border-amber-500/20";
  }
}

export const PAYMENT_PLAN_LABELS: Record<string, string> = {
  FULL: "Soluzione unica",
  INSTALMENTS_3: "3 rate mensili",
  MONTHLY_12: "12 rate mensili",
};

export const ENERGY_POINT_LABELS: Record<string, string> = {
  ELECTRICITY: "Luce",
  GAS: "Gas",
};

/** How a supply point is named on screen: its code when one was recorded
    (contracts from before Session 53), otherwise its place among the points
    of its kind in the pratica -- "POD 1", "POD 2", "PDR 1" -- since the code
    is no longer asked. A POD is luce, a PDR gas. */
export function pointCode(point: {
  pod_code?: string | null;
  pdr_code?: string | null;
  position?: number;
  point_kind?: string | null;
  energy_type?: string | null;
}): string {
  if (point.pod_code) return `POD ${point.pod_code}`;
  if (point.pdr_code) return `PDR ${point.pdr_code}`;
  const kind = point.point_kind ?? (point.energy_type === "GAS" ? "PDR" : "POD");
  return point.position ? `${kind} ${point.position}` : "Punto di fornitura";
}

/** "2 POD · 1 PDR" -- how many points of each kind a pratica has. */
export function pointsBreakdown(points: { point_kind?: string | null }[]): string {
  const pdr = points.filter((p) => p.point_kind === "PDR").length;
  const pod = points.length - pdr;
  return [pod > 0 ? `${pod} POD` : null, pdr > 0 ? `${pdr} PDR` : null].filter(Boolean).join(" · ");
}

export function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString("it-IT") : "—";
}
