# Business Rules

Status: no source document (`Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf`)
was present in the repository at the time this was written. Every numeric threshold,
percentage and formula below is a **placeholder** used to make the system runnable and
testable. None of it should be treated as the real commercial policy of the club
until confirmed. Every placeholder is also listed in `open-questions.md` with the exact
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

### Rank promotion progress (PLACEHOLDER)

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

### Automatic monthly rank evaluation (PLACEHOLDER)

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

### Promoter disattivato: il contratto risale allo sponsor attivo {#terminated-promoter-fallback}

A customer's referring promoter can be deactivated (`agent_profiles.status =
TERMINATED`) months after that customer signed up. `create_contract()` refuses
to attribute a contract to a non-ACTIVE agent — correctly: a contract that
activates and pays nobody is a silent loss for the network. The result was a customer who could not
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

## Pagamento del contratto: unica, 3 rate, 12 rate {#contract-payment}

**Contracts only.** The Shop's own checkout (orders) is a separate flow: an
order is a purchase, a contract is a subscription to a service. Club fees
are a third, separate flow (`club-portal.md`).

**Il pagamento è sempre un bonifico.** Il cliente sceglie il piano e annuncia
il bonifico (`POST /contract-requests/{id}/bank-transfer`, corpo facoltativo
`{"payment_plan": "FULL" | "INSTALMENTS_3" | "MONTHLY_12"}`, default `FULL`);
può caricare la ricevuta. Il **primo bonifico** vale l'intero importo (FULL)
oppure la prima rata di ogni contratto. Un amministratore lo conferma
(`POST /contract-requests/{id}/bank-transfer/confirm`, oppure
`contracts/service.py::record_transfer_payment` per un contratto singolo); ogni
rata successiva si conferma **una per una**
(`POST /contracts/{id}/instalments/{number}/confirm`). Nessun piano ha uno
sconto: un bonifico costa quanto il prezzo del contratto.

### Quando si può pagare {#contract-prepayment}

Subito, senza aspettare i documenti: il cliente può pagare appena il
contratto esiste. `contracts/service.py::PREPAYABLE_STATUSES` = `SUBMITTED`,
`DOCUMENTS_PENDING`, `UNDER_REVIEW`, `APPROVED`, `PAYMENT_PENDING`;
`is_payable()` also requires a frozen amount and `paid_at IS NULL`.

**Paying is not activating.** *Le provvigioni partono solo all'approvazione*:

- Payment confirmed while the documents are not yet approved → `paid_at` is
  set, the JavCash is credited, staff are notified
  (`CONTRACT_PAID_BEFORE_APPROVAL`, audit `contract.paid_before_approval`) —
  and **the status does not move**.
- Administrator approves → `APPROVED → PAYMENT_PENDING` as always, and
  `transition_contract` sees `paid_at` already set and continues straight to
  `PAID → ACTIVATION_PENDING → ACTIVE`. That is the only point commissions
  and the network snapshot are produced.
- Payment confirmed when the documents are already approved
  (`PAYMENT_PENDING`) → `PAID` → `ACTIVE` immediately.
- **Rejecting a paid contract** notifies staff (`CONTRACT_PAID_REJECTED`):
  refund and the credited JavCash are human decisions, never automatic. A
  payment confirmed on a contract already rejected is still recorded (the
  money moved), earns no JavCash, and raises the same notification.

### Le tre modalità

| Piano | Come funziona |
|---|---|
| **Soluzione unica** (`FULL`) | Un bonifico per l'intero importo. |
| **3 rate mensili** (`INSTALMENTS_3`) | Primo bonifico = prima rata; le altre due le conferma l'amministrazione quando arrivano. |
| **12 rate mensili** (`MONTHLY_12`) | Identico, con 12 rate. |

3 and 12 rate are **the same mechanism** and differ only in the count. The
instalment schedule (`contract_instalments`) is created when the first
payment is confirmed; each row is `SCHEDULED` until an administrator confirms
it, then `PAID` with `payment_source = ADMIN` and `confirmed_by_user_id`.

### Gli arrotondamenti, detti e non nascosti

A price rarely divides evenly by 3 or 12. The instalment is rounded to the
cent and the plan's real total (`instalment × N`) is **shown next to each
option**, with the difference from the contract spelled out when there is
one — at most 6 cents for 12 instalments.

### Prezzo del contratto: unica soluzione e prezzo mensile {#contract-price-periods}

**Only for recurring product types** (`pricing.RECURRING_PRODUCT_TYPES` =
`SERVICE`, `SUBSCRIPTION`). A `PHYSICAL` or `DIGITAL` product always costs
its listed price once, whatever `billing_period` / duration its version
carries, and never has a rate price.

Paying in rate may cost more than paying at once, so a package can have
**two prices**, both net of VAT:

- `base_price_cents` = the whole term **in unica soluzione**
  (`pricing.contract_net_amount_cents`);
- `monthly_price_cents` = the **rata mensile**; paid in rate the contract costs
  `monthly × contract_duration_months` (`pricing.contract_instalments_net_amount_cents`).
  **12 rate and 3 rate split the same total.**

With no monthly price the rate split the one-go price. VAT (business
customers only) is added to each total. The contract freezes both at
creation: `net/vat/gross_amount_cents` (one go) and
`instalments_net/vat/gross_amount_cents` (rate). Every plan-dependent amount
(options, instalment schedule, cashback, commission preview, accounting,
dossier) reads `payment_plans.plan_gross_cents` / `chosen_amounts`, never
`gross_amount_cents` directly.

Rank volumes stay on the **monthly** figure (`rank_progress._volume_cents`) —
every rank threshold is calibrated on it.

### Cashback JavCash sul contratto: quando arriva {#contract-cashback-timing}

`product_versions.contract_cashback_percentage` of what the customer pays
(VAT included), **0 by default** (`open-questions.md` #9). It is credited
**when the money arrives**, not at activation:

- **Soluzione unica**: the whole amount at once, key
  `contract-cashback:{contract_id}`, guard `contracts.cashback_credited_at`.
- **3 / 12 rate**: by default **one instalment at a time** (a customer who
  stops paying after month one must not already hold the year in JavCash),
  key `contract-cashback:{contract_id}:rata-{n}` — the same month confirmed
  twice is still one month. The amount is the plan's instalment, never what
  the transfer said. See also `#instalment-cashback` for the "intero in
  anticipo" setting.

