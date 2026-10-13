# Business Rules

Status: no source document (`Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf`)
was present in the repository at the time this was written. Every numeric threshold,
percentage and formula below is a **placeholder** used to make the system runnable and
testable. None of it should be treated as the real Jav commercial policy until
confirmed. Every placeholder is also listed in `open-questions.md` with the exact
config location to change once real figures are available.

## Money

- All monetary amounts are stored as integer cents (`*_cents BIGINT`) in the database
  and as `Decimal` in Python at the API boundary. `float` is never used for money,
  percentages, or any economic quantity.
- Currency is EUR only in v1; a `currency` column exists on ledger rows for future
  multi-currency support but is not exercised.
- Rounding: half-up to the nearest cent, applied only at the point a figure is
  persisted to `commission_movements` — intermediate calculation steps keep full
  precision (`Decimal` with explicit context), see `commission-engine-specification.md`.

## Ranks / career plan (PLACEHOLDER — see open-questions.md #1)

Configured via the `ranks` table, not hardcoded. Seed values used for demo/tests:

| code | level | personal_token_cents | notes |
|---|---|---|---|
| S1 | 1 | 4000 | base seller |
| S2 | 2 | 4500 | |
| S3 | 3 | 5000 | |
| TL1..TL4 | 4-7 | 5500-7000 | Team Leader tiers |
| MD1..MD5 | 8-12 | 7500-9500 | Manager Director tiers |

`single_branch_cap_percentage` defaults to 33% for every rank (see "Regola del 33%"
below) but is per-rank, per-plan-version configurable.

### Rank promotion progress (PLACEHOLDER, added Session 15)

`personal_volume_threshold_cents` / `group_volume_threshold_cents` were present
in the schema since the very first migration but always left at 0 (never
populated, never read) until the user explicitly asked for real numbers
("procurati quei criteri qualifica e falli tu" -- go get those qualification
criteria and set them yourself) rather than leave the feature unbuilt.
Migration `0010` and `seed/ranks.py` seed the figures below; they are still a
placeholder pending the real `Allegato_A_Piano_Carriera_Regolamento_
Provvigionale.pdf` (see `open-questions.md #1`) -- reasonable, ascending,
demo-scale numbers picked by the assistant on explicit request, not confirmed
Jav policy.

| code | personal_volume_threshold_cents | group_volume_threshold_cents |
|---|---|---|
| S1 | 0 | 0 |
| S2 | 1500 | 1500 |
| S3 | 3000 | 4000 |
| TL1 | 3000 | 8000 |
| TL2 | 3000 | 12000 |
| TL3 | 3000 | 16000 |
| TL4 | 3000 | 20000 |
| MD1 | 3000 | 25000 |
| MD2 | 3000 | 30000 |
| MD3 | 3000 | 35000 |
| MD4 | 3000 | 40000 |
| MD5 | 3000 | 45000 |

`GET /network/agents/{agent_id}/rank-progress`
(`commissions/services/rank_progress.py`) compares an agent's CUMULATIVE
("lifetime", not evaluated over `evaluation_window_months` -- that column
remains unused, a separate not-yet-built axis of this same placeholder)
contract value on `ACTIVE`/`RENEWED` contracts against the NEXT rank's
thresholds: `personal_volume_cents` is what the agent personally produced;
`group_volume_cents` is the same sum across their entire downline including
themselves (same descendant lookup as `get_branch_summary`). Surfaced as two
progress bars in the promoter's own "La mia Azienda" panel and in the admin's
per-promoter "Apri Rete" drill-down (same shared component). An agent already
at the top rank (no higher `level` exists for their `rule_version`) shows
"qualifica massima raggiunta" instead of a bar.

### Automatic monthly rank evaluation (PLACEHOLDER, added Session 20)

Separate axis from the progress display above, and from the same unconfirmed
placeholder thresholds: `commissions/services/rank_evaluation.py` actually
**writes** `AgentProfile.current_rank_id`, both up and down, instead of just
displaying progress toward it. Explicit user decisions behind this design,
pending the real `Allegato_A_...Regolamento_Provvigionale.pdf`:

- **Single-calendar-month window, uniform for every rank** -- not the
  cumulative lifetime total `rank_progress.py` uses, and not a per-rank
  rolling window via `evaluation_window_months` (still unused). Every ACTIVE
  agent's personal and group volume is recomputed from scratch for one
  month, and the rank ladder (`ranks` rows with `valid_to IS NULL` for the
  org) is walked to find the highest rank whose thresholds are both met.
- **Promotes AND demotes**: the rank is always realigned exactly to that
  month's production in either direction -- an agent who produced nothing
  that month can drop all the way back to the floor rank even after a strong
  track record in prior months. There is no rolling average or grace period.
