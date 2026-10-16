// Mirrors the Pydantic response schemas in apps/api/app/domains/*/schemas.py.
// Kept hand-written for this vertical slice; generating from the OpenAPI schema
// (packages/api-client) is tracked as Phase F follow-up work.

export type ContractRead = {
  id: string;
  customer_id: string;
  /** Null only while the contract is a draft line of a pratica whose
      package has not been chosen yet (Session 52). */
  product_version_id: string | null;
  /** The pratica this contract was filled in and paid with. */
  contract_request_id?: string | null;
  status: string;
  notes: string | null;
  created_at: string;
  activated_at: string | null;
  expires_at: string | null;
  product_name: string | null;
  iban: string | null;
  email: string | null;
  /** Intestatario as typed in the activation wizard (Session 49). Null on
      older and staff-created contracts. */
  holder_first_name: string | null;
  holder_last_name: string | null;
  pec: string | null;

  // --- Chi lo ha costruito (Session 38) ---
  /** CUSTOMER / PROMOTER / ADMIN. Null on contracts created before this
      existed -- the creator is still in the status history. */
  created_by_role: string | null;
  /** Set ONLY when a promoter completed the contract in place of the
      customer. Null means the customer signed up themselves -- which is why
      the admin screen can say which of the two happened instead of guessing
      from whoever earns the commission. */
  activated_by_promoter_id: string | null;
  activated_by_promoter_name: string | null;
  /** The promoter who originally brought this customer in -- a different
      person whenever somebody else assisted them. */
  first_referrer_agent_id: string | null;
  first_referrer_name: string | null;

  // --- Economia congelata alla creazione ---
  customer_kind: string | null;
  net_amount_cents: number | null;
  /** Percentage points (22.0), not a fraction. 0 for a private customer. */
  vat_rate: number | null;
  vat_amount_cents: number | null;
  gross_amount_cents: number | null;

  // --- Pagamento ---
  payment_plan: string | null;
  payment_method: string | null;
  paid_at: string | null;
  terms_accepted_at: string | null;
  terms_version: string | null;
};

// --- Pratica di attivazione (Session 52) ---------------------------------

/** One row of every pratiche list. Every count is derived server-side from
    the contracts, never stored twice. */
export type ContractRequestSummaryRead = {
  /** The message left for the administration (Session 83). */
  notes?: string | null;
  id: string;
  /** First 8 characters of the id, upper case -- how a pratica is named aloud. */
  code: string;
  customer_id: string;
  customer_name: string | null;
  /** The pratica's kind (Session 85: chosen in its data form, else the customer's). */
  customer_kind: string | null;
  holder_kind: string | null;
  /** DRAFT / SUBMITTED / CANCELLED */
  status: string;
  created_at: string;
  submitted_at: string | null;
  updated_at: string | null;
  created_by_role: string | null;
  activated_by_promoter_id: string | null;
  activated_by_promoter_name: string | null;
  holder_name: string | null;
  points_total: number;
  points_by_status: Record<string, number>;
  points_active: number;
  points_to_review: number;
  points_documents_pending: number;
  points_without_package: number;
  points_paid: number;
  points_payable: number;
  total_gross_cents: number;
  payment_plans: string[];
  /** Session 65: the customer announced a bank transfer, not yet confirmed. */
  bank_transfer_pending: boolean;
  bank_transfer_total_cents: number | null;
  bank_transfer_requested_at: string | null;
  payment_proof_uploaded_at: string | null;
  /** What was actually paid for the paid contracts. */
  total_paid_cents: number;
};

export type ContractRequestPointRead = ContractRead & {
  /** 1-based place of the contract in the pratica: contratto 1, 2, ... */
  position: number;
  product_id: string | null;
  documents_missing: number;
  documents_rejected: number;
  instalments_total: number | null;
  instalments_paid: number;
};

export type ContractRequestDetailRead = ContractRequestSummaryRead & {
  /** Who last wrote the notes: "Promoter Mario Bianchi", "Cliente (...)". */
  notes_author?: string | null;
  notes_updated_at?: string | null;
  /** What the documents step still lacks (identity, fiscal code, visura /
      P.IVA for a business). Empty = the pratica may go past it. */
  documents_blocking: string[];
  /** The holder's address, asked once for the whole pratica. */
  street: string | null;
  city: string | null;
  province: string | null;
  postal_code: string | null;
  holder_first_name: string | null;
  holder_last_name: string | null;
  email: string | null;
  pec: string | null;
  iban: string | null;
  /** Session 85, business pratica: ragione sociale and legal representative's CF. */
  company_name: string | null;
  legal_rep_fiscal_code: string | null;
  /** Session 89: a private holder's CF; birth date and place of whoever signs. */
  holder_fiscal_code: string | null;
  holder_birth_date: string | null;
  holder_birth_place: string | null;
  holder_birth_place_code: string | null;
  /** What in the fiscal code does not match the signer's data: a warning only. */
  fiscal_code_problems: string[];
  points: ContractRequestPointRead[];
};

/** A comune (current or suppressed) or a foreign state, for «Luogo di nascita». */
export type BirthplaceRead = {
  code: string;
  name: string;
  province: string;
  foreign: boolean;
  active: boolean;
  until: string | null;
};