## Anteprima provvigioni e provvigioni per rata {#commission-preview}

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
- A contract paid before its preview was accepted does **not** activate on
  its own: the payment is recorded and it waits for an administrator to
  accept the preview.

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
- Who confirms a payment: an administrator, always. Instalment 1 with the
  first bank transfer; later ones one by one
  (`POST /contracts/{id}/instalments/{n}/confirm`, audit
  `contract.instalment_confirmed_manually`). `UNIQUE (contract_id, number)`
  makes a double release impossible.

## Cashback dei contratti pagati a rate: intero in anticipo o rata per rata {#instalment-cashback}

Il cashback JavCash di un contratto (percentuale del prodotto sul
totale IVA inclusa) arriva **tutto subito** se il contratto è
pagato in unica soluzione. Per 3 o 12 rate lo decide l'amministratore in
**Impostazioni → Cashback dei contratti pagati a rate**
(`organizations.settings.contract_instalment_cashback_mode`):

- `PER_INSTALMENT` — **predefinito**: una parte a ogni rata confermata
  dall'amministrazione, così chi smette di pagare
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
  (`contract-cashback:<contratto>:rata-<n>`): la stessa rata confermata due
  volte dà cashback una volta sola.
- Nessun cashback su un contratto respinto o cessato.
- La schermata di pagamento del cliente dice come arriverà il cashback, secondo
  l'impostazione.

## La pratica {#contract-request}

**Regola:** un cliente che sottoscrive 3 servizi firma **3 contratti** — 3
per il cliente, 3 per il promoter, ognuno con il suo pacchetto, la sua
approvazione, le sue rate e le sue provvigioni — ma compila i propri dati una
volta, carica il documento d'identità una volta e **paga con un bonifico
solo**.

La pratica (`contract_requests`) è il contenitore che rende possibile tutto
questo. **Non possiede niente che possieda già un contratto**: stato,
pacchetto, prezzo congelato, approvazione, rate, provvigioni restano sul
singolo contratto. Un contratto respinto, sospeso o cessato dentro una pratica
non tocca gli altri.

**Ogni contratto appartiene a una pratica** (`contracts.contract_request_id`,
NOT NULL). Un contratto creato fuori dal flusso (admin "Nuovo Contratto", le
rotte `/contracts/mine` e `/contracts/for-customer`) riceve una pratica di un
solo contratto.

Nel codice e nelle rotte i contratti della pratica si chiamano ancora
`points` (`/contract-requests/{id}/points/...`, `points_count`): vuol dire
"contratto della pratica", nient'altro.

**Sblocca pratica.** Una pratica inviata ma non pagata (nessun contratto o
rata pagati, nessuna ricevuta di bonifico) può essere riportata in
compilazione dall'amministrazione, per cambiare i pacchetti scelti. Tutti i
contratti vivi tornano bozza; le approvazioni si perdono e la pratica,
reinviata, si rivede da capo; il bonifico solo annunciato si annulla.

**Chi firma e il suo codice fiscale.** Nei dati della pratica chi firma --
l'intestatario privato o, per un'azienda, il legale rappresentante -- dà
codice fiscale, data e luogo di nascita (un comune, anche soppresso, o uno
Stato estero, scelto dall'elenco). Il codice fiscale si controlla con
cognome, nome, data e luogo, e si controlla anche il carattere di controllo.
L'omocodia è accettata. **Il controllo non blocca**: se il codice non torna i
dati si salvano lo stesso, il form avvisa («Continua comunque») e la scheda
pratica mostra «Codice fiscale da verificare». Bloccano solo il codice
mancante o non di 16 caratteri, data e luogo mancanti e chi firma minorenne.

### Il percorso

1. **Dati**, in un'unica schermata: intestatario (nome, cognome, email, PEC,
   IBAN), indirizzo dell'intestatario e **quanti contratti** (1–50). La
   pratica nasce `DRAFT` con quel numero di contratti `DRAFT` senza
   pacchetto; in bozza se ne aggiungono o tolgono (un contratto tolto va in
   `CANCELLED`, transizione `DRAFT → CANCELLED`).
   - Il produttore delle provvigioni si risolve **per contratto** (promoter
     che compila, o referente del cliente con risalita al primo sponsor
     attivo, auditata).