- Celery Beat (`celery_app.py`, `monthly-rank-evaluation`) runs this on day 1
  of each month at 02:00 UTC for every organization, evaluating the calendar
  month that just closed (`previous_calendar_month()`). An admin holding
  `commissions.evaluate_ranks` (SUPER_ADMIN/ORGANIZATION_ADMIN only, same
  restriction as `network.approve`) can also trigger the identical logic on
  demand via `POST /commissions/rank-evaluation/run` (optional `?month=
  YYYY-MM`, the admin promoter panel's "Valuta gradi ora" button) -- useful
  if the scheduled run needs to be re-run or previewed. Every change is
  recorded in `agent_rank_history` (`calculation_source` AUTOMATIC or
  MANUAL) and `audit_log`, and the affected agent gets an in-app
  notification.

### Promoter disattivato: il contratto risale allo sponsor attivo (Session 38) {#terminated-promoter-fallback}

A customer's referring promoter can be deactivated (`agent_profiles.status =
TERMINATED`) months after that customer signed up. `create_contract()` refuses
to attribute a contract to a non-ACTIVE agent — correctly: a contract that
activates and pays nobody is the failure documented in
`paid-contract-commission-audit.md`. The result was a customer who could not
activate anything, ever, and saw only "Si è verificato un errore imprevisto"
(the refusal escaped `POST /contracts/mine` as an unhandled 500). Three real
customers were in this state when it was found.

**Rule, chosen explicitly by the business**: walk **up** to the nearest ACTIVE
sponsor rather than block.

- `network/service.py::resolve_nearest_active_agent` returns the agent if they
  are ACTIVE, otherwise the closest ACTIVE ancestor, otherwise `None`. It
  reads the closure table for structurally open edges and then filters by the
  agent's own status — the two are independent (`effective_to IS NULL` means
  "this edge is current", not "this person is still working").
- Walking up, rather than falling back to the root, is the point: the branch
  that actually built the relationship keeps it.
- **The original referrer is still recorded** on the contract
  (`first_referrer_agent_id`), so nothing is rewritten — and the substitution
  writes an `audit_log` row (`contract.producer_substituted`, with the old and
  new agent), because somebody other than the customer's own referrer is being
  credited and "why is this Alessandro's and not Salvatore's?" deserves an
  answer, not an inference from two statuses.
- **The same rule widens the CRM path**: the inheriting sponsor may activate a
  contract for that customer. Without it, a customer whose promoter left is
  unreachable from both sides — they cannot self-activate and nobody can do it
  for them. It widens access to the **upline only**; a promoter on a different
  branch is still refused.
- **No active upline at all** → still blocked, but with a sentence a customer
  can act on ("contatta l'assistenza: ti verrà assegnato un nuovo referente"),
  never an English exception string with a UUID in it, and never a 500.
- The **first-referrer bonus does NOT follow this walk-up**
  (`_maybe_add_first_referrer_bonus` skips a non-ACTIVE referrer). That bonus
  is defined as belonging to the person who brought the customer in; if they
  have left, nobody earns it. The recursive commission is a different thing
  and does transfer. No product enables the bonus today, so this is currently
  theoretical — flag it if that changes.

## Pagamento del contratto: unica, 3 rate, 12 rate (Session 44) {#contract-payment}

**Contracts only.** The Shop's own checkout (orders, imported orders) is a
separate, already-working flow and is untouched: an order is a purchase, a
contract is a subscription to a service.

### Sconto per il pagamento in unica soluzione (Session 64) {#full-payment-discount}

Chi paga il contratto (o l'intera pratica) **tutto subito con carta** ha uno
sconto sul prezzo: **32%** di default, impostabile in Impostazioni (0 = nessuno
sconto). 3 e 12 rate restano a prezzo pieno.

- Lo sconto si applica al prezzo IVA inclusa, arrotondato al centesimo: è lo
  stesso che scontare il prezzo netto e poi aggiungere l'IVA (180 − 32% + IVA).
- Il prezzo del contratto (`gross_amount_cents`) non cambia; lo sconto scelto si
  congela sul contratto (`payment_discount_cents`) quando il cliente sceglie la
  soluzione unica, e tutto ciò che segue (rata registrata, cashback, anteprima
  provvigioni) usa quanto pagato davvero. Un cambio dell'impostazione vale solo
  per i pagamenti successivi.
- Il **cashback** di un pagamento unico scontato è calcolato su quanto pagato
  (open-questions #18). I gettoni provvigionali non cambiano.
- **Bonifico della pratica (Session 65)**: il cliente può scegliere "Paga con
  bonifico" nel checkout finale. È sempre una soluzione unica, con lo stesso
  sconto, congelato su ogni contratto al momento della scelta. I contratti
  risultano pagati solo quando un amministratore conferma "bonifico ricevuto"
  dalla pratica: da lì tutto (rata registrata, cashback, attivazione) segue lo
  stesso percorso del pagamento con carta. Il cliente può caricare la ricevuta;
  un pagamento con carta fatto dopo chiude comunque la pratica.
- Un bonifico confermato a mano dallo staff su un contratto per cui il cliente
  non l'aveva scelto è a prezzo pieno.
- Percentuale confermata dall'azienda: 32%. Cambiandola, i pagamenti già
  scelti o fatti restano con lo sconto di allora.

### Quando si può pagare {#contract-prepayment}

**Changed in Session 49: subito, senza aspettare i documenti.** Per explicit
business request, the customer can pay as soon as the contract exists —
straight from the activation wizard, documents skipped, nothing approved yet.
`contracts/service.py::PREPAYABLE_STATUSES` = `SUBMITTED`,
`DOCUMENTS_PENDING`, `UNDER_REVIEW`, `APPROVED`, `PAYMENT_PENDING`;
`is_payable()` also requires a frozen amount and `paid_at IS NULL`.

**Paying is not activating.** Business rule, restated by the business in the
same session: *le provvigioni partono solo all'approvazione*. So:

- Payment confirmed while the documents are not yet approved → `paid_at` is
  set, the JavCash is credited, staff are notified
  (`CONTRACT_PAID_BEFORE_APPROVAL`, audit `contract.paid_before_approval`) —
  and **the status does not move**.
- Administrator approves → `APPROVED → PAYMENT_PENDING` as always, and
  `transition_contract` sees `paid_at` already set and continues straight to
  `PAID → ACTIVATION_PENDING → ACTIVE`. That is the only point commissions
  and the network snapshot are produced, exactly as before.
- Payment confirmed when the documents are already approved
  (`PAYMENT_PENDING`) → unchanged: `PAID` → `ACTIVE` immediately.
- **Rejecting a paid contract** notifies staff (`CONTRACT_PAID_REJECTED`):
  refund, the credited JavCash and, on an instalment plan, cancelling the
  Stripe subscription are human decisions, never automatic. A payment that
  lands on a contract already rejected is still recorded (the money moved),
  earns no JavCash, and raises the same notification.

### Le tre modalità

| Piano | Come funziona |
|---|---|
| **Soluzione unica** | Un addebito, `mode="payment"`. |
| **3 rate mensili** | Abbonamento Stripe, prima rata subito, altre due addebitate da sole. |
| **12 rate mensili** | Identico, con 12 rate. |

3 rate and 12 rate are **the same mechanism** and differ only in the count.
No external financing provider is involved — Jav splits its own
invoice — so this needs no capability beyond ordinary card payments. (This is
what the earlier "finanziaria Stripe" question turned out to mean; see
`open-questions.md` #12.)

**Everything is created through the API, per contract.** No Stripe Product or
Price is defined in the dashboard: the Price is built inline from
`contracts.gross_amount_cents`, the amount already frozen on that contract
with that customer's VAT. A fixed Price would have to be re-made by hand on
every price change and would know nothing about who is buying.

**A subscription runs forever unless told to stop**, so "12 rate" is made
true explicitly: `cancel_at` is set on the subscription right after it
exists, rather than counting invoices as they arrive — one missed webhook
delivery would otherwise keep charging somebody who had finished paying.

### Gli arrotondamenti, detti e non nascosti

A Stripe subscription bills the **same** amount every period, and a price
rarely divides evenly by 3 or 12. The instalment is rounded to the cent and
the plan's real total (`instalment × N`) is **shown next to each option**,
with the difference from the contract spelled out when there is one — at most
6 cents for 12 instalments, and exactly 0 for every price currently in the
catalog (249,00 divides cleanly by both 3 and 12).

The two obvious alternatives are worse: adding the remainder to the first
invoice requires a Stripe Product created **per contract**
(`add_invoice_items` cannot take an inline product), littering the account
with one object per sale to recover a few cents; and silently rounding up
overcharges without saying so.

### Cosa rende un contratto pagato

Only the **verified webhook**. The success URL is never proof — a customer
can open it by hand. On `checkout.session.completed` a contract already
approved moves `PAYMENT_PENDING → PAID` (one not yet approved only gets
`paid_at`, see above), which auto-cascades to `ACTIVE` through the
existing state machine, so commissions are calculated at exactly the same
point as for any other contract. For an instalment plan this happens on the
**first** payment: the contract is in force and the rest is collected
automatically.

### Prezzo del contratto: unica soluzione e prezzo mensile {#contract-price-periods}

**Only for recurring product types** (`pricing.RECURRING_PRODUCT_TYPES` =
`ENERGY_CONTRACT`, `SUBSCRIPTION`). A `PHYSICAL` or `DIGITAL` product always
costs its listed price once, whatever `billing_period` / duration its version
carries, and never has a rate price. Shop orders never went through this
and still charge `base_price_cents` once.

Business decision, Session 84 (replaces Session 49's "canone × mesi"): paying
in rate costs more than paying at once, and not by one fixed percentage, so a
package has **two prices**, both net of VAT:

- `base_price_cents` = the whole term **in unica soluzione**
  (`pricing.contract_net_amount_cents`);
- `monthly_price_cents` = the **rata mensile**; paid in rate the contract costs
  `monthly × contract_duration_months` (`pricing.contract_instalments_net_amount_cents`).
  **12 rate and 3 rate split the same total** (3 rate = Klarna-style "in tre").

VAT (business customers only) is added to each total. The contract freezes
both at creation: `net/vat/gross_amount_cents` (one go) and
`instalments_net/vat/gross_amount_cents` (rate). Every plan-dependent amount
(options, Stripe lines, instalment schedule, cashback, commission preview,
accounting, dossier) reads `payment_plans.plan_gross_cents` / `chosen_amounts`,
never `gross_amount_cents` directly.

The listino given by the business (Session 84):

| Pacchetto | Unica soluzione | 12 rate | 3 rate |
|---|---|---|---|
| Privati, Energia circolare | 149 € (no IVA) | 18,30 €/mese = 219,60 € | 219,60 € |
| P.IVA, Energia circolare | 249 € + IVA = 303,78 € | 25 € + IVA = 30,50 €/mese = 366 € | 366 € |
| Condomini e aziende > 15 kW | 350 € + IVA = 427 € | 35 € + IVA = 42,70 €/mese ≈ 512 € | ≈ 512 € |

**No monthly price** (every product right after migration 0064, which
multiplied `base_price_cents` out so no price moved): the rate split the
one-go price, as before. The **one-go discount** (org setting
`contract_full_payment_discount_percentage`, default 32%) applies **only** to
contracts without a rate price (`payment_plans.one_go_discount_percentage`):
with two prices the advantage is already in them, and 32% off 149 € would
sell the package at 101 €.

Rank volumes stay on the **monthly** figure (`rank_progress._volume_cents`:
monthly price, else the old canone backed out of the whole-term price) —
every rank threshold is calibrated on it.

### Cashback JavCash sul contratto: quando arriva {#contract-cashback-timing}

`product_versions.contract_cashback_percentage` of what the customer pays
(VAT included) — set to **100** on the Jav products in Session 49
(*cashback dell'intero importo*). It is credited **when the money arrives**,
not at activation:

- **Soluzione unica** (or a bank transfer an admin confirms): the whole
  amount at once, key `contract-cashback:{contract_id}`, guard
  `contracts.cashback_credited_at`.
- **3 / 12 rate**: **one instalment at a time** (business decision: a
  customer who stops paying after month one must not already hold the year
  in JavCash). The first instalment is credited by the
  `checkout.session.completed` handler (key `…:first`); every later one by
  `invoice.paid` with `billing_reason = subscription_cycle` (key
  `…:{invoice_id}`). The first invoice's own `invoice.paid`
  (`subscription_create`) deliberately credits nothing, so it can never
  double the first month. The amount is the plan's instalment, never the
  invoice's own figure. Approval of a prepaid instalment contract adds
  nothing on top.

### Rate successive

**Stripe configuration required**: the webhook endpoint must have
`invoice.paid` and `invoice.payment_failed` enabled in addition to
`checkout.session.completed` — without them Stripe still charges every month
but the app never hears of it. The subscription id is read from both invoice
shapes (`invoice.subscription` before API "basil",
`invoice.parent.subscription_details.subscription` after).

`invoice.paid` / `invoice.payment_failed` are recorded in the audit log. A
failed monthly charge notifies **both** the staff and the customer and
**does not** suspend the contract: one declined card is not grounds for
automatically cutting off somebody's energy supply — that is a decision for a
human with the context.

### Idempotenza a livello di evento {#stripe-event-idempotency}

`stripe_webhook_events` records the Stripe `event.id` **before** any handler
runs; the UNIQUE constraint decides which of two concurrent deliveries
proceeds. Previously the webhook relied on each handler happening to be
idempotent on its own — true for the flows that existed, but an instalment
plan fires `invoice.paid` every month for the same subscription, so "the same
event again" and "the next instalment" had to stop being indistinguishable.
Stripe promises at-least-once delivery, not exactly-once.

## Anteprima provvigioni e provvigioni per rata (Session 50) {#commission-preview}

Business rules stated by the business: *solo i contratti danno provvigioni*;
the administrator's approval is what sets them going, so the administrator
must **see and accept a preview** first; a contract paid in one go pays its
commissions once, a contract paid in 3 or 12 instalments pays them 3 or 12
times, **each slice when that instalment has really been paid**.

### L'anteprima {#commission-preview-gate}

- `GET /contracts/{id}/commission-preview` (`contracts.review`) —
  `commissions/services/preview.py`, read-only. Same chain the activation
  snapshot would freeze (ancestors of the producer, ACTIVE agents only), same
  tokens (product `commission_tokens` first, rank default second), same pure
  calculator, same `instalment_share`. Shows each beneficiary (role, rank,
  movement type, total), the first-referrer bonus, how it is spread over the
  customer's payments (schedule with dates if paid; every possible split if
  not), the customer's JavCash cashback (explicitly *not* a commission) and
  warnings (unpaid, inactive promoters skipped, no rank, empty chain).
- **Server-enforced gate** (`contracts/router.py::transition_contract`): a
  transition into `APPROVED / PAYMENT_PENDING / PAID / ACTIVATION_PENDING /
  ACTIVE` on a contract never activated before (and not SUSPENDED) is refused
  unless a preview was already accepted or the request carries
  `accept_commission_preview_checksum`. The server **recomputes** the preview
  and refuses (409) if the checksum no longer matches what was on screen.
- Accepted previews are stored verbatim in `contract_commission_plans` (one
  per contract, audit `contract.commission_preview_accepted`) and reopened
  from the contract's **Provvigioni** button as a log, next to the movements
  actually written. If the network changes between acceptance and activation
  the frozen snapshot at activation wins — the log shows both, it does not
  pretend they are the same.
- A contract approved before this existed and paid through Stripe does **not**
  activate on its own: the payment is recorded and it waits for an
  administrator to accept the preview.

### Le rate e le quote di provvigione {#commission-instalments}

- `contract_instalments`: one row per payment owed (1, 3 or 12), created at the
  first recorded payment (the count comes from the plan actually paid; a
  bank transfer confirmed by staff is always 1).
- Each beneficiary's commission is split with
  `run_calculation.py::instalment_share`: equal shares, remainder on the last
  one, so the slices add up **exactly** to the whole commission (e.g. 40,00 €
  on 3 rate = 13,33 + 13,33 + 13,34). Never the whole commission N times. The
  first-referrer bonus is a one-off and goes out whole with instalment 1.
- **Nothing is released before ACTIVE.** At activation every instalment
  already paid is released (`instalments.release_paid_instalments`); after
  that each newly paid instalment releases immediately.
- A paid instalment is released by emitting exactly one
  `ContractInstalmentPaid` outbox event, claimed with a conditional UPDATE on
  `contract_instalments.commission_event_id`; the dispatcher runs the engine
  for that slice (`instalment_number` of `instalments_total`) against the
  snapshot frozen at activation. `ContractActivated` no longer calculates
  anything for a contract that has instalment rows (it would pay the first
  slice twice); `ContractRenewed` is unchanged.
- Who confirms a payment: instalment 1 → the checkout webhook (or staff
  confirming a bank transfer); later ones → `invoice.paid`
  (`billing_reason = subscription_cycle`), matched by Stripe invoice id.
  A failed charge marks the row FAILED with its invoice id and releases
  nothing; staff can confirm it by hand
  (`POST /contracts/{id}/instalments/{n}/confirm`, audit
  `contract.instalment_confirmed_manually`), and Stripe's later retry of that
  same invoice then finds it already paid. `UNIQUE (contract_id, number)` and
  `UNIQUE stripe_invoice_id` make a double release impossible.

## Cashback dei contratti pagati a rate: intero in anticipo o rata per rata (Session 59) {#instalment-cashback}

Il cashback JavCash di un contratto Jav (percentuale del prodotto sul
totale IVA inclusa, Session 49) arriva **tutto subito** se il contratto è
pagato in unica soluzione. Per 3 o 12 rate lo decide l'amministratore in
**Impostazioni → Cashback dei contratti pagati a rate**
(`organizations.settings.contract_instalment_cashback_mode`):

- `PER_INSTALMENT` — **predefinito**, la regola dalla Session 49: una parte a
  ogni rata incassata (Stripe o confermata a mano), così chi smette di pagare
  non ha ricevuto il cashback delle rate mancanti.
- `UPFRONT` — alla **prima rata** il cliente riceve in un'unica ricarica il
  cashback dell'**intero contratto**, e nulla sulle rate successive. Rischio
  accettato scegliendola: se il cliente smette di pagare, il cashback è già
  stato dato (respingere o interrompere il contratto non lo storna da solo).

Regole che valgono in entrambi i casi (`contracts/service.py::
credit_contract_instalment_cashback`):

- **La scelta si applica al pagamento della prima rata e vale per tutta la vita
  del contratto.** Un contratto già accreditato in anticipo (riga di wallet con
  chiave `contract-cashback:<contratto>`, la stessa del pagamento unico) non
  riceve mai il cashback per rata, anche se l'impostazione viene cambiata dopo.
- La chiave di idempotenza per rata è il **numero della rata**
  (`contract-cashback:<contratto>:rata-<n>`), non la fattura Stripe: una rata
  fallita, confermata a mano dall'amministratore e poi riaddebitata con
  successo da Stripe sulla stessa fattura dà cashback una volta sola.
- **Una rata confermata a mano** dall'amministratore (bonifico, carta
  sistemata al telefono) dà il suo cashback come una incassata da Stripe:
  prima non ne dava nessuno.
- Nessun cashback su un contratto respinto o cessato.
- La schermata di pagamento del cliente dice come arriverà il cashback, secondo
  l'impostazione.

## La pratica di attivazione (Session 52) {#contract-request}

**Regola, detta dal business:** un cliente con 10 POD firma **10 contratti** —
10 per il cliente, 10 per il promoter, ognuno con il suo pacchetto, la sua
approvazione, le sue rate e le sue provvigioni — ma compila i propri dati una
volta, carica il documento d'identità una volta, sceglie il pacchetto punto per
punto e **paga una volta**.

La pratica (`contract_requests`) è il contenitore che rende possibile tutto
questo. **Non possiede niente che possieda già un contratto**: stato,
pacchetto, prezzo congelato, approvazione, rate, provvigioni restano sul
singolo contratto. Un contratto respinto, sospeso o cessato dentro una pratica
non tocca gli altri.

**Ogni contratto appartiene a una pratica** (`contracts.contract_request_id`,
NOT NULL). Un contratto creato fuori dal flusso (admin "Nuovo Contratto", le
vecchie rotte `/contracts/mine` e `/contracts/for-customer`) riceve una pratica
di un solo contratto. I contratti esistenti prima della migrazione 0042 hanno
ciascuno la propria, con **lo stesso id del contratto**.

**Sblocca pratica (Session 89).** Una pratica inviata ma non pagata
(nessun contratto o rata pagati, nessun pagamento con carta, nessuna
ricevuta di bonifico, niente addebiti a rate) può essere riportata in
compilazione dall'amministrazione, per cambiare i pacchetti scelti. Tutti
i contratti vivi tornano bozza; le approvazioni si perdono e la pratica,
reinviata, si rivede da capo; il bonifico solo annunciato si annulla; un
link di pagamento aperto prima non paga più niente.

**Chi firma e il suo codice fiscale (Session 89).** Nei dati della pratica
chi firma -- l'intestatario privato o, per un'azienda, il legale
rappresentante -- dà codice fiscale, data e luogo di nascita (un comune,
anche soppresso, o uno Stato estero, scelto dall'elenco). Il codice fiscale
si controlla con cognome, nome, data e luogo, e si controlla anche il
carattere di controllo. L'omocodia è accettata. Il sesso non si chiede: il
giorno vale com'è o +40. **Per scelta dell'utente il controllo non blocca**:
se il codice non torna i dati si salvano lo stesso, il form avvisa
(«Continua comunque») e la scheda pratica mostra «Codice fiscale da
verificare». Bloccano solo il codice mancante o non di 16 caratteri, data e
luogo mancanti e chi firma minorenne. Chi firma dev'essere maggiorenne. Una bozza aperta
prima di questa regola non si invia finché questi dati non ci sono.

### Il percorso

Ridisegnato in Session 53 su richiesta esplicita: **tutti i dati una volta
all'inizio, poi "quanti POD hai?", poi i POD sono già creati e si sceglie solo
il contratto per ciascuno. Il codice POD non si chiede.**

1. **Dati**, in un'unica schermata: intestatario (nome, cognome, email, PEC,
   IBAN), **indirizzo di fornitura** (`contract_requests.street/city/
   province/postal_code`) e **"Quanti POD hai?"** (contatore o numero, 1–50).
   La pratica nasce `DRAFT` con quel numero di POD già creati: ognuno è un
   contratto `DRAFT` senza pacchetto, con un supply point all'indirizzo della
   pratica e **nessun codice POD/PDR** e **nessun tipo energia**
   (`supply_points.energy_type` nullable). Cambiare il numero in bozza
   aggiunge POD o toglie **prima quelli senza contratto scelto**, i più
   recenti per primi; un POD tolto va in `CANCELLED` (nuova transizione `DRAFT
   → CANCELLED`). Cambiare l'indirizzo della pratica sposta tutti i POD che
   erano ancora a quell'indirizzo; un POD spostato su un indirizzo suo lo
   tiene.
   - Il produttore delle provvigioni si risolve **per POD**, con le stesse
     regole di sempre (promoter che compila, o referente del cliente con
     risalita al primo sponsor attivo, auditata).
2. **Documenti d'identità** sulla pratica: identità, codice fiscale, visura
   (per chi la deve dare), più una **bolletta facoltativa** per chi ha
   un'unica bolletta con tutti i punti.
3. **Un contratto per ogni POD**: tutti i pacchetti INTERNAL attivi adatti
   alla tipologia di cliente, oppure "Stesso contratto per tutti i POD".
   **È il pacchetto a decidere se il POD è luce o gas** (il supply point prende
   `energy_type` del prodotto) e **il prezzo si congela sul contratto in quel
   momento** (`contracts/service.py::freeze_price`). Un vincolo CHECK
   (`ck_contracts_product_required`) impedisce a un contratto senza pacchetto
   di uscire da `DRAFT`. Facoltativi per POD: un indirizzo diverso, la bolletta
   o la foto del contatore.
4. **Invio** (`submit`): tutti i POD passano insieme `DRAFT → SUBMITTED →
   DOCUMENTS_PENDING`, e ciascuno va da solo in `UNDER_REVIEW` appena i
   **suoi** documenti obbligatori ci sono. Lo staff riceve **una** notifica
   per pratica. Dopo l'invio POD e contratti scelti non si modificano più: un
   altro POD è una nuova pratica.
5. **Pagamento**, solo dal cliente (il promoter compila e invia, non paga).

Senza codice POD non c'è più il controllo "stesso POD con due contratti in
corso": l'identificazione del punto reale avviene sulla bolletta, in verifica
documenti.

### Documenti: pratica o contratto

Un documento appartiene **a un contratto oppure a una pratica, mai a
entrambi** (`ck_documents_one_owner`). Per ogni casella di un contratto vale
il documento **del contratto se c'è, altrimenti quello della pratica**: la
bolletta del singolo punto vince su quella comune. Caricare un documento sulla
pratica rivaluta tutti i suoi contratti (`maybe_advance_to_under_review`). Il
fascicolo (zip/Drive) di ogni contratto include anche i documenti della
pratica.

### Un pagamento, N contratti

Paga **ogni contratto della pratica inviato, prezzato e non ancora pagato**
(`is_payable`). Un solo piano per pagamento (unica soluzione, 3 o 12 rate).

- **Unica soluzione**: una Checkout Session con **una riga per contratto**.
- **Rate**: **un solo abbonamento Stripe con una voce per contratto**. Ogni
  mese un solo addebito sulla carta, una fattura con N righe.
- L'importo di ogni riga è la rata **di quel contratto**
  (`breakdown_for(piano, prezzo del contratto)`), quindi ogni contratto
  registra esattamente la sua rata e il suo cashback; il cliente vede la somma.
- **Limite Stripe: 20 voci per abbonamento.** Oltre 20 contratti da pagare
  insieme le rate non sono offerte (resta l'unica soluzione, o due pratiche).
- Ogni sessione aperta viene congelata in `contract_request_checkouts`
  (quali contratti, quali importi) **prima** di mandare il cliente su Stripe;
  il webhook paga quello che dice quella riga. Le sessioni precedenti ancora
  aperte vengono fatte scadere. Se comunque due sessioni arrivano a buon fine,
  i contratti già pagati **non vengono ripagati**: lo staff riceve l'avviso
  "Pagamento doppio" e rimborsa quelle righe.
- Ogni riga del prodotto inline porta `metadata.contract_id`; al completamento
  si legge l'abbonamento e si salva su ogni contratto il suo
  `stripe_subscription_item_id`. Ogni `invoice.paid` successivo viene letto
  **riga per riga dall'API** (il payload del webhook non contiene tutte le
  righe) e ogni riga registra la rata del suo contratto: cashback con chiave
  `contract-cashback:{contract}:{invoice}`, provvigioni per rata come da
  Session 50. `contract_instalments.stripe_invoice_id` è ora unico **per
  contratto**, non globalmente.
- Una rata non riscossa manda **un** avviso allo staff e **uno** al cliente
  per tutta la pratica.
- **Cosa legge il cliente su Stripe** (Session 56). Per un abbonamento la
  pagina di Stripe mostra solo "X € al mese": un cliente ha visto "340,00 € al
  mese" per una pratica da 1.020 € e non ha capito che erano 3 rate. Ogni
  Checkout della pratica porta ora sopra il pulsante di pagamento
  (`custom_text.submit`) il piano scritto per intero — "Paghi 3 rate mensili da
  340,00 €, per un totale di 1.020,00 € (3 contratti)… gli addebiti si fermano
  da soli dopo la 3ª rata" — e ogni riga la sua descrizione ("3 rate mensili da
  140,00 € · totale 420,00 €", oppure "Pagamento unico").

### Interrompere gli addebiti di un contratto

"Interrompi addebiti" (`POST /contracts/{id}/stop-billing`, staff) toglie
dall'abbonamento **solo la voce di quel contratto** (senza proration); se era
l'ultima voce, o l'abbonamento era di quel contratto soltanto, annulla
l'abbonamento. Segna `billing_stopped_at`. Il rimborso di quanto già incassato
resta una decisione umana sul pannello Stripe.

### Il catalogo è una vetrina; il promoter compila per il cliente (Session 55)

- **Si attiva solo con la pratica.** In "I miei Contratti" e in Home i pacchetti
  Jav hanno il pulsante **Dettagli**, non più "Attiva Contratto": si
  leggono, e il popup porta a "Attiva nuovo contratto", cioè la stessa pratica
  del pulsante in alto (con quel pacchetto già scelto per ogni POD).
- **Il promoter fa la stessa procedura al posto del cliente**, da "Miei
  Clienti": per un cliente appena registrato (la pratica si apre subito dopo
  la registrazione) o per uno già esistente. La pratica e ogni contratto
  registrano `activated_by_promoter_id` e `created_by_role = PROMOTER` —
  "compilata da X" lo vedono cliente, promoter e amministrazione — ma **tutto
  appartiene al cliente**: `customer_id`, documenti, pagamento.
- All'invio di una pratica compilata da un promoter il cliente riceve una
  **notifica** e un'**email** ("I tuoi contratti sono pronti") con il link a
  "I miei Contratti", dove controlla e **paga lui**. L'email è best-effort,
  dopo il commit.
- **Documenti: file o foto.** Ogni casella e gli allegati aggiuntivi hanno,
  oltre a "Carica", un pulsante **Foto** che apre direttamente la fotocamera
  del telefono (`capture="environment"`, JPG/PNG), per il cliente e per il
  promoter.
- **Accesso ai documenti di un contratto** (`documents/router.py::
  _assert_contract_document_access`): il cliente del contratto; il promoter
  che ne è produttore **o** che ha compilato la sua pratica; lo staff. Si
  controllano **entrambe** le relazioni qualunque sia il primo ruolo nel
  token: un promoter entrato con "Lavora con noi" mantiene il ruolo CUSTOMER e
  prima veniva rifiutato sui documenti dei propri clienti.

### Chi può fare cosa (`/contract-requests`)

- **Cliente**: le proprie pratiche, tutto compreso il pagamento.
- **Promoter**: le pratiche dei clienti per cui può agire (propri, o
  ereditati da un promoter disattivato sotto di lui) — compilare, documenti,
  inviare; **non pagare**.
- **Staff** (`contracts.review`): vede tutte le pratiche e i tentativi di
  pagamento. Approvare e respingere restano **per contratto**, con la stessa
  anteprima provvigioni obbligatoria; "Approva i N contratti in revisione"
  manda N transizioni, ciascuna con il checksum della sua anteprima.

Un utente può essere cliente e promoter insieme: si controllano entrambe le
relazioni, non il primo ruolo del token.

### Correggere il pacchetto di un POD (Session 71) {#staff-repackage}

Il cliente sceglie il pacchetto punto per punto, e può sbagliarlo o non
sceglierlo affatto. Fino alla Session 71 nessuno poteva più rimediare: la
pratica del cliente non era modificabile dall'amministrazione (che poteva
riprendere solo le proprie bozze) e dopo l'invio non era modificabile da
nessuno — restava respingere il contratto e rifare la pratica.

Ora lo **staff** può scegliere o cambiare il pacchetto di un singolo POD dal
dettaglio della pratica (bottone "Scegli pacchetto" / "Cambia pacchetto",
`requests.py::staff_set_point_product`, stessa rotta
`PUT /contract-requests/{id}/points/{contract_id}/product` che usa il
cliente: è l'accesso a decidere quale delle due regole si applica).

Il confine è il denaro, non lo stato della pratica: si cambia finché quel
contratto è in `DRAFT`, `SUBMITTED`, `DOCUMENTS_PENDING`, `UNDER_REVIEW`,
`APPROVED` o `PAYMENT_PENDING` **e** non è pagato (`paid_at`), non ha
addebiti Stripe attivi e non è attivo. Il prezzo viene ricongelato subito e
il punto di fornitura diventa luce o gas secondo il pacchetto scelto; il
cambio finisce nell'audit log (`contract.package_changed_by_staff`) con
pacchetto e importo di prima e di dopo. Un link di pagamento già inviato al
cliente resta all'importo vecchio: dopo la correzione il cliente deve
riaprire il pagamento dalla sua area.

## Contract economics: IVA, tipo cliente, cashback, bonus (Session 38) {#contract-economics}

Three rules that had **no server-side implementation at all** before this,
plus the two configuration switches they hang off.

### IVA -- one rule, one module {#vat}

`apps/api/app/domains/catalog/pricing.py` is the single place VAT is decided.
Before it, VAT existed only as a number two React components multiplied the
displayed price by; nothing on the server ever computed it, so "the price the
customer saw" and "the price the backend would charge" were two independent
implementations.

- **Contratto per un privato: nessuna IVA.** **Contratto per azienda / P.IVA:
  prezzo + IVA.** The *customer's* kind decides whether VAT applies at all;
  the product only decides *which rate* applies when it does
  (`product_versions.tax_configuration->>'vat_percentage'`, unchanged -- there
  is still no VAT percentage hardcoded anywhere in this codebase).
- `VAT_LIABLE_CUSTOMER_KINDS = {SOLE_PROPRIETOR, COMPANY, CONDOMINIUM}`.
  Deliberately **not** the same grouping as
  `customers/service.py::PRIVATE_LIKE_KINDS`, which puts SOLE_PROPRIETOR with
  PRIVATE: that answers a different question (first/last name vs. company
  name). A ditta individuale has a person's name *and* a P.IVA.
- **Snapshotted, never recomputed**: `contracts.net_amount_cents / vat_rate /
  vat_amount_cents / gross_amount_cents` plus `contracts.customer_kind` are
  frozen at creation, so an admin editing the product tomorrow can never
  restate a contract somebody already signed -- the same discipline as network
  snapshots and commission calculations.
- Rounding is `Decimal`, half-up on the cent (249,00 x 22% is exactly 54,78;
  in binary floating point it is 5477.999...).
- `catalog/pricing.py::contract_net_amount_cents` defines the taxable amount as
  `base_price_cents` -- the single figure the dashboard has always shown as the
  product price. `initial_fee_cents` / `recurring_fee_cents` have never been
  charged by any code path, so folding them in would start billing amounts
  nobody agreed to. **If the business means something else by "il totale del
  contratto", that one function is the only place that changes.**

### Chi puo comprare cosa {#product-audience}

`products.customer_type` existed but nothing ever read it, and its vocabulary
(PMI, ENERGY_INTENSIVE, ...) did not line up with `customers.kind` (COMPANY,
...), so the two could never be compared. It now holds the binary business
answer: **PRIVATE / BUSINESS / BOTH** (legacy values still parse and collapse
onto BUSINESS). A customer is only offered contracts their kind may activate,
and the server rejects the rest independently -- hiding a card is never the
enforcement. Existing rows were migrated to **BOTH**, not to their literal old
value: nothing filtered on this column before, so BOTH is the only
behaviour-preserving choice.

### Cashback: tre regole distinte, mai confuse {#cashback-modes}

`catalog/pricing.py::cashback_mode_for` classifies every product into exactly
one of three, **derived** from the fields that actually drive behaviour rather
than stored in a fourth column that could drift:

| Modalita | Chi | Regola |
|---|---|---|
| `STANDARD` | Prodotti DROPSHIPPING/PARTNER (`cashback_enabled`) | Opt-in: il cliente paga il **+5%** al checkout e riceve 100% + 5% come JavCash. **Invariata.** |
| `AUTOMATIC_INTERNAL_SERVICE` | Contratti Jav e formazione (`contract_cashback_percentage > 0`) | **Automatico, senza il +5%**: pagare il contratto e' esso stesso cio' che genera il credito. |
| `NO_CASHBACK` | Tutto il resto, incluso ogni prodotto esistente oggi | Nessun accredito. |

The partner-invoice redemption (`invoice_redemptions`, the other 5% rule) is a
separate domain entirely and is **not touched** by any of this.

The contract credit is a percentage of the **gross** (VAT included), i.e. of
what the customer actually handed over -- never a pre-discount or otherwise
inflated base. Exactly-once is enforced twice: `contracts.cashback_credited_at`
as the readable guard, and the deterministic wallet idempotency key
`contract-cashback:{contract_id}` against the UNIQUE constraint on
`wallet_transactions` for the case the guard is raced (a replayed webhook).
`source = "CONTRACT_CASHBACK"`, distinct from `ORDER_CASHBACK_BASE` and
`INVOICE_REDEMPTION_BASE` precisely so accounting can tell the three apart.

### Bonus primo segnalatore {#first-referrer-bonus}

An extra one-off amount **on top of** the recursive commission the plan
already pays, going **exclusively** to the promoter who originally brought the
customer into Jav. Two concepts that look identical in the ordinary
case and come apart exactly where this bonus matters:

- **referrer / segnalatore**: a property of the CUSTOMER
  (`customer_attributions`), frozen onto the contract at creation as
  `contracts.first_referrer_agent_id`.
- **producer / chi compila**: a property of the CONTRACT
  (`contract_attributions.producer_agent_id`), who earns the commission.

Rules: configured per product version (`first_referrer_bonus_enabled` /
`first_referrer_bonus_cents`) -- never keyed off a price or a product id in
code; never paid to the upline, only to that one agent; **once per contract,
ever, not once per activation** -- the idempotency key deliberately omits the
trigger event so the UNIQUE constraint on `commission_movements` is itself the
guarantee, even on a renewal or a replayed event; skipped if that agent is no
longer ACTIVE. `movement_type = "FIRST_REFERRER_BONUS"`, its own auditable row.
Reassigning the customer afterwards does **not** move the bonus on a contract
already opened -- reassignment changes who earns future business.

### Chi ha costruito il contratto {#contract-authorship}

`contracts.created_by_user_id` / `created_by_role` /
`activated_by_promoter_id`. The last is set **only** when a promoter completed
the contract in place of the customer, so "Contratto attivato dal promoter X"
is shown exactly when it is true, never inferred from who happens to earn the
commission. `contract_status_history` and `audit_log` remain the full
technical trail; these are the denormalized answer to the one question the
admin screen asks constantly.

## Contract state machine

```
DRAFT → SUBMITTED → DOCUMENTS_PENDING → UNDER_REVIEW → APPROVED
      → PAYMENT_PENDING → PAID → ACTIVATION_PENDING → ACTIVE
ACTIVE → SUSPENDED → ACTIVE
ACTIVE → CANCELLED
ACTIVE → EXPIRED
ACTIVE → RENEWED
RENEWED → SUSPENDED / CANCELLED / EXPIRED / RENEWED   (a renewed contract is still
                                                        in force -- it renews again
                                                        every subsequent term, not once)
EXPIRED → RENEWED / CANCELLED                          (a lapsed contract can be revived)
any pre-ACTIVE state → REJECTED
```

Only the transitions enumerated in `apps/api/app/domains/contracts/state_machine.py`
are permitted; every other transition raises `InvalidTransitionError`. Every transition
is recorded in `contract_status_history` with actor, reason, and correlation id, and
emits a domain event (`ContractSubmitted`, `ContractApproved`, `PaymentConfirmed`,
`ContractActivated`, `ContractCancelled`, `ContractRenewed`).

**Rule**: creating a contract (`DRAFT`/`SUBMITTED`) never generates a commission.
Commissions are generated exactly once, when a contract transitions into `ACTIVE`
(see `commission-engine-specification.md §Trigger`).

**Term / expiry**: entering `ACTIVE` or `RENEWED` sets `contracts.activated_at` to
that moment and computes `contracts.expires_at` as `activated_at +
product_versions.contract_duration_months` (12 by default for an energy contract;
`NULL` for a one-off `DIGITAL`/`PHYSICAL` product with no renewal concept). Every
renewal restarts both fields from the renewal's own timestamp — `expires_at` is never
retroactively recomputed if the product version's duration later changes, matching the
"frozen at the moment it happens" pattern used for network snapshots and commission
calculations elsewhere in this document.

**Who can move a contract through this pipeline (confirmed, then extended,
Session 29)**: `PATCH /contracts/{id}/status` (manual, per-hop transitions)
still requires `contracts.review`, held by
ADMIN/BACK_OFFICE_OPERATOR/SUPER_ADMIN/ORGANIZATION_ADMIN, **never** by
CUSTOMER or PROMOTER (see `rbac/models.py`'s `DEFAULT_ROLE_PERMISSIONS`) --
a customer still cannot approve or activate a contract by taking a status-
transition action directly. What changed: a customer CAN now originate and
carry a Jav contract most of the way there themselves, through a
dedicated self-service path -- see "Self-service contract activation"
below. The two surfaces coexist: `POST /contracts` (staff, any producer)
and `POST /contracts/mine` (self-service, own account only, own referring
promoter only) both land on the exact same `Contract` row shape and the
exact same state machine.

### Self-service contract activation ("Attiva Contratto", Session 29) {#contract-self-service}

Per explicit request, a customer can now activate a Jav (`category
= INTERNAL`) product without any promoter/admin action to get it started:

- **`POST /contracts/mine`** (`contracts/router.py::create_my_contract`,
  no special permission -- `get_current_user` only, same "self-checkout,
  own account only" shape as `POST /orders/mine`): takes a
  `product_version_id` plus the supply-point details (address, POD/PDR,
  meter number) collected by the new `contract-activation-wizard.tsx`.
  `contracts/service.py::create_contract_self_service`:
  1. Resolves the customer's own record from `current_user.user_id`.
  2. Rejects anything that isn't an `INTERNAL` product (DROPSHIPPING/
     PARTNER products go through `orders`, never here).
  3. Resolves the commission producer from the customer's own referral
     attribution (`_resolve_referring_agent_id_for_customer` -- same
     `CustomerAttribution`→`PromoterCode` lookup "lavora con noi"
     auto-activation uses) -- there is no self-service way to pick a
     different one; registration being invite-only is exactly what
     guarantees this attribution always exists. No attribution found ->
     `SelfServiceContractError`, loudly, rather than silently attributing
     to nobody and breaking commissions later.
  4. Creates the `SupplyPoint`/`Address` (reusing
     `customers/service.py::add_supply_point` directly -- bypassing its
     normal `customers.update`-gated router, the same "call the service,
     skip the staff-only endpoint" pattern used elsewhere for self-service).
  5. Creates the `Contract` (`DRAFT`) and immediately transitions it
     `SUBMITTED` → `DOCUMENTS_PENDING` -- self-service has no "save as
     draft, decide whether to send it later" step the way a promoter/admin
     building one up by hand does.
- The customer then uploads the required documents through the same
  `ContractDocumentsPanel` every contract already used (no new upload
  mechanism) -- embedded directly in the wizard's second step, and always
  available again later from "I miei Contratti".
- **Auto-advance to `UNDER_REVIEW`** (`documents/service.py::
  upload_document` → `_maybe_advance_to_under_review`): once every required
  document type for the contract's customer kind has at least one uploaded
  document (any status -- this only means "the customer is done", not "a
  human already approved them"), the contract advances itself
  `SUBMITTED|DOCUMENTS_PENDING` → `UNDER_REVIEW` with no staff action. Not
  self-service-specific: a staff-created contract gets the identical
  courtesy advance once its documents are all in.
- **Two staff clicks left, by explicit product decision** (the user was
  asked: auto-approve documents entirely, or keep one human check before
  payment -- chose the latter): `contracts/service.py::transition_contract`
  gained `AUTO_CASCADE_AFTER = {"APPROVED": "PAYMENT_PENDING", "PAID":
  "ACTIVATION_PENDING", "ACTIVATION_PENDING": "ACTIVE"}` -- every hop is
  still a real, individually audited `transition_contract()` call (network
  snapshot, outbox event, `ContractStatusHistory` row, all per-hop, exactly
  as if a human had clicked each one), just chained automatically. So:
  - Staff clicks **"Approva"** (`UNDER_REVIEW`→`APPROVED`) after actually
    looking at the uploaded documents -- the contract lands in
    `PAYMENT_PENDING` without a second click.
  - Staff clicks **"Conferma pagamento"** (`PAYMENT_PENDING`→`PAID`) once
    the initial-fee bank transfer arrives -- the contract cascades through
    `ACTIVATION_PENDING` straight into `ACTIVE` (which is exactly the hop
    that enqueues the `ContractActivated` event and triggers commission
    calculation, unchanged from before).
  - This cascade is general, not gated to self-service-originated
    contracts -- a staff-created contract gets the same two-click path.
  - The admin contracts panel's status-transition dropdown needed **no
    changes**: it already only ever offers the next state-machine-valid
    target for a manual click; the cascade happens server-side, so picking
    "APPROVED" there simply comes back already at `PAYMENT_PENDING`.

## Condivisione dei link: bottoni per app, non solo copia (Session 45) {#share-buttons}

Every place a link is shared — the promoter's personal link, "Invita un
amico", a single product a promoter recommends, and the personal link an
admin hands to a newly created root promoter — offers the same set:

**WhatsApp · Telegram · SMS · Email · Altro · Copia link**

- Each destination is a **plain link**, not an SDK: no third-party script, no
  tracking pixel, nothing added to the bundle. The target app opens with the
  message and the URL already filled in.
- **SMS** and **Altro** (the phone's own share sheet, for Messenger, Signal,
  AirDrop, whatever is installed) appear only on touch devices, via a
  `@media (pointer: coarse)` rule rather than a JavaScript check — no
  hydration mismatch, no state to keep in sync.
- **Copia link** copies straight to the clipboard and deliberately does NOT
  open the native sheet first: somebody who pressed "Copia link" has already
  decided.
- **Inline nearly everywhere**: Invita un amico, the admin's root-promoter
  result, and the promoter header bar. In the header the labels are hidden
  below `sm` and only the icons show — that bar is on every page of the
  promoter dashboard, and six labelled pills would wrap onto three lines on a
  phone and push the page down. The labels are hidden, never removed, so a
  screen reader and a long-press still name the destination.
- The one exception is a **product card in a grid**, where a row per card
  would crowd out the product itself: there the same set opens in a small
  sheet.

One component, `components/share-buttons.tsx`, backs all of it: adding a
destination is one entry in its `TARGETS` list and it appears everywhere at
once.

## "Invita un amico": rete a un livello, staccata, senza provvigioni (Session 39) {#friend-referrals}

A **second, completely separate** referral structure, added on explicit
request: "non c'entra nulla con l'attuale rete, è una cosa staccata e separata
che ogni cliente ha".

- **Naming (Session 39, corrected same day)**: the feature is **"Invita un
  amico"** everywhere a person can read it. The first pass used
  "segnala/segnalatore", which the business rejected -- in Italian *segnalare*
  carries a reporting-on-somebody connotation, wrong for what is meant to be
  a warm invitation. Internal identifiers keep the neutral English
  `friend_referrals`. The commission-side "Bonus primo segnalatore" label was
  renamed for the same reason ("Bonus primo invito"); the stored
  `movement_type` is unchanged.
- **Who has one**: everyone with a login, promoter or not. Each gets a
  personal invite code (`friend_referral_codes`, prefix `INV-`), created
  lazily the first time they open "Invita un amico". Codes issued before the
  rename (prefix `SEG-`) keep working -- resolution is an exact match on the
  whole code, never on the prefix.
- **What it holds**: one flat level. `friend_referrals` records who signed up
  through whose link. No hierarchy, no closure table, **no commissions** --
  the whole thing could be dropped tomorrow without changing a single euro.
- **Where the invited customer actually lands in the COMMERCIAL tree** is
  decided by the existing rules and is untouched by this:
  - the referrer **is** an active promoter → their own tree, exactly as
    before;
  - the referrer is **not** → under the referrer's **own** promoter
    (`friend_referrals/service.py::promoter_code_for_referrer`), because a
    plain customer earns nothing and cannot have a downline. If that promoter
    has since been deactivated, the same walk-up applies as everywhere else
    (see #terminated-promoter-fallback).
  A promoter's normal link feeds the list too, so their segnalati list and
  their tree agree — the list is purely additive.
- **When somebody "counts"**: only once one of their contracts is genuinely in
  force (`ACTIVE`/`RENEWED`), which is the business's explicit choice over
  "has started a contract". The list shows three states so progress is still
  visible: `INVITED` / `IN_PROGRESS` / `ACTIVE`. State is **derived** from
  contracts at read time, never stored: a stored flag would need an event hook
  on every path that activates, renews or cancels, and the first one anybody
  forgot would leave the count permanently wrong.
- **The gift, one every 5**: at 5, 10, 15 ... activated invitees the person
  may request **una gift card da 25 euro** -- explicitly *not only for the
  first 5*, it repeats at every multiple. The wording of the gift lives in
  ONE place, `friend_referrals/models.py::REWARD_DESCRIPTION`, and is sent to
  the dashboard rather than written into a React component: it appears in
  four places (panel, progress line, claim button, admin screen) and the
  business will certainly revise it. Nothing is computed from it -- it is
  copy, because the payout is manual. Milestones are absolute, and
  `uq_friend_referral_claim_user_milestone` makes each claimable exactly once,
  ever. Somebody who never claimed at 5 and is now at 12 is offered 5 first,
  then 10 — they are not silently skipped past what they earned.
- **Not an automatic payout**: the business chose to keep a human in the loop,
  so a claim is a *request* that notifies staff ("Omaggi Segnalatori" in the
  admin dashboard), who mark it delivered or not and write a note the customer
  sees. That way the gift can be JavCash, a product or a voucher, decided
  case by case — nothing is minted automatically.
- **Privacy**: the list shows an invited person's **name and state only** —
  never their email, phone or address. Sharing a link with somebody does not
  entitle you to their contact details.
- **Notifications**: the inviter is told when one of their people goes
  active, and whether that unlocked a gift (`FRIEND_REFERRAL_ACTIVATED`);
  staff are told about a request (`FRIEND_REFERRAL_REWARD_REQUESTED`); the
  requester is told the outcome (`FRIEND_REFERRAL_REWARD_HANDLED`).

## "Lavora con noi": quali documenti si firmano (Session 40) {#collaboration-documents}

Becoming a promoter has always required accepting a collaboration agreement
and confirming with an emailed OTP. Two things were wrong with it until now:

1. **The text shown was not the contract.** It was a one-paragraph summary
   hardcoded in `customer-promoter-application-card.tsx` — so the app
   displayed something nobody had drafted as a contract, and updating the
   real one would not have changed what people saw.
2. **There was one acceptance where the paper form has more than one.**

### Dove vive il testo

`apps/api/app/domains/network/collaboration_documents.py`, on the server, and
served to the dashboard by `GET /network/agents/apply/documents`. Deliberately
not in a React component:

- it is what people legally sign, so there must be exactly one copy of it;
- the acceptance record stores the **version** somebody actually saw, which is
  only meaningful if text and version are defined together;
- changing it needs no frontend release.

It travels as **structured blocks** (heading / paragraph / clause / bullets /
table / signature), never as markup: the dashboard decides typography and
never interprets HTML. A test asserts no document contains `<` or `>`.

### I documenti

| Chiave | Cosa | Perché è separato |
|---|---|---|
| `CONTRACT` | Il contratto di procacciamento di affari, integrale (16 articoli, 77 clausole numerate) | — |
| `SPECIFIC_CLAUSES` | **Allegato al contratto**: approvazione specifica delle clausole (artt. 1341 e ss. c.c.) + Allegato A e Allegato B | La legge richiede che le clausole vessatorie siano approvate separatamente dal contratto, quindi non può essere accorpato al documento sopra. |

**Le tabelle di Allegato A e B mancano ancora.** I due allegati sono
dichiarati e descritti, ma le cifre non ci sono: il testo fornito per
l'allegato era un duplicato del contratto e non conteneva alcuna tabella.
Sono numeri che le persone firmano, quindi non sono stati inventati. I due
paragrafi segnati `DA COMPLETARE` in `_ATTACHMENT_BLOCKS` vanno sostituiti
con `table(columns=[...], rows=[[...]])` e la `version` del documento
incrementata; la dashboard rende la tabella da sé.

**Il testo non parla mai della carta.** Il contratto cartaceo è la *fonte*
di queste parole, non il loro argomento: a chi legge sullo schermo non si
dice cosa richiederebbe un foglio che non ha mai visto. Un test lo verifica.

### Come si firma

Immutato: si leggono i documenti, si spunta **una casella per documento**, poi
si conferma con il **codice OTP** che arriva via email — la prova che ha
acconsentito il titolare dell'account e non solo chi è loggato.

### Cosa viene registrato

`agent_profiles.collaboration_accepted_documents`, JSONB:
`{chiave: {"version": ..., "accepted_at": ...}}`, una voce per documento. Una
mappa e non una coppia di colonne per documento, perché l'elenco dei documenti
è una decisione di business che cambierà ancora e ogni cambio non deve costare
una migrazione. Le colonne preesistenti
(`collaboration_contract_version`/`collaboration_accepted_at`) restano e
continuano a essere allineate per il contratto principale.

**Il server non si fida della casella.** L'applicazione deve inviare
`{chiave: versione}` per **ogni** documento attualmente richiesto, e il server
rifiuta se ne manca uno o se la versione è vecchia (la pagina era aperta
mentre il testo cambiava). Una casella dice solo che qualcuno ha cliccato;
una versione dice **quale testo** è stato accettato.

**Aggiungere o cambiare un documento**: si aggiunge una voce a
`COLLABORATION_DOCUMENTS`, o si incrementa la sua `version`. La dashboard
rende automaticamente un pannello e una casella in più, e il backend inizia a
pretendere quell'accettazione dal deploy successivo. Mai modificare un testo
senza incrementare la versione: significherebbe riscrivere in silenzio ciò che
qualcuno ha già firmato. Le accettazioni già registrate non vengono mai
riscritte, e i promoter esistenti hanno la mappa vuota — non è stato inventato
un consenso a un testo che non avevano mai visto.

## Commercial network rules

- No cycles, no self-parenting, no duplicate active edges, no cross-organization
  edges. Enforced in `network` domain service before any closure-table write.
- Every move of an agent to a new parent is a single DB transaction: update
  `network_nodes.direct_parent_agent_id`, insert a closed-off `network_edges` row and
  a new one, recompute affected `network_closure` rows, insert
  `network_assignment_history`, write an audit row, invalidate branch-count caches.
  Moves require `requested_by`; `approved_by` is required unless the mover has
  `network.manage` and self-approval is explicitly allowed for that role (PLACEHOLDER —
  see open-questions.md #2).
- A contract's commercial chain is frozen at activation via `network_snapshots` /
  `network_snapshot_id` on the contract. Subsequent moves of any agent in that chain
  never retroactively change attribution, past calculations, or past ledger entries.

### New promoter suggest-then-approve workflow (added Session 17)

Every new collaborator, however they're created, only ever gets SUGGESTED --
never immediately live:

- `POST /network/agents` (an ADMIN adding a promoter anywhere in the org
  tree) and `POST /network/agents/recruit` (a promoter enrolling their own
  direct collaborator) both now create the agent with
  `status = PENDING_APPROVAL`, not `ACTIVE`.
- A `PENDING_APPROVAL` agent already exists and is visible in the network
  tree (it's a real row, a real node) but cannot be used as a contract
  producer -- `contracts/service.py::create_contract()` already rejected any
  non-`ACTIVE` producer before this feature existed, so no new guard was
  needed there; the approval workflow rides entirely on a check that was
  already correct.
- Only `network.approve` holders can turn a suggestion into a real
  collaborator: `PATCH /network/agents/{id}/approve` (→ `ACTIVE`) or `PATCH
  /network/agents/{id}/reject` (→ `TERMINATED`, with an optional reason kept
  on the row, never a hard delete). `network.approve` is granted only to
  `SUPER_ADMIN`/`ORGANIZATION_ADMIN` -- the "amministratore principale" the
  user asked for -- deliberately NOT to a plain `ADMIN`, who already holds
  `network.manage` (can suggest) but not `network.approve` (cannot confirm
  their own suggestion). Re-approving/re-rejecting an already-decided agent
  is rejected (`AgentApprovalError`), not silently accepted.
- Both creation paths and both approval outcomes fire a notification (see
  `database-model.md §7`) -- `PROMOTER_APPROVAL_REQUESTED` to every
  `network.approve` holder when something needs a decision,
  `PROMOTER_APPROVED`/`PROMOTER_REJECTED` back to the suggested agent's own
  `user_id` if they already have a login.

## Entrepreneurial Difference ("Differenza Imprenditoriale")

Defined as the difference between the personal token that a given rank would earn on a
contract and the amount already recognized to the rank(s) below it in the same
ascendant chain for that same contract. Walking the chain from the producer upward:

```
already_distributed_cents starts at producer's own personal_token_cents
for each ascendant beneficiary (by increasing distance):
    if beneficiary.rank.personal_token_cents > already_distributed_cents:
        entrepreneurial_difference_cents = beneficiary.rank.personal_token_cents - already_distributed_cents
        already_distributed_cents = beneficiary.rank.personal_token_cents
    else:
        entrepreneurial_difference_cents = 0
```

This guarantees the same differential is never paid twice up the chain — each
ascendant is only credited the marginal amount their rank adds over what has already
been recognized below them. See `commission-engine-specification.md` for the full
algorithm including the 33% cap and Energia Circolare handling.

## Commission payment tracking (added Session 16)

`commission_movements.status`/`paid_date` existed since the very first migration
but nothing ever set anything other than `ACCRUED` -- the admin dashboard's
"Provvigioni pagate" KPI always showed €0,00 because there was no code path
that could ever produce a `PAID` row. `PATCH
/commissions/movements/{id}/pay` (admin-tier only, `commissions.approve`)
is the missing write path: transitions one movement `ACCRUED -> PAID`, stamps
`paid_date`, and writes an audit row. Re-paying an already-`PAID` movement is
rejected (`CommissionPaymentError`), not silently accepted -- this is a
manual "I sent the bank transfer" confirmation per movement, not a batch
payroll run; there is no bulk-pay-everything-for-this-promoter action yet
(a reasonable next iteration once real payout batching requirements exist).

### Admin commission traceability (`GET /commissions/movements`)

Every `CommissionMovement` already had a matching `CommissionCalculationStep`
row (contract → calculation → per-beneficiary step, computed at activation
time by `run_calculation_for_contract`) carrying `rank_at_calculation`,
`base_amount_cents`, `already_distributed_cents`,
`entrepreneurial_difference_cents`, and a human-readable `explanation` string
-- none of it was ever exposed through any endpoint before this. The new
endpoint (admin-tier only -- it is org-wide, unlike `commissions.read_branch`
which `TEAM_LEADER`/`PROMOTER` also hold for their own branch, so it cannot
reuse that permission) joins all of this together per movement: which
contract, which customer, which promoter earned it, their depth below the
contract's producer (`network_snapshot_nodes.depth`, frozen at activation --
0 is the producer themselves), their rank AT calculation time vs. their rank
NOW, and the full breakdown of how the amount was derived. Surfaced in the
admin "Provvigioni" tab (`admin-commissions-panel.tsx`) as an expandable
ledger row per movement, plus `GET /commissions/movements/by-level`
(`commissions/services/admin_ledger.py::get_commission_totals_by_level`) for
the per-network-level rollup (contracts / revenue / commission generated at
each depth).

## Regola del 33%

No single first-level branch under a beneficiary may contribute more than
`single_branch_cap_percentage` (default 33%, PLACEHOLDER) of that beneficiary's
qualifying group production for rank-evaluation and volume-based bonus purposes.
Excess production from one branch beyond the cap is excluded (not moved to another
branch, not carried over) from that evaluation period's eligible total. This is
implemented as an isolated, independently testable policy —
`apps/api/app/domains/commissions/policies/branch_cap.py` — not inlined into the main
calculator, so it can be unit tested against the matrix in
`commission-engine-specification.md §33% rule test matrix` without invoking the full
engine.

## Energia Circolare (PLACEHOLDER — see open-questions.md #3)

Treated in v1 as a product flag (`products.code` / `product_versions` metadata) that
can carry its own `commission_plan_version_id`, so Energia Circolare contracts can use
different rules without touching the shared calculator code. No Energia-specific bonus
formula is implemented yet — only the extension point.

## Renewals & reversals

- A renewal is a status transition on the **same** contract row (`ACTIVE`/`EXPIRED` →
  `RENEWED`, or `RENEWED` → `RENEWED` for the year after that), not a new contract --
  see "Term / expiry" above for how `activated_at`/`expires_at` are recomputed each
  time. It is also a new `contract_events` row of type `RENEWED` plus a new commission
  calculation; it does not mutate the original calculation or its movements.
- A reversal ("storno") never deletes or edits a prior `commission_movements` row. It
  creates a new movement with `movement_type = REVERSAL`, linked via
  `commission_reversals.original_movement_id`, carrying a negative amount, an
  explanation, and the recovered period. Formula for partial-period recovery
  (PLACEHOLDER — see open-questions.md #4):
  `refund_cents = original_amount_cents * remaining_months / total_contract_months`.

## Support tickets

- Anyone opening a ticket (a `CUSTOMER` or `PROMOTER`) can only ever see and reply to
  their **own** tickets -- there is no shared inbox between a customer and the
  promoter who referred them. Staff (any admin-tier role with `tickets.respond`) sees
  every ticket in the organization and can reply to any of them.
- `Ticket.opened_by_role` and `TicketMessage.author_role` are snapshots taken at
  creation time, not derived from the user's current roles at read time -- the same
  "frozen at the moment it happens" rule used for network snapshots and commission
  calculations. A later role change never rewrites who a past ticket/message
  "belongs to".
- A staff reply on an `OPEN` ticket automatically moves it to `IN_PROGRESS` -- the
  ticket owner should see "someone is looking at this" without the admin having to
  remember a separate status update. Only staff (`tickets.respond`) can set
  `RESOLVED`/`CLOSED`; the ticket owner can only imply it's solved via a message.
- A ticket can optionally reference a `contract_id`, letting a customer or promoter
  open a ticket directly "about this contract" instead of the admin having to guess
  which one they mean from free text.

### Richiesta di chiusura account (Session 89)

- Dalle Impostazioni del cliente, «Richiedi chiusura account» apre un ticket
  di categoria `CHIUSURA_ACCOUNT` (`POST /support/tickets/account-closure`,
  `support/service.py::request_account_closure`): stesso avviso allo staff e
  stessa email all'indirizzo delle notifiche di ogni ticket, più una conferma
  al cliente. **Non cancella niente**: la chiusura la fa lo staff a mano,
  dopo aver controllato contratti, ordini e JavCash aperti.
- Una sola richiesta aperta (OPEN o IN_PROGRESS) per utente: la seconda
  risponde 409. La categoria non compare nel modulo «Nuovo ticket».

### Search, filter, and deletion (added Session 19)

- The admin ticket list (`AdminTicketsPanel`) can be filtered by opener
  (customer/promoter), category, and status, plus a free-text search over
  subject and opener name. Filtering is entirely client-side (the ticket
  list for one organization is small enough that this is simpler than
  adding query params to `GET /support/tickets`) -- if the dataset grows
  large enough to matter, move this filtering server-side rather than
  fetching the whole list.
- A ticket can be **permanently deleted only once its status is
  `RESOLVED`** (not `CLOSED` -- deliberately narrower, matching exactly
  what was asked for; revisit if `CLOSED` should also be eligible). The
  delete control (in both the ticket list row and the ticket detail view)
  is disabled for any other status, so there is no way to trigger the
  attempt from the UI on a non-resolved ticket. The backend enforces the
  same rule independently (`support/service.py::delete_ticket`, raising
  `TicketDeletionError` -> `400`) -- the frontend disabled-state is a UX
  courtesy, not the actual guard.
- Deletion always shows a confirmation dialog naming the ticket subject
  before calling `DELETE /support/tickets/{id}`; there is no direct delete
  with no confirmation step anywhere in the UI.
- Gated by a new `tickets.delete` permission, deliberately narrower than
  `tickets.respond` (granted to `SUPER_ADMIN`/`ORGANIZATION_ADMIN`/`ADMIN`
  only, not `BACK_OFFICE_OPERATOR`) -- same "narrower than the capability
  that looks like it should cover it" pattern as `network.approve` (see
  `security-model.md`), since permanently destroying a ticket is more
  consequential than replying to one.
- Deleting a ticket also deletes its `TicketMessage` rows in the same
  transaction (no FK `ondelete` cascade exists at the DB level) and
  records an audit entry (`action="ticket.deleted"`, with the subject/
  category/status snapshotted into `previous_value`) before the rows are
  removed -- the audit trail survives even though the ticket itself no
  longer does.

## Notifications (added Session 17)

See `database-model.md §7` for the table shape. Behavior:

- **Who gets what**: `CONTRACT_CREATED`/`TICKET_CREATED`/
  `PROMOTER_APPROVAL_REQUESTED` fan out to every user holding a role in a
  fixed set (`notifications/service.py::STAFF_NOTIFY_ROLES` for the first
  two, the narrower `APPROVAL_NOTIFY_ROLES` for the third -- only
  `network.approve` holders can act on an approval request, so only they
  are told about one). `COMMISSION_EARNED`/`PROMOTER_APPROVED`/
  `PROMOTER_REJECTED` go to exactly one specific user -- the beneficiary
  agent's own `user_id`, when they have a login at all (an agent with no
  `user_id` -- a collaborator who predates having their own account --
  simply generates no notification for that event, not an error).
- **The actor never notifies themselves**: whoever triggered the event
  (created the contract, opened the ticket) is excluded from that event's
  own fan-out (`notify_roles(..., exclude_user_id=actor_user_id)`) -- an
  admin creating a contract doesn't need to be told they just did that.
- **Read state is per person**: marking a notification read only affects
  the row for that recipient; a fanned-out event that reached five admins
  produces five independent rows, so one admin dismissing it doesn't
  silently clear it for the other four.
- **No push, no email** -- notifications are in-app only, polled every 25s
  by the frontend. Real-time delivery (WebSockets/SSE) and email digests are
  future work, not built here.

## Promoter reassignment

- An admin can move a customer's attribution from one promoter to another
  (`POST /customers/{id}/reassign-promoter`) -- but a customer can never end up
  with NO promoter ("nessuno può stare senza promoter che lo invita" is a closed
  circuit both at registration and afterward): reassignment is rejected if the
  customer has no existing `customer_attributions` row to correct in the first
  place (e.g. a customer created directly by admin, never through a referral
  link, has none).
- Reassigning to the SAME promoter the customer is already attributed to is
  rejected as a no-op, not silently accepted -- it would create a meaningless
  `attribution_corrections` audit row.
- Every reassignment writes an `attribution_corrections` row (previous promoter,
  new promoter, who requested it, why) -- this table existed since the first
  session's schema but had no code path writing to it until this feature.
- Reassignment only changes future commission attribution going forward; it never
  retroactively touches `network_snapshots` or past `commission_movements` for
  contracts already activated under the previous promoter (same "frozen at
  activation" rule as everywhere else commission chains are involved).

## Photo uploads

- Customer, promoter, and product photos are stored in a bucket
  (`jav-media`/`S3_BUCKET_MEDIA`) that is deliberately SEPARATE from and less
  restrictive than the documents bucket (`jav-documents`): public-read, no
  signed URLs, because these are ordinary profile/product photos, not sensitive
  documents. Never put anything sensitive in this bucket -- see
  `security-model.md §Documents`.
- Uploads are validated server-side regardless of what the browser claims:
  content-type must be one of `image/jpeg|png|webp|gif`, max 5 MB
  (`core/storage.py::upload_media()`). A new upload never overwrites the
  previous photo's object in place -- it gets a fresh random key and the
  `photo_url` column is repointed; the old object is simply orphaned (not worth
  a cleanup job for a handful of KB-sized images).
- If no photo has been uploaded, `photo_url` is `NULL` and every list/detail view
  shows a generic person icon -- never a broken `<img>` tag.

## Contract documents (added Session 14)

- Every contract requires `IDENTITY`, `FISCAL_CODE`, and `UTILITY_BILL`
  (`documents/service.py::BASE_REQUIRED_DOCUMENT_TYPES`); a customer of kind
  `COMPANY` or `CONDOMINIUM` additionally requires `CHAMBER_OF_COMMERCE`
  (`COMPANY_LIKE_KINDS`). This is a hardcoded, honest default in the service
  layer, not read from the pre-existing `product_versions.required_documents`
  jsonb column -- that column has never actually been populated or wired to
  any behavior, so treating it as configurable today would be pretending.
- A `SOLE_PROPRIETOR` (ditta individuale / partita IVA) is **offered** the
  `CHAMBER_OF_COMMERCE` slot but is never blocked by it
  (`CHAMBER_OF_COMMERCE_OPTIONAL_KINDS`, added Session 45). They are a
  business for VAT (`catalog/pricing.py`), but a professionista with a
  partita IVA is not in the Registro Imprese and has no visura to give:
  demanding one would strand exactly the customers who cannot produce it,
  while hiding the slot would leave the ones who can with nowhere to put it.
  The slot carries `required: false`, and the auto-advance to `UNDER_REVIEW`
  gates only on the required ones.
- Beyond the fixed slots, anyone who can upload to a contract can attach
  **extra documents** of type `OTHER` (added Session 45), each carrying a
  `description` its uploader writes ("Carta d'identità retro", "Delega
  firmata", "Contratto di locazione"). The description is mandatory for
  `OTHER` and ignored for every other type: a slot document is already named
  by its type, and accepting a caller-supplied label there would let a file
  land in the identity slot calling itself something else. Extra documents
  accumulate -- a second one does not supersede the first, unlike a second
  upload into the same slot -- and never gate the contract.
- `GET /contracts/{id}/documents` returns one row per *slot* for that
  customer's kind -- each with `required`, and with `document: null` when
  nothing has been uploaded yet, so "missing" is a first-class, visible
  state, not silence -- plus an `extra` array holding every attachment no
  slot accounts for. That second list also catches a document whose slot has
  since disappeared (a visura uploaded while the customer was registered as
  a company, later corrected to `PRIVATE`): the file is still in the bucket
  either way, and a documents list must never quietly hide one.
- Either the customer (their own contract only) or staff can upload a
  document; only staff can review (approve/reject with a note). This covers
  both the normal flow (customer uploads, admin reviews) and the exception
  the user specifically asked for: a customer sends a document some other
  way (email, in person) and an admin uploads it into the system on their
  behalf.
- Uploading a document does not, by itself, change contract status --
  reviewing/transitioning is a separate, explicit action. The state machine's
  `SUBMITTED`/`UNDER_REVIEW` → `DOCUMENTS_PENDING` transition is how staff
  flags "this contract can't proceed until the customer completes their
  paperwork"; the transition's `notes` field is where staff records *which*
  document is missing, surfaced back to the promoter's own network view
  (`get_branch_contracts()`'s `admin_note` field) so they know what to chase.
- See `security-model.md §Documents` for how these files are stored --
  private bucket, presigned-URL-only access, never a public or guessable
  link.

## Il fascicolo di un contratto (Session 48) {#contract-dossier}

Un contratto non vive solo qui dentro: prima o poi la pratica va mandata a
un fornitore, a un commercialista, a un legale. Fino a Session 48 l'unico
modo era aprire gli allegati uno per uno dai link a scadenza, risalvarli a
mano, e ricopiare i dati del cliente da tre schermate diverse.

- **Il contenuto lo costruisce un solo modulo**, `contracts/dossier.py`:
  tutti gli allegati del contratto più un PDF riassuntivo di contratto e
  cliente. Due sbocchi -- uno zip scaricato dal browser
  (`GET /contracts/{id}/dossier.zip`) o una cartella su Google Drive
  (`POST /contracts/{id}/dossier/drive`) -- e un solo posto che decide cosa
  ci finisce dentro, così le due strade non possono divergere.
- **Nome**: `<nome cliente>-<id contratto>`, per l'archivio e per la
  cartella. Il nome cliente è quello mostrato ovunque nel gestionale
  (`customers/service.py::display_name_for`), l'id è l'UUID intero. Gli
  accenti restano; spariscono solo i caratteri che romperebbero un percorso
  (`/ \ : * ? " < > |`, i controlli), i punti e gli spazi finali (Windows li
  taglierebbe comunque, e un nome tagliato da altri non è più quello scritto
  nel database) e i nomi riservati DOS.
