// Mirrors the Pydantic response schemas in apps/api/app/domains/*/schemas.py.
// Kept hand-written for this vertical slice; generating from the OpenAPI schema
// (packages/api-client) is tracked as Phase F follow-up work.

export type ContractRead = {
  id: string;
  customer_id: string;
  supply_point_id: string;
  /** Null only while the contract is a draft point of a pratica whose
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
  supply_point_label: string | null;
  pod_code?: string | null;
  pdr_code?: string | null;
  /** ELECTRICITY / GAS -- of the supply point. */
  energy_type?: string | null;
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
  /** Session 64: discount taken off a single payment (0 otherwise). */
  payment_discount_cents?: number;
  payment_method: string | null;
  paid_at: string | null;
  /** An administrator stopped Stripe charging this contract every month. */
  billing_stopped_at?: string | null;
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
  instalments_failed: number;
  /** Session 65: the customer announced a bank transfer, not yet confirmed. */
  bank_transfer_pending: boolean;
  bank_transfer_total_cents: number | null;
  bank_transfer_requested_at: string | null;
  payment_proof_uploaded_at: string | null;
  /** What was actually paid for the paid points (discounts taken off). */
  total_paid_cents: number;
};

export type ContractRequestPointRead = ContractRead & {
  /** 1-based place of the point among those of its kind: POD 1, POD 2, PDR 1. */
  position: number;
  /** "POD" (luce) or "PDR" (gas). */
  point_kind: "POD" | "PDR";
  meter_number: string | null;
  street: string | null;
  city: string | null;
  province: string | null;
  postal_code: string | null;
  product_id: string | null;
  documents_missing: number;
  documents_rejected: number;
  instalments_total: number | null;
  instalments_paid: number;
  instalments_failed: number;
  /** Stripe is still charging this contract every month. */
  billing_active: boolean;
};

export type ContractRequestCheckoutRead = {
  id: string;
  created_at: string;
  payment_plan: string;
  total_cents: number;
  instalment_cents: number;
  contracts: number;
  completed_at: string | null;
  stripe_checkout_session_id: string;
  stripe_subscription_id: string | null;
  outcome: string | null;
};

export type ContractRequestDetailRead = ContractRequestSummaryRead & {
  /** Who last wrote the notes: "Promoter Mario Bianchi", "Cliente (...)". */
  notes_author?: string | null;
  notes_updated_at?: string | null;
  /** What the documents step still lacks (identity, bill, visura / P.IVA
      for a business). Empty = the pratica may go past it. */
  documents_blocking: string[];
  /** The supply address every POD of the pratica starts from. */
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
  /** Staff only. */
  checkouts: ContractRequestCheckoutRead[];
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
  /** Session 64: price before the one-go discount, the discount, and the
      JavCash this option earns. */
  list_total_cents: number;
  discount_percentage: number;
  discount_cents: number;
  cashback_cents: number;
};