export type ContractRequestPaymentOptionRead = {
  key: string;
  label: string;
  description: string;
  instalments: number;
  instalment_cents: number;
  total_cents: number;
  rounding_difference_cents: number;
  available: boolean;
  unavailable_reason: string | null;
  /** Session 64: the JavCash this option earns. */
  cashback_cents: number;
};

export type ContractRequestPaymentOptionsRead = {
  contract_request_id: string;
  /** gross_cents in one go; instalments_gross_cents in rate (Session 84). */
  lines: { contract_id: string; label: string; gross_cents: number; instalments_gross_cents: number }[];
  total_gross_cents: number;
  /** Session 85: amounts are VAT included and there is VAT in them (business pratica). */
  vat_included: boolean;
  options: ContractRequestPaymentOptionRead[];
  points_paid: number;
  cashback_total_cents: number;
  /** On an instalment plan: a slice per instalment, or all at the first. */
  cashback_mode: "PER_INSTALMENT" | "UPFRONT";
  /** Session 65: paying by bank transfer. */
  bank_transfer_available: boolean;
  bank_transfer_pending: boolean;
  /** The amount of the first transfer: the whole pratica in one go, or the
      first instalment. */
  bank_transfer_total_cents: number | null;
  bank_transfer_requested_at: string | null;
  payment_proof_uploaded_at: string | null;
  bank_iban: string | null;
  bank_account_holder: string | null;
  bank_transfer_instructions: string | null;
  bank_transfer_reference: string | null;
};

export type ContractStatusHistoryRead = {
  id: string;
  from_status: string | null;
  to_status: string;
  actor_user_id: string;
  actor_name: string;
  reason: string | null;
  notes: string | null;
  created_at: string;
};

export type CommissionMovementRead = {
  id: string;
  agent_id: string;
  contract_id: string;
  movement_type: string;
  amount_cents: number;
  currency: string;
  status: string;
  effective_date: string;
};

export type NotificationRead = {
  id: string;
  type: string;
  entity_type: string;
  entity_id: string;
  title: string;
  body: string | null;
  is_read: boolean;
  created_at: string;
};

export type CommissionMovementDetailRead = {
  id: string;
  contract_id: string;
  customer_id: string;
  customer_name: string;
  product_name: string;
  value_cents: number;
  agent_id: string;
  agent_name: string;
  agent_promoter_code: string;
  agent_current_rank_code: string | null;
  producer_agent_id: string;
  producer_name: string;
  depth_from_producer: number | null;
  movement_type: string;
  rank_at_calculation: string | null;
  base_amount_cents: number | null;
  already_distributed_cents: number | null;
  entrepreneurial_difference_cents: number | null;
  amount_cents: number;
  explanation: string | null;
  status: string;
  effective_date: string;
  paid_date: string | null;
};

export type CommissionLevelTotalsRead = {
  depth: number;
  contracts: number;
  value_cents: number;
  commission_cents: number;
};

export type BranchMemberRead = {
  agent_id: string;
  depth: number;
  display_name: string;
  promoter_code: string;
  status: string;
  rank_code: string | null;
  parent_agent_id: string | null;
  /** The person's ACCOUNT is frozen -- distinct from `status` (their agent
      lifecycle). Only ever true for admin-tier viewers: the server prunes
      frozen members and their whole subtree for everyone else. */
  is_frozen?: boolean;
};

export type AgentProfileRead = {
  id: string;
  organization_id: string;
  user_id: string | null;
  display_name: string;
  promoter_code: string;
  status: string;
  photo_url: string | null;
  current_rank_id: string | null;
  rank_code: string | null;
  rejection_reason: string | null;
  is_blacklisted: boolean;
  collaboration_accepted_at: string | null;
  /** {key: {version, accepted_at}} -- which documents this promoter
      accepted and at which wording. Empty for anyone who signed up before
      multi-document acceptance existed. */
  collaboration_accepted_documents?: Record<string, { version: string; accepted_at: string }>;
};

export type SimulationStepRead = {
  beneficiary_agent_id: string;
  rank_code: string;
  gross_amount_cents: number;
  movement_type: string;
  explanation: string;
};

export type RankRead = {
  id: string;
  code: string;
  name: string;
  level: number;
  personal_token_cents: number;
};

export type RankEvaluationChangeRead = {
  agent_id: string;
  display_name: string;
  previous_rank_code: string | null;
  new_rank_code: string;
  direction: "PROMOTED" | "DEMOTED";
};

export type CustomerRead = {
  id: string;
  organization_id: string;
  user_id: string | null;
  kind: string;
  fiscal_code: string | null;
  vat_number: string | null;
  email: string;
  phone: string | null;
  pec: string | null;
  photo_url: string | null;
  display_name: string;
  /** Null for a company/condominium with no person's profile. */
  first_name: string | null;
  last_name: string | null;
  created_at: string;
  email_verified: boolean | null;
  privacy_accepted: boolean | null;
  user_status: "ACTIVE" | "FROZEN" | null;
  /** Session 88: codice fiscale e residenza compilati (il terzo controllo d'ingresso). */
  profile_complete?: boolean | null;
};

export type AddressRead = {
  id: string;
  kind: string;
  street: string;
  city: string;
  province: string;
  postal_code: string;
  country: string;
};