2. **Documenti** sulla pratica: identità, codice fiscale, visura (per chi ha
   partita IVA).
3. **Un pacchetto per ogni contratto**, oppure "Stesso pacchetto per tutti".
   **Il prezzo si congela sul contratto in quel momento**
   (`contracts/service.py::freeze_price`). Un vincolo CHECK
   (`ck_contracts_product_required`) impedisce a un contratto senza pacchetto
   di uscire da `DRAFT`.
4. **Invio** (`submit`): tutti i contratti passano insieme `DRAFT → SUBMITTED →
   DOCUMENTS_PENDING`, e ciascuno va da solo in `UNDER_REVIEW` appena i
   **suoi** documenti obbligatori ci sono. Lo staff riceve **una** notifica
   per pratica. Dopo l'invio i contratti scelti non si modificano più: un
   altro contratto è una nuova pratica.
5. **Pagamento**, solo dal cliente (il promoter compila e invia, non paga).

### Documenti: pratica o contratto

Un documento appartiene **a un contratto oppure a una pratica, mai a
entrambi** (`ck_documents_one_owner`). Per ogni casella di un contratto vale
il documento **del contratto se c'è, altrimenti quello della pratica**.
Caricare un documento sulla pratica rivaluta tutti i suoi contratti
(`maybe_advance_to_under_review`). Il fascicolo (zip) di ogni contratto
include anche i documenti della pratica.

### Un pagamento, N contratti

Paga **ogni contratto della pratica inviato, prezzato e non ancora pagato**
(`is_payable`), con **un solo piano** (unica soluzione, 3 o 12 rate) e **un
solo bonifico**: l'importo del primo bonifico è la somma, per ogni contratto,
dell'intero prezzo o della sua prima rata (`bank_transfer_total_cents` nelle
`payment-options`). Ogni contratto registra la sua rata e il suo cashback; il
cliente vede la somma. La conferma dell'amministratore sulla pratica conferma
tutti i suoi contratti insieme, con una notifica sola.

### Il catalogo è una vetrina; il promoter compila per il cliente

- **Si attiva solo con la pratica.** In "I miei Contratti" e in Home i pacchetti
  Jav hanno il pulsante **Dettagli**, non più "Attiva Contratto": si
  leggono, e il popup porta a "Attiva nuovo contratto", cioè la stessa pratica
  del pulsante in alto (con quel pacchetto già scelto per ogni contratto).
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
- **Staff** (`contracts.review`): vede tutte le pratiche e i bonifici
  annunciati. Approvare e respingere restano **per contratto**, con la stessa
  anteprima provvigioni obbligatoria; "Approva i N contratti in revisione"
  manda N transizioni, ciascuna con il checksum della sua anteprima.

Un utente può essere cliente e promoter insieme: si controllano entrambe le
relazioni, non il primo ruolo del token.

### Correggere il pacchetto di un contratto {#staff-repackage}