- **Il PDF contiene tutto** quello che serve a chi legge la pratica senza
  avere accesso al gestionale: intestatario, tipologia, codice fiscale e
  P.IVA, dati societari, recapiti, indirizzi, punto di fornitura con POD/PDR
  e matricola, prodotto, importi netto/IVA/lordo, modalità e stato del
  pagamento, IBAN, promoter che ha attivato e promoter che ha portato il
  cliente, e l'elenco degli allegati con il loro stato di verifica.
- **Un allegato irrecuperabile non fa fallire il fascicolo.** Se un file non
  si legge dal bucket (cancellato a mano, migrazione storage andata storta),
  al suo posto entra un `.txt` che dice quale documento manca e perché. Il
  resto del dossier serve comunque, e chi apre la cartella deve *leggere*
  cosa non c'è invece di accorgersene contando i file.
- **Permesso: `documents.review`**, non `documents.download`. Il secondo ce
  l'ha anche il cliente per i propri documenti; qui si scarica l'intero
  fascicolo di una pratica -- anagrafica, IBAN, riferimenti di pagamento --
  ed è roba da amministrazione, cioè esattamente le stesse persone che quei
  documenti li verificano uno per uno. Ogni download e ogni invio su Drive
  finiscono nell'audit log (`contract.dossier_downloaded`,
  `contract.dossier_sent_to_drive`).