export type CustomerDetailRead = CustomerRead & {
  addresses: AddressRead[];
  current_promoter_agent_id: string | null;
  current_promoter_name: string | null;
};

export type AgentListItemRead = {
  id: string;
  display_name: string;
  first_name: string | null;
  last_name: string | null;
  promoter_code: string;
  status: string;
  photo_url: string | null;
  current_rank_id: string | null;
  rank_code: string | null;
  direct_parent_agent_id: string | null;
  joined_at: string;
  rejection_reason: string | null;
  email: string | null;
  is_blacklisted: boolean;
  user_id: string | null;
  collaboration_accepted_at: string | null;
  /** {key: {version, accepted_at}} -- which documents this promoter
      accepted and at which wording. Empty for anyone who signed up before
      multi-document acceptance existed. */
  collaboration_accepted_documents?: Record<string, { version: string; accepted_at: string }>;
  email_verified: boolean;
  privacy_accepted: boolean;
  user_status: "ACTIVE" | "FROZEN" | null;
};

export type RootPromoterCreateResponse = {
  agent_id: string;
  display_name: string;
  promoter_code: string;
  personal_link: string;
  email: string;
  temporary_password: string;
};

export type DocumentationPostRead = {
  id: string;
  title: string;
  body: string | null;
  audience: "CUSTOMER" | "PROMOTER" | "BOTH";
  status: "PUBLISHED" | "ARCHIVED";
  image_url: string | null;
  pdf_url: string | null;
  pdf_filename: string | null;
  video_url: string | null;
  created_at: string;
};

export type ProductVersionRead = {
  id: string;
  version_label: string;
  name: string;
  description: string;
  image_url: string | null;
  /** For a contract: the price of the whole term paid in one go (Session 84). */
  base_price_cents: number;
  /** Session 84: a contract's monthly rata, net of VAT -- NOT base / 12.
      null: no rate price, the rate split the one-go price. */
  monthly_price_cents: number | null;
  initial_fee_cents: number;
  recurring_fee_cents: number;
  billing_period: string;
  vat_percentage: number | null;
  contract_duration_months: number | null;
  commission_tokens: Record<string, number>;
  credit_discount_percentage: number;
  cashback_enabled: boolean;
  /** 0-100: share of a paid CONTRACT's gross (VAT included) credited back as
      JavCash, automatically and with no surcharge. INTERNAL products only;
      0 means a contract generates no JavCash at all. */
  contract_cashback_percentage: number;
  /** One-off bonus to the promoter who originally brought the customer in.
      Configured here rather than keyed off a price in code. */
  first_referrer_bonus_enabled: boolean;
  first_referrer_bonus_cents: number;
  /** NO_CASHBACK / STANDARD / AUTOMATIC_INTERNAL_SERVICE -- derived server-side
      from the fields above plus the product's category, never stored. */
  cashback_mode: string;
  /** The whole contract's price before VAT, in one go and in rate (monthly
      price x months; null = the rate split the one-go price) -- computed
      server-side (catalog/pricing.py). See lib/product-audience.ts::contractPrices. */
  contract_billing_periods: number;
  contract_net_amount_cents: number;
  contract_instalments_net_amount_cents: number | null;
  valid_from: string;
  valid_to: string | null;
  status: string;
};

export type ProductRead = {
  id: string;
  organization_id: string;
  code: string;
  product_type: string;
  customer_type: string;
  status: string;
  category: "INTERNAL" | "DROPSHIPPING" | "PARTNER";
};

export type ProductWithVersionsRead = ProductRead & {
  versions: ProductVersionRead[];
};

export type ProductCatalogRead = ProductRead & {
  current_version: ProductVersionRead | null;
  /** Le categorie di Shop a cui appartiene, dentro la sezione (`category`)
      in cui il prodotto è venduto -- vedi ShopCategoryRead. Opzionale
      perché un catalogo salvato prima delle categorie non ne ha nessuna. */
  category_ids?: string[];
};

export type ContractTotals = {
  total: number;
  active: number;
  pending_approval: number;
  rejected: number;
  cancelled: number;
  suspended: number;
  expired: number;
};

export type CommissionTotals = {
  accrued_cents: number;
  payable_cents: number;
  paid_cents: number;
  reversed_cents: number;
};

export type DashboardSummary = {
  contracts: ContractTotals;
  commissions: CommissionTotals;
  active_promoters: number;
  active_customers: number;
  period_new_contracts: number;
  period_new_commissions_cents: number;
  generated_at: string;
};

export type AttentionItem = {
  contract_id: string;
  customer_id: string;
  status: string;
  days_in_status: number;
  reason: string;
};

export type RecentActivityItem = {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  reason: string | null;
  created_at: string;
};

export type TimeseriesPoint = {
  period: string;
  value: number;
};

export type PromoterCodeRead = {
  id: string;
  code: string;
  personal_link: string;
  status: string;
  promoter_display_name: string | null;
};

export type BranchAgentSummaryRead = {
  agent_id: string;
  depth: number;
  display_name: string;
  promoter_code: string;
  status: string;
  rank_code: string | null;
  contracts_total: number;
  contracts_by_status: Record<string, number>;
  contracts_problem: number;
  contracts_in_progress: number;
  contracts_processed: number;
  commission_cents: number;
};