Il cliente sceglie il pacchetto contratto per contratto, e può sbagliarlo o
non sceglierlo affatto. Lo **staff** può scegliere o cambiare il pacchetto di
un singolo contratto dal dettaglio della pratica (bottone "Scegli pacchetto" /
"Cambia pacchetto", `requests.py::staff_set_point_product`, stessa rotta
`PUT /contract-requests/{id}/points/{contract_id}/product` che usa il
cliente: è l'accesso a decidere quale delle due regole si applica).

Il confine è il denaro, non lo stato della pratica: si cambia finché quel
contratto è in `DRAFT`, `SUBMITTED`, `DOCUMENTS_PENDING`, `UNDER_REVIEW`,
`APPROVED` o `PAYMENT_PENDING` **e** non è pagato (`paid_at`) e non è attivo.
Il prezzo viene ricongelato subito; il cambio finisce nell'audit log
(`contract.package_changed_by_staff`) con pacchetto e importo di prima e di
dopo.

## Contract economics: IVA, tipo cliente, cashback, bonus {#contract-economics}

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
(PMI, ...) did not line up with `customers.kind` (COMPANY,
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

The contract credit is a percentage of the **gross** (VAT included), i.e. of
what the customer actually handed over -- never a pre-discount or otherwise
inflated base. Exactly-once is enforced twice: `contracts.cashback_credited_at`
as the readable guard, and the deterministic wallet idempotency key
`contract-cashback:{contract_id}` against the UNIQUE constraint on
`wallet_transactions` for the case the guard is raced (two administrators
confirming at once). `source = "CONTRACT_CASHBACK"`, distinct from
`ORDER_CASHBACK_BASE` precisely so accounting can tell them apart.

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
product_versions.contract_duration_months` (12 by default for a yearly service;
`NULL` for a one-off `DIGITAL`/`PHYSICAL` product with no renewal concept). Every
renewal restarts both fields from the renewal's own timestamp — `expires_at` is never
retroactively recomputed if the product version's duration later changes, matching the
"frozen at the moment it happens" pattern used for network snapshots and commission
calculations elsewhere in this document.

**Who can move a contract through this pipeline**: `PATCH /contracts/{id}/status` (manual, per-hop transitions)
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

### Self-service contract activation ("Attiva Contratto") {#contract-self-service}

Per explicit request, a customer can now activate a Jav (`category
= INTERNAL`) product without any promoter/admin action to get it started:

- **`POST /contracts/mine`** (`contracts/router.py::create_my_contract`,
  no special permission -- `get_current_user` only, same "self-checkout,
  own account only" shape as `POST /orders/mine`): takes a
  `product_version_id` collected by `contract-activation-wizard.tsx`.
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
  4. Creates the `Contract` (`DRAFT`) and immediately transitions it
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

## Condivisione dei link: bottoni per app, non solo copia {#share-buttons}

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

## "Invita un amico": rete a un livello, staccata, senza provvigioni {#friend-referrals}

A **second, completely separate** referral structure, added on explicit
request: "non c'entra nulla con l'attuale rete, è una cosa staccata e separata
che ogni cliente ha".

- **Naming**: the feature is **"Invita un
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

## "Lavora con noi": quali documenti si firmano {#collaboration-documents}

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

### New promoter suggest-then-approve workflow

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
algorithm including the 33% cap.

## Commission payment tracking

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

### Richiesta di chiusura account

- Dalle Impostazioni del cliente, «Richiedi chiusura account» apre un ticket
  di categoria `CHIUSURA_ACCOUNT` (`POST /support/tickets/account-closure`,
  `support/service.py::request_account_closure`): stesso avviso allo staff e
  stessa email all'indirizzo delle notifiche di ogni ticket, più una conferma
  al cliente. **Non cancella niente**: la chiusura la fa lo staff a mano,
  dopo aver controllato contratti, ordini e JavCash aperti.
- Una sola richiesta aperta (OPEN o IN_PROGRESS) per utente: la seconda
  risponde 409. La categoria non compare nel modulo «Nuovo ticket».

### Search, filter, and deletion

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

## Notifications

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
- Every image is stored **optimized** (`core/storage.py::optimize_image`, Pillow):
  turned upright from its EXIF orientation, shrunk to 1600 px on the long side
  (800 for profile photos: athletes, customers, promoters, club coaches --
  `AVATAR_MAX_SIDE`), all metadata stripped (no GPS from a phone photo),
  re-encoded as progressive JPEG q85, or PNG when it has transparency (a logo).
  A GIF is kept as it is. A file that doesn't decode as an image is refused,
  even with the right magic bytes.
- Profile photos (the round ones) are **cropped in the browser first**
  (`components/ui/image-cropper.tsx`): drag, zoom (slider, wheel, two fingers),
  a live preview in the circle at three sizes; the square crop goes up as a
  JPEG of at most 800 px, never upscaled.
- If no photo has been uploaded, `photo_url` is `NULL` and every list/detail view
  shows a generic person icon -- never a broken `<img>` tag.

## Contract documents

- Every contract requires `IDENTITY`, `FISCAL_CODE`, and `UTILITY_BILL`
  (`documents/service.py::BASE_REQUIRED_DOCUMENT_TYPES`); a customer of kind
  `COMPANY` or `CONDOMINIUM` additionally requires `CHAMBER_OF_COMMERCE`
  (`COMPANY_LIKE_KINDS`). This is a hardcoded, honest default in the service
  layer, not read from the pre-existing `product_versions.required_documents`
  jsonb column -- that column has never actually been populated or wired to
  any behavior, so treating it as configurable today would be pretending.
- A `SOLE_PROPRIETOR` (ditta individuale / partita IVA) is **offered** the
  `CHAMBER_OF_COMMERCE` slot but is never blocked by it
  (`CHAMBER_OF_COMMERCE_OPTIONAL_KINDS`). They are a
  business for VAT (`catalog/pricing.py`), but a professionista with a
  partita IVA is not in the Registro Imprese and has no visura to give:
  demanding one would strand exactly the customers who cannot produce it,
  while hiding the slot would leave the ones who can with nowhere to put it.
  The slot carries `required: false`, and the auto-advance to `UNDER_REVIEW`
  gates only on the required ones.
- Beyond the fixed slots, anyone who can upload to a contract can attach
  **extra documents** of type `OTHER`, each carrying a
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

## Il fascicolo di un contratto {#contract-dossier}

Un contratto non vive solo qui dentro: prima o poi la pratica va mandata a
un commercialista o a un legale, e aprire gli allegati uno per uno dai link
a scadenza non è un modo di lavorare.

- **Il contenuto lo costruisce un solo modulo**, `contracts/dossier.py`:
  tutti gli allegati del contratto più un PDF riassuntivo di contratto e
  cliente, scaricati come zip dal browser
  (`GET /contracts/{id}/dossier.zip`).
- **Nome**: `<nome cliente>-<id contratto>`. Il nome cliente è quello mostrato ovunque nel gestionale
  (`customers/service.py::display_name_for`), l'id è l'UUID intero. Gli
  accenti restano; spariscono solo i caratteri che romperebbero un percorso
  (`/ \ : * ? " < > |`, i controlli), i punti e gli spazi finali (Windows li
  taglierebbe comunque, e un nome tagliato da altri non è più quello scritto
  nel database) e i nomi riservati DOS.
- **Il PDF contiene tutto** quello che serve a chi legge la pratica senza
  avere accesso al gestionale: intestatario, tipologia, codice fiscale e
  P.IVA, dati societari, recapiti, indirizzi, prodotto, importi netto/IVA/lordo, modalità e stato del
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
  documenti li verificano uno per uno. Ogni download finisce nell'audit log
  (`contract.dossier_downloaded`).

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
- **Branded HTML email**: this was the one email in the
  whole platform still sent as plain text via a separate, since-removed
  `core/email.py::send_email()` helper -- every other email (OTP codes,
  cashback credited, order notifications, ...) already used the
  shared branded template (`core/email_templates.py::render_email`, logo +
  consistent styling + a CTA button). Password reset now uses the exact
  same `send_html_email`/`render_email` path as everything else, so it is
  never the odd one out.
- `POST /auth/reset-password` (token + new password) revokes every active session
  for that user on success -- a password reset is exactly the moment to assume the
  old password may have leaked, so anyone still logged in with it is logged out.
  It also clears `failed_login_attempts`/`locked_until`, so completing a reset is
  the normal way out of a lockout, and marks the account email-verified if it
  wasn't already (see `#account-gates`: clicking an emailed link is
  the same proof of inbox control the dedicated verification link gives).