export type ContractRequestPaymentOptionsRead = {
  contract_request_id: string;
  card_available: boolean;
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
  /** Session 65: paying by bank transfer (single payment, same discount). */
  bank_transfer_available: boolean;
  bank_transfer_pending: boolean;
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

export type SupplyPointRead = {
  id: string;
  label: string | null;
  energy_type: string;
  pod_code: string | null;
  pdr_code: string | null;
  meter_number: string | null;
  supply_address_id: string;
};

export type CustomerDetailRead = CustomerRead & {
  addresses: AddressRead[];
  supply_points: SupplyPointRead[];
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
  energy_type: string | null;
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
  supply_point_label: string | null;
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
  reference_invoice_redemption_id: string | null;
  reference_order_id: string | null;
  reference_imported_order_id: string | null;
  /** Marketplace 1 (CJ), 2 (Shopify) and 3 (AliExpress API) orders.
      reference_imported_order_id stays the hand-kept AliExpress plugin. */
  reference_cj_order_id?: string | null;
  reference_shopify_order_id?: string | null;
  reference_aliexpress_order_id?: string | null;
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
  /** Discount (%) on a contract paid in one go; null = 32 (default). */
  contract_full_payment_discount_percentage: number | null;
};

export type PaymentSettingsRead = {
  stripe_publishable_key: string | null;
  stripe_secret_key_configured: boolean;
  stripe_secret_key_last4: string | null;
  stripe_webhook_secret_configured: boolean;
};

export type PartnerRead = {
  id: string;
  name: string;
  logo_url: string | null;
  is_active: boolean;
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
  payment_method: "BANK_TRANSFER" | "CARD";
  stripe_checkout_session_id: string | null;
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
  card_available: boolean;
  cashback_available: boolean;
  cashback_percentage: number;
};

export type ImportProviderRead = {
  id: string;
  provider_type: string;
  name: string;
  base_url: string | null;
  api_key_configured: boolean;
  api_key_last4: string | null;
  /** AliExpress Dropshipping API (Session 71). */
  app_key: string | null;
  app_secret_configured: boolean;
  app_secret_hint: string | null;
  connected: boolean;
  account_label: string | null;
  token_expires_at: string | null;
  last_connected_at: string | null;
  enabled: boolean;
  created_at: string;
};

export type ImportedProductAdminRead = {
  id: string;
  provider_id: string;
  provider_name: string;
  external_id: string | null;
  external_url: string | null;
  name: string;
  description: string;
  image_url: string | null;
  price_cents: number;
  credit_discount_percentage: number;
  status: "ACTIVE" | "INACTIVE";
  created_at: string;
  category_ids?: string[];
};

export type ImportedProductRead = {
  id: string;
  name: string;
  description: string;
  image_url: string | null;
  price_cents: number;
  credit_discount_percentage: number;
  /** price_cents is the full (card) price; bank transfer takes this % off. */
  bank_transfer_discount_percentage?: number;
  /** I prodotti a mano contano come AliExpress: stesse categorie, stessa
      scheda nello Shop del cliente. */
  category_ids?: string[];
};

export type ImportedOrderRead = {
  id: string;
  customer_user_id: string;
  customer_display_name: string;
  imported_product_id: string;
  product_name: string;
  product_image_url: string | null;
  created_by_user_id: string;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  /** Taken off by bank transfer (frozen), and residual minus that discount. */
  bank_transfer_discount_cents?: number;
  amount_due_cents?: number;
  bank_transfer_discount_percentage?: number;
  /** Session 74: come sugli ordini dei tre Marketplace -- l'IVA compresa nel
      prezzo, congelata sull'ordine. Assente sugli ordini di prima. */
  vat_percentage?: number;
  vat_amount_cents?: number;
  /** Session 78: INCLUDED sugli ordini di prima, ADDED da lì in poi. Le
      stesse colonne hanno significato opposto fra i due. */
  vat_mode?: "INCLUDED" | "ADDED";
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER" | "CARD";
  stripe_checkout_session_id: string | null;
  payment_proof_uploaded_at: string | null;
  note: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
};

export type ImportedOrderQuoteRead = {
  imported_product_id: string;
  product_name: string;
  amount_cents: number;
  /** Session 78: il prezzo a catalogo è l'imponibile e questa è l'IVA che
      si aggiunge; amount_cents le contiene entrambe. */
  items_cents?: number;
  vat_cents?: number;
  vat_percentage?: number;
  credit_discount_percentage: number;
  max_creditable_cents: number;
  customer_wallet_balance_cents: number;
  bank_transfer_available: boolean;
  card_available: boolean;
  /** Bank transfer costs less than card. */
  bank_transfer_discount_percentage?: number;
  bank_transfer_amount_cents?: number;
};

export type FinancialMovementRead = {
  id: string;
  /** CONTRACT_PAYMENT: one paid instalment of a Jav contract (Session 54). */
  kind: "WALLET" | "ORDER_PAYMENT" | "REDEMPTION_PAYMENT" | "CONTRACT_PAYMENT";
  type: string | null;
  source: string | null;
  payment_method: "BANK_TRANSFER" | "CARD" | null;
  amount_cents: number;
  currency: "JAVCASH" | "EUR";
  product_name: string | null;
  order_id: string | null;
  invoice_redemption_id: string | null;
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
  spent_card_cents: number;
  spent_bank_transfer_cents: number;
  spent_this_month_cents: number;
  spent_orders_cents: number;
  spent_redemptions_cents: number;
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

/** Everything about one movement, or about the order / cashback redemption /
    contract it refers to -- the "Contabilità" detail popup. */
export type AccountingDetailRead = {
  ref: string;
  kind: "WALLET" | "ORDER" | "REDEMPTION" | "CONTRACT";
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
  tab: "orders" | "cashback" | "contracts" | "wallet" | null;
  order_id: string | null;
  invoice_redemption_id: string | null;
  contract_id: string | null;
};

export type InvoiceRedemptionRead = {
  id: string;
  partner_id: string;
  partner_name: string;
  customer_user_id: string;
  customer_display_name: string;
  original_filename: string;
  content_type: string;
  declared_amount_cents: number;
  confirmed_amount_cents: number | null;
  payment_due_cents: number | null;
  payment_reference_code: string | null;
  payment_method: "BANK_TRANSFER" | "CARD" | null;
  stripe_checkout_session_id: string | null;
  payment_proof_uploaded_at: string | null;
  status: "SUBMITTED" | "PAYMENT_PENDING" | "CREDITED" | "REJECTED";
  rejection_reason: string | null;
  created_at: string;
  verified_at: string | null;
  credited_at: string | null;
  /** Session 89: il controllo della fattura dopo una ricarica con carta
   *  (null se l'amministratore l'ha verificata prima del pagamento). */
  review_status: "PENDING" | "APPROVED" | "REJECTED" | null;
  reviewed_at: string | null;
  review_note: string | null;
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


// --- Pagamento del contratto (Session 44) ----------------------------------
// Contracts only; the Shop checkout is separate and unchanged. Every amount
// is computed server-side from the figure frozen on the contract -- the
// browser sends back a plan key and nothing else.

export type ContractPaymentOptionRead = {
  /** FULL / INSTALMENTS_3 / MONTHLY_12 */
  key: string;
  label: string;
  description: string;
  instalments: number;
  instalment_cents: number;
  total_cents: number;
  /** Difference between this plan's total and the contract's own amount,
      caused by rounding an instalment to the cent. Shown, never hidden. */
  rounding_difference_cents: number;
};

export type ContractPaymentOptionsRead = {
  contract_id: string;
  payable: boolean;
  status: string;
  /** At the payment step but with no frozen amount -- a contract created
      before the price snapshot existed. Distinct from "not payable" so the
      message can say whose problem it is. */
  missing_amount: boolean;
  gross_amount_cents: number | null;
  card_available: boolean;
  options: ContractPaymentOptionRead[];
  /** Set once Stripe confirmed the (first) payment -- possibly while the
      documents are still waiting for approval (Session 49). */
  paid_at: string | null;
  payment_plan: string | null;
  /** Automatic JavCash on this contract: the percentage, and what it comes
      to on the whole amount. On instalments it is credited rata per rata. */
  cashback_percentage: number;
  cashback_total_cents: number;
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
  /** SCHEDULED / PAID / FAILED */
  status: string;
  paid_at: string | null;
  /** STRIPE_CHECKOUT / STRIPE_INVOICE / ADMIN */
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

// --- Shop Jav Partner (CJ Dropshipping, Session 60) ---------------------------------

export type CjSettingsRead = {
  api_key_configured: boolean;
  api_key_hint: string | null;
  connected: boolean;
  token_expires_at: string | null;
  enabled: boolean;
  sandbox: boolean;
  usd_eur_rate: number;
  markup_percentage: number;
  markup_fixed_cents: number;
  price_rounding: "90" | "99" | "NONE";
  shipping_mode: "CUSTOMER_PAYS" | "INCLUDED";
  default_credit_percentage: number;
  destination_country: string;
  auto_forward: boolean;
  last_balance_usd: number | null;
  last_balance_at: string | null;
};

export type CjCatalogItem = {
  pid: string;
  name_en: string;
  sku: string;
  image_url: string | null;
  sell_price_usd: string;
  estimated_price_cents: number | null;
  inventory: number | null;
  category_name: string | null;
  free_shipping: boolean;
  already_imported: boolean;
};

export type CjCatalogPage = {
  page: number;
  total_pages: number;
  total_records: number;
  items: CjCatalogItem[];
};

export type CjProductPreview = {
  pid: string;
  sku: string;
  name_en: string;
  description_text: string;
  category_name: string | null;
  images: string[];
  origin_country: string;
  shipping_estimate_usd: number | null;
  shipping_estimate_cents: number | null;
  shipping_days: string | null;
  shipping_carrier: string | null;
  ships_to_destination: boolean;
  variants: {
    vid: string;
    sku: string;
    label: string;
    image_url: string | null;
    cost_usd: number;
    weight_g: number;
    inventory: number;
    price_cents: number;
  }[];
};

export type CjVariantAdminRead = {
  id: string;
  cj_vid: string;
  cj_sku: string | null;
  label: string;
  image_url: string | null;
  cost_usd: number;
  weight_g: number;
  price_cents: number;
  price_override_cents: number | null;
  effective_price_cents: number;
  inventory: number;
  active: boolean;
  available_on_cj: boolean;
};

export type CjProductAdminRead = {
  id: string;
  cj_pid: string;
  cj_sku: string | null;
  name: string;
  name_en: string | null;
  description: string;
  image_url: string | null;
  images: string[];
  category_name: string | null;
  origin_country: string;
  shipping_estimate_usd: number | null;
  shipping_days: string | null;
  status: "ACTIVE" | "INACTIVE";
  credit_discount_percentage: number;
  markup_percentage: number | null;
  last_synced_at: string | null;
  sync_error: string | null;
  paid_orders: number;
  created_at: string;
  variants: CjVariantAdminRead[];
  category_ids?: string[];
};

/** Session 68: rules shared by the three shops of imported products. */
export type ShopSectionKey = "internal" | "partner" | "dropshipping";

export type MarketplaceConfigRead = {
  /** Session 79: quattro negozi, «Fai la Spesa con Jav» compreso. */
  labels: { aliexpress: string; cj: string; shopify: string; jav_market: string; kappa_market: string; vaitto_market: string; symphonya_market: string; soleil_market: string };
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

export type CjProductRead = {
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
  /** Prices are the full (card) ones; bank transfer takes this % off. */
  bank_transfer_discount_percentage: number;
  in_stock: boolean;
  variants: { id: string; label: string; image_url: string | null; price_cents: number; in_stock: boolean }[];
  /** Le categorie di questo Marketplace a cui il prodotto appartiene: è con
      queste che il cliente filtra la griglia dello Shop. */
  category_ids?: string[];
};

export type CjQuoteRead = {
  variant_id: string;
  product_name: string;
  variant_label: string;
  quantity: number;
  unit_price_cents: number;
  items_cents: number;
  /** Quanto paga il cliente: max(costo reale AliExpress, minimo configurato). */
  shipping_cents: number;
  /** Session 78: l'IVA aggiunta sopra la merce, già dentro amount_cents. */
  vat_cents?: number;
  vat_percentage?: number;
  /** Session 76, solo informativi: quanto costa a noi, il minimo in vigore e
      se è stato il minimo a decidere. Al cliente si mostra shipping_cents. */
  supplier_shipping_cents?: number;
  minimum_shipping_cents?: number;
  shipping_is_minimum?: boolean;
  /** Solo «Fai la Spesa» (ottobre 2026): minimo d'ordine e spedizione
      gratuita, misurati sulla merce IVA inclusa (merchandise_cents). */
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
  card_available: boolean;
  default_address: { street: string | null; city: string | null; province: string | null; postal_code: string | null };
};

export type CjFulfillmentStatus =
  | "NOT_SENT" | "SENDING" | "SENT" | "PROCESSING" | "SHIPPED" | "DELIVERED" | "ERROR" | "CJ_CANCELLED";

export type CjDeliveryStatus = "RECEIVED" | "PREPARING" | "SHIPPED" | "DELIVERED" | "PROBLEM";

export type CjPaymentStatus = "NOT_REQUIRED" | "PENDING" | "PAYMENT_REQUIRED" | "PAID" | "FAILED";

export type CjCashSummary = {
  orders_to_pay: number;
  orders_payment_required: number;
  required_usd: number;
  required_cents: number;
  balance_usd: number | null;
  balance_at: string | null;
  shortfall_usd: number;
  shortfall_cents: number;
  sandbox: boolean;
  auto_forward: boolean;
};

export type CjOrderRead = {
  id: string;
  customer_user_id: string;
  customer_display_name: string;
  cj_product_id: string;
  cj_variant_id: string;
  product_name: string;
  product_image_url: string | null;
  variant_label: string | null;
  created_by_user_id: string;
  quantity: number;
  unit_price_cents: number;
  shipping_cents: number;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  /** Taken off for paying by bank transfer (0 by card). */
  bank_transfer_discount_cents: number;
  /** Today's bank-transfer discount, for switching an unpaid order to bank transfer. */
  bank_transfer_discount_percentage: number;
  /** What is really paid in euro: residual - bank-transfer discount. */
  amount_due_cents: number;
  /** Session 74: l'IVA già compresa nel prezzo, congelata alla creazione
      dell'ordine (imponibile = importo - sconto bonifico; i JavCash non lo
      riducono). Un ordine di prima non ce l'ha, o ce l'ha a 0: lì non si
      scrive niente, mai "IVA 0,00 €". */
  vat_percentage?: number;
  vat_amount_cents?: number;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER" | "CARD";
  stripe_checkout_session_id: string | null;
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
  /** The only shipping state a customer sees: RECEIVED until the supplier
      is paid (whatever the reason), then PREPARING, SHIPPED, DELIVERED. */
  delivery_status: CjDeliveryStatus | null;
  tracking_number: string | null;
  tracking_url: string | null;
  shipped_at: string | null;
  delivered_at: string | null;
  // Admin only
  fulfillment_status?: CjFulfillmentStatus;
  cj_payment_status?: CjPaymentStatus;
  cj_cost_usd?: number;
  cj_cost_is_actual?: boolean;
  cj_cost_cents?: number;
  cj_order_code?: string | null;
  cj_pay_url?: string | null;
  cj_product_amount_usd?: number | null;
  cj_postage_amount_usd?: number | null;
  cj_ioss_amount_usd?: number | null;
  cj_paid_at?: string | null;
  attempt_count?: number;
  last_attempt_at?: string | null;
  next_retry_at?: string | null;
  last_error_kind?: string | null;
  cj_order_id?: string | null;
  cj_order_status?: string | null;
  cj_amount_usd?: number | null;
  sandbox?: boolean;
  logistic_name?: string;
  origin_country?: string;
  unit_cost_usd?: number;
  shipping_cost_usd?: number;
  usd_eur_rate?: number;
  estimated_margin_cents?: number;
  forwarded_at?: string | null;
  forward_error?: string | null;
  last_cj_sync_at?: string | null;
};

// --- Marketplace 3: Shopify dropshipping (Session 68) ---------------------------------------

/** Same shape as CjProductRead on purpose: the Shop grid and the product
    window treat every Marketplace the same way. */
export type ShopifyProductRead = CjProductRead;
/** Same fields as CjQuoteRead. */
export type ShopifyQuoteRead = CjQuoteRead;

export type ShopifySettingsRead = {
  shop_domain: string | null;
  /** CLIENT_CREDENTIALS = app from the Dev Dashboard; TOKEN = legacy shpat_. */
  auth_mode: "CLIENT_CREDENTIALS" | "TOKEN" | null;
  client_id: string | null;
  client_secret_configured: boolean;
  client_secret_hint: string | null;
  access_token_configured: boolean;
  access_token_hint: string | null;
  api_version: string;
  enabled: boolean;
  shop_name: string | null;
  shop_currency: string | null;
  currency_rate: number;
  price_basis: "COST" | "PRICE";
  markup_percentage: number;
  markup_fixed_cents: number;
  price_rounding: "90" | "99" | "NONE";
  shipping_mode: "CUSTOMER_PAYS" | "INCLUDED";
  shipping_flat_cents: number;
  shipping_days: string | null;
  default_credit_percentage: number;
  max_credit_percentage: number;
  auto_forward: boolean;
  last_connected_at: string | null;
};

export type ShopifyCatalogVariant = {
  variant_id: string;
  sku: string | null;
  label: string;
  image_url: string | null;
  cost_amount: number | null;
  source_price_amount: number;
  inventory: number | null;
  price_cents: number;
};

export type ShopifyCatalogProduct = {
  product_id: string;
  handle: string | null;
  title: string;
  vendor: string | null;
  status: string | null;
  description_text: string;
  image_url: string | null;
  images: string[];
  variants: ShopifyCatalogVariant[];
  min_price_cents: number | null;
  max_price_cents: number | null;
  currency: string | null;
  already_imported?: boolean;
};

export type ShopifyCatalogPage = { items: ShopifyCatalogProduct[]; next_cursor: string | null };

export type ShopifyProductAdminRead = {
  id: string;
  shopify_product_id: string;
  handle: string | null;
  name: string;
  source_title: string | null;
  vendor: string | null;
  description: string;
  image_url: string | null;
  images: string[];
  status: "ACTIVE" | "INACTIVE";
  credit_discount_percentage: number;
  markup_percentage: number | null;
  last_synced_at: string | null;
  sync_error: string | null;
  paid_orders: number;
  created_at: string;
  variants: {
    id: string;
    shopify_variant_id: string;
    sku: string | null;
    label: string;
    image_url: string | null;
    cost_amount: number | null;
    source_price_amount: number;
    price_cents: number;
    price_override_cents: number | null;
    effective_price_cents: number;
    inventory: number | null;
    active: boolean;
    available_in_store: boolean;
  }[];
  category_ids?: string[];
};

export type ShopifyFulfillmentStatus = "NOT_SENT" | "SENDING" | "SENT" | "SHIPPED" | "DELIVERED" | "ERROR" | "CANCELLED";

export type ShopifyOrderRead = Omit<
  CjOrderRead,
  | "cj_product_id" | "cj_variant_id" | "fulfillment_status" | "cj_payment_status" | "cj_cost_usd" | "cj_cost_is_actual"
  | "cj_cost_cents" | "cj_order_code" | "cj_pay_url" | "cj_product_amount_usd" | "cj_postage_amount_usd"
  | "cj_ioss_amount_usd" | "cj_paid_at" | "cj_order_id" | "cj_order_status" | "cj_amount_usd" | "sandbox"
  | "logistic_name" | "origin_country" | "unit_cost_usd" | "shipping_cost_usd" | "usd_eur_rate" | "last_cj_sync_at"
> & {
  shopify_product_id: string;
  shopify_variant_id: string;
  // Admin only
  fulfillment_status?: ShopifyFulfillmentStatus;
  shopify_order_id?: string | null;
  shopify_order_name?: string | null;
  shopify_draft_order_id?: string | null;
  shopify_fulfillment_status?: string | null;
  tracking_company?: string | null;
  unit_cost_amount?: number | null;
  currency_rate?: number;
  supplier_cost_cents?: number | null;
  last_sync_at?: string | null;
};

// --- Marketplace 3: AliExpress dropshipping API (Session 71) ---------------------------------

/** Same shape as CjProductRead, exactly like the Shopify twin: the Shop grid
    and the product window treat every Marketplace the same way. */
export type AliexpressProductRead = CjProductRead;
/** Same fields as CjQuoteRead. */
export type AliexpressQuoteRead = CjQuoteRead;

/** Everything the Shopify settings carry for pricing, but the connection is
    an app of the openservice.aliexpress.com portal (App Key + App Secret)
    plus the seller's authorization, which hands out a token with an expiry
    the server renews on its own -- there is no shop domain and no fixed
    token to paste. */
export type AliexpressSettingsRead = {
  app_key: string | null;
  app_secret_configured: boolean;
  app_secret_hint: string | null;
  connected: boolean;
  account_label: string | null;
  token_expires_at: string | null;
  last_connected_at: string | null;
  enabled: boolean;
  /** Where we ship and in which currency/language AliExpress answers. */
  ship_to_country: string;
  target_currency: string;
  target_language: string;
  currency_rate: number;
  price_basis: "COST" | "PRICE";
  markup_percentage: number;
  markup_fixed_cents: number;
  price_rounding: "90" | "99" | "NONE";
  shipping_mode: "CUSTOMER_PAYS" | "INCLUDED";
  /** Session 76: la spesa di spedizione **minima** addebitata al cliente,
      non più un forfait. Si paga il costo reale che AliExpress quota per
      quel carrello, e questo importo quando quello è più basso; il minimo
      vale una volta per ordine, mai per articolo. */
  shipping_minimum_cents: number;
  shipping_days: string | null;
  default_credit_percentage: number;
  max_credit_percentage: number;
  auto_forward: boolean;
};

export type AliexpressCatalogVariant = {
  variant_id: string;
  /** AliExpress' own SKU key, needed when the order is placed. */
  sku_attr: string | null;
  sku: string | null;
  label: string;
  image_url: string | null;
  cost_amount: number | null;
  source_price_amount: number;
  inventory: number | null;
  price_cents: number;
};

export type AliexpressCatalogProduct = {
  product_id: string;
  product_url: string | null;
  title: string;
  vendor: string | null;
  status: string | null;
  description_text: string;
  image_url: string | null;
  images: string[];
  /** Empty on a search hit: AliExpress only lists the SKUs on the detail
      call (catalog/product), which is what the import window loads. */
  variants: AliexpressCatalogVariant[];
  min_price_cents: number | null;
  max_price_cents: number | null;
  currency: string | null;
  /** Search hits only. */
  evaluate_rate?: string | null;
  already_imported?: boolean;
};

export type AliexpressCatalogPage = { items: AliexpressCatalogProduct[]; next_cursor: string | null };

export type AliexpressProductAdminRead = {
  id: string;
  aliexpress_product_id: string;
  product_url: string | null;
  name: string;
  source_title: string | null;
  vendor: string | null;
  description: string;
  image_url: string | null;
  images: string[];
  status: "ACTIVE" | "INACTIVE";
  credit_discount_percentage: number;
  markup_percentage: number | null;
  last_synced_at: string | null;
  sync_error: string | null;
  paid_orders: number;
  created_at: string;
  variants: {
    id: string;
    aliexpress_sku_id: string;
    sku_attr: string | null;
    sku: string | null;
    label: string;
    image_url: string | null;
    cost_amount: number | null;
    source_price_amount: number;
    price_cents: number;
    price_override_cents: number | null;
    effective_price_cents: number;
    inventory: number | null;
    active: boolean;
    available_in_store: boolean;
  }[];
  category_ids?: string[];
};

/** Same states as the Shopify twin: what the supplier order is doing. */
export type AliexpressFulfillmentStatus = ShopifyFulfillmentStatus;

export type AliexpressOrderRead = Omit<
  ShopifyOrderRead,
  | "shopify_product_id" | "shopify_variant_id" | "fulfillment_status" | "shopify_order_id" | "shopify_order_name"
  | "shopify_draft_order_id" | "shopify_fulfillment_status"
> & {
  aliexpress_product_id: string;
  aliexpress_variant_id: string;
  // Admin only
  fulfillment_status?: AliexpressFulfillmentStatus;
  aliexpress_order_id?: string | null;
  aliexpress_order_status?: string | null;
  /** Our own reference, the one AliExpress echoes back on the order. */
  out_order_id?: string | null;
  /** Session 76: il numero d'ordine che legge il cliente, progressivo e
      condiviso fra i negozi. `order_code` è lo stesso numero come stringa,
      con il ripiego sull'UUID per gli ordini creati prima della sequenza. */
  number?: number;
  order_code?: string;
  /** Session 75: le righe dell'ordine. Le colonne di testata
      (product_name, quantity, unit_price_cents) descrivono la prima e
      restano per gli ordini storici; questo è cosa è stato comprato
      davvero. Ogni ordine ne ha almeno una, anche quelli di prima del
      carrello — la migrazione 0055 gliela ha costruita. */
  items?: AliexpressOrderItemRead[];
  /** Admin: quale numero d'ordine AliExpress è finito su quale riga. Un
      ordine Jav può corrispondere a più ordini fornitore (venditori
      diversi). */
  item_supplier_orders?: { item_id: string; product_name: string; aliexpress_order_id: string | null }[];
  /** Admin, Session 76: la spedizione ha un margine suo. `null` sugli ordini
      venduti prima che il costo reale venisse rilevato. */
  supplier_shipping_cents?: number | null;
  minimum_shipping_cents?: number | null;
  shipping_margin_cents?: number | null;
};

export type AliexpressOrderItemRead = {
  id: string;
  product_id: string;
  variant_id: string;
  /** Congelato sulla riga: un prodotto rinominato non riscrive un ordine passato. */
  product_name: string;
  variant_label: string | null;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
  /** Session 76: il freight AliExpress di questa riga. Il costo reale di un
      ordine è la somma di queste. `null` sugli ordini di prima. */
  supplier_shipping_cents: number | null;
  /** Per riga, perché il fornitore può spezzare un ordine in più spedizioni. */
  tracking_number: string | null;
  tracking_url: string | null;
};

// --- Categorie degli shop (Session 73) ------------------------------------
// Ogni shop (il nostro catalogo e i tre Marketplace) ha le sue categorie:
// l'amministratore le crea nella pagina di quello shop, il cliente ci filtra
// i prodotti. Una categoria appartiene a UNO shop: "Casa" di CJ e "Casa" di
// Shopify sono due righe diverse, perché i cataloghi sono separati.
export type ShopKey = "internal" | "partner" | "dropshipping" | "aliexpress" | "cj" | "shopify" | "jav_market" | "kappa_market" | "vaitto_market" | "symphonya_market" | "soleil_market";

export type ShopCategoryRead = {
  id: string;
  shop: ShopKey;
  name: string;
  /** Ordine di comparsa nella barra delle categorie del cliente. */
  position: number;
  active: boolean;
  /** Quanti prodotti di quello shop sono in questa categoria. */
  product_count: number;
};

/** Per ogni prodotto, le categorie a cui appartiene dentro il suo shop. */
export type ShopCategoryAssignments = Record<string, string[]>;

// --- Il carrello dello Shop (Session 75) ---------------------------------
//
// Una sezione per negozio: i quattro negozi hanno regole che si escludono a
// vicenda (indirizzo e spedizione nei Marketplace, cashback nel catalogo
// interno), quindi righe di negozi diversi non finiscono nello stesso
// ordine. Il cliente vede comunque un carrello solo, diviso in sezioni.

export type CartShop = "aliexpress" | "cj" | "shopify" | "jav_market" | "kappa_market" | "vaitto_market" | "symphonya_market" | "soleil_market" | "catalog";

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
export type CartSectionRead = Omit<CjQuoteRead, "variant_id" | "product_name" | "variant_label" | "quantity" | "unit_price_cents"> & {
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


// --- Marketplace 4: «Fai la Spesa con Jav» (Session 79) -----------------
//
// Catalogo scritto a mano dall'amministratore, con l'azienda produttrice in
// scheda a parte. Al cliente si comporta come gli altri Marketplace, quindi
// la card riusa la stessa forma di CjProductRead: la griglia dello Shop la
// disegna senza sapere da quale negozio venga.

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

/** La card nella griglia del cliente: CjProductRead più il produttore. */
export type JavMarketProductRead = CjProductRead & {
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
  variants: {
    id: string; label: string; sku: string | null; image_url: string | null;
    price_cents: number; inventory: number | null; active: boolean; in_stock: boolean;
  }[];
};

export type JavMarketSettingsRead = {
  enabled: boolean;
  /** Session 80: l'ordine pagato parte da solo verso le aziende. Nasce
      spento — mandare una email a un'azienda vera è un'azione verso
      l'esterno, e la prima volta la si vuole guardare. */
  auto_forward: boolean;
  shipping_mode: "CUSTOMER_PAYS" | "INCLUDED";
  /** Qui è un importo, non un minimo: senza fornitore non c'è un costo
      reale da confrontare (a differenza di AliExpress). */
  shipping_flat_cents: number;
  shipping_days: string | null;
  ship_to_country: string;
  /** Solo «Fai la Spesa» (Kappa condivide il tipo ma non le ha): merce IVA
      inclusa minima per ordinare (0 = nessuna) e da cui la spedizione è
      gratis (null = mai). */
  min_order_cents?: number;
  free_shipping_threshold_cents?: number | null;
};

/** Stessa forma dell'ordine degli altri Marketplace, più il produttore
    congelato su ogni riga. */
export type JavMarketOrderRead = Omit<
  AliexpressOrderRead,
  "aliexpress_product_id" | "aliexpress_variant_id" | "aliexpress_order_id" | "aliexpress_order_status" | "out_order_id"
> & {
  items_cents: number;
  items?: (AliexpressOrderItemRead & { producer_name: string | null })[];
  /** Admin, Session 80: lo stato dell'invio alle aziende. */
  forwarded_at?: string | null;
  forward_error?: string | null;
  producers?: { name: string }[];
};

// --- Marketplace 5: «Market Kappa» (Session 87) ---------------------------
// Clone di «Fai la Spesa con Jav» con tabelle e rotte sue
// (/kappa-market/...), solo Kappa e Robe di Kappa. Le risposte hanno la
// stessa forma, quindi i tipi sono gli stessi; i nomi a parte servono a
// leggere il codice, e a lasciare i due negozi liberi di divergere.
export type KappaMarketProducerPublic = JavMarketProducerPublic;
export type KappaMarketProducerRead = JavMarketProducerRead;
export type KappaMarketProductRead = JavMarketProductRead;
export type KappaMarketAdminProductRead = JavMarketAdminProductRead;
export type KappaMarketSettingsRead = JavMarketSettingsRead;
export type KappaMarketOrderRead = JavMarketOrderRead;

// --- Marketplace 6: «Marketplace VAITTO» (Session 88) ---------------------
// Clone di Market Kappa, rifornito dal feed di Vaitto: in più il costo, il
// listino da mostrare barrato, il ricarico e lo stato del feed.
export type VaittoMarketProducerPublic = JavMarketProducerPublic;
export type VaittoMarketProducerRead = JavMarketProducerRead;
export type VaittoMarketProductRead = Omit<JavMarketProductRead, "variants"> & {
  /** Session 88: il prezzo ha già l'IVA dentro (prezzo del marchio). */
  vat_included?: boolean;
  /** Il listino Vaitto più alto delle varianti, se supera il nostro prezzo. */
  compare_at_cents?: number | null;
  variants: (JavMarketProductRead["variants"][number] & { compare_at_cents?: number | null })[];
};
export type VaittoMarketAdminProductRead = Omit<JavMarketAdminProductRead, "variants"> & {
  vaitto_product_id: string | null;
  category_name: string | null;
  subcategory: string | null;
  gender: string | null;
  source_url: string | null;
  /** null = il ricarico del negozio. */
  markup_percentage: number | null;
  missing_from_feed: boolean;
  /** La percentuale JavCash è stata scelta a mano per questo prodotto. */
  credit_locked: boolean;
  last_synced_at: string | null;
  variants: (JavMarketAdminProductRead["variants"][number] & {
    /** Solo amministrazione: quanto lo paghiamo a Vaitto. */
    cost_cents: number | null;
    /** Il prezzo di vendita suggerito da Vaitto: la base del nostro prezzo. */
    suggested_price_cents: number | null;
    compare_at_cents: number | null;
    barcode: string | null;
    available_in_store: boolean;
    price_locked: boolean;
    /** Non copre costo + spedizione + IVA: non si vende. */
    below_cost: boolean;
  })[];
};
export type VaittoMarketSettingsRead = JavMarketSettingsRead & {
  feed_configured: boolean;
  feed_hint: string | null;
  auto_import: boolean;
  markup_percentage: number;
  /** Session 88: la percentuale JavCash di tutti i prodotti non personalizzati. */
  credit_percentage: number;
  /** FIXED = credit_percentage per tutti; MARGIN = credit_margin_share% del nostro guadagno. */
  credit_mode: "FIXED" | "MARGIN";
  credit_margin_share: number;
  /** Session 88: il prezzo di Vaitto ha già l'IVA dentro (prezzo del marchio). */
  prices_include_vat: boolean;
  /** La nostra spedizione per prodotto, solo nel calcolo del guadagno. */
  shipping_cost_cents: number;
  last_import_at: string | null;
  last_import_summary: string | null;
  last_import_error: string | null;
};
export type VaittoMarketOrderRead = Omit<JavMarketOrderRead, "items"> & {
  items?: (NonNullable<JavMarketOrderRead["items"]>[number] & {
    supplier_sku?: string | null;
    barcode?: string | null;
    supplier_url?: string | null;
  })[];
};
export type VaittoFacets = {
  brands: { id: string; name: string; products: number; active: number }[];
  subcategories: { key: string; name: string; products: number; active: number }[];
};

// --- «Marketplace SYMPHONYA» (Session 89, Marketplace 6 per il cliente) ----
// Clone di VAITTO, rifornito dall'API di Symphonya (profumi e cosmetici).
// Clone di Market Kappa, rifornito dal feed di Symphonya: in più il costo, il
// listino da mostrare barrato, il ricarico e lo stato del feed.
export type SymphonyaMarketProducerPublic = JavMarketProducerPublic;
export type SymphonyaMarketProducerRead = JavMarketProducerRead;
export type SymphonyaMarketProductRead = Omit<JavMarketProductRead, "variants"> & {
  /** Session 88: il prezzo ha già l'IVA dentro (prezzo del marchio). */
  vat_included?: boolean;
  /** Il listino Symphonya più alto delle varianti, se supera il nostro prezzo. */
  compare_at_cents?: number | null;
  variants: (JavMarketProductRead["variants"][number] & { compare_at_cents?: number | null })[];
};
/** Session 89: una pagina della vetrina del cliente, uguale per tutti i
 *  Marketplace (GET …/products/mine/page o …/products/active/page; vedi
 *  apps/api/app/domains/marketplaces/paging.py): i cataloghi arrivano un po'
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
export type SymphonyaMarketAdminProductRead = Omit<JavMarketAdminProductRead, "variants"> & {
  symphonya_product_id: string | null;
  category_name: string | null;
  subcategory: string | null;
  gender: string | null;
  source_url: string | null;
  /** null = il ricarico del negozio. */
  markup_percentage: number | null;
  missing_from_feed: boolean;
  /** La percentuale JavCash è stata scelta a mano per questo prodotto. */
  credit_locked: boolean;
  last_synced_at: string | null;
  variants: (JavMarketAdminProductRead["variants"][number] & {
    /** Solo amministrazione: quanto lo paghiamo a Symphonya. */
    cost_cents: number | null;
    /** Il prezzo di vendita suggerito da Symphonya: la base del nostro prezzo. */
    suggested_price_cents: number | null;
    compare_at_cents: number | null;
    barcode: string | null;
    available_in_store: boolean;
    price_locked: boolean;
    /** Non copre costo + spedizione + IVA: non si vende. */
    below_cost: boolean;
  })[];
};
export type SymphonyaMarketSettingsRead = JavMarketSettingsRead & {
  feed_configured: boolean;
  feed_hint: string | null;
  auto_import: boolean;
  markup_percentage: number;
  /** Session 88: la percentuale JavCash di tutti i prodotti non personalizzati. */
  credit_percentage: number;
  /** FIXED = credit_percentage per tutti; MARGIN = credit_margin_share% del nostro guadagno. */
  credit_mode: "FIXED" | "MARGIN";
  credit_margin_share: number;
  /** Session 88: il prezzo di Symphonya ha già l'IVA dentro (prezzo del marchio). */
  prices_include_vat: boolean;
  /** La nostra spedizione per prodotto, solo nel calcolo del guadagno. */
  shipping_cost_cents: number;
  last_import_at: string | null;
  last_import_summary: string | null;
  last_import_error: string | null;
};
export type SymphonyaMarketOrderRead = Omit<JavMarketOrderRead, "items"> & {
  items?: (NonNullable<JavMarketOrderRead["items"]>[number] & {
    supplier_sku?: string | null;
    barcode?: string | null;
    supplier_url?: string | null;
  })[];
};
export type SymphonyaFacets = {
  brands: { id: string; name: string; products: number; active: number }[];
  subcategories: { key: string; name: string; products: number; active: number }[];
};

// --- «Marketplace SOLEIL» (Session 90, «Market 7» per il cliente) ----------
// Clone di Symphonya, rifornito dall'Excel del portale affiliati SoleilDrop
// (nessuna chiave API: l'import è solo a mano).
export type SoleilMarketProducerPublic = JavMarketProducerPublic;
export type SoleilMarketProducerRead = JavMarketProducerRead;
export type SoleilMarketProductRead = SymphonyaMarketProductRead;
export type SoleilMarketAdminProductRead = Omit<SymphonyaMarketAdminProductRead, "symphonya_product_id"> & {
  soleil_product_id: string | null;
};
export type SoleilMarketSettingsRead = Omit<SymphonyaMarketSettingsRead, "feed_configured" | "feed_hint" | "auto_import"> & {
  /** API affiliati SoleilDrop (13/10/2026). Mai la chiave né il segreto:
      solo se ci sono e le ultime cifre della chiave. */
  api_configured: boolean;
  api_key_hint: string | null;
  webhook_configured: boolean;
  /** L'indirizzo da incollare nell'area SoleilDrop, sezione Webhook. */
  webhook_url: string | null;
  auto_import: boolean;
  eshop_name: string | null;
  wallet_balance_cents: number | null;
  last_api_check_at: string | null;
  last_api_error: string | null;
  last_webhook_at: string | null;
  last_order_sync_at: string | null;
};
export type SoleilMarketOrderRead = SymphonyaMarketOrderRead & {
  /** L'ordine su SoleilDrop, quando è partito via API (solo admin). */
  external_ref?: string;
  soleil_order_number?: string | null;
  soleil_status_code?: string | null;
  soleil_status_label?: string | null;
  soleil_wallet_charged_cents?: number | null;
  soleil_synced_at?: string | null;
};
export type SoleilFacets = SymphonyaFacets;

// --- PIN dei JavCash (Session 87) ---------------------------------------
/** Come il cliente conferma l'uso dei JavCash al checkout. `method` è
    quello valido adesso: EMAIL anche con il PIN acceso, se è bloccato. */
export type SpendPinStatusRead = {
  enabled: boolean;
  method: "PIN" | "EMAIL";
  locked_until: string | null;
};