export type BranchSummaryTotals = {
  contracts: number;
  commission_cents: number;
  contracts_by_status: Record<string, number>;
  contracts_closed: number;
  contracts_rejected: number;
  contracts_pending: number;
  contracts_in_progress: number;
  levels_below: number;
  people_total: number;
};

export type BranchSummaryRead = {
  agents: BranchAgentSummaryRead[];
  totals: BranchSummaryTotals;
};

export type RankProgressRead = {
  current_rank_code: string | null;
  current_rank_name: string | null;
  next_rank_code: string | null;
  next_rank_name: string | null;
  is_max_rank: boolean;
  personal_volume_cents: number;
  personal_volume_threshold_cents: number;
  group_volume_cents: number;
  group_volume_threshold_cents: number;
};

export type OrganizationNetworkLevelsRead = {
  people_total: number;
  levels_total: number;
  people_by_level: Record<string, number>;
};

export type BranchContractRead = {
  contract_id: string;
  status: string;
  customer_id: string;
  customer_name: string;
  customer_email: string | null;
  customer_phone: string | null;
  product_name: string;
  value_cents: number;
  expires_at: string | null;
  producer_agent_id: string;
  producer_name: string;
  commission_cents: number;
  my_commission_cents: number | null;
  is_problem: boolean;
  admin_note: string | null;
};

export type TicketMessageRead = {
  id: string;
  ticket_id: string;
  author_user_id: string;
  author_role: string;
  author_name: string | null;
  body: string;
  created_at: string;
};

export type TicketRead = {
  id: string;
  organization_id: string;
  opened_by_user_id: string;
  opened_by_role: string;
  opened_by_name: string | null;
  subject: string;
  category: string;
  status: string;
  contract_id: string | null;
  created_at: string;
  message_count: number;
  last_message_at: string | null;
};

export type TicketDetailRead = TicketRead & {
  messages: TicketMessageRead[];
};

/** «Non hai trovato ciò che cercavi?» -- richieste di prodotto dallo Shop,
    un sistema di ticket separato dal supporto (API /product-requests). */
export type ProductRequestMessageRead = {
  id: string;
  request_id: string;
  author_user_id: string;
  author_role: string;
  author_name: string | null;
  body: string;
  created_at: string;
};

export type ProductRequestRead = {
  id: string;
  opened_by_user_id: string;
  opened_by_role: string;
  opened_by_name: string | null;
  product_name: string;
  reference_url: string | null;
  status: "OPEN" | "IN_PROGRESS" | "FOUND" | "NOT_FOUND" | "CLOSED";
  created_at: string;
  message_count: number;
  last_message_at: string | null;
  last_author_role: string | null;
};

export type ProductRequestDetailRead = ProductRequestRead & {
  messages: ProductRequestMessageRead[];
};

export type WalletRead = {
  id: string;
  user_id: string;
  address: string;
  balance_cents: number;
  currency: string;
  can_transfer: boolean;
  created_at: string;
};

export type WalletAdminListItemRead = WalletRead & {
  owner_display_name: string;
  owner_email: string;
  owner_roles: string[];
};

export type WalletTransactionRead = {
  id: string;
  from_wallet_id: string | null;
  from_address: string | null;
  from_display_name: string | null;
  to_wallet_id: string | null;
  to_address: string | null;
  to_display_name: string | null;
  amount_cents: number;
  currency: string;
  type: string;
  source: string | null;
  reference_contract_id: string | null;
  reference_order_id: string | null;
  reverses_transaction_id: string | null;
  note: string | null;
  actor_user_id: string | null;
  created_at: string;
};

export type OrganizationSettingsRead = {
  bank_iban: string | null;
  bank_account_holder: string | null;
  bank_transfer_instructions: string | null;
  /** PER_INSTALMENT (default) / UPFRONT -- Session 59. */
  contract_instalment_cashback_mode: "PER_INSTALMENT" | "UPFRONT" | null;
};

export type OrderRead = {
  id: string;
  customer_user_id: string;
  customer_display_name: string;
  product_version_id: string;
  product_name: string;
  product_image_url: string | null;
  created_by_user_id: string;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  cashback_requested: boolean;
  cashback_surcharge_cents: number;
  cashback_credited_at: string | null;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER";
  payment_proof_uploaded_at: string | null;
  note: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
};

export type OrderQuoteRead = {
  product_version_id: string;
  product_name: string;
  amount_cents: number;
  credit_discount_percentage: number;
  max_creditable_cents: number;
  customer_wallet_balance_cents: number;
  bank_transfer_available: boolean;
  cashback_available: boolean;
  cashback_percentage: number;
};

export type FinancialMovementRead = {
  id: string;
  /** CONTRACT_PAYMENT: one paid instalment of a Jav contract (Session 54). */
  kind: "WALLET" | "ORDER_PAYMENT" | "CONTRACT_PAYMENT";
  type: string | null;
  source: string | null;
  payment_method: "BANK_TRANSFER" | null;
  amount_cents: number;
  currency: "JAVCASH" | "EUR";
  product_name: string | null;
  order_id: string | null;
  contract_id?: string | null;
  contract_request_id?: string | null;
  note: string | null;
  customer_user_id: string | null;
  customer_display_name: string | null;
  created_at: string;
};