- Both endpoints are rate-limited per client IP (`core/rate_limit.py`, Redis
  fixed-window counter) -- 5 requests/5min for `forgot-password`, 10/5min for
  `reset-password` -- independent of the per-account lockout in `authenticate()`.

## Internal wallet

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
- **Omaggio di benvenuto**: every account can claim a one-off
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
  ) -- best-effort, fires after the credit is already
  committed. The one exception: a credit tied to an order
  (`reference_order_id` set) is skipped here on purpose, since the order's
  own "pagamento completato" email already mentions the cashback.
- **Admin visibility**: `GET /wallets/admin` lists every wallet's balance
  org-wide; `GET /wallets/admin/{user_id}` and
  `GET /wallets/admin/{user_id}/transactions` show one user's wallet and
  history (does **not** lazily create a wallet just by viewing -- an admin
  looking at a user who never transacted sees "no wallet yet");
  `GET /wallets/admin/transactions` is the global ledger, filterable by
  type/user, with CSV export in the dashboard.
- **Peer-to-peer transfer is denied by default** (`Wallet.can_transfer`) for every wallet, customer or promoter -- an admin must
  enable it individually per promoter (`PATCH
  /wallets/admin/{user_id}/transfer-permission`, `wallet.manage`-gated).
  Deliberately per-wallet, not a role grant: opening it for "all promoters"
  would be wrong the first time only some of them should have it, which is
  exactly today's situation.

## Product cashback -- "riscuoti subito cashback"

A separate way wallet credit enters the system (alongside the plain admin
top-up and the contract cashback), earned directly from a catalog purchase:

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
- **Payout**: once the order reaches `PAID` -- an admin confirming the bank
  transfer -- the whole extra payment (the residual actually paid + the 5%
  surcharge) is credited back to the customer's wallet as JavCash, as two
  separate transaction rows (`ORDER_CASHBACK_BASE`/`ORDER_CASHBACK_BONUS`).
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
- **Sblocco dell'account**: solo il superadmin può segnare
  come fatti per un cliente i controlli d'ingresso (email, privacy,
  profilo). Email e privacy si segnano; codice fiscale e residenza vanno
  scritti (mai inventati), e lo sblocco senza profilo completo si rifiuta.
  Ogni sblocco è nell'audit (`user.account_unlocked`) con chi l'ha fatto: la
  privacy così «accettata» è raccolta dal superadmin, non un clic del
  cliente.
- **PIN dei JavCash al posto dell'email**: dalle sue
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

## "JavCash" -- wallet balance/transaction labeling

Purely a dashboard label, not a new concept: every wallet balance and
transaction amount (top-ups, cashback credits, peer transfers,
purchase debits) is displayed with a "JavCash" suffix instead of a euro
sign, to keep it visually unmistakable from *real* money. Real-money
amounts -- what a customer actually paid by bank transfer on an order, a
contract or a club fee -- are always shown in genuine EUR. No schema or currency-field change; `wallets.currency`
is still `"EUR"` in the database, this is presentation-only.

## Accounting / "Contabilità"

A new customer-facing dashboard section (`GET /accounting/mine`, no
permission beyond authentication -- same pattern as `GET /wallets/me`)
merges a user's own `wallet_transactions` (JavCash movements) and their
own paid orders' and contracts' real-money payments (EUR, bank transfer) into one
chronological, filterable feed with running totals per category and a CSV
export. Computed on the fly from the two existing tables (see
`database-model.md` §14) -- deliberately not a new persisted table, so
there is nothing here that can drift from the wallet ledger or the orders
table, which remain the actual source of truth for their own domains.

### Totali, pagamenti dei contratti, dettaglio collegato {#accounting-detail}

- **I pagamenti dei contratti ci sono.** Ogni rata pagata
  (`contract_instalments.status = PAID`) è un movimento `CONTRACT_PAYMENT`
  in euro, sempre bonifico confermato dall'amministrazione (`ADMIN`). Una rata = una
  riga, alla data in cui è stata incassata. Anche il cashback JavCash di un
  contratto porta ora il suo `contract_id`.