- **Google Drive** (`integrations/google_drive.py`): un amministratore
  autorizza una volta il proprio account, e da lì in poi il pulsante
  funziona per tutti gli amministratori dell'organizzazione. Lo scope è
  `drive.file`, non `drive`: l'applicazione vede e tocca soltanto ciò che ha
  creato lei, non può leggere né elencare il resto di quel Drive. Il refresh
  token vive in `Organization.settings` con lo stesso trattamento delle
  chiavi Stripe: non torna mai indietro da nessuna risposta.
- **Premere due volte "Invia su Drive" non duplica niente**: se la cartella
  esiste già viene riusata, e un file con lo stesso nome viene sostituito,
  non affiancato. Il criterio è il nome, perché il nome è ciò che vede chi
  apre la cartella.
- L'upload è **resumable**, non multipart: Drive documenta il multipart fino
  a 5 MB e un allegato qui può arrivare a 15 (`MAX_DOCUMENT_BYTES`).
  Scegliere la strada che funziona solo per i file piccoli significa
  aspettare la prima foto di bolletta fatta con un telefono recente per
  scoprirlo.

## Password reset

- `POST /auth/forgot-password` always returns success regardless of whether the
  email exists for that organization -- the same enumeration-safety principle as
  login. If the account is real, a `password_reset_tokens` row is created: an
  opaque random token (only its sha256 hash persisted), expiring in 60 minutes,
  single-use (`used_at`).
- Email delivery is real SMTP when `SMTP_HOST` is configured (`core/email.py`); if
  not, the reset link is written to the API process log only
  (`docker compose logs api`) -- **never** to `audit_log` or any other place a
  web-UI role could read it, since that would let staff take over any account by
  reading its reset link. This is a genuine, working fallback, not a stub: the
  link is real and valid the moment it's generated, only its delivery channel
  differs.
- **Branded HTML email (fixed Session 33)**: this was the one email in the
  whole platform still sent as plain text via a separate, since-removed
  `core/email.py::send_email()` helper -- every other email (OTP codes,
  cashback credited, order/redemption notifications, ...) already used the
  shared branded template (`core/email_templates.py::render_email`, logo +
  consistent styling + a CTA button). Password reset now uses the exact
  same `send_html_email`/`render_email` path as everything else, so it is
  never the odd one out.
- `POST /auth/reset-password` (token + new password) revokes every active session
  for that user on success -- a password reset is exactly the moment to assume the
  old password may have leaked, so anyone still logged in with it is logged out.
  It also clears `failed_login_attempts`/`locked_until`, so completing a reset is
  the normal way out of a lockout, and marks the account email-verified if it
  wasn't already (Session 36 -- see `#account-gates`: clicking an emailed link is
  the same proof of inbox control the dedicated verification link gives).
- Both endpoints are rate-limited per client IP (`core/rate_limit.py`, Redis
  fixed-window counter) -- 5 requests/5min for `forgot-password`, 10/5min for
  `reset-password` -- independent of the per-account lockout in `authenticate()`.

### Delegated reset delivery for the two shared admin accounts (Session 37)

`superadmin@example.com` and `admin@example.com` are shared role
mailboxes nobody reads day to day, which made "dimenticata password" a dead
end for exactly the two accounts that most need a recovery path. For these
two addresses **only**, the reset email is delivered to a named delegate
(`auth/service.py::PASSWORD_RESET_DELEGATE_EMAIL` /
`PASSWORD_RESET_DELEGATE_FOR`) instead of the account's own inbox.

- **Only the delivery address changes.** The token is still bound to the
  admin account, the audit row still names that account, and that account
  is the one whose password actually changes. This is not an alias, not a
  shared login, and nothing about the delegate's own user record is touched.
- The email **names which admin account** the link is for -- the delegate
  receives resets for two different accounts, so without it the two would be
  indistinguishable in their inbox.