/** The totals at the top of "Contabilità", computed server-side (Session 54). */
export type AccountingSummaryRead = {
  spent_total_cents: number;
  spent_bank_transfer_cents: number;
  spent_this_month_cents: number;
  spent_orders_cents: number;
  spent_contracts_cents: number;
  payments_count: number;
  javcash_balance_cents: number;
  javcash_received_cents: number;
  javcash_spent_cents: number;
  cashback_received_cents: number;
  contracts_active: number;
  instalments_paid: number;
  next_instalment_due_date: string | null;
  next_instalment_cents: number | null;
  /** Null unless the account is also a promoter. */
  commissions_total_cents: number | null;
  commissions_to_collect_cents: number | null;
  commissions_paid_cents: number | null;
  commissions_count: number | null;
};

/** Everything about one movement, or about the order / contract it refers
    to -- the "Contabilità" detail popup. */
export type AccountingDetailRead = {
  ref: string;
  kind: "WALLET" | "ORDER" | "CONTRACT";
  title: string;
  subtitle: string | null;
  status: string | null;
  status_tone: "success" | "warning" | "danger" | "neutral";
  amount_cents: number | null;
  currency: "EUR" | "JAVCASH";
  direction: "in" | "out" | null;
  facts: { label: string; value: string; mono: boolean }[];
  timeline: { label: string; at: string | null; by: string | null; tone: "done" | "pending" | "warning" }[];
  instalments: {
    number: number;
    instalments_total: number;
    due_date: string;
    amount_cents: number;
    status: string;
    paid_at: string | null;
    source: string | null;
    confirmed_by: string | null;
  }[];
  related_refs: string[];
  tab: "orders" | "contracts" | "wallet" | null;
  order_id: string | null;
  contract_id: string | null;
};

// --- "Invita un amico" (Session 39) ----------------------------------------
// A one-level list every account has, deliberately separate from the
// commercial network: no hierarchy, no commissions. See
// apps/api/app/domains/friend_referrals/models.py.

export type FriendReferralItemRead = {
  id: string;
  display_name: string;
  /** INVITED / IN_PROGRESS / ACTIVE -- only ACTIVE counts towards the gift. */
  state: string;
  /** PROMOTER_LINK / FRIEND_LINK -- which of the two kinds of link was used. */
  source: string;
  invited_at: string;
};

export type FriendReferralClaimRead = {
  id: string;
  milestone: number;
  status: "REQUESTED" | "FULFILLED" | "REJECTED";
  note: string | null;
  requested_at: string;
  handled_at: string | null;
};

export type FriendReferralSummaryRead = {
  code: string;
  invited_total: number;
  active_total: number;
  reward_every: number;
  /** What the gift is, in the customer's words -- server-owned, never
      hardcoded here (see friend_referrals/models.py::REWARD_DESCRIPTION). */
  reward_description: string;
  missing_for_next_reward: number;
  claimable_milestone: number | null;
  referrals: FriendReferralItemRead[];
  claims: FriendReferralClaimRead[];
};

export type FriendReferralAdminClaimRead = {
  id: string;
  referrer_user_id: string;
  referrer_name: string;
  referrer_email: string | null;
  milestone: number;
  status: "REQUESTED" | "FULFILLED" | "REJECTED";
  note: string | null;
  requested_at: string;
  handled_at: string | null;
};


// --- Contratto di collaborazione "Lavora con noi" (Session 40) -------------
// The legal text is served by the backend (structured blocks, never markup)
// so there is exactly one copy of it and changing it needs no frontend
// release. See apps/api/app/domains/network/collaboration_documents.py.

export type CollaborationDocumentBlock =
  | { type: "heading"; text: string }
  | { type: "paragraph"; text: string }
  | { type: "clause"; number: string; text: string }
  | { type: "bullets"; items: string[] }
  | { type: "table"; columns: string[]; rows: string[][]; caption: string | null }
  | { type: "signature"; text: string };

export type CollaborationDocumentRead = {
  key: string;
  /** Echoed back on submit: the record stores WHICH TEXT was agreed to, not
      just that a box was ticked. */
  version: string;
  title: string;
  subtitle: string;
  acceptance_label: string;
  blocks: CollaborationDocumentBlock[];
};


// --- Anteprima provvigioni e rate del contratto (Session 50) ---------------
// Computed entirely server-side (commissions/services/preview.py). The
// dashboard only renders it and sends back its checksum on acceptance.

export type CommissionPreviewBeneficiary = {
  agent_id: string;
  name: string;
  rank_code: string;
  depth: number;
  role: string;
  movement_type: string;
  movement_label: string;
  total_cents: number;
  explanation: string;
};

export type CommissionPreviewScheduleRow = {
  number: number;
  due_date: string | null;
  customer_amount_cents: number;
  commission_cents: number;
  per_beneficiary_cents: Record<string, number>;
  release: string;
};