- **I totali li calcola il server** (`GET /accounting/mine/summary`,
  `accounting/service.py::my_summary`) dagli stessi movimenti dell'elenco, così
  le card e la lista non possono dire cose diverse: totale speso, speso nel
  mese corrente, per ordini / contratti, saldo JavCash (dal wallet), JavCash ricevuti e spesi, cashback
  ricevuto (fonti `*_CASHBACK_*` e `CONTRACT_CASHBACK`), contratti attivi,
  rate pagate e **prossima rata** (somma delle rate previste nello stesso
  giorno). **Provvigioni** solo se
  l'account è anche un promoter: totale maturato, da incassare (`ACCRUED`/
  `PAYABLE`/`SCHEDULED`), pagate; `REVERSED`/`CANCELLED` escluse.
- **Dettaglio** (`GET /accounting/mine/detail?ref=…`, e
  `/accounting/admin/detail` per lo staff con `wallet.manage`;
  `accounting/details.py`): `wallet:<id>`, `order:<id>`, `contract:<id>`. Stessa forma per
  tutti: dati, **cronologia con data e ora al secondo e chi ha agito**
  (creazione, ricevuta del bonifico caricata, pagamento confermato
  dall'amministratore, cashback accreditato, annullamento,
  approvazione, ogni rata incassata, prossima rata), le rate di un contratto,
  e i riferimenti collegati. Lato cliente tutto è limitato alle proprie cose:
  ciò che non è suo risulta "non trovato", mai "vietato".
- **Tutto collegato**: ogni riga apre il suo dettaglio; il chip "Ordine /
  Contratto #…" apre quella cosa, che elenca tutti i movimenti che
  ha prodotto (pagamento in euro, JavCash usati, cashback), ognuno apribile a
  sua volta.

## Account gates

Three independent, self-service gates block dashboard use until satisfied,
each with its own acceptance state persisted on `users`/`agent_profiles` and
visible to admins (Anagrafiche Clienti/Promoter, small badges next to each
account). None of these are enforced client-side only -- every corresponding
backend action independently requires the same state.

- **Privacy consent**: `users.privacy_accepted_at`, set once at
  self-registration (`RegisterRequest.accept_privacy`, a required checkbox --
  the request is rejected server-side if unticked). NULL for every account
  created by an administrator -- there is no retroactive consent to
  backfill, so it simply stays NULL for those.
- **Email verification** (new registrations only): `users.email_verified_at`
  (a column that already existed, previously unused). Registration sends a
  branded confirmation email (`core/email_templates.py`) with a link to
  `/verify-email?token=...`, backed by `email_verification_tokens` (opaque
  token, hashed at rest, 24h expiry, single-use -- same pattern as
  password-reset tokens). **Explicit product decision**: every account that
  existed before this feature shipped is grandfathered as already-verified
  (the 0026 migration backfills `email_verified_at = COALESCE(email_verified_at,
  created_at)` for every NULL row) -- nobody who was already using the
  product gets a surprise "confirm your email" wall.
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

**Notification emails** (same branded-HTML-shell mechanism):
an admin wallet top-up (`wallets/service.py::credit_wallet`) and a new
support ticket opened
(`support/service.py::create_ticket`, sent to
`Organization.settings.admin_notification_email`, defaulting to
`admin@example.com` -- `organizations/service.py::DEFAULT_ADMIN_NOTIFICATION_EMAIL`,
admin-editable via the existing company-settings PATCH). All best-effort:
an SMTP hiccup is logged, never blocks the underlying action (ticket
creation, cashback crediting, registration all already committed by the
time the email send is attempted).

## Store orders vs. contracts

Two structurally different things both live under "products", and this
distinction is load-bearing, not cosmetic:

- **`category=INTERNAL` products** are the matrix a **Contract** is created
  from (`POST /contracts`, the pratica) -- these are what a promoter earns
  commissions on, and what shows up in the network/commission engine. They
  never go through the `orders` domain at all
  (`orders/service.py::_get_sellable_product_version` explicitly rejects
  INTERNAL products with a "si acquistano come contratto" error).
- **DROPSHIPPING/PARTNER catalog products** (catalog categories, not
  external suppliers) are an e-commerce-style purchase through the `orders`
  domain (self-checkout, `POST /orders/mine`) -- no commission, no network
  effect, paid partly in wallet credit and partly by bank transfer.
- The **Shop** (`jav_market`) is a third, separate catalog with variants
  (sizes) and shipping — equipment, judogi — see `#jav-market`.

Orders show the product photo (`ProductVersion.image_url` →
`OrderRead.product_image_url`) everywhere, open a product detail before
checkout, and are listed in "I miei Ordini" with their status. The
order-confirmation email (`orders/service.py::_send_order_confirmation_email`,
best-effort, after commit) gives the IBAN and causale for the bank transfer,
or confirms that credit covered everything. `ProductVersion.
credit_discount_percentage` is clamped to 0 for `INTERNAL` products
(`catalog/service.py::_clamp_credit_discount`); `orders/service.py::
get_quote()`/`max_creditable_cents()` read that product's own value, never a
global constant.

## Chi può aprire una pratica di attivazione {#pratica-authors}

Una pratica è sempre la stessa cosa — intestatario, N contratti, un pacchetto
per contratto, documenti — e cambia solo chi la compila:

- **il cliente**, per sé (`created_by_role="CUSTOMER"`): guadagna il promoter
  che lo ha portato (o il primo sponsor attivo sopra di lui);
- **il promoter**, per un cliente suo (`PROMOTER`): guadagna lui, e il cliente
  riceve notifica ed email per pagare dalla propria area;
- **l'amministrazione** (`ADMIN`): può indicare a quale promoter
  attribuirla (validato ACTIVE); senza indicazione vale la regola del
  self-service. Il cliente riceve lo stesso avviso.

**Il pagamento è sempre del cliente**: promoter e staff non possono
annunciare il bonifico al suo posto (la pratica accetta il pagamento solo dall'intestatario);
lo staff può però confermare un bonifico ricevuto. Chi ha compilato la pratica
resta scritto sulla pratica e su ogni contratto.

## Lo Shop {#marketplace}

Un solo negozio, `jav_market` («Fai la Spesa con Jav» nell'interfaccia):
attrezzatura, judogi, cinture, materiale. Nessun fornitore esterno collegato
via API: il catalogo lo scrive l'amministratore. Le regole comuni (JavCash,
IVA, spedizione) stanno in `domains/marketplaces/rules.py`, pensato perché un
eventuale secondo negozio le riusi invece di copiarle.

### «Fai la Spesa con Jav» {#jav-market}

Il negozio segue le regole di `marketplaces/rules.py` -- JavCash solo da
spendere e mai per intero, niente cashback, nessuno sconto per il bonifico,
IVA aggiunta al prezzo, carrello con una spedizione sola -- e **il catalogo
lo scrive l'amministratore**. Un ordine può indicare **per quale atleta** è
(`jav_market_orders.athlete_id`, facoltativo, verificato sulla famiglia del
cliente).

Ne discende il resto. Non ci sono prezzi ricalcolati a ogni sync, né cambio
valuta, né ricarico su un costo: il prezzo è quello di vendita. La
spedizione è un importo fisso e non un minimo, perché senza fornitore non
esiste un costo reale da confrontare. Il tracking lo segna l'amministratore
quando il fornitore glielo manda, ed è anche il momento in cui il cliente
riceve l'email.

**Chi è il fornitore di un prodotto (ottobre 2026).** Il fornitore scelto
sul prodotto (`jav_market_products.producer_id`); se manca, quello della
**prima categoria** del prodotto (per `position`, poi nome) che ne ha uno
(`shop_categories.producer_id`, solo per le categorie dello Shop). Il
prodotto vince sulla categoria. Una categoria nascosta al cliente conta lo
stesso. La regola sta in un posto solo, `jav_market.service.resolve_suppliers`.
Il fornitore così risolto si **congela sulla riga d'ordine**
(`jav_market_order_items.producer_id` e `producer_name`) alla creazione:
spostare dopo un prodotto su un'altra azienda non dirotta gli ordini già
fatti. Eccezione voluta: una riga nata **senza** fornitore prende quello di
oggi finché non parte (così assegnarlo dopo basta a farla partire), e viene
congelata quando parte.

**L'ordine pagato va al fornitore, per riga.** Una riga è «da mandare»
finché `supplier_dispatch_id` è NULL (ordine pagato, non ancora spedito né
consegnato). Tre strade, che segnano le stesse righe e quindi non mandano
mai due volte la stessa merce:

- **«Fornitori da avvisare»** (la strada normale): gli ordini pagati
  raccolti per fornitore. «Prepara email» genera una lettera in italiano
  (saluto, un blocco per ordine con numero, data, righe «quantità ×
  prodotto – variante», indirizzo di consegna, telefono e note del cliente,
  richiesta di rispondere con corriere e tracking, firma dalle impostazioni)
  che l'amministratore può correggere — destinatario, oggetto e testo —
  prima di «Invia». Si mandano **le righe che c'erano nell'anteprima**, non
  quelle arrivate nel frattempo.
- il pulsante **«Invia alle aziende»** sul singolo ordine, senza anteprima:
  manda solo le righe non ancora partite;
- l'**invio automatico** al pagamento, se `auto_forward` è acceso (nasce
  spento: mandare una email a un'azienda vera è un'azione verso l'esterno).

In ogni caso **mai i prezzi** che il cliente ha pagato, che mostrerebbero il
ricarico, e solo ordini già pagati. L'email parte da
`jav_market_settings.supplier_email_from` (es. info@…), che è anche
Reply-To e copia nascosta: la risposta col tracking torna lì e la casella
conserva ogni ordine mandato (è il modo di rimandarne uno perso). Vuoto = il
mittente predefinito dell'SMTP.

**Un'email non partita non segna niente.** L'invio dalla coda usa
`send_html_email` e non la versione «best effort» (eccezione voluta a
CLAUDE.md §5: qui l'email *è* l'operazione): se l'SMTP non è configurato o
rifiuta, l'amministratore riceve un messaggio chiaro e le righe restano da
mandare. Solo un'email partita crea una riga in
`jav_market_supplier_dispatches` (con il testo esatto) e la collega alle
righe d'ordine. Contro il doppio clic le righe si bloccano (`FOR UPDATE`) e
devono essere ancora tutte da mandare e di quel fornitore: il secondo
invio riceve un 409 «aggiorna la pagina» prima di spedire. Un ordine passa
a `fulfillment_status = SENT` quando tutte le sue righe con un fornitore
sono partite (dal pulsante sul singolo ordine, come prima, basta un
fornitore avvisato). Un fornitore senza email o una riga senza fornitore
vengono mostrati (coda: elenco «righe senza fornitore»; pulsante: allo staff
e in `forward_error`), mai saltati in silenzio.

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
modificabili dalle Impostazioni del negozio.

### Vetrina a pagine {#shop-paging}

Regola dell'utente: **il server non deve mai bloccarsi o rallentare perché un
negozio ha tanti prodotti.** Lo Shop dà al cliente **48 prodotti alla
volta**; sotto la griglia «N di M prodotti» e il pulsante
**«Mostra altri prodotti»**. Ricerca e categoria cercano in tutto il negozio
(le filtra il server, non il browser). Un prodotto acceso che non si può
vendere (esaurito) non lascia pagine a metà. Un negozio nuovo deve usare la
stessa vetrina a pagine (`marketplaces/paging.py`), mai restituire tutto il
catalogo. Restano in una sola risposta solo i pacchetti/contratti, piccoli
per natura.

## Categorie degli shop {#shop-categories}

Ogni shop ha le **sue** categorie: il catalogo interno (una serie per
sezione: `internal`, `partner`, `dropshipping`) e lo Shop (`jav_market`).

Dominio a sé (`domains/shop_categories`): **nessuna colonna aggiunta alle
tabelle dei prodotti**.

- `shop_categories`: nome (unico per shop, senza distinzione fra maiuscole
  e minuscole), `position` (ordine nella barra del cliente), `active`, e
  solo per lo Shop `producer_id`: il fornitore ereditato dai prodotti della
  categoria che non ne hanno uno loro (regola in «Fai la Spesa con Jav»).
  È l'unica chiave esterna del dominio verso un altro (ON DELETE SET NULL);
  sceglierlo su una categoria di un altro shop è rifiutato.
- `shop_category_products`: l'appartenenza. `product_id` è un UUID **senza
  vincolo di chiave esterna**, perché punta a righe di tabelle diverse
  (prodotti del catalogo, prodotti dello Shop): è scritto nel docstring del
  modello.

Chi fa cosa: creare, rinominare, riordinare, nascondere ed eliminare vuole
`products.manage` (eliminare una categoria **non elimina i prodotti**);
leggere l'elenco basta essere loggati, perché al cliente servono i nomi.
Ogni lettura di prodotto porta con sé `category_ids`, caricati con **una
query per pagina**, mai una per prodotto.

Come si assegna un prodotto: nel modulo di modifica del prodotto, oppure in
blocco dalla card Categorie ("Assegna più prodotti a una categoria").

Nello Shop del cliente compaiono le categorie (solo quelle attive e con
almeno un prodotto in elenco) e una casella di ricerca su nome e
descrizione. I due filtri si sommano.

## Account freeze

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

### A frozen member disappears from the network

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

## Club: famiglie, quote, gare {#club}

La specifica completa è `club-portal.md`; qui le regole che non si negoziano.

- **Il genitore è l'unico che accede.** I figli sono atleti senza account
  (`club_athletes.guardian_user_id`); un adulto che si allena è un genitore
  con un atleta `is_self`. Ogni lettura e scrittura del genitore verifica la
  famiglia lato server: ciò che non è suo risulta "non trovato".
- **Il piano lo sceglie l'età federale** (anni compiuti entro il 31
  dicembre): a gennaio chi entra nella fascia del gruppo dopo paga già la
  mensilità del gruppo nuovo; la segreteria può fissarlo a mano
  (`plan_locked`).