- `audit_log.new_value` records `delivered_to` **only** when the delivery was
  redirected, so a redirected admin reset stands out to an auditor rather
  than looking like every other reset. The token itself is still never
  written there (see the bullet above).
- **Accepted security trade-off, deliberate**: whoever controls the delegate
  mailbox can take over both admin accounts at will. That is the point of
  the override. It is therefore intentionally *not* editable from the admin
  dashboard -- changing it takes a code change + deploy, which leaves a
  reviewable git trail, rather than being a setting any admin-tier account
  could silently repoint at themselves.

## Internal wallet (added Session 21)

Every user (customer or promoter, whether or not they also hold the other
role) has an internal EUR wallet, styled after a cryptocurrency wallet: an
address (`0x` + 40 hex chars, cosmetic only -- no real blockchain), an
integer-cents balance, and a global append-only transaction ledger
(`wallets`/`wallet_transactions`, see `database-model.md §9`). This is a
purely internal, virtual balance -- there is no connection to real banking
rails, no payment provider integration, and no withdrawal path to real
money, by design.

- **Cashback / top-up**: after a customer buys a product, an admin can
  credit ("bonifica") an arbitrary amount to that customer's wallet,
  optionally linked to the contract that earned it (`reference_contract_id`)
  -- or as a plain, purchase-unrelated recharge. Gated by `wallet.manage`
  (`SUPER_ADMIN`/`ORGANIZATION_ADMIN`/`ADMIN` only, deliberately not
  `BACK_OFFICE_OPERATOR` -- same sensitivity tier as
  `commissions.evaluate_ranks`). The wallet is created lazily on first
  credit if the recipient never had one.
- **Omaggio di benvenuto (Session 37)**: every account can claim a one-off
  **20 JavCash** welcome bonus (`wallets/service.py::WELCOME_BONUS_CENTS`,
  `source = "WELCOME_BONUS"`), via a card on the dashboard home that
  disappears for good once claimed. Self-service, authentication-only, and
  always credited to the caller's **own** wallet -- the user id comes from
  the session, never the request.
  - **"Exactly once, forever" is enforced by the ledger itself**, not a
    separate flag: the transaction's `idempotency_key` is derived from the
    user id (`welcome-bonus:{user_id}`) and `wallet_transactions` has a
    UNIQUE constraint on it. A double-click, a retry, or two concurrent
    requests can only ever produce one row -- and a repeat claim is a
    harmless no-op returning the original row, not an error. There is
    deliberately no second "claimed" column that could drift out of sync.
  - Like the admin top-up, this **mints credit from nothing**, a conscious
    exception to the anti-loop rule below. It is a fixed code constant
    rather than an admin-editable setting precisely because of that:
    changing the amount takes a deploy and leaves a git trail.
  - Eligibility was an explicit business decision: it applies to **every**
    account, including the ones that already existed when it shipped, not
    only new signups.
- **Peer-to-peer transfer**: any wallet holder can send money to any other
  wallet in the same organization by address, no relationship required
  (like a real crypto wallet) -- self-transfer and cross-organization
  transfers are both rejected. Self-service, gated only by authentication
  (the caller's own wallet is always the source, resolved from their own
  login, never from the request body) plus a per-IP rate limit (20
  requests/60s on `POST /wallets/transfer`) against scripted abuse.
- **Balance integrity**: a debit can never take a wallet below zero --
  enforced both by an atomic compare-and-swap `UPDATE` at write time and by
  a DB `CHECK (balance_cents >= 0)` constraint as defense in depth. Every
  credit/transfer/reversal request carries a client-generated
  `idempotency_key`; a retried request with the same key returns the
  original result instead of double-applying.
  An operation that touches **two** wallets (a transfer, a reversal) first
  row-locks both in id order (`_lock_wallets`, 2026-10-13): crossed
  transfers A→B / B→A at the same instant then wait for each other instead
  of deadlocking, which Postgres resolved by aborting one of them.
- **Reversal**: an admin can correct a mistaken `ADMIN_CREDIT` or `TRANSFER`
  (`wallet.manage`-gated `POST /wallets/admin/transactions/{id}/reverse`).
  This inserts a new, linked `REVERSAL` row -- the original is never
  mutated, same append-only discipline as `commission_reversals`. Reversing
  a `TRANSFER` re-debits the original recipient, which can itself fail with
  "saldo insufficiente" if they've since spent the funds; this is an
  accepted, documented outcome, not a bug. A `REVERSAL` row can never itself
  be reversed.
- **Notifications**: the recipient of a credit or transfer gets an in-app
  notification (`CASHBACK_RECEIVED` / `WALLET_TRANSFER_RECEIVED`). An
  `ADMIN_CREDIT` (the "Ricarica" top-up above) also gets a branded email
  (`wallets/service.py::credit_wallet` → `_send_wallet_credited_email`,
  added Session 32) -- best-effort, fires after the credit is already
  committed. The one exception: a partner-invoice cashback credit
  (`reference_invoice_redemption_id` set) is skipped here on purpose, since
  `invoice_redemptions/service.py::confirm_payment` already sends its own
  richer email (partner name, base+bonus split) right after calling
  `credit_wallet()` -- this flag is exactly how the two are told apart, so
  a redemption credit never doubles up on emails.
- **Admin visibility**: `GET /wallets/admin` lists every wallet's balance
  org-wide; `GET /wallets/admin/{user_id}` and
  `GET /wallets/admin/{user_id}/transactions` show one user's wallet and
  history (does **not** lazily create a wallet just by viewing -- an admin
  looking at a user who never transacted sees "no wallet yet");
  `GET /wallets/admin/transactions` is the global ledger, filterable by
  type/user, with CSV export in the dashboard.
- **Peer-to-peer transfer is denied by default** (`Wallet.can_transfer`,
  added Session 23) for every wallet, customer or promoter -- an admin must
  enable it individually per promoter (`PATCH
  /wallets/admin/{user_id}/transfer-permission`, `wallet.manage`-gated).
  Deliberately per-wallet, not a role grant: opening it for "all promoters"
  would be wrong the first time only some of them should have it, which is
  exactly today's situation.

## Partner-invoice cashback (added Session 23)

A second, entirely separate way wallet credit enters the system, alongside
the plain admin `ADMIN_CREDIT` top-up above -- see
`docs/cashback-partner-invoices-plan.md` for the full design rationale and
`database-model.md` for the schema. Summary:

- **What it is**: Jav brokers for external energy suppliers
  (`partners`, e.g. Eviso). A customer or promoter who already pays one of
  these directly can redeem part of that spend as internal wallet credit,
  by uploading proof of payment (`invoice_redemptions`) and then paying Jav
  5% of the confirmed amount by bank transfer (or card -- see Session 33 below). Once that 5% is confirmed
  received, the wallet is credited 100% + a further 5% bonus.
- **Cardinal rule**: credit is minted **only** against a real, confirmed
  external payment (the 5%, bank transfer or card) -- never against spending existing credit.
  Paying a Jav product with wallet credit (once Phase 4/checkout exists)
  must never itself generate more credit, or the system would create value
  from nothing.
- **Lifecycle**: `SUBMITTED` (uploaded) → `PAYMENT_PENDING` (an admin
  confirmed the real amount and a payment reference code was generated) →
  `CREDITED` (the 5% payment arrived, confirmed by an admin or automatically by the Stripe webhook; two `wallet_transactions`
  rows are written -- `INVOICE_REDEMPTION_BASE` and `INVOICE_REDEMPTION_BONUS`,
  never one combined row, both carrying `reference_invoice_redemption_id`).
  `REJECTED` is reachable from `SUBMITTED` or `PAYMENT_PENDING`.
- **Carta all'invio: JavCash subito, controllo dopo (Session 89, scelta
  dell'utente, 2026-10-04).** Nel modulo il cliente sceglie «Carta, subito»
  o «Bonifico». Con la carta la richiesta nasce già `PAYMENT_PENDING`
  sull'importo **dichiarato** (`confirmed_amount_cents` = dichiarato,
  `verified_at` NULL), il cliente paga subito il 5% su Stripe e alla
  conferma del webhook arrivano i JavCash (100% + 5%) senza nessun
  amministratore; `review_status` diventa PENDING e lo staff riceve un
  avviso. Dopo, l'amministratore controlla la fattura: **APPROVED** o
  **REJECTED** con motivo (il cliente lo riceve). Un rifiuto **non tocca il
  wallet** -- lo storno, se serve, lo fa lo staff a mano (il cliente può
  aver già speso i JavCash: «gli telefoneremo») -- e **il 5% pagato non si
  rimborsa**. Se il cliente, prima di pagare, passa al bonifico, la
  richiesta torna `SUBMITTED` e segue il percorso del bonifico. Il bonifico
  non cambia: verifica dell'importo, bonifico, «Conferma bonifico
  ricevuto», ricarica; e l'amministratore non può mai confermare a mano un
  pagamento con carta. Rischio accettato dall'utente: con la carta il
  cliente spende subito JavCash su un importo che ha scritto lui.
- **Percentage unified to 5% (Session 33)**: was 3% until Session 33, changed
  to match `orders/service.py::ORDER_CASHBACK_PERCENTAGE` (the per-product
  "riscuoti subito cashback" figure, see below) at explicit user request --
  one consistent number wherever "cashback" appears in the product, not two
  different ones depending on which flow. Still two separate constants in
  two files (`invoice_redemptions/models.py::CASHBACK_PERCENTAGE` and
  `orders/service.py::ORDER_CASHBACK_PERCENTAGE`), just kept in sync by
  convention, not by sharing an import.
- **No OCR today**: the customer types the amount they read; an admin always
  verifies against the uploaded document before anything is unlocked. This
  is a deliberate simplification, not a stub -- the flow is fully functional
  without automated reading, just slower per-request for the admin.