export type CommissionPreviewRead = {
  contract_id: string;
  customer_name: string;
  gross_amount_cents: number;
  beneficiaries: CommissionPreviewBeneficiary[];
  first_referrer_bonus: { agent_id: string; name: string; amount_cents: number; note: string } | null;
  total_commission_cents: number;
  payment: {
    paid: boolean;
    paid_at: string | null;
    plan_key: string | null;
    plan_label: string | null;
    instalments: number | null;
    schedule: CommissionPreviewScheduleRow[];
    last_release_date: string | null;
    scenarios: { plan_key: string; plan_label: string; instalments: number; commission_per_instalment_cents: number }[];
  };
  customer_cashback_cents: number;
  warnings: string[];
  checksum: string;
  /** Only on GET /commission-preview. */
  already_accepted?: boolean;
};

export type ContractInstalmentRead = {
  number: number;
  instalments_total: number;
  due_date: string;
  amount_cents: number;
  /** SCHEDULED / PAID */
  status: string;
  paid_at: string | null;
  /** ADMIN: confirmed by hand (bank transfer). */
  payment_source: string | null;
  confirmed_by: string | null;
  commission_released_at: string | null;
  commission_pending: boolean;
};

export type ContractCommissionLogRead = {
  contract_id: string;
  status: string;
  payment_plan: string | null;
  accepted_plan: {
    accepted_at: string;
    accepted_by: string | null;
    total_commission_cents: number;
    preview: CommissionPreviewRead;
  } | null;
  instalments: ContractInstalmentRead[];
};

/** Session 72: the Shop's own sections, each renamable and switchable. */
export type ShopSectionKey = "internal" | "partner" | "dropshipping";

export type MarketplaceConfigRead = {
  /** Il nome con cui il cliente vede lo Shop (impostazione dell'admin). */
  labels: { jav_market: string };
  /** Session 72: the Shop's own sections, each renamable and switchable. */
  sections: Record<ShopSectionKey, { label: string; enabled: boolean }>;
  bank_transfer_discount_percentage: number;
  /** Session 78: l'aliquota che si **aggiunge** al prezzo esposto (22% se
      l'amministratore non la cambia).
      Opzionale finché il campo non arriva anche dal server: mancando, non si
      mostra nessuna IVA invece di mostrarne una sbagliata. */
  vat_percentage?: number;
  default_credit_percentage: number;
  max_credit_percentage: number;
};

/** La card di un prodotto dello Shop nella griglia del cliente. */
export type MarketProductRead = {
  id: string;
  name: string;
  description: string;
  image_url: string | null;
  images: string[];
  min_price_cents: number;
  max_price_cents: number;
  credit_discount_percentage: number;
  shipping_days: string | null;
  shipping_included: boolean;
  /** Prices are the full ones; bank transfer takes this % off. */
  bank_transfer_discount_percentage: number;
  in_stock: boolean;
  variants: { id: string; label: string; image_url: string | null; price_cents: number; in_stock: boolean }[];
  /** Le categorie dello Shop a cui il prodotto appartiene: è con queste che
      il cliente filtra la griglia. */
  category_ids?: string[];
};

/** Il preventivo dello Shop: cosa paga il cliente, prima di ordinare. */
export type MarketQuoteRead = {
  variant_id: string;
  product_name: string;
  variant_label: string;
  quantity: number;
  unit_price_cents: number;
  items_cents: number;
  shipping_cents: number;
  /** Session 78: l'IVA aggiunta sopra la merce, già dentro amount_cents. */
  vat_cents?: number;
  vat_percentage?: number;
  /** Ottobre 2026: minimo d'ordine e spedizione gratuita, misurati sulla
      merce IVA inclusa (merchandise_cents). */
  merchandise_cents?: number;
  min_order_cents?: number;
  min_order_missing_cents?: number;
  free_shipping_threshold_cents?: number | null;
  free_shipping?: boolean;
  free_shipping_missing_cents?: number;
  shipping_included: boolean;
  shipping_days: string | null;
  amount_cents: number;
  credit_discount_percentage: number;
  max_creditable_cents: number;
  customer_wallet_balance_cents: number;
  bank_transfer_discount_percentage: number;
  /** amount_cents paid all by bank transfer, discount taken off (no JavCash). */
  bank_transfer_amount_cents: number;
  bank_transfer_available: boolean;
  default_address: { street: string | null; city: string | null; province: string | null; postal_code: string | null };
};

/** The only shipping state a customer sees. */
export type MarketDeliveryStatus = "RECEIVED" | "PREPARING" | "SHIPPED" | "DELIVERED" | "PROBLEM";

// --- Categorie degli shop (Session 73) ------------------------------------
// Ogni shop (le sezioni del nostro catalogo e lo Shop) ha le sue categorie:
// l'amministratore le crea nella pagina di quello shop, il cliente ci filtra
// i prodotti. Una categoria appartiene a UNO shop: "Casa" del catalogo e
// "Casa" dello Shop sono due righe diverse, perché i cataloghi sono separati.
export type ShopKey = "internal" | "partner" | "dropshipping" | "jav_market";

export type ShopCategoryRead = {
  id: string;
  shop: ShopKey;
  name: string;
  /** Ordine di comparsa nella barra delle categorie del cliente. */
  position: number;
  active: boolean;
  /** Solo Shop: il fornitore a cui vanno gli ordini dei prodotti di questa
      categoria che non ne hanno uno loro. */
  producer_id?: string | null;
  /** Quanti prodotti di quello shop sono in questa categoria. */
  product_count: number;
};