- **Le quote si generano da sole** (il 1° del mese per i mesi fatturati del
  piano, l'iscrizione a inizio stagione o alla creazione dell'atleta) e sono
  UNIQUE per (atleta, tipo, periodo): un job ripetuto non crea doppioni.
  L'importo si congela quando la quota è emessa.
- **La prova di pagamento segna subito le quote come pagate.** Una prova
  copre una o più quote (un bonifico per due figli). La segreteria può
  rifiutarla con un motivo: le quote tornano da pagare e il genitore riceve
  notifica ed email. Può anche segnare pagata a mano una quota (dicendo come:
  contanti e a chi, carta al POS, bonifico), condonarla o riaprirla. Il
  genitore può dichiarare i contanti indicando a chi li ha dati: niente foto,
  quella persona viene avvisata. Ogni quota pagata registra il metodo.
- **Certificato agonistico valido alla data della gara** per le gare che lo
  richiedono, controllato dal server all'iscrizione. Avvisi automatici a 30
  e 7 giorni dalla scadenza e a certificato scaduto, una volta sola per
  gradino (`club_reminders_sent`).
- **Cintura attuale e Jav Ranking si calcolano**: la cintura è la più alta
  dello storico, il ranking somma punti per piazzamento × coefficiente del
  livello di gara. Correggere un risultato corregge la classifica.

## GDPR notes

Consent versions, retention periods, and the legal basis for each processing purpose
are **not** implemented as final policy in this phase — schema hooks exist
(`documents.expires_at`, audit of all document access) but retention windows and the
lawful basis registry require legal sign-off before being treated as authoritative.
See `open-questions.md #5`.
