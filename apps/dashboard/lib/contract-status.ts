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
      return " bg-slate-200/50 text-slate-500 border-slate-300";
    case "REJECTED":
    case "CANCELLED":
    case "SUSPENDED":
      return "bg-rose-500/10 text-rose-400 border-rose-500/20";
    case "UNDER_REVIEW":
      return "bg-sky-500/10 text-sky-400 border-sky-500/20";
    default:
      return "bg-amber-500/10 text-amber-700 border-amber-500/20";
  }
}

export const PAYMENT_PLAN_LABELS: Record<string, string> = {
  FULL: "Soluzione unica",
  INSTALMENTS_3: "3 rate mensili",
  MONTHLY_12: "12 rate mensili",
};

/** How a contract of a pratica is named on screen: its place in the
    pratica -- "Contratto 1", "Contratto 2". */
export function pointCode(point: { position?: number }): string {
  return point.position ? `Contratto ${point.position}` : "Contratto";
}

/** "3 contratti" -- how many contracts a pratica holds. */
export function pointsBreakdown(points: unknown[]): string {
  return points.length === 1 ? "1 contratto" : `${points.length} contratti`;
}

export function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString("it-IT") : "—";
}
