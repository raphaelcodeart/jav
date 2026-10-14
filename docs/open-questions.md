# Open Questions / Assumptions Requiring Confirmation

Source document `docs/Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf` was not
present in the repository. Everything below is a placeholder that makes the system
runnable and testable; none of it is confirmed Jav policy. Each item names the
exact config location to update once real figures/rules are available — no formula is
silently invented into unlabelled code.

## 1. Rank table (career plan) figures

**Placeholder**: `S1..S3`, `TL1..TL4`, `MD1..MD5` with linearly increasing
`personal_token_cents` (4000 → 9500), see `business-rules.md §Ranks`.
**Update**: `personal_volume_threshold_cents` /
`group_volume_threshold_cents` are no longer 0 -- populated with placeholder
ascending figures at the user's explicit request ("go get
those criteria and set them yourself"), used by the new rank-promotion-progress
feature (`business-rules.md §Rank promotion progress`). Still not confirmed
Jav policy. `evaluation_window_months` remains unused/unknown -- the
progress calculation is lifetime-cumulative, not evaluated over any window.
**Where to fix**: `apps/api/app/seed/ranks.py` (what the bootstrap writes into
`ranks`), plus the `ranks` rows of an already-installed organization, or a new
`commission_rule_versions` row once the real plan document is
available — no application code change needed, only data.
**Also**: `network/service.py::AUTO_ACTIVATION_RANK_CODE = "S1"`
hardcodes the floor rank self-service "lavora con noi" applicants start at,
instead of deriving the lowest-`level` rank from the org's ladder. If code
`S1` is ever renamed/removed, this silently resolves to no rank
(`_get_current_rank_id()` returns `None`, no error) rather than failing loud.
**Where to fix**: same file, alongside item #1's other placeholder figures.
**Update**: a second, independent axis now exists —
`commissions/services/rank_evaluation.py` actually **writes** the agent's
rank (promotes or demotes) once a month, using a fixed single-calendar-month
window, explicitly NOT `evaluation_window_months` (still unused by anything).
This was an explicit user decision, not a resolution of this open question —
see `business-rules.md §Automatic monthly rank evaluation`. If the real plan
document specifies a genuine rolling window, both this and item #6 below need
updating together, since they'd likely share the same window definition.

## 2. Network move approval

**Assumption**: a role with `network.manage` may self-approve a branch move
(`approved_by` optional in that case); all other moves require a second approver.
**Where to fix**: `apps/api/app/domains/network/service.py::move_agent()` — the
self-approval check is a single `if` guarded by this assumption; flip it once the real
approval policy is confirmed.

## 4. Reversal ("storno") refund formula

**Assumption**: linear proration —
`refund_cents = original_amount_cents * remaining_months / total_contract_months`.
**Where to fix**: `apps/api/app/domains/commissions/calculators/reversal.py`.

## 5. GDPR retention & legal basis

**Assumption**: none finalized. Schema hooks exist (`documents.expires_at`, full audit
of document access/download) but retention windows per document category and the
lawful-basis registry require legal sign-off, not an engineering guess.
**Where to fix**: this requires a decision from Jav's legal counsel, then a
`retention_policies` table (not yet created) keyed by document category.

## 6. 33% branch cap — exact denominator