- **Real partners configured (Session 31)**: the org previously had zero
  `Partner` rows -- the redemption dropdown was empty and the "Nuova
  richiesta" button correctly disabled itself (see the empty-state fix
  earlier in this same file's history). Three real partners were added via
  the existing `POST /partners` admin endpoint: **Jav** itself
  (deliberately included first -- lets a customer redeem cashback on their
  own Jav bill too, not only on an external supplier's), **Eviso**,
  and **Aenergy**. Logos: Jav's own (`example.com/img/logo.png`)
  and a verified real Eviso logo (hotlinked from `eviso.it`, visually
  confirmed before use) are set; Aenergy's `logo_url` was deliberately left
  `null` rather than guessing at an unverified company/logo for a
  real third-party trademark shown to customers -- set it via the admin
  Partner panel once the correct one is confirmed.
- **Where the document lives**: NOT the `documents` table (that one's
  `contract_id` is NOT NULL by design, for contract KYC documents) --
  `invoice_redemptions` carries its own `storage_key` in the same private
  bucket via `core/storage.py`.
- **Spending side (Phase 4, added Session 24; self-checkout + card payments
  added Session 26)**: `Product.category` (`INTERNAL`/`DROPSHIPPING`/
  `PARTNER`) and `ProductVersion.credit_discount_percentage` (0-100,
  enforced to 0 for `INTERNAL`) gate a new `orders` domain -- deliberately
  NOT `Contract` (`Contract.supply_point_id` is NOT NULL by design, every
  contract is an energy supply; an order for e.g. a partner t-shirt has no
  equivalent). Either an admin or the customer themselves (self-checkout)
  picks a DROPSHIPPING/PARTNER product version and how much wallet credit
  to apply (capped by both the product's percentage and the customer's
  balance, previewed via `GET /orders/quote` or `/orders/quote/mine` first);
  that amount is debited immediately via a `PURCHASE_DEBIT` wallet-transaction
  type (the mirror of `ADMIN_CREDIT`: `to_wallet_id` NULL instead of
  `from_wallet_id` NULL). The residual is paid one of two ways: **bank
  transfer**, confirmed by an admin exactly like a contract's `PAID`
  transition, or **card via Stripe** (`app/domains/payments/`), confirmed
  automatically by a webhook once `checkout.session.completed` fires -- the
  only case in this domain where `PAID` is reached with no human actor. If
  credit alone covers 100%, the order skips straight to `PAID` regardless of
  payment method. Cancelling an `AWAITING_PAYMENT` order reverses the exact
  `PURCHASE_DEBIT` row via `reverse_transaction()` (extended to handle a
  debit with no recipient wallet), refunding the customer precisely.
- **Payment method availability is gated, not just visually disabled**:
  bank transfer requires an IBAN set in `Organization.settings`
  (`bank_iban`, admin-editable, `organization.manage` permission); card
  requires BOTH a Stripe secret key and publishable key set (a separate,
  stricter `organization.manage_payments` permission -- **SUPER_ADMIN
  only**, deliberately narrower than the bank IBAN's permission tier). A
  frontend must never render a payment-method button for an unconfigured
  method; `create_order()` independently rejects the request server-side
  regardless (`PaymentMethodNotAvailableError`), so this is enforced even if
  the frontend were bypassed. Stripe secret/webhook keys are never returned
  in full by any endpoint, only "configured yes/no" plus the secret key's
  last 4 characters -- same principle as a password never round-tripped in
  plaintext.
- **Stripe webhook is per-organization and unauthenticated by design**:
  `POST /payments/stripe/webhook/{organization_id}` takes no auth
  dependency -- the Stripe signature, verified against THAT organization's
  own webhook secret, is the authentication. The organization id in the URL
  is what a SUPER_ADMIN pastes into their own Stripe Dashboard's webhook
  config, and is what keeps one endpoint correct for every tenant in
  principle, even though this deployment currently has one organization.
  **Needs a dedicated nginx location to actually be reachable (bug found and
  fixed Session 33)**: this route lives under `/api/`, which nginx normally
  routes entirely to the dashboard's BFF, not FastAPI -- see
  `infrastructure/nginx/nginx.conf`'s `location /api/payments/stripe/webhook/`
  and `server-migration-guide.md §8` bug #15. Without it every webhook
  delivery 404s and no card order/redemption is ever auto-confirmed.
- **Redemption fee now also payable by card, with a proof-upload option for
  bank transfer (Session 33)**: originally the redemption fee could only
  be paid by bank transfer with a reference code, manually reconciled by an
  admin with no self-service card option and no proof upload. It now works
  exactly like an order's residual: `invoice_redemptions.payment_method`
  (default `BANK_TRANSFER` at `verify()` time, switchable to `CARD` via
  `PATCH /invoice-redemptions/mine/{id}/payment-method` while still
  `PAYMENT_PENDING`), a Stripe Checkout Session for exactly
  `payment_due_cents()` (`POST
  /invoice-redemptions/mine/{id}/checkout-session`), and an optional
  bank-transfer receipt upload (`POST
  /invoice-redemptions/mine/{id}/payment-proof`, purely advisory, same
  private-bucket pattern as an order's payment proof). `confirm_payment()`
  (the manual admin action) refuses a `CARD`-method redemption
  server-side -- only the Stripe webhook may credit those, same anti-fraud
  rule as an order (see `security-model.md`).

## Product cashback -- "riscuoti subito cashback" (added Session 33)

A third, separate way wallet credit enters the system (alongside the plain
admin top-up and the partner-invoice redemption above), this time earned
directly from a Shop purchase rather than an external bill:

- **Per-product toggle**: an admin can enable `cashback_enabled` on any
  DROPSHIPPING/PARTNER product version (never on an INTERNAL Jav
  product -- same forced-off invariant, same single enforcement point
  pattern, as `credit_discount_percentage`).
- **At checkout**: if the product allows it, the customer sees a
  "riscuoti subito cashback" option. Opting in adds a flat
  `ORDER_CASHBACK_PERCENTAGE` (5%) surcharge on top of whatever is actually
  still owed in new money (`amount_cents - credit_applied_cents` -- i.e.
  AFTER any wallet-credit discount is already applied, never before it).
  Cashback can only be requested when that residual is greater than zero --
  a 100%-credit-covered order has nothing left to earn cashback on.
- **Payout**: once the order reaches `PAID` -- an admin confirming a bank
  transfer, or the Stripe webhook for a card charge -- the whole extra
  payment (the residual actually paid + the 5% surcharge) is credited back
  to the customer's wallet as JavCash, as two separate transaction rows
  (`ORDER_CASHBACK_BASE`/`ORDER_CASHBACK_BONUS`), exactly mirroring the
  partner-invoice redemption's base+bonus split above.
- **Anti-fraud, by explicit request**: the credited amount is always
  computed from the real new money paid in *that* order, never a
  pre-discount or otherwise inflated base -- so a customer can never use
  wallet credit to pay, then have cashback computed as if they'd paid more,
  manufacturing credit from credit. Crediting is idempotent
  (`orders.cashback_credited_at` guard + deterministic idempotency keys).
- **Spending existing credit now needs an OTP**: see the OTP bullet under
  "Internal wallet" above / `security-model.md` -- any self-checkout order
  that applies `credit_applied_cents > 0` requires a fresh emailed OTP,
  regardless of whether cashback was also requested on the same order.
- **Sblocco dell'account (Session 88)**: solo il superadmin può segnare
  come fatti per un cliente i controlli d'ingresso (email, privacy,
  profilo). Email e privacy si segnano; codice fiscale e residenza vanno
  scritti (mai inventati), e lo sblocco senza profilo completo si rifiuta.
  Ogni sblocco è nell'audit (`user.account_unlocked`) con chi l'ha fatto: la
  privacy così «accettata» è raccolta dal superadmin, non un clic del
  cliente.
- **PIN dei JavCash al posto dell'email (Session 87)**: dalle sue
  Impostazioni il cliente può scegliere di confermare l'uso dei JavCash con
  un **PIN di 4 cifre** scelto da lui invece del codice via email. Regole:
  per attivarlo, cambiarlo o spegnerlo serve la **password dell'account**
  (una sessione rubata non basta a sostituire la prova della casella email);
  niente PIN ovvi (cifre tutte uguali o in fila); salvato come la password,
  mai in chiaro; **5 errori = PIN bloccato 15 minuti** con email al cliente,
  e nel frattempo vale solo il codice via email; il codice via email resta
  **sempre** possibile («Non ricordi il PIN?»); ogni attivazione, cambio o
  spegnimento manda un'email al cliente. Tutti i checkout passano da
  `auth/service.py::request_spend_code` / `verify_spend_code`: la regola
  vive in un punto solo, e un checkout nuovo deve usare quelle due funzioni.

## "JavCash" -- wallet balance/transaction labeling (added Session 33)

Purely a dashboard label, not a new concept: every wallet balance and
transaction amount (top-ups, redemption/cashback credits, peer transfers,
purchase debits) is displayed with a "JavCash" suffix instead of a euro
sign, to keep it visually unmistakable from *real* money. Real-money
amounts -- what a customer actually paid via Stripe or bank transfer on an
order or a redemption fee -- are always shown in genuine EUR, labeled with
the payment method. No schema or currency-field change; `wallets.currency`
is still `"EUR"` in the database, this is presentation-only.

## Accounting / "Contabilità" (added Session 33)

A new customer-facing dashboard section (`GET /accounting/mine`, no
permission beyond authentication -- same pattern as `GET /wallets/me`)
merges a user's own `wallet_transactions` (JavCash movements) and their
own paid orders' real-money payments (EUR, tagged Bonifico/Carta) into one
chronological, filterable feed with running totals per category and a CSV
export. Computed on the fly from the two existing tables (see
`database-model.md` §14) -- deliberately not a new persisted table, so
there is nothing here that can drift from the wallet ledger or the orders
table, which remain the actual source of truth for their own domains.

### Session 54: totali, pagamenti dei contratti, dettaglio collegato {#accounting-detail}

- **I pagamenti dei contratti ci sono.** Ogni rata pagata
  (`contract_instalments.status = PAID`) è un movimento `CONTRACT_PAYMENT`
  in euro: carta se incassata da Stripe (`STRIPE_CHECKOUT`/`STRIPE_INVOICE`),
  bonifico se confermata a mano dall'amministrazione (`ADMIN`). Una rata = una
  riga, alla data in cui è stata incassata. Anche il cashback JavCash di un
  contratto porta ora il suo `contract_id`.
- **I totali li calcola il server** (`GET /accounting/mine/summary`,
  `accounting/service.py::my_summary`) dagli stessi movimenti dell'elenco, così
  le card e la lista non possono dire cose diverse: totale speso (carta +
  bonifico) e ripartizione, speso nel mese corrente, per ordini / riscatti /
  contratti, saldo JavCash (dal wallet), JavCash ricevuti e spesi, cashback
  ricevuto (fonti `*_CASHBACK_*` e `CONTRACT_CASHBACK`), contratti attivi,
  rate pagate e **prossima rata** (somma delle rate previste nello stesso
  giorno, contratti con addebiti non interrotti). **Provvigioni** solo se
  l'account è anche un promoter: totale maturato, da incassare (`ACCRUED`/
  `PAYABLE`/`SCHEDULED`), pagate; `REVERSED`/`CANCELLED` escluse.
- **Dettaglio** (`GET /accounting/mine/detail?ref=…`, e
  `/accounting/admin/detail` per lo staff con `wallet.manage`;
  `accounting/details.py`): `wallet:<id>`, `order:<id>` (ordine normale o
  "Acquisti Jav"), `redemption:<id>`, `contract:<id>`. Stessa forma per
  tutti: dati, **cronologia con data e ora al secondo e chi ha agito**
  (creazione, ricevuta del bonifico caricata, pagamento confermato "Stripe
  (automatico)" o dall'amministratore, cashback accreditato, annullamento,
  approvazione, ogni rata incassata, prossima rata), le rate di un contratto,
  e i riferimenti collegati. Lato cliente tutto è limitato alle proprie cose:
  ciò che non è suo risulta "non trovato", mai "vietato".
- **Tutto collegato**: ogni riga apre il suo dettaglio; il chip "Ordine /
  Riscatto / Contratto #…" apre quella cosa, che elenca tutti i movimenti che
  ha prodotto (pagamento in euro, JavCash usati, cashback), ognuno apribile a
  sua volta.

## Account gates (Session 27)

Three independent, self-service gates block dashboard use until satisfied,
each with its own acceptance state persisted on `users`/`agent_profiles` and
visible to admins (Anagrafiche Clienti/Promoter, small badges next to each
account). None of these are enforced client-side only -- every corresponding
backend action independently requires the same state.

- **Privacy consent**: `users.privacy_accepted_at`, set once at
  self-registration (`RegisterRequest.accept_privacy`, a required checkbox --
  the request is rejected server-side if unticked). NULL for every account
  that predates this field (admin-created accounts, or self-registered
  before Session 27) -- there is no retroactive consent to backfill, so it
  simply stays NULL for those.
- **Email verification** (new registrations only): `users.email_verified_at`
  (a column that already existed, previously unused). Registration sends a
  branded confirmation email (`core/email_templates.py`) with a link to
  `/verify-email?token=...`, backed by `email_verification_tokens` (opaque
  token, hashed at rest, 24h expiry, single-use -- same pattern as
  password-reset tokens). **Explicit product decision**: every account that
  existed before this feature shipped is grandfathered as already-verified
  (the 0026 migration backfills `email_verified_at = COALESCE(email_verified_at,
  created_at)` for every NULL row) -- nobody who was already using the
  product gets a surprise "confirm your email" wall. The rule applies only
  going forward, to accounts created after Session 27.
- **Profile completion** (fiscal code + residence address): `users.fiscal_code`
  + `residence_street/city/province/postal_code/country`. Unlike email
  verification, this one is deliberately retroactive -- **every** account,
  existing or new, sees the blocking popup at next login until filled in
  (`PATCH /auth/me/profile`, `users/service.py::is_profile_complete`).
  Demo/seed accounts are pre-filled so they're never blocked.
- **Promoter collaboration agreement + OTP** ("lavora con noi"):
  `agent_profiles.collaboration_accepted_at` /
  `collaboration_contract_version` / `collaboration_otp_verified_at`.
  Becoming a promoter now requires ticking a collaboration-agreement
  checkbox (`accept_contract`) AND typing back a 6-digit code emailed via
  `POST /network/agents/apply/request-otp` (`otp_codes` table, purpose
  `PROMOTER_APPLICATION_OTP_PURPOSE`, 10-minute expiry, single-use, verified
  server-side in `apply_as_promoter()` before any of the existing
  auto-activation/reapplication branching runs) -- proof the account holder,
  not just whoever is logged in, actually agreed.
- All four gates apply only to CUSTOMER/PROMOTER accounts, not admin-tier
  roles (`account-gate.tsx` checks live roles from `GET /auth/me` before
  rendering the blocking modal) -- there is no scenario where blocking a
  SUPER_ADMIN's own dashboard behind a fiscal-code popup makes sense.

**Notification emails** (also Session 27, same branded-HTML-shell mechanism):
cashback credited (`invoice_redemptions/service.py::confirm_payment`, fires
after the wallet credit) and a new support ticket opened
(`support/service.py::create_ticket`, sent to
`Organization.settings.admin_notification_email`, defaulting to
`info@example.com` -- `organizations/service.py::DEFAULT_ADMIN_NOTIFICATION_EMAIL`,
admin-editable via the existing company-settings PATCH). All best-effort:
an SMTP hiccup is logged, never blocks the underlying action (ticket
creation, cashback crediting, registration all already committed by the
time the email send is attempted).

## Store orders vs. Jav contracts -- and the Session 28 e-commerce pass

Two structurally different things both live under "products", and this
distinction is load-bearing, not cosmetic:

- **Jav (`category=INTERNAL`) products** are the matrix a real
  energy-supply **Contract** is created from (`POST /contracts`) -- these
  are what a promoter earns commissions on, and what shows up in the
  network/commission engine. They never go through the `orders` domain at
  all (`orders/service.py::_get_sellable_product_version` explicitly
  rejects INTERNAL products with a "si acquistano come contratto" error).
- **DROPSHIPPING/PARTNER products** are a separate, purely additional perk:
  a customer's cashback wallet balance can be spent on them via the `orders`
  domain (self-checkout, `POST /orders/mine`) -- no commission, no network
  effect, just an e-commerce-style purchase paid partly in wallet credit and
  partly by bank transfer or card.

**Session 28** brought the store/order side of this up to a real e-commerce
standard, per explicit request ("rendilo un ecommerce professionale"):

- **Product photo everywhere a product/order shows one**: `ProductVersion.
  image_url` (already existed, admin-uploadable since an earlier session)
  now also flows through to `OrderRead.product_image_url`
  (`orders/service.py::to_read_dict` joins it in) -- the same photo appears
  as a thumbnail on every order row, admin or customer side, not just the
  shop grid. A shared `product-thumbnail.tsx` component renders it (or a
  neutral package-icon placeholder when there is none) everywhere, so the
  "no photo yet" look is consistent instead of each screen inventing its
  own fallback.
- **Product detail page before checkout**: clicking a purchasable
  (DROPSHIPPING/PARTNER) product card opens `product-detail-modal.tsx`
  first -- full description, price breakdown, photo -- rather than jumping
  straight from the grid card into the checkout flow, matching how a real
  storefront works. INTERNAL (Jav) products never get this
  treatment; those stay contract-only.
- **"I miei Ordini"** (`customer-orders-panel.tsx`, new customer-dashboard
  tab): every order the customer has placed, with its status (in attesa di
  pagamento / pagato / annullato) and a "Paga ora" action on an unpaid one
  -- exactly the "reservation list" the request asked for, so a customer
  never has to remember what they bought or track down how to finish
  paying for it. The existing `admin-orders-panel.tsx` (already a full
  gestionale -- create, confirm bank transfer, cancel, filter by status)
  gained the same photo thumbnails for consistency.
- **Order-confirmation email** (`orders/service.py::_send_order_confirmation_email`,
  fires at the end of `create_order()`, after the order is already
  committed): summarizes what was bought and explains exactly how to pay --
  the IBAN + causale for a bank-transfer residual, or a real, freshly-minted
  Stripe payment link for a card residual, or a simple "no payment needed"
  confirmation when credit covered everything. Best-effort like every other
  email in this project: both `EmailNotConfiguredError` (SMTP off) and any
  `stripe.error.StripeError` (bad/revoked key, Stripe outage) are caught so
  a payment-provider hiccup can never take an already-created order down
  with it -- the customer can still get a fresh Stripe link later from "I
  miei Ordini".
- **Stripe checkout opens in a new tab, never a full-page redirect**
  (`window.open(checkout_url, "_blank", "noopener,noreferrer")` in both
  `product-checkout-modal.tsx` and `customer-orders-panel.tsx`) -- per
  explicit request: if Stripe fails or the customer changes their mind
  mid-payment, the dashboard tab they were already on is never lost.
- **Dashboard header images**: the Wikimedia-hotlinked `SectionBanner`
  images (dim/dark, and "commissions"/"wallets" sharing one photo) were
  replaced with brighter, distinct, locally-bundled photos per section
  (`apps/dashboard/public/images/header-*.jpg`) -- same "bundle it locally,
  don't hotlink" convention `documentation-header.jpg` already established.

### Session 29 follow-up: verified, then polished further

The user asked to re-verify two things before continuing -- both checked
against the live database, not just the code:

- **Per-product credit-discount percentage**: confirmed correct end-to-end,
  no bug found. `ProductVersion.credit_discount_percentage` is clamped to 0
  for `INTERNAL` products and 0-100 for DROPSHIPPING/PARTNER
  (`catalog/service.py::_clamp_credit_discount`); `orders/service.py::
  get_quote()`/`max_creditable_cents()` read that product's own value, never
  a global constant. Live-verified: a 69,00€ PARTNER product with a
  30%-in-credits version correctly quoted `max_creditable_cents: 2070`
  (exactly 30% of 6900) via `GET /orders/quote/mine`.
- **Contract flow authority**: see "Who can move a contract through this
  pipeline" above -- confirmed staff-only, not a customer self-service
  flow; documented since the user asked to double check their own mental
  model of it.

Then, cosmetic/UX polish on top of the already-correct backend:

- **Product showcase redesign** (`customer-products-panel.tsx`): bigger,
  bolder price and "crediti usabili" (computed from that product's own
  price × discount %, shown in euro, not just a percentage badge) side by
  side at the bottom of each card; a discount ribbon and category chip
  overlaid on the photo; hover zoom on the image, card lift + glow, and a
  staggered fade-in on the grid; the whole photo stays clickable through to
  `product-detail-modal.tsx`, which got the same bigger price/credits
  treatment plus a full-width gradient "Acquista ora" button.
- **Energy header photo swapped again**: from a ground-level solar-panel
  row to a bright aerial shot of a full solar farm (blue sky, vivid green)
  -- more strikingly "energia" and more luminous than the previous pick,
  per explicit feedback that the header art should lean into energy/light
  themes and brightness specifically.
- **Cashback-redemption camera capture upgraded to a real live viewfinder**
  (`camera-capture-modal.tsx`, `getUserMedia` + a `<video>` preview +
  canvas-frame capture) -- the previous "Scatta foto" button (Session 27)
  used a plain `<input capture="environment">`, which only opens a camera
  on some mobile browsers and does nothing at all on desktop (no webcam
  access). The new modal opens an actual live camera preview everywhere a
  camera exists, with a clear error+fallback state (close and use "Carica
  file") when it can't get camera access at all.
- **Desktop top nav bar added** alongside the existing sidebar
  (`app-shell.tsx`) -- big pill buttons for every nav item, pinned under
  the header on every page, mirroring the mobile bottom bar's "always one
  tap away" idea; the mobile bottom bar's own touch targets were also
  enlarged. This closes the gap left after Session 27 only shipped the
  mobile half of "primary tools as big buttons, bottom on mobile / top on
  desktop."

## Chi può aprire una pratica di attivazione (Session 66) {#pratica-authors}

Una pratica è sempre la stessa cosa — intestatario, N POD, un'offerta per POD,
documenti — e cambia solo chi la compila:

- **il cliente**, per sé (`created_by_role="CUSTOMER"`): guadagna il promoter
  che lo ha portato (o il primo sponsor attivo sopra di lui);
- **il promoter**, per un cliente suo (`PROMOTER`): guadagna lui, e il cliente
  riceve notifica ed email per pagare dalla propria area;
- **l'amministrazione** (`ADMIN`, Session 66): può indicare a quale promoter
  attribuirla (validato ACTIVE); senza indicazione vale la regola del
  self-service. Il cliente riceve lo stesso avviso.

**Il pagamento è sempre del cliente**: promoter e staff non possono aprire il
checkout né pagarlo (la pratica accetta il pagamento solo dall'intestatario);
lo staff può però confermare un bonifico ricevuto. Chi ha compilato la pratica
resta scritto sulla pratica e su ogni contratto.

## Marketplace: i tre shop di prodotti importati (Sessions 67-71) {#marketplace}

Tre fonti, tre tabelle separate, una sola promessa al cliente:

| Nello Shop del cliente | Fonte | Dominio / tabelle | Admin |
|---|---|---|---|
| **Marketplace 1** | CJ Dropshipping (API) | `cj_dropshipping` | Shop CJ |
| **Marketplace 2** | Shopify (Admin API) | `shopify_dropshipping` | Shop Shopify |
| **Marketplace 3** | AliExpress (Dropshipping API) | `aliexpress_dropshipping` | Shop AliExpress |

(Numerazione e nomi del menu decisi dall'utente in Session 70.)

Il vecchio plugin "a mano" (`imported_products`, Session 34) resta in piedi
sotto lo stesso Marketplace 3, come scheda secondaria "Prodotti inseriti a
mano": serviva quando AliExpress non aveva API e continua a funzionare per
qualunque prodotto si voglia vendere senza fornitore collegato. I suoi 5
prodotti di prova sono stati cancellati in Session 71 (nessun ordine li
aveva mai usati).

I tre shop sono **domini isolati**: tabelle proprie, client proprio, ordini
propri. Quello che NON è isolato, per scelta esplicita dell'utente (Session
34), è la gestione: "I miei Ordini" del cliente, "Ordini" dell'admin e la
Contabilità mostrano un elenco unico, con un tag interno `source` che il
cliente non vede mai.

### La spedizione AliExpress: costo reale, con un minimo {#marketplace-shipping}

Dalla Session 76 la spedizione dei prodotti AliExpress **non è un forfait**.
Si chiede ad AliExpress quanto costa davvero
(`aliexpress.ds.freight.query`, per prodotto / SKU / quantità /
destinazione) e si addebita:

    spedizione addebitata = max(costo reale AliExpress, minimo configurato)

Il minimo è il campo delle impostazioni che prima era il forfait
(`shipping_minimum_cents`): cambiarlo dall'admin cambia il checkout subito,
senza toccare codice. **A zero il minimo non esiste** e si paga esattamente
il costo reale — è la configurazione scelta dall'utente il 21/09/2026, dopo
aver visto che il catalogo va da 1,99 a 44,16 EUR di spedizione vera. Il
meccanismo resta nel codice e si riattiva rimettendo un importo.

**Il minimo vale una volta per ordine, mai per articolo.** Tre prodotti con
1,20 di spedizione ciascuno fanno 3,60 di costo reale e 5,90 addebitati,
non 17,70. Il costo reale di un ordine è la **somma delle righe**: la DS API
di AliExpress quota il freight per prodotto e non espone una quotazione di
carrello, quindi sommare è un'operazione nostra, non sua.

**Se non si riesce a sapere quanto costa spedire, non si vende.** È l'unico
errore del dominio senza ripiego (`AliexpressShippingUnavailableError`):
addebitare il minimo vorrebbe dire decidere che AliExpress spedisce a meno
di 5,90 senza averglielo chiesto, e incassare 5,90 su una spedizione da 20
euro; addebitare zero è peggio. Un'opzione senza prezzo non è una
spedizione gratis: è un'opzione di cui AliExpress non ha detto il costo. Nel
carrello questo si vede come sezione non acquistabile con la ragione
scritta, non come errore.

**Tre numeri congelati sull'ordine**, non uno: quanto è costata
(`supplier_shipping_cents`, e per riga sugli item), il minimo in vigore quel
giorno (`minimum_shipping_cents`) e quanto ha pagato il cliente
(`shipping_cents`). Il margine di spedizione è la differenza fra l'ultimo e
il primo, e senza tutti e tre non sarebbe ricostruibile. Sugli ordini
precedenti i primi due sono NULL — "non rilevato", che è la verità: uno zero
direbbe che spedire non costava niente e gonfierebbe ogni margine passato.

**Ad AliExpress non si manda mai il nostro numero.** Il minimo riguarda solo
ciò che addebitiamo al cliente; l'ordine verso il fornitore porta i suoi
dati logistici reali.

Il freight si tiene in cache mezz'ora per (organizzazione, prodotto, SKU,
quantità, destinazione): un cliente che alza e abbassa la quantità non deve
costare una chiamata ogni volta, e la chiave contiene tutto ciò che può
cambiare il prezzo, quindi cambiare variante o quantità produce una chiave
nuova senza che nessuno debba invalidare niente.

**Attenzione al nome di un campo**: nella risposta di `ds.freight.query`
`shipping_fee_cent` **non porta centesimi**, porta un importo ("1.99" =
1,99 EUR). Verificato sul gateway vero nella Session 76, dopo che la
Session 71 lo aveva lasciato segnato come da verificare. Leggerlo come
centesimi divideva ogni spedizione per cento, ed è il tipo di errore che
non si vede finché il numero non tocca il prezzo.

Con `shipping_mode = INCLUDED` non cambia nulla rispetto a prima: il minimo
entra nel prezzo di listino e al checkout non si addebita spedizione.

### Marketplace 4: «Fai la Spesa con Jav» {#jav-market}

Il quarto negozio (Session 79) segue tutte le regole di questa sezione --
JavCash solo da spendere e mai per intero, niente cashback, bonifico
scontato, IVA aggiunta al prezzo, carrello con una spedizione sola -- e ne
ha una sua: **il catalogo lo scrive l'amministratore**, non un fornitore.

Ne discende il resto. Non ci sono prezzi ricalcolati a ogni sync, né cambio
valuta, né ricarico su un costo: il prezzo è quello di vendita. La
spedizione è un importo fisso e non un minimo, perché senza fornitore non
esiste un costo reale da confrontare. E non c'è un ordine da inoltrare: un
ordine pagato aspetta che l'amministratore lo spedisca e ne segni il
tracking, che è anche il momento in cui il cliente riceve l'email.

**L'ordine pagato va all'azienda**, a mano con un pulsante o da solo se
`auto_forward` è acceso (nasce spento: mandare una email a un'azienda vera
è un'azione verso l'esterno). Parte **una email per azienda**, con solo le
sue righe, l'indirizzo di consegna e le note del cliente — mai i prezzi che
il cliente ha pagato, che mostrerebbero il ricarico. Solo un ordine già
pagato si inoltra. Un'azienda senza email o una riga senza azienda vengono
segnalate allo staff e scritte in `forward_error`, mai saltate in silenzio.
Il reinvio è ammesso: qui non si crea niente dall'altra parte, a differenza
di AliExpress dove un secondo invio sarebbe un secondo acquisto.

**L'azienda produttrice ha una scheda sua** e il suo nome si congela sulla
riga d'ordine: è il motivo per cui questo negozio esiste — qui si sa chi fa
la merce — e rinominarla non deve cambiare cosa dice un ordine di sei mesi
fa. Al cliente si mostrano nome, descrizione e sito; partita IVA, email,
telefono e sede restano all'amministrazione.

**Ordine minimo e spedizione gratuita (13/10/2026), solo qui.** Spedizione
fissa 15 €, ordine minimo 80 €, spedizione gratis da 150 € in su. Entrambe
le soglie si misurano sulla **merce IVA inclusa** (scelta dell'utente):
spedizione esclusa, prima dei JavCash. Sotto il minimo il carrello si apre
e dice quanto manca, ma non si paga e `create_order` rifiuta l'ordine (anche
con «Acquista subito»). Valori in `jav_market_settings.min_order_cents`
(0 = nessun minimo) e `free_shipping_threshold_cents` (NULL = mai gratis),
modificabili dalle Impostazioni del negozio. Gli altri Marketplace non hanno
queste regole.

### AliExpress: disponibilità quasi in tempo reale (Session 87) {#aliexpress-live}

Un prodotto importato da AliExpress può sparire o esaurirsi in qualunque
momento. Tre livelli, dal più largo al più stretto: la **sync completa ogni
3 ore**; la **rilettura della scheda** quando il cliente la apre (se
l'ultima lettura ha più di 10 minuti); la **rilettura delle righe prima di
creare l'ordine** (2 minuti), prima di JavCash, codice e pagamento. Nessuno
può quindi pagare un articolo che AliExpress ha già tolto.

Due regole: la sync aggiorna solo ciò che decide AliExpress (costo, scorte,
disponibilità, foto) e mai ciò che decide l'amministratore (nome,
descrizione, JavCash, ricarico, prezzo a mano, acceso/spento, categorie); e
un AliExpress che non risponde non spegne niente — si resta sull'ultima
lettura buona. Il caso che resta scoperto è l'esaurimento nei secondi dopo il
pagamento: l'ordine al fornitore fallisce e lo staff riceve l'avviso, come
prima.

Dalla Session 88 la stessa lettura controlla anche che AliExpress **spedisca
in Italia**: un prodotto senza nessuna spedizione con un prezzo si nasconde
al cliente («Non spedibile in Italia») e torna da solo quando la spedizione
riappare. Un AliExpress che non risponde non nasconde niente.

### Vetrina dei Marketplace a pagine (Session 89) {#shop-paging}

Regola dell'utente: **il server non deve mai bloccarsi o rallentare perché un
negozio ha tanti prodotti.** Ogni Marketplace (CJ, Shopify, AliExpress, Fai la
Spesa con Jav, Market Kappa, VAITTO, Shop Beauty) dà al cliente **48
prodotti alla volta**; sotto la griglia «N di M prodotti» e il pulsante
**«Mostra altri prodotti»**. Ricerca e categoria cercano in tutto il negozio
(le filtra il server, non il browser). Un prodotto acceso che non si può
vendere (esaurito, non spedibile in Italia) non lascia pagine a metà. Un
Marketplace nuovo deve usare la stessa vetrina a pagine
(`marketplaces/paging.py`), mai restituire tutto il catalogo. Restano in una
sola risposta solo i pacchetti/contratti e il vecchio AliExpress a mano,
cataloghi scritti dall'amministratore e piccoli per natura.

### «Marketplace SYMPHONYA» («Shop Beauty» per il cliente) {#symphonya-market}

Profumi e cosmetici dal grossista Symphonya (symphonya.eu), Session 89. Per
il cliente si chiama **«Shop Beauty»** (nome scelto dall'utente il
2026-10-02; è un'impostazione, `marketplace_labels.symphonya_market`), in
amministrazione «Shop Symphonya». Stesse regole del Marketplace VAITTO, da
cui è clonato:

- il catalogo arriva dall'API di Symphonya, **spento**: si accende per marca
  o categoria. **Online per i clienti dal 2026-10-02**: acceso tutto ciò che
  è vendibile (31.794 prodotti su 31.885); i prodotti nuovi dei prossimi
  import arrivano ancora spenti;
- **prezzo al cliente = prezzo consigliato al pubblico di Symphonya (rrp),
  IVA inclusa**; dove Symphonya non lo dà, il costo più il 40% e l'IVA;
- **JavCash dal guadagno, stessa formula di VAITTO** (dal 2026-10-02):
  guadagno = prezzo IVA inclusa ÷ 1,22 − costo a noi così com'è (niente
  spedizione, niente IVA sul costo); JavCash = metà del guadagno, in % del
  prezzo IVA inclusa, per difetto. Es. 58,62 € ÷ 1,22 = 48,05 − 25,42 =
  22,63, metà 11,31 = 19,3% → **19%**. Un articolo con guadagno ≤ 0 non si
  vende. Il campo «Spedizione nostra per prodotto» (`shipping_cost_cents`)
  resta in tabella ma non entra più nel calcolo;
- **spedizione al cliente: 10 € a ordine**, come VAITTO;
- **vetrina a pagine**, come tutti i Marketplace (vedi «Vetrina dei
  Marketplace a pagine»): con il catalogo intero in una sola risposta erano
  63 MB, 8 secondi e ~500 MB di memoria del server per ogni apertura;
- **ordini a mano** su symphonya.eu: Symphonya vende all'ingrosso (minimo
  d'ordine 99 €, bonifico anticipato) e spedisce a noi, non al cliente.

### «Marketplace SOLEIL» («Market 7» per il cliente) {#soleil-market}

Il catalogo affiliato di **SoleilDrop** (soleildrop.com), Session 90. Per il
cliente si chiamava **«Market 7»**; dal 13/10/2026 si chiama **«Fai la Spesa
con Jav 2»** (scelta dell'utente; impostazione
`marketplace_labels.soleil_market`), in amministrazione «Shop SoleilDrop».
**Online per i clienti dal 2026-10-13**: 5179 referenze dall'API, tutte
accese; spedizione fissa **10 €** a ordine, pagata dal cliente.
Clone di Shop Beauty con le **stesse regole** (scelta dell'utente: «uguali
per tutti i negozi»):

- SoleilDrop è un gestionale con un portale per gli affiliati in
  dropshipping e **non ha un'API da leggere** (il suo connettore spinge il
  catalogo dentro PrestaShop o WooCommerce). Il catalogo arriva quindi
  dall'**Excel di «Il Mio Catalogo → Esporta → Excel generico (.xlsx)»**,
  caricato a mano nel pannello (va bene anche lo stesso file salvato come
  CSV). Va esportato «Tutte quelle in elenco»: una referenza che manca dal
  file smette di essere comprabile (salvo file troncato, < metà dei noti);
- i prodotti nuovi arrivano **spenti**: si accendono per marca o categoria;
- **prezzo al cliente = «Prezzo vendita (ivato)» del file** (il prezzo che
  l'affiliato ha fissato nel portale); dove manca, il «Prezzo Soleil» più
  il 40% e l'IVA; il «Prezzo Soleil» è il nostro costo (IVA esclusa);
- **JavCash dal guadagno, stessa formula di VAITTO e Symphonya**;
- il file non dice quante scorte ci sono, solo «Disponibile Sì/No»:
  disponibile = nessun limite, «No» = non comprabile;
- **ordini a mano** nel portale SoleilDrop, che spedisce al cliente;
- spedizione al cliente: un'impostazione del negozio (come gli altri).

**API affiliati SoleilDrop v1 (dal 13/10/2026)** — SoleilDrop ha pubblicato
l'API (https://www.soleildrop.com/api-affiliati.html, v1 del 08/10/2026).
Con la chiave «sdk_…» nelle impostazioni (si scrive, non si rilegge):

- **catalogo** da `GET /catalog?all=1` ogni 3 ore (o «Importa adesso»),
  con le stesse regole dell'Excel; chiave = codice SoleilDrop, come la
  colonna «Codice», quindi i due ingressi aggiornano gli stessi prodotti.
  Il `sell_price` dell'API è senza IVA: si porta IVA inclusa con l'aliquota
  della referenza. **Nel catalogo reale `sell_price` è vuoto per tutte le
  referenze** (13/10/2026): vale il prezzo di riserva, costo + 40% + IVA,
  e quella formula oggi usa il **22% fisso** anche per gli alimentari al 10%
  e al 4% (`vat_rate` dell'API: 22, 10, 4, 5) -- **da correggere**, come lo
  scorporo dell'IVA al checkout, che usa l'aliquota del negozio. Si vende solo a pezzi (`units.piece`). Se l'API elenca
  più id di quante referenze manda, non si spegne niente;
- **ordini** con `POST /orders`, `external_ref` = «JAV-<numero>»:
  SoleilDrop non duplica mai lo stesso riferimento, quindi rimandare è
  sicuro. Si mandano solo codici, quantità, indirizzo e note: **nessun
  prezzo nostro** (né `sell_price` né `total_paid`). Pagati dal wallet
  prepagato: con credito insufficiente → WAITING_WALLET (202) e notifica
  allo staff, poi riparte da solo alla ricarica. 409/429/5xx/rete → RETRY
  (job ogni 10 min); altri errori → ERROR + notifica. Invio automatico solo
  se `auto_forward` è acceso (nasce spento);
- **stato e tracking** dal webhook `POST /api/soleil-market/webhook/{org}`
  (HMAC-SHA256 del corpo grezzo con il segreto, doppioni scartati con
  `X-Soleil-Delivery`) e, come riserva, `GET /orders?since=` ogni 30 min.
  Spedito/consegnato avvisano il cliente una volta; annullato da SoleilDrop
  → notifica allo staff, il rimborso al cliente è a mano;
- senza chiave tutto resta come prima (Excel + ordini a mano).

### Marketplace 6: «Marketplace VAITTO» {#vaitto-market}

Clone di Market Kappa, indipendente, rifornito dal feed di Vaitto (Session
88). Per il cliente era «Marketplace 5»; oggi il nome impostato
dall'amministratore è **«Top Brand»** (in amministrazione «Marketplace
VAITTO»). **Online per i clienti dal 2026-10-02** (2.005 prodotti vendibili
accesi, spedizione 10 € a ordine). Regole scelte dall'utente:

- **tutto il catalogo si importa, spento**: un prodotto nuovo del feed è
  INACTIVE; si accende per marca o categoria (mai «tutto» con un clic);
- **prezzo = prezzo suggerito da Vaitto + nostro ricarico** (Session 88,
  seconda scelta dell'utente: il ricarico è 0 di base, sovrascrivibile per
  prodotto, e si aggiunge sopra il suggerito senza arrotondamenti); l'IVA si
  aggiunge al checkout come in ogni Marketplace; il costo all'ingrosso lo
  vede solo l'amministratore (le condizioni di Vaitto vietano di mostrarlo ai
  consumatori); il listino Vaitto si mostra barrato solo se è più alto del
  nostro prezzo;
- **JavCash**: uguale per tutti (percentuale del negozio) oppure **dal
  nostro guadagno** -- formula dell'utente (Session 89, 2026-10-02):
  guadagno = prezzo al cliente IVA inclusa ÷ (1 + IVA) − costo Vaitto così
  com'è (niente spedizione, niente IVA sul costo); JavCash = la quota
  scelta (di norma metà) del guadagno in % del prezzo IVA inclusa, per
  difetto, sulla variante che rende meno. Es. Moose Knuckles a 450 €: 450 ÷
  1,22 = 368,85 − 129,38 = 239,47, metà 119,73 = 26,6% → **26%** (il cliente
  può usare 117 €). Una variante con guadagno ≤ 0 **non si vende**. La
  formula di prima (Session 88: prezzo − (costo + 5 €) × 1,22) non si usa
  più, e «Spedizione nostra per prodotto» è sparita dal pannello;
- **IVA**: con il prezzo del marchio («Sell at brand RRP», `price_basis`
  «rrp») l'IVA è dentro il prezzo e al checkout si scorpora; con il prezzo
  dal ricarico («markup») si aggiunge, come negli altri Marketplace. Lo dice
  il feed; una percentuale
  scritta a mano su un prodotto resta finché non la si riporta alla regola;
- un prezzo **scritto a mano** resta finché qualcuno non lo riporta al
  ricarico; l'import aggiorna solo costo, listino, scorte, disponibilità e
  categoria, mai nome, descrizione, foto scelte, stato, JavCash o ricarico;
- ciò che sparisce dal feed smette di essere comprabile ma non si cancella;
  un feed con meno della metà dei prodotti noti non spegne i mancanti;
- **gli ordini non partono da soli**: l'ordine pagato resta nel pannello con
  SKU, EAN, link e indirizzo, e lo si inserisce a mano su vaitto.com.

### CJ: disponibilità quasi in tempo reale (Session 88) {#cj-live}

Come AliExpress (vedi sopra): sync ogni 3 ore, rilettura della scheda
all'apertura (10 minuti) e delle righe prima dell'ordine (2 minuti), avviso
allo staff se la sync si rompe. La spedizione era già chiesta a CJ dal vivo a
ogni checkout.

### Marketplace 5: «Market Kappa» {#kappa-market}

Il quinto negozio (Session 87) è un clone di «Fai la Spesa con Jav»: stesse
regole, stesso funzionamento, catalogo scritto dall'amministratore. È
dedicato **solo** ai marchi Kappa e Robe di Kappa, e l'utente lo ha voluto
**indipendente**: tabelle, rotte, menu e carrello suoi, mai mescolato al
catalogo di «Fai la Spesa con Jav». Nei testi le «aziende produttrici» si
chiamano **marchi**.

L'EAN è lo `sku` della variante: è l'unico codice che identifica davvero un
capo (articolo + colore + taglia), ed è quello da usare per aggiornare le
scorte da un nuovo file di magazzino.


Un carrello per **(cliente, negozio)**, non uno solo per tutto. Al cliente
se ne mostra uno, diviso in sezioni: il totale in cima è la somma, il
pulsante di pagamento è per sezione. Il motivo non è tecnico ma di regole:

- i Marketplace hanno indirizzo di consegna, spedizione, IVA congelata e
  sconto bonifico; il catalogo interno non ha niente di tutto questo e ha
  invece il «riscuoti subito cashback», che nei Marketplace **è vietato**;
- righe con regole che si escludono a vicenda non possono finire nello
  stesso ordine, quindi non stanno nello stesso carrello.

Conseguenze da conoscere, tutte già implementate:

- **Nel carrello non ci sono prezzi.** Ogni lettura li ricalcola dal
  listino di quel momento; il prezzo si congela solo sull'ordine. Un
  articolo messo nel carrello a gennaio si paga al prezzo di quando lo si
  compra, che è anche l'unico che il cliente vede prima di confermare.
- **La spedizione si conta una volta per ordine**, non per riga.
- **Il tetto JavCash si calcola riga per riga**: la percentuale di ogni
  prodotto sul valore di quel prodotto, quantità compresa. Il tetto
  dell'ordine è la loro somma, mai oltre l'intero ordine meno un centesimo.
  **La spedizione non conta**: i JavCash scontano la merce, non il
  corriere. Così il tetto è esattamente quello che il cliente ottiene
  sommando a mano le percentuali dei prodotti che ha nel carrello, e un
  numero che si può rifare a mano è un numero di cui ci si fida.

  Quello che la finestra mostra è `min(tetto, saldo del wallet)`: se il
  saldo è più basso, è lui il limite, e va detto — altrimenti il cliente
  crede che il tetto sia sbagliato.

  Nella Session 75 era una media pesata sull'ordine, e **era sbagliata**:
  la media va arrotondata a percentuale intera, e l'arrotondamento non
  rispetta i singoli prodotti. Un articolo da 5 EUR al 99% accanto a uno da
  500 EUR allo 0% dava una media dell'1%, cioè 5,05 EUR spendibili — più di
  quanto il primo concedesse, presi da un prodotto che di JavCash non ne
  accetta affatto; in altre combinazioni toglieva mezzo euro a chi ne aveva
  diritto. **Un prodotto non presta mai il suo diritto a un altro.**

  Con una riga sola il calcolo torna identico a un acquisto singolo (la
  quota di spedizione è tutta sua), quindi comprare un articolo dal
  carrello o dalla sua scheda dà lo stesso tetto.
- **Un OTP solo** per checkout, non uno per riga.
- **Una riga invendibile non blocca il carrello**: si apre lo stesso, la
  riga è segnata con il motivo e il pagamento è sospeso finché non la si
  toglie. Pagare il resto in silenzio consegnerebbe un ordine diverso da
  quello composto dal cliente.
- **L'ordine si crea prima, il carrello si svuota dopo.** Se la creazione
  fallisce il cliente ritrova il carrello intatto.

Un ordine porta N righe (`<shop>_order_items`); **il denaro resta sulla
testata** — importo, spedizione, IVA, sconto bonifico, JavCash, sessione
Stripe. È la ragione per cui pagamenti, webhook, Contabilità ed email non
sono cambiati quando il carrello è arrivato.

**Ogni ordine ha un numero progressivo** (`shop_order_number_seq`,
`marketplaces/models.py`), assegnato dal database e condiviso da tutti i
negozi: in "I miei Ordini" i tre Marketplace stanno insieme, e tre "ordine
1042" diversi non si potrebbero distinguere. Si parte da 1000. È il numero
che finisce nelle email e che il cliente detta al telefono; gli ordini
creati prima della sequenza continuano a chiamarsi con le prime cifre del
loro UUID, perché rinominarli li renderebbe irrintracciabili.

**L'ordine vero al fornitore parte solo a pagamento avvenuto**, e solo se
l'amministratore ha acceso l'invio automatico. Con `auto_forward` spento
— com'è dal 21/09/2026 — un ordine pagato aspetta in "Marketplace
AliExpress → Ordini" che qualcuno prema "Crea su AliExpress": una verifica
umana prima di spendere davvero.

**Le email di un ordine sono tre, non una.** Conferma d'ordine alla
creazione (cosa hai ordinato, come pagarlo), **ricevuta al pagamento
confermato** (cosa hai pagato: articoli, spedizione, JavCash, sconto
bonifico, totale, metodo, IVA contenuta), spedito/consegnato con il
tracking. La ricevuta ripete l'elenco invece di rimandare alla prima
email: una ricevuta che non si basta da sola non è una ricevuta. Parte da
`_mark_paid()` e da nessun altro punto, ed è protetta dal doppio invio
dalle guardie `AWAITING_PAYMENT` dei due chiamanti — un webhook Stripe
ripetuto non manda una seconda ricevuta.

**Il cliente non sa mai da quale fornitore arriva la merce.** Nessuna
stringa rivolta al cliente nomina AliExpress, CJ o Shopify: le schede si
chiamano «Marketplace 1/2/3» (rinominabili dall'amministratore), le email
sono firmate Jav, `tracking_company` è salvato ma non mostrato, e
i nomi dei fornitori compaiono solo nelle notifiche allo staff. L'unico
residuo è il link di tracciamento, che punta al sito del corriere quando il
fornitore lo restituisce, altrimenti a 17track.

**Il margine si misura su tutte le righe.** Il costo fornitore di un ordine
è la somma delle righe: contare solo la testata dichiarerebbe i ricavi di
tutte e i costi di una.

**CJ quota il carrello intero in una chiamata**, perché `products` nella
sua API di freight è una lista: il prezzo che torna è quello della
spedizione unica. Sommare quotazioni separate farebbe pagare al cliente più
spedizioni di quante ne partono. Per lo stesso motivo un ordine CJ non può
mettere insieme righe da **magazzini diversi**: `startCountryCode` è uno
solo, e magazzino e corriere stanno sulla testata dell'ordine fornitore.
Chi ci prova legge il perché invece di vedersi creare un ordine che CJ
rifiuta.

**Lo split del fornitore.** Le API accettano già più righe (AliExpress
`product_items`, CJ `products`, Shopify `line_items`), ma un ordine Jav
può diventare più ordini fornitore: AliExpress li spezza per venditore e
risponde con una lista di numeri, CJ tiene magazzino e corriere sulla
testata. Per questo il numero d'ordine del fornitore e il tracking stanno
**sulla riga**, non solo sulla testata. Quando i numeri non si possono
abbinare con certezza alle righe, lo staff riceve un avviso invece di
vedersi attribuire un tracking a caso.

### Come si collega ciascuno {#marketplace-credentials}

| Shop | Credenziali | Dove si mettono |
|---|---|---|
| CJ | API key (cjdropshipping.com → My CJ → Authorization → API) | Shop CJ → Impostazioni |
| Shopify | App del **Dev Dashboard**: Client ID + Client secret, oppure un vecchio token `shpat_` | Shop Shopify → Impostazioni |
| AliExpress | App **Drop Shipping** di openservice.aliexpress.com: App Key + App Secret | Shop AliExpress → Impostazioni |

Shopify e AliExpress richiedono, dopo le credenziali, **l'installazione/
autorizzazione sul negozio o sull'account**, che è un giro OAuth: l'admin
preme "Collega", approva sul portale del fornitore e torna su una pagina di
esito (`/admin/shopify-connected`, `/admin/aliexpress-connected`). Gli
indirizzi da registrare nei due portali:

- Shopify — URL dell'app `https://jav.ecodo.ai`, URL di
  reindirizzamento `https://jav.ecodo.ai/api/shopify/oauth/callback`;
- AliExpress — Callback URL
  `https://jav.ecodo.ai/api/aliexpress/oauth/callback`.

I token non si scrivono mai a mano: Shopify con l'app del Dev Dashboard usa
il *client credentials grant* (token di 24 ore, rinnovato 5 minuti prima
della scadenza e dopo un 401) o il token offline dell'installazione;
AliExpress rilascia un token a scadenza con il suo `refresh_token`, rinnovato
allo stesso modo. Nessun secret viene mai restituito da un endpoint: solo
"configurato" e le ultime 4 cifre.

I nomi "Marketplace 1/2/3" sono impostazioni (`organizations.settings.marketplace_labels`,
card "Regole dei Marketplace" in cima a ciascuna delle tre pagine admin). Il
cliente non vede mai la fonte.

**Ogni sezione dello Shop si accende, si spegne e si rinomina** (Session 72).
Le tre schede che vengono dal catalogo nostro — "Jav" (INTERNAL),
"Prodotti Partner" (PARTNER), "Offerte Jav" (DROPSHIPPING) — hanno nome e
interruttore in `organizations.settings.shop_sections`
(`{internal|partner|dropshipping: {label, enabled}}`, tutto acceso finché un
amministratore non dice il contrario), card **"Sezioni dello Shop del
cliente"** nella pagina Prodotti. Le tre schede dei Marketplace hanno il
proprio interruttore ("Shop visibile ai clienti") nelle impostazioni del
rispettivo shop e il nome nella card Regole dei Marketplace. Due regole che
si sommano: **una scheda Marketplace compare solo se è accesa E ha almeno un
prodotto in vendita** — accesa con catalogo vuoto, il cliente non vede
niente. L'interruttore di visibilità dei tre shop **si salva da solo** al
clic: prima cambiava solo il modulo e chi non premeva "Salva" credeva di
aver acceso lo shop mentre i clienti continuavano a non vederlo. Il titolo dello Shop del cliente è **"Fai la
spesa con Jav"**; la vecchia scheda di catalogo DROPSHIPPING, che
aveva quel nome, ora si chiama "Offerte Jav".

Regole comuni (`apps/api/app/domains/marketplaces/rules.py`, l'unico posto dove vivono):

- **Stesso prezzo con bonifico e con carta: nessuno sconto bonifico**
  (Session 86, decisione dell'azienda: «non possiamo fare sconto se paghi con
  bonifico»). Fino alla Session 85 il bonifico toglieva il 5%
  (`marketplace_bank_transfer_discount_percentage`): ora
  `rules.get_bank_transfer_discount_percentage` e
  `rules.bank_transfer_discount_cents` danno sempre 0, il valore salvato
  nelle impostazioni viene ignorato e cancellato al primo salvataggio, e il
  campo per impostarlo non c'è più. La colonna `bank_transfer_discount_cents`
  resta sugli ordini: è quanto è stato scontato davvero sugli ordini vecchi,
  e i pannelli la mostrano solo quando è maggiore di zero. Vale anche per il
  bonifico delle pratiche di contratto (vedi sotto). Mai un aumento sulla
  carta.
- **IVA inclusa nel prezzo** (Session 74). Il prezzo mostrato è quello
  finale, come impone il Codice del Consumo (artt. 14-15) verso i
  consumatori: nessun "+IVA" da aggiungere al totale. L'IVA **contenuta**
  nel prezzo si legge nel checkout, nell'email di conferma e nel dettaglio
  dell'ordine ("IVA inclusa nel prezzo (22%)"), e viene congelata
  sull'ordine (`vat_percentage`, `vat_amount_cents`). Aliquota:
  `marketplace_vat_percentage`, default **22**, massimo 30, modificabile
  nella card Regole dei Marketplace; un cambio non tocca gli ordini già
  fatti. Base imponibile = importo − sconto bonifico: lo sconto abbassa il
  prezzo, quindi abbassa l'IVA, mentre **il JavCash non la riduce** perché
  è un mezzo di pagamento, non uno sconto (conseguenza visibile: con molto
  JavCash l'IVA contenuta può superare l'importo ancora da pagare). Il
  margine mostrato all'amministratore è al netto di IVA e sconto: l'IVA non
  è un nostro ricavo.
- **Niente cashback, JavCash solo in parte.** I prodotti dei Marketplace non
  generano cashback: servono a spendere il JavCash, mai per il 100% del
  prezzo. Un prodotto nuovo entra al **30%**; l'amministratore può alzarlo
  fino al **99%** (vincolo anche nel database). Con JavCash serve l'OTP.
- **Niente aumento sulla carta**: in Italia la maggiorazione sui pagamenti
  con carta dei consumatori è vietata (PSD2 art. 62(4), D.Lgs. 11/2010 art. 3
  c. 4, Codice del Consumo art. 62). Le Sessions 67-68 avevano un +5% sulla
  carta, mai andato in produzione; dalla 68 alla 85 c'era invece uno sconto
  del 5% sul bonifico, tolto nella 86.

## Shop Jav Partner: CJ Dropshipping (Session 60) {#partner-shop}

Un secondo negozio "importato", accanto ad "Acquisti Jav", collegato
davvero all'API di CJ Dropshipping. Tabelle e gestione proprie
(`cj_dropshipping`), esperienza del cliente identica agli altri negozi.

**Per il cliente, uguale a tutto lo Shop.** I prodotti compaiono nella
categoria **"Marketplace 1"** dello Shop (Session 64; dalla Session 62 alla 63
erano dentro "Fai la spesa con Jav"):
al cliente non si dice mai da dove arriva un prodotto (né CJ né "Partner" in
finestra prodotto, pagina Stripe, Contabilità). Checkout con JavCash (codice via email), bonifico o carta, ordine in "I miei
Ordini", movimenti in Contabilità. Questi prodotti **non generano cashback**:
servono a spendere JavCash, come gli Acquisti Jav. In più: variante,
quantità (1–10), indirizzo di consegna (precompilato dal profilo, telefono
obbligatorio per il corriere), stato della spedizione e tracking.

**Nessun importo arriva dal browser.** Prezzo della variante e spedizione si
ricalcolano sul server alla creazione dell'ordine; la spedizione è il
preventivo reale di CJ per quella variante, quantità e destinazione (l'opzione
più economica), con cache di 30 minuti. Conta `totalPostageFee`, ciò che CJ
addebita davvero (sdoganamento incluso), non il prezzo base `logisticPrice`
(Session 63). Il costo CJ di un ordine comprende anche l'IVA di importazione
IOSS (~22% del prodotto): stimata per i margini finché CJ non restituisce
l'importo reale.

**Prezzo di vendita.** `costo CJ (USD) × cambio × (1 + ricarico%) + ricarico
fisso`, poi arrotondato **sempre per eccesso** a ,90 / ,99 o al centesimo: un
arrotondamento non può mai abbassare il margine. Ricarico generale predefinito 100% (costo 10 → prezzo 20 prima di cambio e
arrotondamento, Session 61). Ricarico per singolo prodotto
opzionale, già sceglibile nella finestra di importazione (se uguale al
generale non viene salvato e il prodotto segue le Impostazioni); prezzo fisso per variante opzionale (non segue più il costo).
Spedizione: la paga il cliente al costo reale (predefinito) oppure è inclusa
nel prezzo (stima della spedizione più economica sommata al prezzo, e al
checkout spedizione 0). Ogni cambio delle regole ricalcola subito tutti i
prezzi; il costo e il cambio usati restano congelati sull'ordine, così il
margine di un ordine passato non cambia.

**JavCash usabili.** Percentuale per prodotto (predefinita 100%, impostabile),
calcolata sul totale compresa la spedizione.

**Stati.** `status` è il pagamento del cliente (come ogni ordine);
`fulfillment_status` è il pacco: NOT_SENT → SENDING → SENT (su CJ, non pagato)
→ PROCESSING (pagato su CJ) → SHIPPED → DELIVERED, oppure ERROR (invio
rifiutato) / CJ_CANCELLED. Un ordine si invia a CJ **solo se pagato dal
cliente**. Si annulla (con restituzione dei JavCash) solo finché non è pagato.

**Pagamento a CJ senza saldo precaricato (Session 63) {#partner-shop-payment}.**
Tre fatti distinti per ogni ordine: pagamento del cliente (`status`), ordine su
CJ (`fulfillment_status`), pagamento a CJ (`cj_payment_status`). Flusso
ibrido, automatico di default:

1. Il cliente paga (bonifico confermato, Stripe, o tutto in JavCash).
2. L'ordine si crea su CJ **una sola volta** con `payType=1`: CJ lo conferma e
   restituisce la sua pagina di pagamento (`cjPayUrl`).
3. Si legge lo stato su CJ: se risulta già pagato (sandbox, oppure pagato a
   mano sulla pagina CJ) si registra e basta.
4. Altrimenti si legge il saldo CJ: se copre il costo reale dell'ordine si paga
   dal saldo; se no l'ordine resta **Pagamento CJ richiesto**. Non è un errore:
   nessun messaggio al cliente, una notifica allo staff ("CJ richiede $X; saldo
   $Y, mancano $Z").
5. Lo sblocchi pagando dalla pagina CJ dell'ordine ("Apri pagamento CJ") o
   ricaricando il saldo: il controllo ogni 10 minuti (o "Verifica pagamento
   CJ") vede il pagamento, oppure paga dal saldo appena basta, dal più vecchio,
   senza mai spendere due volte la stessa ricarica.

Il cliente vede **Ordine ricevuto** finché CJ non è pagato, poi **In
preparazione**, **Spedito** (con tracking solo quando esiste), **Consegnato**.
Mai ricariche automatiche. Riepilogo di cassa in admin: ordini da pagare a CJ,
totale necessario, saldo, differenza.

**Mai due ordini, mai due pagamenti.** Presa in carico con UPDATE
condizionale. Prima di creare si chiede a CJ il nostro numero `JAV-<id>`: si
crea solo se CJ risponde "order not found"; timeout o CJ occupato fermano e si
riprova dopo. Prima di pagare si rilegge lo stato su CJ.

**Errori.** Classificati: temporanei e di accesso si riprovano da soli (attesa
crescente, massimo 6 tentativi); dati rifiutati e casi non riconosciuti
chiedono un controllo dello staff (notifica); saldo insufficiente è uno stato,
non un errore.

**Invio a CJ.** A mano ("Invia a CJ") o automatico dopo il pagamento
(impostazione). L'ordine viene creato su CJ con numero `JAV-<id>` e pagato dal
**saldo CJ** dell'azienda. Una sola presa in carico per ordine (UPDATE
condizionale): clic e invio automatico non creano mai due ordini. Se CJ rifiuta,
l'errore resta sull'ordine e lo staff riceve una notifica; se l'ordine è
creato ma il saldo non basta, resta "Su CJ, da pagare" e il tentativo
successivo paga soltanto. Un invio interrotto a metà si riprende dopo 10 minuti
cercando prima su CJ il numero `JAV-<id>`. Merce extra-UE verso l'UE: IOSS di
CJ (`iossType=3`, vedi open-questions #17).

**Sandbox.** Con sandbox accesa gli ordini sono di prova su CJ (nessuna
spedizione, nessun addebito): il cliente però paga davvero. Lo shop si tiene
spento finché la prova non è conclusa.

**Stock e magazzino.** Lo stock di ogni variante si legge da
`getInventoryByPid` (il dettaglio prodotto spesso non lo contiene). Un prodotto
parte da un solo magazzino: quello dove sono disponibili più varianti, a parità
il più vicino (Italia, resto d'Europa, USA, Cina).

**Aggiornamenti da CJ.** Ogni 30 minuti stato, tracking e consegna degli
ordini in viaggio; al passaggio a "Spedito" e "Consegnato" il cliente riceve
notifica ed email (con link di tracciamento). Ogni notte alle 03:30 costo,
stock e disponibilità dei prodotti; una variante non più offerta da CJ resta
nel database (gli ordini la citano) ma non è più vendibile.

**Chiave API.** Salvata solo nel database, mai restituita dalle API (solo le
ultime 4 cifre), mai nel repository. Cambiarla cancella i token salvati.
Permessi: catalogo e impostazioni `imported_products.manage`, ordini
`wallet.manage` (come gli altri negozi).

## Categorie degli shop (Session 73) {#shop-categories}

Ogni shop ha le **sue** categorie: il nostro catalogo (una serie per
sezione: `internal`, `partner`, `dropshipping`) e i tre Marketplace
(`aliexpress`, `cj`, `shopify`). "Casa" di CJ e "Casa" di Shopify sono due
righe diverse, perché i cataloghi sono separati e un prodotto non passa mai
da uno shop all'altro. I prodotti fatti a mano del vecchio plugin
(`imported_products`) si categorizzano insieme a quelli AliExpress: il
cliente li vede nella stessa scheda.

Dominio a sé (`domains/shop_categories`, migrazione 0053), pensato per
essere rimosso senza toccare niente: **nessuna colonna aggiunta alle cinque
tabelle dei prodotti**.

- `shop_categories`: nome (unico per shop, senza distinzione fra maiuscole
  e minuscole), `position` (ordine nella barra del cliente), `active`.
- `shop_category_products`: l'appartenenza. `product_id` è un UUID **senza
  vincolo di chiave esterna**, perché punta a una riga di cinque tabelle
  diverse: è l'unico punto in cui l'isolamento dei domini si paga, ed è
  scritto nel docstring del modello.

Chi fa cosa: creare, rinominare, riordinare, nascondere ed eliminare vuole
`products.manage` (eliminare una categoria **non elimina i prodotti**);
leggere l'elenco basta essere loggati, perché al cliente servono i nomi.
Ogni lettura di prodotto (catalogo, i tre Marketplace, prodotti a mano)
porta con sé `category_ids`, caricati con **una query per pagina**, mai una
per prodotto.

Come si assegna un prodotto: spuntando le categorie **nella finestra di
importazione** (così un catalogo importato in blocco nasce già ordinato),
nel modulo di modifica del prodotto, oppure in blocco dalla card Categorie
("Assegna più prodotti a una categoria": si sceglie la categoria, si
spuntano i prodotti e si aggiungono o si tolgono — utile sui cataloghi già
importati).

Nello Shop del cliente: i negozi si scelgono con bottoni grandi, sotto
compaiono le categorie di quel negozio (solo quelle attive e con almeno un
prodotto in elenco) e una casella di ricerca su nome e descrizione. I due
filtri si sommano.

## Shop AliExpress: la Dropshipping API (Session 71) {#aliexpress-shop}

Il terzo shop collegato davvero a un fornitore, dopo CJ (Session 60) e
Shopify (Session 68). Stesso schema dei due precedenti — dominio isolato
(`aliexpress_dropshipping`: `aliexpress_settings`, `aliexpress_products`,
`aliexpress_variants`, `aliexpress_orders`), stessa esperienza per il
cliente, stesse regole comuni dei Marketplace (sconto bonifico, JavCash
parziale, niente cashback).

**L'app e l'autorizzazione.** L'app si crea su openservice.aliexpress.com,
categoria *Drop Shipping*; dà **App Key** e **App Secret**, e va autorizzata
sull'account venditore (il giro OAuth descritto in
[#marketplace-credentials](#marketplace-credentials)). Il token ha una
scadenza: `client.py` lo rinnova con il `refresh_token` dieci minuti prima
e dopo un rifiuto del gateway. Il permesso **DS va concesso all'app a
parte**: senza, le chiamate al catalogo rispondono "no permission" anche con
l'app approvata.

**La firma.** Gateway "iop" di Alibaba: parametri ordinati per nome,
concatenati nome+valore, HMAC-SHA256 con l'App Secret, esadecimale
maiuscolo. Le chiamate di sistema (`/auth/token/create`, `/auth/token/refresh`)
vanno su `/rest<path>` e includono il path nella firma; le chiamate DS
(`aliexpress.ds.*`) vanno su `/sync` con il parametro `method`, senza path
nella firma e con il token nel parametro `session`.

**Prezzo di vendita.** Come Shopify: `costo × cambio × (1 + ricarico%) +
ricarico fisso`, arrotondato **sempre per eccesso** a ,90 / ,99 o al
centesimo; ricarico predefinito 100%, override per prodotto; spedizione
pagata dal cliente (importo fisso) o inclusa. Costo e cambio restano
congelati sull'ordine. Le impostazioni hanno in più `ship_to_country` (IT),
`target_currency` (EUR) e `target_language` (it): sono i parametri con cui
si interroga il catalogo, quindi decidono i prezzi che AliExpress ci mostra.

**L'ordine al fornitore.** Quando il cliente ha pagato, l'ordine viene
creato su AliExpress con `aliexpress.ds.order.create` (indirizzo di
consegna, `sku_attr` della variante, il nostro riferimento `out_order_id`);
il tracking arriva con `aliexpress.ds.order.tracking.get` e porta l'ordine
a `SHIPPED` e poi `DELIVERED`, avvisando il cliente. Attenzione: `SENT`
significa "creato presso il fornitore", **non pagato**: il pagamento ad
AliExpress resta un passaggio manuale nell'account AliExpress.

**Una divergenza voluta rispetto a Shopify.** A Shopify si poteva chiedere
"hai già un ordine con il mio tag?", quindi una risposta persa si
riprovava da sola. La DS API non offre quella domanda: se `ds.order.create`
fallisce *dopo* che la richiesta è partita, o risponde senza numero
d'ordine, l'ordine va in `ERROR` **senza alcun riprovo automatico** e lo
staff riceve un avviso con l'`out_order_id` da cercare su AliExpress.
Decide una persona: spedire due colli è peggio che aspettare. I fallimenti
*prima* dell'invio mantengono il riprovo automatico con backoff.

**Da verificare dal vivo** (l'account non era ancora autorizzato quando il
dominio è stato scritto; ogni punto è marcato nel codice con un commento
`Da verificare dal vivo:`): l'involucro della richiesta di
`ds.order.create` e se `out_order_id` renda l'ordine idempotente; i nomi
dei prezzi SKU in `ds.product.get` (`offer_sale_price` vs `sku_price` —
sbagliarli alzerebbe tutti i prezzi); i parametri e l'annidamento di
`ds.text.search`; `ds.freight.query`; la forma della risposta di
`ds.order.tracking.get`; come si riconosce un ordine annullato dal
fornitore. Tutte le risposte sono lette in modo difensivo (più forme
accettate, errori del gateway riportati con le parole del gateway, mai un
risultato vuoto silenzioso).

## Account freeze (Session 28)

`PATCH /users/{id}/freeze` / `/unfreeze`, gated by a new, deliberately
narrow `users.manage_lifecycle` permission (**SUPER_ADMIN only** -- the
user's own explicit request, since this is more sensitive than the
ADMIN/ORGANIZATION_ADMIN tier that already manages day-to-day
customer/promoter records). Freezing sets `users.status = "FROZEN"`,
which `auth/service.py::authenticate()` now checks before even looking at
the password (reuses `AccountLockedError`/423, same as the existing
too-many-failed-attempts lock, just with a different message) -- AND
revokes every one of that user's existing sessions immediately
(`revoke_all_sessions`), so an already-logged-in frozen account is kicked
out right away, not just blocked on its next fresh login. Deliberately
does **not** touch any other data -- contracts, orders, wallet history,
network position all stay exactly as they were; unfreezing is a full,
lossless undo. An admin cannot freeze their own account.

### A frozen member disappears from the network (Session 37)

Freezing used to have **zero** effect on the network tree: the person kept
showing up in their upline's "Rete Commerciale" looking completely normal,
which is not what an admin freezing an account expects. Now
(`network/service.py::get_branch`, `include_frozen`):

- **Promoters/team leaders no longer see a frozen member at all** -- and
  neither does anyone below them: the frozen person's **entire subtree**
  is pruned with them. Explicit business choice ("nascondi lui e tutto il
  suo ramo"): leaving the downline behind would orphan rows the UI builds
  its tree from (`parent_agent_id`) and misrepresent depth, which is what
  the 12-level commission structure is counted on.
- **Only the admin tier still sees them** (`_FROZEN_VISIBLE_ROLES` in
  `network/router.py`: SUPER_ADMIN / ORGANIZATION_ADMIN / ADMIN), flagged
  `is_frozen` and rendered as a red **CONGELATO** badge. Deliberately
  narrower than `_BRANCH_ACCESS_BYPASS_ROLES`, which also contains
  SALES_MANAGER: seeing *every* branch and seeing *frozen people* are two
  different privileges, and only the admin tier gets the second.
- `get_branch_summary` passes the same flag through, so a hidden member
  never silently inflates an upline's headcount or contract/commission
  totals.
- **Careful:** `BranchMemberRead.is_frozen` is the OWNER'S ACCOUNT status
  (`users.status`), not `status`, which remains the AgentProfile's own
  lifecycle (ACTIVE/SUSPENDED/TERMINATED/...). The two are independent and
  easy to confuse -- freezing has never touched the agent record, and
  still doesn't.
- Commissions are untouched: this is a **visibility** rule only. Frozen or
  not, past commissions stay frozen in their contract's network snapshot,
  and the person's real tree position is unchanged (unfreezing restores
  the previous view exactly).

**"Elimina utente" (hard delete/anonymize) was explicitly deferred by the
user** after being shown the tradeoff: a true cascading delete of
contracts/orders/wallet transactions risks breaking other promoters'
commission history (their network position and commission chain reference
this user) and conflicts with Italian fiscal record-retention requirements
for contracts/invoices. Freeze-only ships for now; a real delete/anonymize
flow is future work, to be designed once the user decides how to reconcile
those two constraints (most likely: anonymize personal data while
preserving the underlying ledger rows, not a literal `DELETE`).

## GDPR notes

Consent versions, retention periods, and the legal basis for each processing purpose
are **not** implemented as final policy in this phase — schema hooks exist
(`documents.expires_at`, audit of all document access) but retention windows and the
lawful basis registry require legal sign-off before being treated as authoritative.
See `open-questions.md #5`.