/** Per ogni prodotto, le categorie a cui appartiene dentro il suo shop. */
export type ShopCategoryAssignments = Record<string, string[]>;

// --- Il carrello dello Shop (Session 75) ---------------------------------
//
// Una sezione per negozio: lo Shop e il catalogo interno hanno regole che si
// escludono a vicenda (indirizzo e spedizione nello Shop, cashback nel
// catalogo interno), quindi righe di negozi diversi non finiscono nello
// stesso ordine. Il cliente vede comunque un carrello solo, diviso in sezioni.

export type CartShop = "jav_market" | "catalog";

export type CartLineRead = {
  cart_item_id: string;
  variant_id: string;
  product_name: string;
  variant_label: string | null;
  image_url: string | null;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
  credit_discount_percentage: number;
  /** Session 76: quanti JavCash porta **questa** riga -- la sua percentuale
      sul suo valore, quota di spedizione compresa. Il tetto dell'ordine è la
      somma di questi, non una media: un prodotto allo 0% non presta nulla
      agli altri. */
  max_creditable_cents?: number;
  /** false quando l'articolo non è più acquistabile: la riga resta visibile
      con il motivo, così il cliente sa cosa togliere. */
  available: boolean;
  unavailable_reason: string | null;
};

/** Una sezione del carrello: le stesse cifre di un preventivo del negozio,
    più le righe e lo stato di acquistabilità. */
export type CartSectionRead = Omit<MarketQuoteRead, "variant_id" | "product_name" | "variant_label" | "quantity" | "unit_price_cents"> & {
  cart_id: string;
  shop: CartShop;
  items: CartLineRead[];
  /** false se anche una sola riga non è più acquistabile. */
  purchasable: boolean;
  problems: string[];
  /** Le chiavi di un tempo, che descrivono la prima riga. */
  variant_id: string;
  product_name: string;
  variant_label: string | null;
  quantity: number;
  unit_price_cents: number;
};

export type CartRead = {
  sections: CartSectionRead[];
  item_count: number;
  total_cents: number;
};


// --- Lo Shop: «Fai la Spesa con Jav» (Session 79) ----------------------
//
// Catalogo scritto a mano dall'amministratore, con l'azienda produttrice in
// scheda a parte. La card riusa la forma di MarketProductRead.

export type JavMarketProducerPublic = {
  name: string;
  description: string;
  website_url: string | null;
  logo_url: string | null;
};

export type JavMarketProducerRead = JavMarketProducerPublic & {
  id: string;
  vat_number: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  active: boolean;
};

/** La card nella griglia del cliente: MarketProductRead più il produttore. */
export type JavMarketProductRead = MarketProductRead & {
  /** Chi vende: lo shop del club (club_id) o quello di JudoArteVida (null). */
  seller?: { club_id: string | null; name: string } | null;
  producer: JavMarketProducerPublic | null;
  /** Solo «Fai la Spesa»: le regole dell'ordine, per dirle prima del checkout. */
  shipping_flat_cents?: number;
  min_order_cents?: number;
  free_shipping_threshold_cents?: number | null;
};

/** La scheda in amministrazione: varianti modificabili, costo e produttore. */
export type JavMarketAdminProductRead = {
  id: string;
  name: string;
  description: string;
  image_url: string | null;
  images: string[];
  status: "ACTIVE" | "INACTIVE";
  credit_discount_percentage: number;
  unit_cost_cents: number | null;
  producer_id: string | null;
  producer: JavMarketProducerRead | null;
  /** Ottobre 2026: il fornitore a cui andranno gli ordini, risolto dal
      server -- quello del prodotto o, se manca, della sua categoria. */
  supplier?: JavMarketSupplierBrief | null;
  supplier_source?: "PRODUCT" | "CATEGORY" | null;
  supplier_category_name?: string | null;
  category_ids?: string[];
  variants: {
    id: string; label: string; sku: string | null; image_url: string | null;
    price_cents: number; inventory: number | null; active: boolean; in_stock: boolean;
  }[];
};

export type JavMarketSupplierBrief = {
  id: string;
  name: string;
  email: string | null;
  active: boolean;
};

/** «Fornitori da avvisare» (GET /jav-market/supplier-queue): le righe pagate
    e non ancora mandate, per fornitore e per ordine. Mai prezzi. */
export type JavMarketSupplierQueueOrder = {
  id: string;
  order_code: string;
  created_at: string;
  paid_at: string | null;
  recipient_name: string;
  city: string;
  province: string;
  items: { id: string; product_name: string; variant_label: string | null; quantity: number }[];
};

export type JavMarketSupplierQueue = {
  suppliers: {
    producer: JavMarketSupplierBrief;
    order_count: number;
    item_count: number;
    piece_count: number;
    orders: JavMarketSupplierQueueOrder[];
  }[];
  /** Righe che non hanno nessun fornitore: non si possono mandare. */
  unassigned: {
    item_id: string;
    order_id: string;
    order_code: string;
    product_id: string;
    product_name: string;
    variant_label: string | null;
    quantity: number;
  }[];
};