**Assumption**: the cap applies to production aggregated at first-level-branch
granularity under the evaluated beneficiary, using the same evaluation window as the
beneficiary's rank re-evaluation (`ranks.evaluation_window_months`).
**Where to fix**: `apps/api/app/domains/commissions/policies/branch_cap.py` — the
aggregation query is isolated there specifically so the denominator can change without
touching the main calculator.
**Note**: the rank re-evaluation that now actually exists
(`rank_evaluation.py`, see item #1) does NOT use `evaluation_window_months`
either — it's a fixed single calendar month. This assumption's cross-reference
to "the same evaluation window" is therefore still unresolved/unverified, not
contradicted; revisit both together once the real window is known.

## 7. MFA and account lockout policy

**Assumption**: MFA schema is present (session/device tables support it) but not
enforced in v1; account lockout threshold is a placeholder (5 failed attempts / 15
minute window) pending a real security policy decision.
**Where to fix**: `apps/api/app/domains/auth/service.py` constants
`MAX_FAILED_ATTEMPTS`, `LOCKOUT_WINDOW_MINUTES`.

## 8. Che cosa è "il totale del contratto"

**Assumption**: the taxable/chargeable amount of a contract is
`product_versions.base_price_cents` — the single figure the dashboard shows
as the product's price, with "+ IVA" next to it. `initial_fee_cents` and
`recurring_fee_cents` exist on the same row but **are not charged by any code
path**, so folding them in would silently start billing amounts nobody has
agreed to.

**Where to fix**: `apps/api/app/domains/catalog/pricing.py::
contract_net_amount_cents` — deliberately one function, so every price, VAT
figure and payment plan in the app follows from changing it in one place.

## 9. Percentuale di cashback sui contratti

**Assumption**: `product_versions.contract_cashback_percentage` is **0 on
every product**, i.e. paying a contract credits no JavCash at all. The
mechanism is built and tested; the number is a deliberate no-op until the
club sets it, because it mints credit and the safe default is "off".

**Where to fix**: admin dashboard, `Prodotti → modifica → Cashback automatico
sul contratto (%)`. No deploy needed.

## 10. Bonus primo segnalatore: su quali prodotti

**Assumption**: `first_referrer_bonus_enabled` is **false on every product**.
**Where to fix**: admin dashboard, `Prodotti → modifica → Bonus primo
segnalatore`. No deploy needed.

## 11. Testo del contratto di collaborazione

`apps/api/app/domains/network/collaboration_documents.py` è un **modello**:
le parti tra parentesi quadre (`[RAGIONE SOCIALE]`, `[SEDE LEGALE]`, `[CITTÀ]`
del foro, ...) vanno compilate con i dati del club che usa la piattaforma, e
il testo va fatto rivedere da un legale prima che un promoter lo accetti.
Dopo ogni modifica del testo si cambia la `version` del documento.

## 12. JavCash nello Shop: sconto sul totale con IVA?

Oggi la percentuale JavCash di un prodotto dello Shop si calcola sul prezzo
**senza IVA**, e l'IVA sull'ordine è quella del prezzo pieno (i JavCash sono
trattati come un modo di pagare, `vat_mode = ADDED`). Se i JavCash vanno
invece trattati come uno sconto, la percentuale andrebbe calcolata sul
totale con IVA e la fattura fatta sul totale scontato: cambia l'IVA da
versare, quindi va deciso con il commercialista prima di toccare i calcoli
(`marketplaces/rules.py`).

## 13. Club: regole da confermare con la segreteria

Valori di partenza scelti per far funzionare il portale, tutti in un posto
solo e modificabili senza toccare il resto (vedi `club-portal.md`):

- **Prova di pagamento accettata subito**: è la regola di autogestione
  richiesta; la segreteria può rifiutare dopo. Se il club preferisce
  controllare prima, è una modifica del servizio delle prove
  (`club/service.py`), non dello schema.
- **Mesi fatturati**: settembre–giugno di default
  (`club/models.py::DEFAULT_BILLING_MONTHS`), modificabile per piano.
- **Età al 1° settembre** per scegliere il piano (`club/seasons.py`).
- **Punti del Jav Ranking**: 1° 100, 2° 70, 3° 50, 5° 30, 7° 20,
  partecipazione 10, × coefficiente del livello (club 1, regionale 2,
  nazionale 3, internazionale 4) — `club/competitions.py`.
- **Avvisi certificati**: a 30 e a 7 giorni dalla scadenza e una volta scaduto (`club/tasks.py`).

## 14. Più club: cosa è condiviso e cosa no

Scelte fatte con la prima versione multi-club (sessione 3), da confermare
quando arriva il secondo club vero:

- **Gare e Jav Ranking per club**: ogni club crea le sue gare e la classifica
  conta solo i suoi atleti. Una gara regionale a cui vanno più club oggi va
  creata da ciascun club. Un ranking di tutta la piattaforma (tutti i club
  insieme) è possibile — i risultati ci sono — ma va deciso: chi crea le gare
  condivise, e se le famiglie vedono gli atleti degli altri club.
- **Una persona, un club**: un'email è un account, e l'account è di un club
  solo. Un genitore con figli in due club, o un istruttore che insegna in due
  club, oggi non è previsto (`club/clubs.py::add_staff` rifiuta un'email già
  esistente).
- **Shop unico**: catalogo, prezzi e bonifici sono della piattaforma; il club
  non guadagna sugli ordini delle sue famiglie e non ha un suo catalogo.