/** L'email pronta da rileggere; `item_ids` sono le righe che manda. */
export type JavMarketSupplierDraft = {
  producer_id: string;
  producer_name: string;
  to_email: string;
  from_email: string | null;
  subject: string;
  body_text: string;
  item_ids: string[];
  order_codes: string[];
};

export type JavMarketSupplierDispatchRead = {
  id: string;
  producer_id: string;
  producer_name: string;
  source: "QUEUE" | "ORDER" | "AUTO" | "LEGACY";
  to_email: string;
  subject: string;
  body_text: string;
  sent_at: string;
  sent_by_email: string | null;
  order_codes: string[];
  order_count: number;
  item_count: number;
  piece_count: number;
};

export type JavMarketSettingsRead = {
  enabled: boolean;
  /** Session 80: l'ordine pagato parte da solo verso le aziende. Nasce
      spento — mandare una email a un'azienda vera è un'azione verso
      l'esterno, e la prima volta la si vuole guardare. */
  auto_forward: boolean;
  shipping_mode: "CUSTOMER_PAYS" | "INCLUDED";
  /** Un importo, non un minimo: senza fornitore non c'è un costo reale da
      confrontare. */
  shipping_flat_cents: number;
  shipping_days: string | null;
  ship_to_country: string;
  /** Merce IVA inclusa minima per ordinare (0 = nessuna) e da cui la
      spedizione è gratis (null = mai). */
  min_order_cents?: number;
  free_shipping_threshold_cents?: number | null;
  /** Da dove partono le email ai fornitori (null = mittente predefinito) e
      la firma in fondo. */
  supplier_email_from?: string | null;
  supplier_email_signature?: string | null;
};

export type JavMarketOrderItemRead = {
  id: string;
  product_id: string;
  variant_id: string;
  /** Congelato sulla riga: un prodotto rinominato non riscrive un ordine passato. */
  product_name: string;
  variant_label: string | null;
  producer_name: string | null;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
  tracking_number: string | null;
  tracking_url: string | null;
};

/** Un ordine dello Shop. Le colonne di testata (product_name, ...)
    riassumono le righe; `items` è cosa è stato comprato davvero. */
export type JavMarketOrderRead = {
  id: string;
  /** Session 76: il numero d'ordine che legge il cliente, progressivo.
      `order_code` è lo stesso numero come stringa. */
  number?: number;
  order_code?: string;
  customer_user_id: string;
  customer_display_name: string;
  product_name: string;
  product_image_url: string | null;
  items?: JavMarketOrderItemRead[];
  items_cents: number;
  shipping_cents: number;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  /** Taken off for paying by bank transfer. */
  bank_transfer_discount_cents: number;
  /** Today's bank-transfer discount percentage. */
  bank_transfer_discount_percentage: number;
  /** What is really paid in euro: residual - bank-transfer discount. */
  amount_due_cents: number;
  /** Session 74: l'IVA congelata alla creazione dell'ordine. Un ordine che
      non ce l'ha, o ce l'ha a 0, non scrive niente, mai "IVA 0,00 €". */
  vat_percentage?: number;
  vat_amount_cents?: number;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER";
  payment_proof_uploaded_at: string | null;
  note: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
  recipient_name: string;
  recipient_phone: string | null;
  address_line1: string;
  address_line2: string | null;
  city: string;
  province: string;
  postal_code: string;
  country_code: string;
  shipping_days: string | null;
  delivery_status: MarketDeliveryStatus | null;
  tracking_number: string | null;
  tracking_url: string | null;
  shipped_at: string | null;
  delivered_at: string | null;
  // Admin only
  fulfillment_status?: "NOT_SENT" | "SENDING" | "SENT" | "SHIPPED" | "DELIVERED" | "ERROR" | "CANCELLED";
  tracking_company?: string | null;
  /** Session 80: lo stato dell'invio alle aziende. */
  forwarded_at?: string | null;
  forward_error?: string | null;
  producers?: { name: string }[];
  /** Righe non ancora mandate a nessun fornitore. */
  supplier_pending_count?: number;
  supplier_cost_cents?: number | null;
  estimated_margin_cents?: number | null;
};

/** Session 89: una pagina della vetrina dello Shop (GET
 *  /jav-market/products/mine/page; vedi
 *  apps/api/app/domains/marketplaces/paging.py): il catalogo arriva un po'
 *  alla volta, con «Mostra altri prodotti». */
export interface ShopProductPage<T> {
  items: T[];
  /** Prodotti che rispondono a ricerca e categoria. */
  total: number;
  /** Prodotti in vetrina senza filtri: la scheda dello Shop e il conteggio. */
  shop_total: number;
  offset: number;
  limit: number;
  /** Da dove chiedere la pagina dopo; null se è l'ultima. */
  next_offset: number | null;
  /** Le categorie che hanno almeno un prodotto in vetrina. */
  category_ids: string[];
}

// --- PIN dei JavCash (Session 87) ---------------------------------------
/** Come il cliente conferma l'uso dei JavCash al checkout. `method` è
    quello valido adesso: EMAIL anche con il PIN acceso, se è bloccato. */
export type SpendPinStatusRead = {
  enabled: boolean;
  method: "PIN" | "EMAIL";
  locked_until: string | null;
};
