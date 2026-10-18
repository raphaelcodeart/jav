# Portale club — palestre e club di judo

Specifica del dominio `club`: ciò che trasforma il gestionale in un portale
per palestre e club di judo, in stile federazione. Scritta prima del codice:
quando codice e specifica divergono, si aggiorna questo file nella stessa
modifica.

## Lo scopo, in una frase

**Il club si gestisce da solo.** Le quote si generano da sole, i genitori
caricano da soli le prove di pagamento e i certificati, gli avvisi partono da
soli. La segreteria interviene solo sulle eccezioni.

Ogni scelta qui sotto discende da questa frase. Se una funzione richiede che
qualcuno dello staff faccia un'azione per ogni iscritto, ogni mese, è
sbagliata.

## Chi usa il portale

| Chi | Ruolo | Cosa fa |
|---|---|---|
| Genitore (o atleta adulto) | `CUSTOMER` | Il **titolare** del conto: figli, quote, prove di pagamento, certificati, gare, ordini di materiale |
| Atleta con il suo accesso | `ATHLETE` | La sua area (`/atleta`): lezioni del mese, "Estou cá", cintura e traguardi, quote in lettura, formazione |
| Segreteria del club | `SECRETARY` | Piani, gare, risultati, eccezioni sui pagamenti, staff e IBAN del club — solo del suo club |
| Istruttore | `INSTRUCTOR` | Corsi, presenze, passaggi di cintura — solo del suo club |
| Superadmin della piattaforma | `SUPER_ADMIN` | Crea i club, ci entra per sistemarli, gestisce lo Shop |

**Il titolare gestisce, l'atleta vede.** Ogni atleta ha un titolare
(`guardian_user_id`): il genitore di un minore, o l'adulto stesso con
l'atleta "me stesso" (`Athlete.is_self`). Un genitore che si allena è
titolare di sé e dei figli, e passa dall'una all'altra area in `/atleta`.

### Il conto dell'atleta

(`club/athlete_access.py`, `club/athlete_router.py`, migrazione 0013)

- **L'accesso lo crea il titolare**, dalla scheda dell'atleta → *Acesso*:
  **nome utente** (minuscolo, unico nell'organizzazione, `users.username`)
  e password di almeno 6 caratteri, e l'email del ragazzo se ce l'ha. Al
  login si scrive "email ou nome de utilizador" (`LoginRequest.email`
  accetta anche un nome utente: senza "@" si cerca per `username`).
  L'account ha il ruolo `ATHLETE` (permesso `club.athlete`) e niente
  cancelli dell'adulto (email verificata, privacy e profilo li ha già il
  titolare). Un atleta senza email ha `<username>@atleta.invalid`: la posta
  non parte (`core/email.py::is_placeholder_address`), la password nuova
  gliela scrive il titolare. *Desligar o acesso* lo congela, chiude le
  sessioni e revoca il QR.
- **Il QR** (`club_athlete_login_codes`): un link `/entrar/<codice>` che
  vale come nome utente e password, 90 giorni, uno solo alla volta,
  revocabile; del codice si salva solo lo sha256 e il QR (SVG disegnato
  dall'API con reportlab) si vede una volta, appena creato.
- **L'area** (`GET /club/athlete-area/{id}`, `club.athlete`, che ha anche
  `CUSTOMER`): la vedono l'atleta e il suo titolare, nessun altro. Le
  lezioni del mese dei corsi a cui è iscritto con lo stato (presente,
  assente, oggi, da fare), **"Estou cá!"** per le lezioni di oggi (le stesse
  regole del genitore: solo oggi, una presenza dello staff non si toglie),
  cintura, livello e traguardi, **le quote in lettura** (paga il titolare),
  e il posto per la formazione (tecniche, regole, giochi: in arrivo).
- **A 18 anni**: l'atleta con il suo accesso vede "torna-te titular da tua
  conta" (mai automatico, solo lui può farlo, serve un'email vera): diventa
  `is_self` e titolare di sé, riceve `CUSTOMER`, e da lì paga da solo. Le
  quote già emesse restano al titolare di prima; il genitore non lo vede
  più tra i suoi.
- Gli atleti "me stesso" che esistevano prima hanno `user_id` = il
  titolare (migrazione): la loro area è già la loro.

## Più club

La piattaforma (un'organizzazione: Jav) ospita **più club**. Il club è la
tabella `clubs` (nome, `slug` per l'indirizzo, stato `ACTIVE`/`SUSPENDED`,
impostazioni con IBAN e intestatario delle quote).

- **Ogni tabella del club ha `club_id`** (piani, atleti, quote, prove,
  certificati, cinture, corsi, presenze, gare, iscrizioni) e **ogni query del
  dominio filtra per club**, mai solo per organizzazione. Le funzioni del
  servizio ricevono un `ClubScope` (organizzazione + club), non un id sciolto.
- **Su quale club lavora una richiesta lo decide `club/scope.py`**, mai il
  chiamante. Un account di un club (`users.club_id`: genitore, segreteria,
  istruttore) lavora solo sul suo, qualunque cosa chieda. Lo staff della
  piattaforma (`users.club_id` NULL, permesso `clubs.enter`) sceglie il club
  ("Entra" nel pannello Club): il cookie `jav_club` diventa l'intestazione
  `X-Jav-Club` nel proxy BFF. Senza scelta l'API risponde 409.
- **Un club sospeso** chiude la porta ai suoi account; il superadmin entra
  comunque. I job automatici girano solo sui club attivi.
- **Creare un club** (`clubs.manage`, superadmin): nome, indirizzo, e se c'è
  l'email della segreteria, che riceve l'invito a scegliersi la password. Se
  l'email non può partire (SMTP non configurato) il link di primo accesso
  viene mostrato a chi crea il club, che lo consegna a mano. La segreteria
  aggiunge poi da sola istruttori o altre persone di segreteria.
- **Le famiglie si registrano dal link del club**, `/c/<slug>`
  (`POST /auth/register-family`): l'account nasce legato al club. Nessun
  promoter, nessun codice d'invito.
- **Lo Shop, il catalogo e JavCash sono della piattaforma**, uno per tutti i
  club: li gestisce il superadmin, che conferma i bonifici e spedisce. La
  segreteria vede, in sola lettura, gli ordini delle famiglie del suo club.
- **Le quote si pagano al club**: l'IBAN mostrato nel pagamento delle quote è
  quello del club (lo imposta la segreteria); quello dello Shop è della
  piattaforma.

## Modello dati

Tutte le tabelle hanno `organization_id` e `club_id` (vedi "Più club").

### Atleta — `club_athletes`
- `guardian_user_id` → `users.id`: il genitore che lo gestisce.
- `first_name`, `last_name`, `birth_date`, `sex` (`M`/`F`), `fiscal_code` (facoltativo),
  `photo_url` (bucket pubblico media, come le foto profilo).
- `is_self`: l'atleta è il titolare stesso dell'account.
- `plan_id` → piano assegnato. **Calcolato dall'età federale** alla
  creazione, a ogni inizio stagione e a ogni mensilità emessa (vedi sotto);
  la segreteria può forzarlo (`plan_locked = true`).
- `status`: `ACTIVE` / `SUSPENDED` / `LEFT`.
- `weight_kg` (facoltativo, per le categorie di gara).
- `federation_number`, `federation_expires_on`: tesseramento federale.

### Piano di iscrizione — `club_plans`
- `name` (es. "Bambini 4–7 anni"), `min_age`, `max_age` (inclusi; `max_age`
  nullo = senza limite).
- `monthly_fee_cents`, `enrollment_fee_cents` (quota annuale d'iscrizione).
- `due_day` (giorno del mese di scadenza, default 10, massimo 28), `active`.
- `billing_months`: i mesi in cui la quota mensile si emette. Default
  settembre–giugno: luglio e agosto nel judo di solito non si pagano, e un
  default che li fattura costringerebbe la segreteria a condonarli a mano
  ogni anno.
- Se più piani coprono un'età vince **il più stretto** ("Agonisti 14–17"
  batte "Tutti 4+").
- **L'età è quella federale** (`seasons.federal_age`): gli anni che l'atleta
  compie entro il 31 dicembre dell'anno solare, cioè anno meno anno di
  nascita. Chi è nato a novembre 2016 ha 10 anni federali per tutto il 2026,
  anche se a settembre ne ha ancora 9.
- **Il gruppo cambia a gennaio**, non a settembre: il 1° gennaio l'età
  federale sale di uno. Il job delle mensilità (`generate_monthly_fees`)
  sceglie il piano di ogni mese con l'età federale di quell'anno; se l'atleta
  entra nella fascia del gruppo dopo, la mensilità di gennaio è già quella
  del gruppo nuovo, il suo `plan_id` passa al gruppo nuovo e il titolare
  riceve una notifica (`CLUB_PLAN_CHANGED`). Le mensilità già emesse non
  cambiano (prezzo congelato); rigenerare un mese passato usa il gruppo di
  quell'anno ma non riporta indietro `plan_id`. Se nessun piano copre la
  nuova età si resta nel piano di prima. Un piano scelto a mano
  (`plan_locked`) non si muove mai.

### Quota — `club_fees`
- `athlete_id`, `kind`: `MONTHLY` / `ENROLLMENT` / `COMPETITION` / `MEMBERSHIP`.
  `MEMBERSHIP` (quota socio del genitore) non ha atleta: ha `guardian_user_id`.
- `period` (`YYYY-MM` per le mensili, l'anno solare `YYYY` per iscrizione e
  quota socio, l'id della gara per le gare), `amount_cents`, `due_date`.
- `gross_amount_cents` (listino), `discount_cents`, `discount_note` (gli
  sconti in parole): congelati con il prezzo.
- `status`: `DUE` → `PAID` (oppure `WAIVED`, condonata dalla segreteria).
  La segreteria può anche segnarla pagata a mano e riaprire un condono o un
  "pagata a mano" sbagliato; una quota pagata con una prova si riapre solo
  rifiutando la prova.
- `payment_method` (migrazione 0014): come è stata pagata — `BANK_TRANSFER`,
  `CASH`, `CARD` (POS in palestra, solo la segreteria), `WALLET` (il credito
  ha coperto tutto) — e per i contanti a chi sono stati dati
  (`cash_received_by_user_id`, e il nome congelato `cash_received_by_name`).
  NULL finché è da pagare; riaprire o rifiutare la prova lo cancella. Le
  quote segnate pagate a mano prima della 0014 non hanno il metodo.
- Una quota mensile si emette solo per i mesi in cui l'atleta era iscritto
  (non prima di `joined_on`, non dopo `left_on`). Alla creazione di un atleta
  si emettono subito l'iscrizione dell'anno (a pro rata), la quota del mese in
  corso e, per un minorenne, la quota socio del genitore.
- **UNIQUE (`athlete_id`, `kind`, `period`)**, e per la quota socio UNIQUE
  (`club_id`, `guardian_user_id`, `period`): è ciò che rende idempotente la
  generazione automatica (CLAUDE.md §5). Il job può girare due volte, la
  quota esiste una volta sola.
- Prezzo **congelato** alla creazione: cambiare il piano o gli sconti non
  riscrive le quote già emesse.

### Prezzi e sconti (`club/pricing.py`)

I parametri stanno in `clubs.settings["pricing"]` e li imposta la segreteria
(Impostazioni → Prezzi e sconti).

- **Iscrizione annuale**: anno solare, 1 gennaio–31 dicembre, importo del
  piano (`enrollment_fee_cents`, per esempio 120 €). Comprende quota di socio,
  taxa de falta, assicurazione sportiva, iscrizione alla federazione e
  all'associazione distrettuale (il testo lo scrive il club). Chi entra a
  metà anno paga i mesi che restano, quello d'ingresso compreso: a settembre
  4/12. **Nessuno sconto.** La genera il 1° gennaio il job dell'anno nuovo.
- **Quota socio del genitore** (`MEMBERSHIP`, default 60 € l'anno): chi ha un
  atleta minorenne (sotto i 18 anni) è socio del club. Una per famiglia e per
  anno, a pro rata come l'iscrizione, senza taxa de falta. Non la paga chi è
  già atleta (`is_self`): la sua iscrizione la comprende.
- **Sconti, solo sulla mensilità**, in quest'ordine:
  1. escalão A/B/C: percentuale decisa dal club (default A 25%). Il **judo
     adattato** vale come escalão A; un atleta con escalão **e** judo
     adattato ha lo sconto maggiore dei due, non la somma. Li imposta solo la
     segreteria (`social_tier`, `adapted_judo` sull'atleta), dopo aver visto
     il documento;
  2. **famiglia**: con almeno N atleti attivi (default 2) nella stessa famiglia
     (stesso account genitore), ogni mensilità ha X € di sconto (default 5 €).
  La quota non va mai sotto zero. Es.: 40 € −25% = 30 €, −5 € = 25 €.
- **Escalão D** in più (A 25%, B 20%, C 15%, D 10% come nel gestionale di
  prima: i default restano A 25%, gli altri li imposta il club).
- **Esenzioni** (`exempt_monthly`, `exempt_annual` sull'atleta, le decide la
  segreteria: staff, órgãos sociais, borse del club): un esente non ha la
  mensilità, o l'iscrizione annuale; una famiglia di soli esenti dalle quote
  annuali non paga la quota socio.
- **Sconto personale** dell'atleta (`custom_discount_*`): in percentuale o in
  euro, sulla mensilità, sulle quote annuali o su entrambe, con la sua
  descrizione ("Grupo 2 · 1x semana"). Sulla mensilità si applica dopo
  l'escalão e prima dello sconto famiglia.
- **Rate**: una quota (di solito l'iscrizione annuale o la quota socio) può
  essere divisa in rate: una riga per rata, periodo `2026/1`, `2026/2`
  (`installment_no` / `installments_total`). L'iscrizione dell'anno non si
  emette di nuovo se ci sono già le sue rate.
- **Multa** (`FINE`): una quota emessa dalla segreteria (es. le faltas agli
  allenamenti), che si paga come le altre.
- **Invita un amico**: ogni account del club (un genitore, o un atleta adulto
  che fa tutto da sé) ha il suo link `/c/<slug>?invito=<codice>`. Ogni volta
  che un atleta della famiglia invitata paga una mensilità, chi ha invitato
  riceve nel wallet il credito deciso dal club (default 5 €). Se quel
  pagamento viene annullato (prova rifiutata, quota riaperta) il credito si
  ritira, salvo che sia già stato speso. Idempotente sulla chiave del
  movimento: quota + momento del pagamento (`club/referrals.py`).
- **Credito nel pagamento**: il genitore può usare il credito del wallet per
  pagare le quote, confermandolo con il PIN o il codice via email come ogni
  spesa di JavCash. Se copre tutto, la ricevuta non serve. Se la prova viene
  rifiutata, il credito torna nel wallet.

### Numero della ricevuta e MB Way

Ogni prova di pagamento ha un numero, "MEN-2026-0042": prefisso per che cosa
si è pagato (MEN mensilità, QUO quote annuali, PRO gare, EQU judogi, MUL
multe, PAG più cose insieme), anno, progressivo per club. Lo assegna
`club/receipts.py` con un contatore atomico (`club_receipt_counters`), e un
indice UNIQUE (club, numero) impedisce comunque i doppioni. Oltre al
bonifico e ai contanti, una famiglia può pagare con **MB Way**, dichiarato
come il bonifico (con la schermata della conferma).

### Come si paga una mensilità

Ogni mensilità è dell'atleta (`club_fees.athlete_id`): ognuno ha le sue,
pagate e da pagare. Il titolare la paga in tre modi, dalla stessa finestra:

- **Bonifico**: la foto della ricevuta (sotto, "Prova di pagamento").
- **Contanti**: niente foto; si dice **a chi** sono stati dati — una persona
  dello staff del club (`GET /club/cash-receivers`: segreteria e istruttori
  attivi) o un nome scritto a mano. È una prova con `method = CASH`: segna
  subito pagato (regola di autogestione), e la persona indicata riceve una
  notifica (`CLUB_CASH_DECLARED`). Se i soldi non sono arrivati, la
  segreteria rifiuta la prova come ogni altra.
- **Carta online**: il bottone c'è ed è **spento** finché il club non ha un
  pagamento online (Stripe). La carta al POS del club la segna la
  segreteria.

La segreteria segna pagata una quota a mano (`POST /club/admin/fees/{id}/
mark-paid`) dicendo sempre il metodo (`CASH`, `CARD`, `BANK_TRANSFER`) e,
per i contanti, a chi.

### Il quadro del mese (`club/month_board.py`)
- La prima cosa della segreteria (in cima alla Panoramica e prima scheda di
  **Quote**, `GET /club/admin/month?period=YYYY-MM`): il mese corrente in
  grande, con le frecce per i mesi prima e dopo, quanto si doveva incassare
  di mensilità e quanto manca, e **un riquadro per atleta attivo** con il
  gruppo (il piano), l'importo e lo stato: pagata, da pagare, in ritardo,
  condonata, esente (`exempt_monthly`), nessuna quota.
- Nel riquadro anche ciò che la persona deve ancora: i **mesi arretrati** e
  le **altre quote scadute entro fine mese** (gare, judogi, iscrizione,
  multe). «Segna pagato» le chiude insieme, con il modo (contanti e a chi,
  MB Way, bonifico, carta), quota per quota come `/fees/{id}/mark-paid`.
- «Segna pagato» registra le quote scelte con **una ricevuta sola**
  (`POST /club/admin/fees/pay`, `club_service.staff_record_payment`) e, sotto
  il modo di pagamento, la **prova facoltativa**: «Scatta una foto» (apre la
  fotocamera) o «Allega un file» (JPG, PNG, PDF), nel bucket privato come le
  prove delle famiglie. Mai quote di due famiglie nella stessa ricevuta.
- Gli ordini dello Shop in attesa di pagamento si contano a parte: li
  conferma la piattaforma.
- La famiglia vede lo stesso calcolo per i suoi figli (`this_month` di
  `GET /club/family`): la card «Questo mese» in cima alla sua pagina, con
  il totale e il bottone che apre il pagamento con quelle quote già scelte.

### Il calendario delle mensilità (`club/months.py`)

Le dodici mensilità della stagione di un atleta, da settembre ad agosto
(`GET /club/athletes/{id}/months` il titolare, `/club/athlete-area/{id}/
months` l'atleta, `/club/admin/athletes/{id}/months` la segreteria). Ogni
mese ha uno stato: `PAID`, `WAIVED`, `DUE`, `OVERDUE` (scaduta: in rosso),
`UPCOMING` (futuro), `NOT_BILLED` (il gruppo non lo fattura), `NOT_ENROLLED`,
`NONE` (passato, senza quota). Per ogni mese: gruppo ed età federale di
quell'anno, la quota con il metodo di pagamento e la prova, le presenze. Per
i mesi futuri un importo **previsto** calcolato dal server con il gruppo di
quell'anno e gli sconti di oggi: il genitore vede in anticipo che a gennaio
la mensilità sale. La quota vera la congela il job del 1° del mese.

Nella pagina della famiglia (`FamilyRead.season_months`) i totali della
stagione per atleta: pagato, da pagare, scaduto.

### Prova di pagamento — `club_payment_proofs`
- Il file (foto o PDF) nel bucket privato documenti, come le prove dei bonifici
  degli ordini. Si scatta dal telefono (`<input capture="environment">`).
- Una prova copre **una o più quote** (`club_payment_proof_fees`): un genitore
  con due figli fa un bonifico solo.
- `status`: `ACCEPTED` / `REJECTED`, `reviewed_by_user_id`, `rejection_reason`.
- `method`: `BANK_TRANSFER` (con il file, o senza se il credito copre tutto)
  o `CASH` (senza file, con `cash_received_by_user_id` o
  `cash_received_by_name`: un CHECK lo impone).

**Regola di autogestione**: caricare la prova **segna subito le quote come
pagate**. La segreteria ha una lista "Prove caricate" che *può* controllare;
se ne rifiuta una, le quote tornano `DUE` e il genitore riceve notifica ed
email con il motivo. Nessuna prova resta in attesa di qualcuno.

**Due tipi di prova.** "Carica un pagamento" chiede per prima cosa *che
cosa* si è pagato, perché le due cose vanno in posti diversi:
- **Quote del club** (mensilità, iscrizione, gare): come sopra, pagate subito,
  IBAN del club.
- **Ordine dello Shop** (judogi, materiale): si sceglie l'ordine in attesa di
  bonifico e si allega la ricevuta (`POST /jav-market/orders/mine/{id}/payment-proof`).
  Qui la foto **non** segna pagato niente: la merce parte quando la
  piattaforma conferma il bonifico, e la ricevuta è ciò che guarda per
  farlo. Ricaricarla sostituisce la precedente.

### Certificato medico — `club_medical_certificates`
- `athlete_id`, `type`: `NON_AGONISTIC` / `AGONISTIC`, `issued_on`, `expires_on`, file.
- Avvisi automatici al genitore a 30 e 7 giorni dalla scadenza, e il giorno dopo.
- Senza certificato **agonistico valido alla data della gara** non ci si iscrive
  a una gara che lo richiede: lo dice il form, non la segreteria.

### Documenti del club — `club_documents` (`club/club_documents.py`)
- I documenti del club, non di un atleta: dichiarazioni, affiliazione e
  rivalidazione alla federazione, atas (assemblee e direzione), certidão
  delle Finanze e della Segurança Social, certificazioni sportive (IPDJ,
  utilità pubblica), assicurazioni, statuto, altro.
- Li carica la segreteria del club (o la piattaforma entrando nel club):
  PDF, JPG o PNG fino a 15 MB, nel bucket **privato**, aperti con un URL
  presigned. Titolo, data, scadenza facoltativa, note.
- Con una scadenza: "in scadenza" negli ultimi 30 giorni, "scaduto" dopo.
  La segreteria riceve una notifica 30 giorni prima e il giorno in cui
  scade (`CLUB_DOCUMENT_EXPIRING`), una volta sola per documento e momento
  (`club_reminders_sent`), con i promemoria del mattino.
- **Condiviso con i soci** (`shared_with_members`, spento di default): il
  documento compare anche nella bacheca di atleti e famiglie del club
  (regolamento, calendario della stagione), che lo aprono con lo stesso URL
  presigned (`/club/board/documents/{id}/url`). Gli altri restano dello staff.

### La bacheca — `club_news_posts` (`club/news.py`)
- Nell'area riservata, voce **Bacheca** per la famiglia e sezione nell'area
  dell'atleta: le notizie del club e i documenti condivisi (`GET /club/board`,
  permesso `club.athlete`, che hanno sia `CUSTOMER` sia `ATHLETE`).
- Una notizia è come un post: titolo, testo, una foto, un video (YouTube e
  Vimeo si vedono dentro la notizia, ogni altro link resta un link), un link.
  La scrive la segreteria da **📰 Notizie** (`/club/admin/news`), con
  l'anteprima; si può fissare in cima, nascondere (bozza) e togliere. Una
  bozza pubblicata dopo prende la data del giorno in cui esce.
- Solo nell'area riservata, **mai sul sito pubblico**. La foto va nel bucket
  dei media (`club-news/<club>/…`), e l'indirizzo della foto deve essere uno
  dei nostri: un'immagine esterna è rifiutata. Video e link solo `http(s)://`.
- "Nuovo" sulle notizie uscite dopo l'ultima visita: lo ricorda il browser
  (localStorage), non il server.

### Il certificato medico lo carica anche l'atleta
Oltre al titolare e alla segreteria, l'atleta con il suo accesso lo carica
dalla sua area (`/club/athlete-area/{id}/certificates`): stesso servizio,
stesse regole (tipo, date, massimo due anni), stesso bucket privato.

### Cinture — `club_belt_grades`
- Storico: `athlete_id`, `grade`, `awarded_on`, `awarded_by_user_id`, `note`.
- La cintura attuale è **la più alta** dello storico (non l'ultima inserita:
  una correzione inserita dopo ma datata prima non deve abbassarla), mai una
  colonna da tenere allineata. Un passaggio si registra solo verso l'alto.
- Ogni atleta nuovo riceve la cintura bianca, o quella dichiarata
  all'iscrizione da chi arriva da un altro club.
- Scala (kyu → dan): `WHITE`, `WHITE_YELLOW`, `YELLOW`, `YELLOW_ORANGE`, `ORANGE`,
  `ORANGE_GREEN`, `GREEN`, `BLUE`, `BROWN`, `BLACK_1`…`BLACK_10`. Etichette e colori
  in un posto solo (`club/belts.py`).

### Corsi e presenze — `club_courses`, `club_course_slots`, `club_course_athletes`, `club_attendances`
- Corso: nome, descrizione, fascia d'età/livello, istruttore (`users.id`).
- Slot settimanali: giorno della settimana, ora inizio/fine, sala. Si
  correggono senza toglierli (clic sull'orario → `PATCH /club/admin/slots/{id}`).
- Presenza: (`athlete_id`, `course_id`, `date`) UNIQUE, segnata dall'istruttore
  da tablet o telefono con un tocco per atleta.

### Gare — `club_competitions`, `club_competition_entries`
- Gara: nome, data inizio/fine, luogo, organizzatore, livello (`CLUB`,
  `REGIONAL`, `ZONAL`, `OPENS`, `NATIONAL`, `INTERNATIONAL`, `EUROPEAN_CUP`,
  `EUROPEAN_CHAMPIONSHIP`, `WORLD_CHAMPIONSHIP`, `OLYMPIC_GAMES`), scadenza
  iscrizioni (e l'ora), quota di iscrizione, `requires_agonistic_certificate`,
  età minima/massima facoltative (al giorno della gara), escalões ammessi
  (`age_groups`), posti, orari, trasporto (`transport_mode`: del club, per
  conto proprio, da confermare), la circolare dell'organizzatore, stato
  `OPEN` / `CLOSED` / `DONE`.
- Una **foto o locandina** facoltativa (`image_url`, bucket media,
  `POST/DELETE /club/admin/competitions/{id}/image`) accanto al nome negli
  elenchi; senza, l'icona grande del tipo (🏆 gara, 🥋 stage, 🧑‍⚖️ arbitragem,
  🎓 formação, 🤝 reunião, 📌 altro).
- Tipo (`kind`): gara (`COMPETITION`, l'unica che dà punti e medaglie),
  `STAGE`, `REFEREEING` (arbitragem), `EDUCATION` (formação), `MEETING`,
  `OTHER`.
- **Eventi della rete** (`club_id` NULL): il calendário comune dei club
  (federazione, ADJA, opens, estágios). Lo vede ogni club
  dell'organizzazione e ognuno ci iscrive i suoi atleti; l'iscrizione e la
  quota hanno il club dell'atleta. Lo modifica solo la piattaforma; un
  club registra i risultati dei suoi atleti (`record_results` tocca solo
  le iscrizioni del club che chiama, e non cambia lo stato dell'evento).
  Niente promemoria automatici per gli eventi della rete: sono decine
  l'anno, e un avviso per ognuno a ogni famiglia sarebbe rumore.
- Risultato: `placement` (1, 2, 3, 5, 7 o 0 = partecipazione), più `rank`
  (la posizione vera quando non è un podio, "9° posto") e `result_notes`.
- Iscrizione: atleta, categoria (età/peso, testo), stato `REGISTERED` /
  `WITHDRAWN`, e il risultato: `placement` (1, 2, 3, 5, 7, oppure
  partecipazione), inserito dalla segreteria a gara finita.
- **Dopo la scadenza nessuno si iscrive più** (`eligibility`: né la
  famiglia né la segreteria), anche se la gara è ancora `OPEN`.
- Iscriversi crea la quota `COMPETITION` (se la gara ha una quota), che si
  paga con la stessa prova di pagamento di tutto il resto. Ritirarsi entro la
  scadenza condona la quota non pagata; reiscriversi la riapre.
- **Gara o stage** (`kind`): lo stage (allenamento collegiale) si gestisce
  come una gara (iscrizioni, quota, certificato) ma non ha piazzamenti e non
  dà punti né medaglie.

### La giustificazione per la scuola — `club_school_letters` (`club/school_letters.py`)
- Per ogni iscritto (`REGISTERED`) la segreteria apre "Giustificazione":
  il sistema propone il testo nella lingua delle lettere del club
  (`letters_language`): il club dichiara che l'atleta (nome, data di
  nascita, numero di tesseramento se c'è; al maschile o al femminile) è
  stato selezionato per le sue capacità per rappresentare il club alla gara
  (nome, luogo, date), e chiede alla scuola di giustificare le assenze. La
  segreteria lo corregge e genera il PDF: carta intestata del club (logo,
  nome, recapiti della pagina del club, colore del club).
- Il PDF ha i dati di un minore: sta nel **bucket privato** dei documenti
  (`club-school-letters/<club>/<gara>/…`) e si apre solo con un URL
  presigned di 5 minuti. Lo scaricano la segreteria e il titolare
  dell'atleta (`GET /club/competitions/{id}/entries/{athlete}/school-letter/
  url`, quando `school_letter_ready`).
- Una lettera per iscrizione (UNIQUE `entry_id`): rigenerarla sostituisce
  testo e file, e il file vecchio si cancella. Il testo salvato è quello
  stampato, e riaprendo la lettera si riparte da lì. Un atleta ritirato non
  ha giustificazione.

### Trasporto — `club_transport_requests` (`club/transport.py`)
- Su un evento la segreteria può chiedere il trasporto: ente (di solito il
  comune; il default è nelle impostazioni del club), email, partenza,
  ritorno, accompagnatori, note.
- **Quando le iscrizioni si chiudono** (il job notturno alla scadenza, o la
  segreteria con "Chiudi iscrizioni") il sistema scrive la lettera, nella
  lingua del club (`letters_language`, default portoghese): evento, date,
  luogo, numero di atleti e accompagnatori, elenco degli iscritti. La
  segreteria riceve una notifica.
- La segreteria la rilegge, la corregge e la manda **con un clic**. Se
  l'evento ha `transport_auto_send`, parte da sola alla chiusura.
- Parte dall'indirizzo della piattaforma, con risposta (Reply-To) e copia
  all'email di contatto del club. Il testo salvato è quello partito; se gli
  iscritti cambiano dopo, l'interfaccia propone di riscrivere la lettera.
- Una richiesta per evento (UNIQUE su `competition_id`). Se l'invio non
  riesce (per esempio SMTP non configurato), la lettera resta in bozza con
  il motivo.

### Jav Ranking
- Punti per livello di gara e risultato (`competitions.LEVEL_POINTS`): è
  la tabella che i club usavano nel gestionale di prima
  (docs/legacy-judo-aev.md), e che le famiglie conoscono. Un 5°, un 7° o un
  piazzamento più basso valgono la partecipazione.

| Livello | Oro | Argento | Bronzo | Partecipazione |
|---|---|---|---|---|
| Club | 3 | 2 | 1 | 1 |
| Regionale | 5 | 3 | 2 | 1 |
| Zonale | 7 | 5 | 3 | 2 |
| Open | 10 | 8 | 5 | 3 |
| Nazionale | 15 | 10 | 8 | 4 |
| Internazionale / Coppa Europa | 20 | 15 | 10 | 5 |
| Campionato europeo | 25 | 20 | 15 | 6 |
| Campionato del mondo | 30 | 25 | 20 | 7 |
| Giochi Olimpici | 35 | 30 | 25 | 8 |

- Classifiche per **anno solare** ("Ranking 2026"), sesso e gruppo: Grupo 1
  (3–7 anni), Grupo 2 (8–12), Grupo 3 (13–29), Veteranos (30+), per età
  federale nell'anno (anno − anno di nascita), come nel gestionale dei club.
  Di **tutta la rete** (ogni club dell'organizzazione con il ranking), con
  il club accanto al nome; nell'area riservata si può restringere al proprio
  club. Calcolata dai risultati, mai salvata a mano: correggere un risultato
  corregge la classifica. Ex aequo: stessa posizione, e i posti successivi
  si saltano (1, 1, 3).
- Nella classifica il nome è "Nome I.": la vedono tutte le famiglie.
- **Sul sito pubblico** (`/ranking` = classifica generale JAV di tutti i
  club; la pagina di ogni club = solo i suoi atleti) compaiono **tutti** gli
  atleti attivi dei club pubblicati, come "Nome I." con club, cintura e
  punti (decisione del titolare, ottobre 2026). Foto e pagina del judoca
  (`has_page`) solo per chi ha il consenso della famiglia ed è pubblicato.
- **Periodi** (`period`): `year` (l'anno solare, il ranking che conta e il
  predefinito), `month` (un mese di un anno) e `all` (da sempre). Per
  "sempre" la fascia d'età è quella di quest'anno. Su `/ranking` si
  sceglie periodo, anno e mese; l'indirizzo si condivide.
- **Ricerca e scheda in popup**: la classifica si filtra mentre si scrive
  (nome o club) e un clic apre la scheda (`GET
  /public-site/ranking/judoka/{id}`, `site.ranking_card`). Con il consenso è
  la scheda completa in stile IJF (foto, categoria, cinture, risultati,
  prove in programma, media); senza, solo ciò che dice una classifica:
  «Nome I.», club, fascia, cintura, posizione, punti e i risultati passati
  (evento, data, piazzamento). **Mai** foto, età, categoria, media o prove
  future: dicono dove sarà un minorenne.

### Taça dos Clubes
- `GET /public-site/ranking/clubs` (`site.public_club_ranking`): i club per
  punti, somma dei punti dei risultati dei loro atleti **per il club con cui
  hanno gareggiato** (l'iscrizione), stessa tabella e stessi periodi del
  ranking dei judoca. Con atleti, gare, risultati e medaglie.
- **La coppa** si assegna a fine anno: per l'anno in corso il primo è "in
  testa" (`is_final` falso), per un anno chiuso è il vincitore. L'albo d'oro
  (`winners`) è il vincitore di ogni anno chiuso con almeno un risultato.

### Livelli e medaglie
- Calcolati, mai salvati (`club/achievements.py`): XP = 10 per presenza +
  150 per passaggio di cintura + i punti ranking di sempre. Il livello cresce
  in modo quadratico (100, 300, 600, 1000 XP...).
- Medaglie: primo allenamento, 10/50/100 allenamenti, nuova cintura, prima
  gara, primo podio, primo oro, 5 podi, cintura nera.

### Materiale (judogi, cinture, attrezzatura)
- È lo Shop esistente (`jav_market`), **uno per tutta la piattaforma**:
  catalogo scritto dal superadmin, taglie come varianti, pagamento con
  bonifico e prova caricata (vedi "Due tipi di prova"). L'ordine
  indica **per quale atleta** è (`jav_market_orders.athlete_id`, facoltativo,
  sempre un atleta della famiglia di chi compra).

## La pagina del genitore

Una schermata sola, pensata per il telefono:

1. **Una card per figlio**: foto, nome, cintura (con il suo colore), piano,
   prossima quota, stato del certificato, prossima gara.
2. **Riepilogo famiglia**: totale da pagare, ultime quote pagate, prove
   caricate.
3. **Tre bottoni grandi**: *Carica un pagamento* (scegli se sono quote del
   club o un ordine dello Shop, poi che cosa, scatta la foto, fatto),
   *Iscrivi a una gara*, *Ordina materiale*.
4. Aggiungere un figlio: nome, cognome, data di nascita. Il piano lo sceglie
   il sistema dall'età.

Nessun termine tecnico, nessun passaggio che si possa evitare.

## Automatismi (Celery beat)

| Quando | Cosa |
|---|---|
| 1° del mese, 03:00 | Genera le quote mensili di ogni atleta `ACTIVE` con il piano dell'età federale di quell'anno (a gennaio il cambio di gruppo, con l'avviso al titolare) |
| 1° gennaio, 03:30 | Anno nuovo: iscrizioni dell'anno e quote socio dei genitori |
| 1° settembre, 03:30 | Nuova stagione: ricalcola i piani per età federale (salvo `plan_locked`) |
| Ogni giorno, 08:00 | Avvisi: quote scadute, certificati in scadenza/scaduti, tesseramenti in scadenza, scadenze iscrizioni gare |
| Ogni giorno, 01:00 | Chiude le iscrizioni alle gare con scadenza passata e prepara (o manda) la richiesta di trasporto |
| Ogni giorno, 03:10 | I costi fissi del club diventano le spese del mese in corso (vedi "Contabilità") |
| Ogni ora, al minuto 5 | Avvisi della mensilità (1, 10, 15 alle 9:00 ora del club) e multa del 16 per i club che li hanno accesi (vedi "Avvisi della mensilità e multa") |

Ogni job gira club per club, solo sui club attivi, ed è idempotente
(vincoli UNIQUE, non flag applicativi). I promemoria
già inviati stanno in `club_reminders_sent` (UNIQUE su tipo, entità,
gradino): un avviso a 30 giorni, uno a 7, uno a scadenza passata, ciascuno
una volta sola. La segreteria può rilanciare a mano la generazione delle
quote del mese e l'inizio stagione (`/club/admin/jobs/...`).

## Sito pubblico

Il portale **JudoArteVida** (`/`, `/clubes`, `/clubes/<slug>`, `/judocas/<id>`,
`/eventos`, `/eventos/<id>`, `/ranking`, `/contactos`) presenta la rete dei club come una
federazione: chi è, i club attivi in un carosello (le schede per scegliere il
club sopra la copertina, `components/site/club-carousel.tsx`), gli eventi, il ranking, le
ultime medaglie, e come iscriversi. Non serve il login; il login resta a un
clic ("Entrar" in alto). Le API sono `GET /public-site/...`, senza
autenticazione (`club/site_router.py`, servizio `club/site.py`).

**Si scrive poco, il resto arriva da solo.** La segreteria scrive solo la
pagina del club (`club_sites`: frase, presentazione, città, copertina, logo,
colori, galleria, allenatori, contatti, social) dall'editor della pagina
(`/club/admin/site`, `club.manage`, solo il proprio club). Orario della
settimana (dai corsi attivi e i loro slot), eventi, judoka, medaglie e
ranking si calcolano dal gestionale a ogni lettura: una gara inserita compare
sul sito, un risultato corretto corregge il ranking pubblico. Il sito
ricarica i dati al massimo ogni minuto.

**Quando un club compare.** Solo se è `ACTIVE` **e** ha pubblicato la sua
pagina. Una pagina nasce in bozza; un club sospeso sparisce dal sito anche
con la pagina pubblicata. Per il sito un club non pubblicato non esiste:
404, nemmeno conoscendone l'indirizzo.

**Privacy degli atleti (GDPR: molti sono minorenni).** Regole non negoziabili:

- un atleta compare **solo se il genitore ha dato il consenso** (dal suo
  portale, `PUT /club/athletes/{id}/public-profile`, `club.family`, solo per
  i propri figli) **e il club lo ha pubblicato** (dall'editor). Il club non
  può pubblicare chi non ha il consenso; il consenso da solo non pubblica;
- deve essere un atleta `ACTIVE` di un club pubblico: chi lascia il club
  esce dal sito;
- **ritirare il consenso** toglie subito l'atleta dal sito, spegne la
  pubblicazione e la foto; un nuovo consenso non ripubblica da solo;
- di un atleta pubblico si mostrano **solo**: nome e iniziale del cognome
  ("Tiago M."), cintura e le date dei passaggi, club, fascia d'età del
  ranking (non la data di nascita), medaglie, punti, posto nel ranking,
  risultati e prove in programma, due righe, e ciò che la segreteria scrive
  per la scheda (profilo IJF, tecnica, guardia: vedi "La scheda del
  judoca"). La **foto solo se la famiglia l'ha permessa** (`show_photo`, un
  consenso a parte); altrimenti le iniziali. Lo stesso permesso vale per le
  foto e i video della scheda;
- **mai**: cognome intero, data di nascita, codice fiscale, peso, genitore,
  contatti, quote, certificati. Il servizio costruisce le risposte campo per
  campo e gli schemi pubblici (`club/site_schemas.py`) non dichiarano quei
  campi: un dato in più non può arrivare al browser per sbaglio;
- negli eventi, come in classifica, tutti gli iscritti dei club pubblici
  compaiono come «Nome I.» con club, fascia e cintura; foto e link alla
  scheda solo per chi ha il consenso (`has_page`);
- le pagine dei judoca non si indicizzano (`noindex`): un minore non deve
  finire nei motori di ricerca con il suo nome;
- ogni consenso, ritiro e pubblicazione va nell'audit con chi l'ha deciso
  (`consent_by_user_id`).

**Gli allenatori** si presentano a mano nell'editor (nome, ruolo, foto): un
account da istruttore non è un consenso a comparire sul web.

**Le foto** vanno nel bucket pubblico dei media (`upload_media`, come le foto
degli atleti): JPG, PNG o WebP fino a 5 MB, galleria di al massimo 24 foto.
Gli indirizzi (mappa, sito) devono essere `http(s)://`. **I social** solo
verso il loro sito e in https (`site.check_social_url`): Facebook
(`facebook.com`, `fb.com`), Instagram (`instagram.com`), YouTube
(`youtube.com`, `youtu.be`), con un percorso (la home di Facebook non è il
club). Chi incolla `facebook.com/club` senza `https://`, o con `http://`,
non riceve un errore: si completa in https. Un'icona di Facebook che porta
altrove sarebbe un inganno.

### Il calendario degli eventi (`/eventos`)
- Tre viste (`components/site/events-explorer.tsx`): **lista** per mese
  (con salto al mese), **calendario** mensile (un evento di più giorni
  compare in ogni giorno; un clic su un giorno ne mostra gli eventi) e
  **anno** (12 mesi, i giorni con eventi colorati per tipo).
- Si naviga mese per mese o anno per anno, anche indietro, con "Oggi".
- Ricerca immediata (nome, luogo, organizzatore, senza accenti) e filtri
  per tipo, livello, club ("rede" = solo il calendário comune; un club =
  i suoi eventi e quelli della rete a cui partecipano i suoi atleti),
  escalão, "iscrizioni aperte". Lo stato è nell'URL: una ricerca si
  condivide.
- Il browser scarica un anno alla volta da `/public-site/events?from=&to=`
  (fino a 500 eventi) e filtra da sé. Per ogni evento: orario, costo
  d'iscrizione (`price_cents`, dell'organizzatore), escalões, trasporto,
  circolare, **numero** di iscritti (mai i nomi).
- Le testate di `/eventos`, `/ranking` e `/clubes` (`page-hero.tsx`) usano
  le foto già pubblicate dai club (`/public-site/photos`: copertine e
  gallerie), con animazioni leggere che si fermano con "riduci movimento".

### Il dettaglio di un evento (`/eventos/<id>`)

- **A sinistra la scheda pratica**, una riga con icona per voce: date e ora
  (con «tra N giorni»), luogo (link a Google Maps, si apre solo al tocco),
  organizzatore, livello, fasce d'età, quota, scadenza delle iscrizioni (con
  «mancano N giorni»), iscritti / posti, la circolare ufficiale, il club
  organizzatore (al suo sito) e «Vuoi partecipare?». Sul computer resta
  ferma mentre si scorre.
- **Gli iscritti come il ranking** (`components/site/event-participants.tsx`,
  con `ClubLogo`, `Place`, `initials` di `ranking-explorer.tsx`): foto o
  iniziali con il logo del club, fascia, categoria, cintura; a gara finita
  medaglia, piazzamento e punti con la barra. Chi ha la scheda si apre nel
  popup del judoca (`JudokaModal`), come nel ranking. Ricerca oltre gli 8
  iscritti, pagine da 20.

### La pagina del club

`/clubes/<slug>` è la pagina del club come una pagina Facebook, ma sua:

- **i colori del club** (`club_sites.brand_primary`, `brand_secondary`,
  `brand_accent`, "#RRGGBB" o vuoti; vuoti = i colori di JudoArteVida,
  #E13F22 e #F3E017). Principale: copertina, bottoni, titoli. Secondario:
  le luci sfumate della copertina e i fondi. Accento: ciò che spicca sulla
  parte scura (il bottone "Inscrever" in fondo, le scritte piccole). Un
  colore mancante prende il posto dell'altro prima di ricadere su JAV;
- **il tema lo calcola l'API** (`club/brand.py`, campo `theme` della
  pagina) e il browser lo usa così com'è, come variabili CSS sul
  contenitore della pagina (token `club-*` in `globals.css`, che fuori
  dalla pagina valgono i colori di JAV). Regole: il testo su un fondo è
  bianco o quasi nero, quello che contrasta di più; per i titoli sul bianco
  il principale si scurisce finché arriva a 4,5:1 (WCAG AA); l'accento
  sulla parte scura si schiarisce fino a 4,5:1; la copertina parte dal
  principale scurito quanto serve per il testo bianco (3:1) e finisce
  scura. L'editor rifà lo stesso calcolo in `lib/brand.ts` per
  l'anteprima dal vivo e avvisa con parole semplici quando il principale è
  stato scurito o l'accento è troppo simile al principale. Un valore che
  non è un colore si rifiuta (e un CHECK nel database lo ripete): nel CSS
  della pagina non finisce altro che un colore;
- **copertina** (la foto `hero_image_url`, velata nei colori del club; senza
  foto il tatami) e **logo rotondo** che sporge dalla copertina; nome, città,
  i numeri del club (atleti attivi, gruppi, allenamenti a settimana,
  allenatori, medaglie: contati, mai scritti; quelli a zero non si dicono),
  i bottoni **Inscrever** (`/c/<slug>`) e **Enviar mensagem** (scende al
  modulo), le icone dei social;
- **le schede** (`components/site/club-tabs.tsx`): una barra di bottoni
  grandi con icona che resta in alto, e sotto **una scheda alla volta**:
  Início (presentazione, "desde 35 €/mês", Informações, numeri, pilastri,
  l'ultima novità), **Horários e preços** (una card per gruppo: numero,
  età, mensilità in grande, allenamenti, "Inscrever neste grupo"; poi la
  settimana come calendario, colorata per gruppo), Treinadores, Fotos e
  vídeos, Novidades (post e storia), Competição (provas, ranking,
  medaglie), Contactos (informazioni, mappa, modulo). Una scheda vuota non
  c'è. La scheda sta nell'indirizzo (`#horarios`; i vecchi `#mensagem`,
  `#grupos`, `#fotos`... aprono la scheda giusta) e "indietro" torna alla
  precedente; tutte le schede sono nell'HTML, nascoste, non caricate dopo;
- **Grupos e preços** sono i gruppi di JAVBOT: ogni piano attivo con la sua
  fascia d'età e gli allenamenti dei corsi la cui età lo tocca
  (`site.plan_slots`, la stessa funzione del bot); mensilità, iscrizione,
  giorno di scadenza e descrizione del piano **solo con "Mostra i prezzi"**
  (`show_prices`), altrimenti "chiedi i prezzi al club" che porta al
  modulo. Nell'API i campi si chiamano `monthly_price_cents`: "fee" resta
  la parola delle quote di una famiglia, che il sito non mostra mai;
- **Ranking do clube**: i primi dieci del club nel ranking della stagione,
  lo stesso calcolo di `/ranking` (stesse regole: solo judoca con consenso
  e pubblicati, mai gli atleti dei corsi JAV), ognuno con il link alla sua
  scheda; poi le ultime medaglie;
- **il mini-sito** (migrazione 0012, tutto scritto dalla segreteria
  nell'editor; una parte vuota non compare, e nemmeno la sua scheda):
  anno di fondazione (`founded_year`, dal 1882: diventa "desde 2004" e il
  riquadro "anos de judo") e sede (`venue`); **i numeri del club**
  (`highlights`, al massimo 6, "40+ · anos de judo": quelli che il club dice
  di sé, accanto a quelli che il portale conta); **Porquê treinar connosco**
  (`pillars`, 6); **la storia** (`history`, 20 tappe, sempre in ordine di
  anno); **le novità** (`news`, 30, come i post di Facebook: data, titolo,
  testo, foto caricata con lo slot `news`, link http(s); dalla più
  recente); **i video** (`videos`, 12: si incolla il link di YouTube, si
  salva solo l'id, come nella scheda del judoca). Gli allenatori hanno anche
  **grado** e **due righe**. `site._clean_*` ripulisce tutto (righe vuote
  tolte, limiti, indirizzi);
- **i video del canale**: se il link YouTube del club è un canale
  (`/channel/UC...`), gli ultimi video compaiono da soli dopo quelli scelti
  (`GET /public-site/clubs/{slug}/videos`, lo stesso feed con cache di
  mezz'ora del portale, `club/videos.py`); un `@nome` non si risolve senza
  le API di Google e resta solo il bottone verso il canale;
- **"Próximo treino"**: sotto la frase, il prossimo allenamento (o "a
  decorrer agora") calcolato nel browser dall'orario del club, all'ora di
  Lisbona; sul server non si disegna, così non c'è un'ora sbagliata;
- **la mappa si carica solo se la si chiede** ("Mostrar o mapa"): un iframe
  di Google all'apertura manderebbe a Google ogni visitatore senza
  consenso. Prima c'è l'indirizzo con "Como chegar";
- **sul telefono**, dopo la copertina, una barra in basso con "Inscrever" e
  "Mensagem", che sparisce quando si arriva al modulo;
- **in fondo, "Envie uma mensagem ao clube"**: il modulo che scrive al club
  (vedi "Messaggi dal sito");
- SEO: titolo, descrizione (la frase del club), indirizzo canonico,
  anteprima di un link condiviso con copertina e logo. Le animazioni sono
  quelle del sito (`Reveal`) e rispettano "riduci movimento".

### Messaggi dal sito

Chiunque può scrivere a un club dalla sua pagina, o a JudoArteVida da
`/contactos` (`club/contact.py`, tabella `contact_messages`). Su
`/contactos` sceglie **a chi** (JudoArteVida o un club: allora il messaggio
è di quel club) e **di che cosa** (`topic`: GENERAL, SPONSOR, ENROLMENT,
EVENTS, OTHER); su `/patrocinadores` il modulo manda sempre `SPONSOR`. La
casella mostra l'argomento e filtra per argomento; lo staff della
piattaforma parte da «Tutti» (i messaggi a JAV e quelli dei club, con il
nome del club):

- `POST /public-site/clubs/{slug}/message` (solo un club che il sito mostra:
  a una pagina in bozza, sospesa o all'unità dei corsi JAV non si scrive,
  404) e `POST /public-site/contact` (a JAV). Nome, email, telefono
  facoltativo, messaggio (10–4000 caratteri), lingua, e **il consenso a
  essere ricontattati** (GDPR): senza, il messaggio non si accetta. I dati
  servono solo a rispondere;
- **contro lo spam, senza captcha esterni**: un campo trappola nascosto
  (`website`: chi lo riempie riceve "inviato" e non si salva niente: un
  robot non deve capire che cosa lo ha fermato), il limite per IP del
  router (`core/rate_limit.py`, 5 ogni 10 minuti) e, siccome quel limite
  lascia passare se Redis non risponde, **un tetto nel database**: 5
  messaggi l'ora per mittente. Dell'IP si salva solo l'impronta (sha256 con
  il segreto del server), dello User-Agent i primi 200 caratteri;
- il messaggio **si salva** e poi: **notifica** `CONTACT_MESSAGE` alla
  segreteria del club (come i messaggi di JAVBOT), o agli amministratori
  della piattaforma (SUPER_ADMIN, ORGANIZATION_ADMIN, ADMIN) se è scritto a
  JAV; **email** all'email di contatto della pagina del club (poi a quella
  delle impostazioni del club), o a `info@judoartevida.com`
  (`JAV_CONTACT_EMAIL`), con "Rispondi" (Reply-To) verso chi ha scritto, in
  portoghese. L'email è una cortesia: senza SMTP, senza indirizzo o con il
  server di posta giù non parte (`emailed_at` resta vuoto) e la richiesta
  riesce lo stesso (CLAUDE.md §5). Un club senza email riceve il messaggio
  solo nella casella: non va a JAV, perché è scritto al club;
- **le caselle "Messaggi"**: la segreteria (`club.manage`) vede solo quelli
  del suo club (`/club/admin/messages`, il club lo decide `club/scope.py`);
  la console di JudoArteVida (`/contact-messages`, `clubs.enter`, solo
  account senza club) quelli scritti a JAV, e con `clubs.manage`
  (superadmin) anche quelli di un club o tutti (`?club=<id>|all`).
  Ognuno si segna letto, da leggere, archiviato (`NEW` / `READ` /
  `ARCHIVED`, ogni cambio nell'audit) e si risponde con "Rispondi via
  email" (si apre il programma di posta, già compilato). Nell'unità dei
  corsi JAV la sezione non c'è.

### La scheda del judoca

`/judocas/<id>` è la pagina personale di ogni judoca pubblico, in stile
scheda IJF: ritratto sul gradiente del club, nome, club, cintura, Portogallo,
i numeri chiave (posto nel ranking della sua fascia nella stagione, punti
della stagione e di sempre, medaglie, gare), la scheda (club, fascia,
categoria, cintura, tecnica, guardia), e le **schede** (`judoka-tabs.tsx`)
Risultati, Prossime gare, Biografia, Foto, Video e Percorso (le cinture con
le date). Biografia, Foto e Video ci sono sempre, con un messaggio quando
sono vuote; `#fotos` nell'indirizzo apre la scheda giusta. La biografia
arriva fino a 1500 caratteri (`site.BIO_MAX`, migrazione 0030). Il ranking (pagina
`/ranking`, home, pagina del club) porta ogni nome e il podio alla scheda.
API: `GET /public-site/judoka/{id}`, la stessa di prima con più campi.

- **Si calcola quasi tutto**: risultati, prove in programma (iscrizioni
  `REGISTERED` a eventi non ancora finiti), posto nel ranking (lo stesso
  calcolo di `/ranking`, fascia d'età e stagione dell'atleta), medaglie e
  percorso delle cinture (`club_belt_grades`). Solo eventi dei club pubblici:
  un evento che il sito non mostra non compare nemmeno nella scheda.
- **La categoria** è il testo scritto sull'iscrizione a una gara ("-38 kg"),
  quello dell'ultima gara fatta (o della prossima): lo stesso che i risultati
  mostravano già. Il **peso** dell'atleta non esce mai.
- **La segreteria scrive** (`club.manage`, scheda dell'atleta → "Pagina
  pubblica", o Sito → Judoka sul sito): link al profilo IJF, due righe (le
  stesse della famiglia: le correggono entrambi), tecnica preferita, guardia
  (sinistra/destra). Il link IJF è accettato **solo** verso le schede
  ufficiali, in https: `www.ijf.org/judoka/<numero>` o JudoBase
  (`judobase.ijf.org/#/competitor/profile/<numero>`); il bottone "Vedi
  profilo IJF" compare solo se c'è. API: `GET|PUT
  /club/admin/site/athletes/{id}/page`.
- **Foto e video**: la segreteria carica le foto (bucket pubblico dei media,
  JPG/PNG/WebP fino a 5 MB, al massimo 24) e aggiunge i video **solo di
  YouTube** (al massimo 12): del video si salva l'id, il sito lo incorpora
  con `youtube-nocookie.com` e nessun indirizzo scritto a mano finisce in un
  iframe. Ogni elemento **nasce non pubblicato** e si pubblica a parte
  (`POST .../page/photos`, `POST .../page/videos`, `PATCH|DELETE
  .../page/media/{id}`). Sul sito compaiono solo se pubblicati **e** se la
  famiglia ha permesso la foto: foto e video di gara mostrano il volto, e
  quel permesso è della famiglia. Ritirare il consenso li rimette tutti non
  pubblicati; un nuovo consenso non li ripubblica.
- **La famiglia** non gestisce foto e video: decide il consenso, la foto
  (che vale anche per la galleria e i video) e le due righe. È la regola di
  sempre: il consenso è della famiglia, la vetrina del club.
- La segreteria **può preparare** la scheda anche prima del consenso: nessuno
  la vede finché la famiglia non lo dà e il club non pubblica l'atleta. Il
  link "Vedi la pagina pubblica" compare solo quando la pagina è davvero
  visibile.
- **Gli atleti dei corsi JAV non hanno scheda**: `site._publishable_club`
  li toglie dal sito anche con media pubblicati, e nell'unità dei corsi le
  rotte della scheda rispondono con un messaggio (l'interfaccia lo spiega
  invece del modulo). Dopo il passaggio a un club, foto e video caricati
  altrove non seguono l'atleta: la scheda mostra solo quelli del club
  attuale.
- Anche la scheda è `noindex`, come ogni pagina di judoca; l'anteprima di un
  link condiviso (OpenGraph) usa la foto solo quando la famiglia l'ha
  permessa.

## JAVBOT

L'assistente in chat, su **ogni pagina dell'area privata** (il bottone rosso
in basso a destra, montato una volta in `components/app-shell.tsx`) e,
in una versione più semplice, **sul sito pubblico** (`components/site/site-shell.tsx`).
Il backend è `apps/api/app/domains/javbot/`. I due JAVBOT sono diversi
apposta:

- **quello del sito** resta semplice e deterministico (parole chiave in
  portoghese, italiano e inglese, `javbot/public.py`): risponde a poche cose
  generiche su club, orari, iscrizioni, eventi;
- **quello dell'area riservata** è un modello vero (Claude,
  `javbot/assistant.py`) con gli strumenti di `javbot/tools.py` e la **base
  di conoscenza** dei PDF (sotto). Il pianificatore a parole chiave
  (`javbot/planner.py`) resta per i percorsi guidati che scrivono e come
  rete di sicurezza.

### Il microfono

> **Oggi è nascosto** (`VOICE_INPUT_ENABLED = false` in
> `components/javbot/use-voice-input.ts`): con 2 CPU la trascrizione
> impiegava circa 10 secondi e sbagliava parole. Il servizio `stt` sta dietro
> il profilo compose **`voice`**: `up -d` non lo avvia e non occupa memoria.
> Per riaccenderlo: `true` lì, `docker compose -f docker-compose.dev.yml
> --profile voice up -d stt`, e un server più potente o un modello migliore.

Nei due JAVBOT, accanto al campo di testo, c'è il bottone 🎤: si parla
invece di scrivere. Il browser registra (al massimo un minuto, `MediaRecorder`:
opus su Chrome/Firefox/Android, mp4 su Safari/iPhone), l'audio va a
`POST /javbot/transcribe` (area, 8 al minuto per utente) o
`POST /public-site/bot/transcribe` (sito, 12 ogni 5 minuti per IP), e l'API
lo gira al servizio **`stt`** (`apps/stt`): Whisper `small` int8 sul nostro
server, nella sola rete dei container. Il testo torna **nel campo**, non
parte da solo: chi parla lo rilegge, lo corregge e lo invia.

- **La voce non si salva**: resta in memoria per la durata della richiesta,
  né l'API né `stt` scrivono file o il contenuto nei log. Nessun fornitore
  esterno. È nella Política de Privacidade.
- **Lingua**: quella dell'interfaccia (pt/it/en) come indizio a Whisper.
- **Velocità** (2 CPU): circa 1,5 secondi di attesa per secondo di voce;
  una trascrizione per volta, le altre in fila fino a 20 secondi, poi «riprova».
  Il modello si cambia con l'argomento di build `WHISPER_MODEL` (`base` è tre
  volte più veloce e sbaglia di più).
- **Memoria**: circa 750 MB, limite del container 1,2 GB.
- `STT_URL` (predefinito `http://stt:8001`) vuoto spegne il microfono (le
  rotte rispondono «non disponibile»). Codice: `javbot/voice.py`,
  `components/javbot/use-voice-input.ts`. Test: `tests/test_javbot_voice.py`.

### Che cosa sa fare

Nell'area privata (`/api/javbot/...`, qualsiasi utente con una sessione):

| Chiede | Risponde / fa |
|---|---|
| "Quanto devo pagare?" | Le quote da pagare per figlio (più la quota socio), quelle scadute, la prossima scadenza, IBAN e intestatario del club, il bottone "Carica un pagamento" |
| "Quanto ho pagato?" | Pagato nell'anno e da sempre, per persona, gli ultimi 6 pagamenti con data, lo Shop dell'anno, i risparmi, quanto resta da pagare (scaduto compreso) e il credito — gli stessi numeri di "I miei conti" (`accounting.personal_account`), con il bottone per aprirli |
| "Ho debiti?" / "Estou em dívida?" | Come "Quanto devo pagare?": un genitore senza `club.manage` che usa parole della segreteria ("em dívida") riceve le sue quote, non l'elenco dei morosi |
| "Cosa sai di me?" | Il riepilogo: ogni atleta in una riga (età, piano, cintura, certificato, allenamenti del mese), pagato nell'anno, da pagare, credito |
| "I miei dati" | Nome, email, telefono, codice fiscale e residenza dell'utente; per ogni atleta nascita ed età, piano e mensilità, tessera federale, peso, iscritto dal, certificato. Chi non ha `club.family` vede solo i suoi dati |
| Cinture, presenze, ranking | Cintura attuale e da quando; allenamenti del mese, della stagione e da sempre; punti della stagione, medaglie, livello, traguardi, prossima gara. Un nome nella domanda ("che cintura ha Luca?") restringe a quell'atleta. Nei corsi JAV niente cinture né gare |
| "Come carico la ricevuta?" / "non funziona" | Prima chiede *che cosa* si è pagato (quote del club o ordine dello Shop), poi i passi; controlla i casi tipici: niente da pagare, nessun ordine in attesa di bonifico, file non JPG/PNG/PDF o oltre 15 MB, foto HEIC dell'iPhone, bottone grigio |
| "Voglio un judogi" | Per quale figlio (se più d'uno) → altezza → taglia (tabella in `javbot/sizes.py`: la decina di cm sopra, tra 100 e 200) → il judogi del catalogo in quella taglia (o una sopra) con il **prezzo calcolato da `jav_market.get_quote`** → indirizzo dal profilo → **"Confermi?"** → l'ordine (`jav_market.create_order`, bonifico, per quell'atleta). Senza judogi nel catalogo propone di avvisare la segreteria |
| Certificati, gare aperte, lezioni di oggi | Stato del certificato per figlio; gare con iscrizioni aperte e chi può iscriversi; lezioni di oggi con il bottone "Segna presente" (`lessons.family_mark`, solo oggi) |
| "Invita un amico", "il mio credito" | Il link personale (`club/referrals.py`) con il bottone per copiarlo; il saldo del wallet |
| "Parlare con la segreteria" | I contatti del club e, se l'utente scrive il messaggio, una notifica alla segreteria del club (dopo conferma) |
| Segreteria: "chi non ha pagato?", "certificati scaduti" | Mensilità del mese ancora da pagare, certificati scaduti/mancanti/in scadenza — solo con `club.manage` |
| Staff: "lezioni di oggi" | Le lezioni di oggi (tutte per la segreteria, le proprie per un istruttore, `club.instruct`) |

Le risposte sono nella lingua dell'interfaccia (il cookie `jav_lang`, che la
dashboard manda con ogni messaggio); le frasi stanno in `javbot/texts.py`.
Sotto la risposta possono esserci bottoni: vai a una sezione, apri
"Carica un pagamento", conferma / annulla, copia il link.

Sul sito (`POST /api/public-site/bot`, senza login): che cos'è
JudoArteVida, i club pubblicati, l'orario della settimana di un club (dai
corsi, come la pagina del club), come iscriversi (`/c/<slug>`), i prossimi
eventi, perché il judo, i contatti del club, i gruppi per età, i prezzi e
gli sconti.

**La scheda del club** ("quanto costa la mensilità di Lagos", "preço judo
Lagos", "quotas", "inscrição", "grupos e idades", "a partir de que idade";
intenzioni `prices` e `groups`, stessa risposta; il club si riconosce anche
dalla città scritta nel messaggio). Si costruisce **solo da ciò che il club
ha configurato** (strumento `public_club_info`), niente si inventa:

- ogni piano attivo è un gruppo: nome e fascia d'età, e gli allenamenti
  del gruppo, cioè i turni dei corsi la cui fascia d'età tocca quella del
  piano (un corso senza età non si attribuisce);
- con "Mostra i prezzi sul sito" (`club_sites.show_prices`, spento per
  default) anche: mensilità, iscrizione annuale, "paga-se até ao dia N"
  (`due_day`), i mesi in cui si paga se non sono tutto l'anno
  (`billing_months`), la descrizione del piano (dove il club scrive, per
  esempio, le aule avulse); poi le altre quote (quota socio del genitore, la
  regola del pro rata, ciò che l'iscrizione comprende — solo se il club lo
  ha scritto in `enrollment_includes`, il testo di default non esce) e gli
  sconti (escalão, judo adattato, famiglia, invita un amico). **Ciò che è a
  zero non si nomina**: uno sconto a 0 è uno sconto che il club non fa;
- senza "Mostra i prezzi": gruppi, età e allenamenti sì; i soldi "li dà il
  club", con i contatti. Anche la descrizione del piano resta fuori, perché
  può contenere importi;
- senza piani attivi: "il club non ha ancora pubblicato gruppi ed età",
  i contatti e l'orario, invece di far credere che nasconda i prezzi.

**Gli sconti** ("como faço para ter um desconto", "come ottengo uno
sconto", "irmãos", "judo adaptado"; intenzione `discounts`): quelli accesi
nel club, con che cosa fare per averli (documento dell'escalão alla
segreteria, stesso account di famiglia, il link personale dell'invito, che
dà credito nel wallet, non uno sconto diretto). Senza "Mostra i prezzi" solo
i nomi degli sconti e i contatti; senza sconti accesi lo dice.

I corsi JAV nelle scuole dicono **sempre** la loro mensilità (dai piani
dell'unità, di regola 25 € senza iscrizione): è una regola di JAV, non una
scelta di un club.

Per caricare la tabella prezzi ufficiale nei club della rete c'è
`apps/api/scripts/load_official_prices.py` (prova di default, `--apply` per
scrivere, idempotente; uso nel docstring), con gli orari di Lagos e di
Alvor (Grupo 1 martedì e giovedì 18:30–19:30; Grupos 2 e 3 lunedì,
mercoledì e venerdì 19:00–22:00, dagli 8 anni); Albufeira senza orario
finché il club non lo dà. Logo, colori e social dei tre club li mette
`apps/api/scripts/load_club_branding.py` (stesso stile; i loghi ripuliti
sono in `scripts/club_branding/`, un logo già caricato non si sostituisce
senza `--replace-logo`).

### Regole di sicurezza

- **Gli strumenti hanno i permessi delle rotte.** Ogni strumento
  (`javbot/tools.py`) chiede lo stesso permesso della rotta equivalente
  (`club.family` solo sulla propria famiglia, `club.manage`, `club.instruct`)
  e lavora sul club che decide `club/scope.py`, mai su uno nominato in chat.
  Il pianificatore non può aggirarli: li chiama come chiunque altro.
- **Nessun importo calcolato da JAVBOT.** Le quote arrivano da
  `club/service.py`, i prezzi dello Shop da `get_quote`, l'ordine li
  ricalcola in `create_order`.
- **JAVBOT scrive solo dopo un sì esplicito.** Ogni azione (ordine,
  messaggio alla segreteria, presenza) nasce come compito `PENDING`
  (`javbot_tasks`) con tutto ciò che serve; il bottone "Conferma" o un "sì"
  scritto lo eseguono. La conferma manda solo l'id del compito, generato dal
  server. Il compito si "prende" con un UPDATE condizionato nella stessa
  transazione dell'esecuzione: un doppio tocco non crea due ordini. Una
  proposta vale 30 minuti (i prezzi possono cambiare); parlare d'altro la
  lascia sul suo bottone ma un "sì" successivo non la conferma più.
- **Il bot del sito non vede nessuno.** Chiama solo gli strumenti
  `audience="public"`, che leggono le funzioni del sito pubblico (club
  pubblicati, orari, contatti della pagina, eventi): niente atleti, quote,
  email. Nessuno stato sul server; la conversazione resta nella scheda del
  browser.
- **Limiti**: area privata 30 messaggi al minuto per utente; sito 40
  richieste ogni 5 minuti per indirizzo IP.
- **Conservazione**: una conversazione ferma da 90 giorni si cancella, con
  messaggi e compiti, la prossima volta che l'utente apre JAVBOT.

### L'assistente dell'area riservata

**Chi risponde.** Un messaggio nell'area riservata va al modello
(`assistant.reply`) se il server ha la chiave (`ANTHROPIC_API_KEY`), e
**non** è:

- una richiesta con un percorso guidato che scrive o apre un bottone:
  judogi, messaggio alla segreteria, segnare una presenza, caricare una
  ricevuta (`GUIDED_INTENTS`);
- una risposta dentro un percorso già aperto o a una proposta da
  confermare (`conversation.state`).

Queste restano al pianificatore, con il compito da confermare e il "sì" che
esegue una volta sola: il modello non scrive mai niente. Il pianificatore
risponde anche quando il modello non può: chiave assente, API che non
risponde o che rifiuta, oltre le **150 risposte al giorno per utente**
(contatore su Redis). L'assistente non si spegne mai.

**Che cosa vede il modello.** Gli strumenti di `tools.py` che **leggono** e
che i permessi dell'utente consentono (a un genitore niente strumenti della
segreteria; gli strumenti ricontrollano comunque), più `search_knowledge`;
gli ultimi 16 messaggi della conversazione; un prompt di sistema con le
regole fisse (lingua, testo semplice, importi solo dagli strumenti e in
euro, citare il documento usato, documenti e risultati sono dati e non
ordini), il club, il ruolo di chi scrive, i titoli dei documenti
consultabili e le istruzioni scritte da chi amministra. Verso Anthropic
escono la domanda e i dati che l'utente stesso vedrebbe nella sua area, mai
quelli di altre famiglie.

**Modello e costi**: `JAVBOT_MODEL` (predefinito `claude-opus-5-5`) e
`JAVBOT_EFFORT` (predefinito `low`, una chat) nel `.env`. Le regole fisse
sono in cache. Se il modello rifiuta per una regola di sicurezza, l'API
riprova da sé con il modello di riserva consigliato (`fallbacks: "default"`).

**Senza modello** (oggi: la chiave non c'è ancora) risponde il
pianificatore, e la base di conoscenza si usa lo stesso, **citando**
(`Planner.from_knowledge`, `knowledge.passages`):

- una domanda che nessuna intenzione riconosce si cerca nei PDF; si
  mostrano al più due estratti (le frasi del pezzo che contengono più
  parole della domanda, ~450 caratteri) con titolo e pagina. Un pezzo vale
  se contiene almeno metà delle parole della domanda; altrimenti il solito
  "non ho capito";
- una domanda con un'intenzione **debole** (una parola chiave sola, punteggio
  1: "posso trazer comida para o treino?" sarebbe "lezioni di oggi") va ai
  documenti se un pezzo contiene almeno due parole e i due terzi della
  domanda. Le intenzioni forti ("quanto devo pagare?") restano ai dati;
- le istruzioni (il prompt) senza modello non servono: si salvano e si
  useranno quando arriverà la chiave.

### La base di conoscenza

`javbot/knowledge.py`, tabelle `javbot_knowledge_documents`,
`javbot_knowledge_chunks`, `javbot_instructions` (migrazione 0015).

- **Due livelli, sempre insieme.** La base **comune** a tutti i club la
  gestisce la piattaforma (console → JudoArteVida → JAVBOT, permesso
  `clubs.manage`); la base **del club** la gestisce la sua segreteria
  (sezione "JAVBOT" del club, `club.manage`, o la piattaforma entrando nel
  club). Un utente di un club consulta la comune e la sua, mai quella di un
  altro club. La segreteria vede i documenti comuni ma non li apre né li
  cancella.
- **Istruzioni** (il "prompt"): una comune e al più una per club, fino a
  8.000 caratteri. Valgono tutte e due; se si contraddicono, per quel club
  vale quella del club. I testi lunghi vanno caricati come PDF.
- **I PDF**: solo PDF con testo, fino a 15 MB, al massimo 200 documenti per
  livello. Il file va nel bucket **privato** (si apre con un URL presigned
  di 5 minuti); il testo si estrae con `pypdf` al caricamento. Una
  scansione senza testo resta in elenco come "Senza testo" (`EMPTY`) e
  l'assistente non la usa: si dice a chi l'ha caricata, non si inventa
  niente.
- **Come si cerca.** Il testo si divide in pezzi di circa 1.500 caratteri
  (con 200 di sovrapposizione, a fine frase quando si può), si salva
  normalizzato (minuscolo, senza accenti) e si cerca con il full-text di
  Postgres in configurazione `simple`, che va bene per le tre lingue
  insieme. Le parole della domanda valgono come prefisso, così plurali e
  coniugazioni si trovano. Niente embedding e niente modelli sul server:
  la ricerca la formula il modello, che può riprovare con altre parole o
  nella lingua del documento.

### Il gancio nella pagina della famiglia

Il bottone "Carica un pagamento" di JAVBOT va alla scheda del club e chiede
a `family-home.tsx` di aprire il suo `PayModal`, con
`requestJavbotPay("fees" | "choose")` (`lib/javbot.ts`). La pagina lo
riceve con una riga: `useJavbotPayRequest(setPay);` — anche se la richiesta
arriva mentre la scheda si sta ancora aprendo.

## Cursos JAV

JudoArteVida non è un club: gestisce i club e, in più, i **corsi
extrascolastici di judo nelle scuole** (primarie e secondarie che chiedono
un corso come attività extrascolastica). Sono corsi per bambini: niente
cinture, niente gare, niente ranking; chi vuole fare sul serio poi passa a
un club ufficiale.

### L'unità e i corsi

- I corsi stanno in **un'unità sola**, un `clubs` con `kind = JAV_COURSES`
  (gli altri sono `CLUB`). Al massimo una per organizzazione (indice UNIQUE
  parziale). La crea il superadmin dalla console ("Cursos JAV" 🏫, accanto
  a "Tutti i club", `POST /clubs/jav-courses`, idempotente) con un piano di
  default: **25 € al mese, iscrizione 0, dai 3 anni**, mesi set–giu,
  modificabile.
- Ogni corso (`club_courses`) si tiene **in una scuola** (`venue_name`,
  `venue_address`, `venue_city`) e si amministra per conto suo: iscritti,
  presenze, quote, incassi, parte del treinador. Ha un treinador
  responsabile (`instructor_user_id`) con la sua percentuale
  (`coach_share_pct`, default 50), un testo per le famiglie
  (`public_description`), il nome del treinador come compare sul sito
  (`public_coach_name`, scritto a mano: un account non è un consenso a
  comparire) e `published` per la sezione pubblica. In un club ufficiale
  questi campi restano vuoti: lì lo staff è pagato a ore.
- Le differenze per tipo stanno **in un posto solo**, `club/kinds.py`
  (`KindRules`): chi deve sapere se un'unità ha cinture, gare, ranking,
  iscrizioni, commissione, chiede a `rules_for`, non confronta stringhe.

### Regole dell'unità

| | Club ufficiale | Cursos JAV |
|---|---|---|
| Cinture | bianca all'iscrizione, passaggi di grado | nessuna: creare un atleta con una cintura e registrare un passaggio sono rifiutati con un messaggio |
| Gare, stage, ranking, medaglie | sì | no: creare una gara è rifiutato; il ranking del club è vuoto |
| Iscrizione annuale | dal piano | sempre 0 (un piano con iscrizione > 0 è rifiutato) |
| Quota socio del genitore | default 60 € | sempre 0 (è una regola, non un default) |
| Sconti escalão, famiglia, invito | default 25% A, 5 € famiglia, 5 € invito | default 0: sono soldi di JAV, li attiva JAV se vuole |
| Commissione della piattaforma | default 10%, la decide il superadmin | sempre 0%, non modificabile: i soldi sono già di JAV |
| Treinador | a ore (cartellino × tariffa) | percentuale degli incassi del suo corso |
| Sito pubblico | carosello, pagina, judoca con consenso | solo i corsi pubblicati, **mai le persone** |

### La mensilità va al corso, e ci resta

- Ogni mensilità dell'unità porta **congelati** il corso (`club_fees.course_id`),
  il treinador responsabile (`coach_user_id`) e la sua percentuale
  (`coach_share_pct`) **del momento in cui è emessa**, come il prezzo. Se
  l'atleta cambia corso, o il corso cambia treinador o percentuale, i mesi
  già emessi non si muovono: valgono per le quote emesse da lì in poi.
- **Un atleta, una mensilità**: chi va a due corsi paga una quota sola,
  attribuita al **primo corso attivo a cui si è iscritto** (a parità, l'id
  più basso: il risultato non dipende dall'ordine delle righe). La quota è
  per bambino, non per corso.
- **Senza corso**: un atleta aggiunto senza sceglierlo ha la mensilità senza
  corso; la segreteria la vede in una riga a parte ("Quote senza corso"), e
  appena l'atleta si iscrive a un corso le sue quote **ancora da pagare e
  senza corso** passano a quel corso. Un'attribuzione già fatta non cambia
  mai, e un incasso già entrato resta dov'era.
- Alla creazione dell'atleta il corso si sceglie subito (`course_id` in
  `POST /club/athletes`): l'iscrizione al corso avviene prima delle quote,
  così la mensilità del mese nasce già attribuita.
- Un corso senza treinador responsabile non ha parte del treinador: la
  quota va tutta a JAV.

### I conti

- **Parte del treinador** = per ogni mese, la sua percentuale delle
  mensilità del corso **pagate** in quel mese (principio di cassa, come
  l'incasso), raggruppate per corso, treinador e percentuale congelati e
  arrotondate al centesimo (metà in su). Nel conto economico dell'unità è
  un costo come lo staff a ore ("Parte del treinador", anche nel libro cassa
  come riga calcolata); ciò che resta (`kept_cents`) è la **parte di JAV**.
  Lo staff a ore dell'unità (chi timbra con una tariffa) resta un costo:
  ai treinador dei corsi non va data anche una tariffa oraria.
- **Corso per corso** (`GET /club/admin/courses-report?period=`): iscritti
  attivi, presenze del periodo, incassato, parte del treinador, parte di
  JAV, emesso e ancora da incassare, debiti di oggi; più la riga delle
  quote senza corso.
- **I guadagni del treinador** (`GET /club/staff/earnings?year=`, "I miei
  guadagni" nella sua area): mese per mese e corso per corso, incassato ×
  percentuale; a parte, le quote emesse e non ancora pagate con la parte
  che arriverà. Solo le sue (l'utente della sessione).
- **Piattaforma**: l'unità non è nei totali dei club né nel conto dei club
  attivi; ha una riga sua (`courses_unit`) e nel contatore una riga a parte
  con ciò che JAV tiene (`earnings.courses_*`: mese con previsione, anno, da
  sempre).

### Il passaggio a un club ufficiale

`POST /club/admin/people/{user_id}/move-to-club` (segreteria dell'unità o
superadmin entrato nell'unità; i club possibili da `GET
/club/admin/move-targets`):

- **rifiutato se la famiglia ha quote da pagare nei corsi** (un messaggio
  dice quante e quanto): pagate o condonate prima;
- l'account (`users.club_id`) e gli atleti non usciti passano al club; le
  iscrizioni ai corsi finiscono; le funzioni (monitor) dell'unità si tolgono;
- nel club ogni atleta riparte da oggi (`joined_on`): piano per età,
  **cintura bianca**, iscrizione dell'anno a pro rata, mensilità **dal mese
  prossimo** (quella del mese l'ha già pagata ai corsi), quota socio se
  serve — con le stesse funzioni di sempre (`service.py`);
- certificati medici e consenso al sito seguono l'atleta, ma la
  pubblicazione sul sito si spegne: la decide il nuovo club;
- la **storia resta ai corsi**: quote, prove di pagamento e presenze restano
  dell'unità, e i suoi conti non cambiano. Nell'audit:
  `club.family_moved_to_club`. Dopo il passaggio le due unità non si
  vedono: l'unità non trova più l'atleta, il club non vede le quote dei corsi.

### Sito pubblico e JAVBOT

- **Gli atleti dell'unità non compaiono mai sul sito**, qualunque consenso
  abbiano: nessun ranking, judoca, evento, medaglia, bot. Lo decide un
  predicato solo, `site._publishable_club` (club attivo **e** di un tipo
  che può comparire come club), usato da ogni query pubblica su club e
  atleti; in più la segreteria dell'unità non può pubblicare un atleta.
  Dopo il passaggio a un club valgono le regole di tutti.
- La sezione **"Cursos JAV nas escolas"** (in home dopo i club, la pagina
  `/cursos`, la voce "Cursos nas escolas" nel menu; `GET
  /public-site/courses`) mostra i corsi **pubblicati e attivi** dell'unità
  attiva: scuola, città, indirizzo, orario della settimana, età, testo, nome
  del treinador scritto per il sito, e "Inscrever" → `/c/<slug>?curso=<id>`.
  I testi della pagina dell'unità (frase, presentazione, contatti) solo se
  la sua pagina è pubblicata. Mai iscritti, account, incassi.
- **Iscriversi da un corso**: la pagina `/c/<slug>?curso=<id>` ricorda il
  corso nel browser; il primo "Aggiungi un figlio" lo trova già scelto. Il
  modulo nell'unità chiede comunque il corso (tra quelli pubblicati) e non
  chiede la cintura.
- Il bot del sito risponde su "corsi nelle scuole" (scuola, orari, età, link
  d'iscrizione: strumento `public_courses`). Nell'area privata, a una
  famiglia dei corsi che chiede delle gare risponde che nei corsi non ce ne
  sono e che si fanno nei club.
- L'interfaccia nasconde ciò che non esiste: nel menu della segreteria e del
  superadmin niente Gare, Cinture, Ranking; per la famiglia niente Gare e
  Ranking, cinture, medaglie e consenso al sito; per il treinador niente
  Cinture e Ranking, e c'è "I miei guadagni". `GET /club/current` dice il
  tipo (`kind`).

## Contabilità

Ogni club ha la sua contabilità, la piattaforma vede quella di tutti, e ogni
famiglia ha i suoi conti. **Si salva solo ciò che nessun altro dato può
dire** (una spesa, un costo fisso, una tariffa oraria, una percentuale);
incassi, debiti, costo dello staff, commissione e risultato si calcolano a
ogni lettura (`club/accounting.py`). Una quota corretta, una prova rifiutata,
un turno sistemato correggono subito ogni numero, anche dei mesi passati.

### Che cosa conta come che cosa

- **Incasso** = le quote `PAID`, nel mese in cui sono state **pagate**
  (`paid_at`), non in quello in cui scadevano: è il denaro entrato davvero
  (principio di cassa). Diviso per tipo (mensilità, iscrizioni, gare, quote
  socio). Ne fa parte anche ciò che la famiglia ha pagato con il credito del
  wallet, mostrato a parte ("di cui con il credito", dalle prove `ACCEPTED`
  del mese): quella parte non arriva con un bonifico.
- **Emesso** = le quote con **scadenza** nel periodo, condonate escluse. Il
  **tasso di riscossione** è la parte dell'emesso già pagata.
- **Mancati incassi** (sulle quote con scadenza nel periodo): sconti
  (`discount_cents`: escalão, judo adattato, famiglia), taxa de falta
  (netto − importo, quando applicata) e condoni (importo delle `WAIVED`).
  Non sono costi: è denaro a cui il club ha rinunciato, e si mostra così.
- **Costi** = spese (`club_expenses`, nel giorno della spesa, comprese quelle
  nate dai costi fissi) + **costo dello staff dal cartellino**.
- **Costo dello staff** = minuti dei turni **chiusi** iniziati nel periodo ×
  tariffa oraria valida **quel giorno** (`club_staff_rates`, da una data in
  poi: una tariffa nuova non riscrive i mesi passati). Un turno aperto (o
  un'uscita dimenticata) non è un costo finché non si chiude o la segreteria
  non lo corregge. **Non si conta due volte**: chi timbra ed ha una tariffa
  non va registrato anche come spesa `STAFF` (l'interfaccia lo dice dove si
  sceglie quella categoria); `STAFF` serve per i compensi di chi non timbra.
- **Commissione della piattaforma** = percentuale degli incassi del mese,
  con la percentuale **valida in quel mese** (`club_platform_fees`, sempre dal
  primo del mese; senza righe vale il **10%**), arrotondata al centesimo
  (metà in su). Si calcola mese per mese e si somma: l'anno è la somma dei
  mesi. La decide **solo il superadmin** (`clubs.manage`, `PUT
  /clubs/{id}/platform-fee`), vale dal mese in corso; cambiarla due volte
  nello stesso mese aggiorna la stessa riga. Non si salva mai una
  commissione mensile.
- **Risultato** = incassi − costi − commissione.
- **Previsione del mese** (solo per un mese non ancora finito) = incassato +
  quote che scadono nel mese e non sono ancora pagate.
- **Confronto**: lo stesso tratto dell'anno prima. Per l'anno in corso si
  confronta da gennaio a oggi con gennaio–stesso mese dell'anno prima, mai
  dieci mesi con dodici.

### Debiti e anzianità

Le quote `DUE` di oggi (importo > 0), per giorni dalla scadenza: **non
ancora scadute**, **1–30**, **31–60**, **61–90**, **oltre 90**. Per famiglia:
la quota di un atleta è del suo genitore, la quota socio del genitore
stesso; prima chi ha più scaduto.

### Spese e costi fissi

- `club_expenses`: data, categoria (`RENT`, `STAFF`, `FEDERATION`,
  `INSURANCE`, `EQUIPMENT`, `TRANSPORT`, `EVENTS`, `UTILITIES`, `MARKETING`,
  `ADMIN`, `OTHER`), importo > 0, descrizione, fornitore, come è stata pagata
  (`BANK_TRANSFER`, `CASH`, `CARD`, `DIRECT_DEBIT`, `OTHER`: è il club che
  paga un fornitore, non una famiglia che paga il club), ricevuta facoltativa
  nel bucket privato dei documenti (JPG, PNG o PDF fino a 15 MB, come le
  prove di pagamento). La commissione della piattaforma non è una categoria:
  si calcola.
- `club_recurring_expenses`: un costo che si ripete ogni mese (affitto,
  compenso fisso), con giorno del mese (1–28), inizio, fine facoltativa,
  `active`. Ogni giorno alle 03:10 il job registra la spesa del mese in
  corso; alla creazione si registrano subito anche i mesi dall'inizio a oggi
  (al massimo due anni indietro). **UNIQUE (`recurring_id`, `period`)** con
  `ON CONFLICT DO NOTHING`: un mese esiste una volta sola. La segreteria può
  rilanciarlo a mano (`POST /club/admin/accounting/jobs/recurring`).
- Una spesa nata da un costo fisso si **corregge** (la bolletta vera è
  diversa dalla rata) ma **non si cancella**: cancellata, il job la
  ricreerebbe. Un costo fisso con mesi registrati si **ferma** (`active`
  falso) invece di sparire; senza mesi registrati si cancella. Modificarlo
  vale per i mesi non ancora registrati.

### Chi vede che cosa

| Chi | Dove | Cosa |
|---|---|---|
| Segreteria (`club.manage`) | "Panoramica" e "Contabilità" del club | Il suo club: conto economico del mese o dell'anno, 12 mesi, confronto, previsione, libro cassa con filtri e CSV, spese con ricevuta, costi fissi, tariffe e costo dello staff, debiti |
| Superadmin (`clubs.enter`; `clubs.manage` per la percentuale) | "Panoramica" della console | Il contatore di quanto spetta alla piattaforma (mese con previsione, anno, da sempre, club per club, 12 mesi), tutti i club insieme e uno per uno, crescita di club, atleti e famiglie, vendite dello Shop (ordini `PAID`, IVA compresa: incasso della piattaforma, non dei club) |
| Famiglia o atleta (`club.family`) | "I miei conti" | Un conto solo: pagato nell'anno e da sempre per tipo, da pagare (scaduto e in arrivo), sconti ricevuti quota per quota, wallet (crediti dagli inviti e investimenti del club al netto degli storni, credito usato per quote e Shop), ordini dello Shop, mese per mese. **Persona per persona solo se ci sono figli**: un atleta adulto senza figli vede un conto solo; se è anche genitore, vede sé stesso, ogni figlio e la quota socio della famiglia |

API: `/club/admin/accounting/{summary,ledger,debts,expenses,recurring,staff-costs,staff-rates}`
(il periodo è `?period=AAAA-MM` o `AAAA`), `/clubs/accounting?year=`,
`/clubs/{id}/platform-fee`, `/club/accounting/mine?year=`. Il browser sceglie
solo il periodo: ogni importo nasce sul server.

## Sponsor

- Tabella `sponsors` (`club/sponsors.py`, `sponsors_router.py`): nome, slug,
  riga sotto il nome, descrizione, logo (bucket dei media, solo caricato da
  qui), sito (`http(s)://`), colore, ordine, attivo. Li gestisce lo staff
  della piattaforma (console → 🤝 Sponsor, `clubs.manage` e account senza
  club).
- La **home** li mostra in una barra di loghi che scorre (solo CSS, si ferma
  sotto il mouse e con «riduci movimento»); senza logo, il nome con le
  iniziali nel colore dello sponsor. Ogni logo porta a
  `/patrocinadores/<slug>`: chi è, la descrizione e un bottone grande verso
  il suo sito. `/patrocinadores` elenca gli sponsor e ha il modulo per
  diventarlo (messaggio con argomento SPONSOR).
- Uno sponsor spento sparisce dal sito (anche la sua pagina: 404), resta in
  console.

## Il Calendário JudoArteVida

- `club/calendar.py`: le prove del club e della rete tra due date (al
  massimo due anni). Per lo staff (`GET /club/staff/calendar[/pdf]`,
  `club.instruct`) e per atleti e famiglie (`GET /club/calendar[/pdf]`,
  `club.athlete`). Nel «Calendario» della segreteria e degli istruttori
  (prima scheda) e nella pagina «Gare» delle famiglie (scheda 📅).
- Tre viste: **schede** (con la locandina o l'icona del tipo), **lista**
  dettagliata e **tabella**, sempre divise per mese con la riga del mese.
- Il **PDF** (A4 orizzontale, in portoghese): una tabella per mese con data,
  prova (tipo, livello, chi la organizza nella rete), local, estado,
  escalões e notas (organizzatore, scadenza iscrizioni, costo, descrizione);
  intestazioni e riga del mese si ripetono in cima a ogni pagina, così il
  calendario continua senza interruzioni.
- Il **flyer del mese** (`render_flyer`, `GET /club/[staff/]calendar/flyer?year&month`,
  bottone «🎨 Scarica flyer del mese» con il mese da scegliere): **sempre una
  pagina A4**. In alto la barra dorata «EVENTOS DO MÊS · OUTUBRO 2026» con il
  numero di eventi; sotto il logo JudoArteVida del sito
  (`app/assets/judoartevida-logo.jpg`) e le icone rotonde di Facebook,
  Instagram, YouTube e del sito, cliccabili, prese dai «Social della rete»
  (`organizations.service.network_socials`; un social senza indirizzo non
  compare). Gli eventi sono righe larghe quanto la pagina: data nel colore del
  tipo, tipo e livello, nome, luogo ed escalões, scadenza delle iscrizioni.
  L'altezza delle righe si adatta al numero di eventi; sotto i 21 punti si
  passa a due colonne. Test: `tests/test_flyer.py`.

### La prova di pagamento dall'area dell'atleta
- Il titolare, o **l'atleta stesso con il suo accesso dai 18 anni di età
  federale** (`can_pay`), paga le quote di quell'atleta dalla sua area
  (`POST /club/athlete-area/{id}/payment-proofs`): stesse regole del
  genitore (bonifico o MB Way con la prova, contanti con chi li ha presi),
  senza il credito del wallet, che è del titolare. La prova risulta caricata
  da chi l'ha caricata (`uploaded_by_user_id`, `paid_by_user_id`).
- In ogni pagamento la prova si sceglie con due bottoni sempre visibili,
  «📷 Scatta una foto» e «📎 Allega un file», con l'anteprima
  (`components/ui/proof-picker.tsx`): due input separati perché con
  `capture` alcuni telefoni aprono solo la fotocamera.

## Gli obblighi dell'atleta (la scheda «salute sportiva»)

- `club/obligations.py`, nella scheda dell'atleta (`obligations` di
  `athlete_cards`): in cima all'area dell'atleta e, per ogni figlio, nella
  pagina della famiglia (`components/club/athlete-health-card.tsx`), con
  foto (si carica toccando il cerchio), età, gruppo, categoria, peso, lezioni,
  gare, medaglie e punti.
- **Judogi del club** (ordine non annullato in `club_equipment_orders`):
  azul per i maschi, rosa per le femmine; dal Grupo 3 (13 anni federali) una
  femmina sceglie rosa o azul.
- **Judogi bianco** (`club_athletes.white_judogi`, lo dichiarano famiglia,
  atleta o segreteria; o un ordine bianco).
- **Certificato medico** valido; **quota annuale** dell'anno pagata
  (l'iscrizione `ENROLLMENT`: socio, taxa de falta, seguro, FPJ e
  associazione distrettuale in un'unica quota, anche a rate).
- **Pronto per le gare**: quota annuale pagata e judogi bianco (un maschio
  anche con l'azul). Per ora è un avviso: non blocca l'iscrizione.
- **«Ha già il judogi bianco»** è un interruttore dentro il riquadro del
  judogi bianco nella scheda dell'atleta (famiglia e area atleta,
  `athlete-health-card.tsx`): si sposta subito e torna indietro se il
  salvataggio non va (`PATCH /club/athletes/{id}` o
  `PUT /club/athlete-area/{id}/white-judogi`).

## La bacheca del circuito

- Un post di un club è **per i soci** (`audience = CLUB`) o **per tutto il
  circuito** (`NETWORK`); JudoArteVida scrive dalla console (📰 Bacheca,
  `/platform-news`, `club_id` NULL, sempre per tutti).
- La bacheca di atleti e famiglie (`feed` di `GET /club/board`) mette insieme
  i post del club, del circuito e di JudoArteVida, e le **prove dei prossimi
  90 giorni come post** (alla data in cui sono state annunciate). Ogni post
  porta nome e logo di chi lo firma e i «mi piace» (`club_news_likes`, uno
  per persona).

## Lo shop del club

- Ogni prodotto e ogni ordine dello Shop hanno un venditore
  (`jav_market_products.club_id`, `jav_market_orders.club_id`): un club, o
  NULL = lo **shop unico di JudoArteVida** del superadmin.
- La segreteria gestisce i prodotti e gli ordini del suo club da «Ordini
  Shop del club» (`/club/admin/shop/...`): prodotti con foto e varianti,
  conferma del pagamento, spedito, consegnato, annulla. JavCash e fornitori
  restano dello shop di JudoArteVida.
- Una famiglia vede nella vetrina lo shop del suo club e quello di
  JudoArteVida, con l'etichetta del venditore e il filtro; mai lo shop di un
  altro club. Un ordine è di un venditore solo (un carrello misto si rifiuta
  con la spiegazione) e il bonifico di un ordine del club va all'IBAN del
  club (`payee`).
- **Dalla migrazione 0040 i prodotti di un club si comprano solo dalla sua
  Loja** (vedi «La Loja del club»): `jav_market.create_order` rifiuta un
  ordine dello Shop con un prodotto di un club. Un ordine dello Shop sarebbe
  un secondo debito, fuori dalle quote e dalla home della famiglia.


## L'area dell'atleta

- L'area (`components/club/athlete-area.tsx`) ha il menu a sinistra come le
  altre aree (AppShell): Home, Lezioni, Gare e stage, Bacheca, Quote,
  Certificato medico, Traguardi, Giochi, Invita un amico.
- **Gare e stage** (`GET /club/athlete-area/{id}/competitions`): le prove in
  arrivo con l'iscrizione dell'atleta, se c'è. L'atleta non si iscrive da solo:
  «🙋 Voglio partecipare» (`POST …/competitions/{cid}/wish`) avvisa il titolare
  del conto con email e notifica, una volta sola per prova; il titolare invece
  vede «Iscrivi», che porta alla pagina delle gare.
- Il **certificato medico** di un minorenne lo carica il titolare (anche il
  server rifiuta con 403 l'upload dall'area di un minorenne).
- **Invita un amico**: il link personale con i bottoni WhatsApp, Facebook,
  Telegram, X, email, «Copia» e la condivisione del telefono
  (`components/club/invite-card.tsx`).

## L'aiuto del club

- `club/support.py`, `club_athlete_supports`: un costo che il club paga per
  un atleta (trasporto, materiale, iscrizione a una prova, esame, stage, altro),
  con importo, data e nota. Lo registra la segreteria dalla scheda persona
  (Persone → atleta → 💚 Aiuto del club, `POST /club/admin/athletes/{id}/supports`).
- Nel **wallet della famiglia** diventa una ricarica del club e subito
  l'addebito del costo (`source = CLUB_SUPPORT`, legati all'atleta): il saldo
  non cambia, ma lo storico dice quando e quanto il club l'ha aiutata.
- La **scheda dell'atleta** (area e scheda della segreteria,
  `GET /club/athlete-area/{id}/money`) mostra il saldo del wallet, il totale
  dell'aiuto per voce, gli investimenti del club e gli ultimi costi
  (`AthleteMoneyCard`). Senza saldo, aiuti né investimenti il riquadro non c'è.

## Avvisi della mensilità e multa

- Si accendono nelle Impostazioni del club (⏰ «Avvisi della mensilità e
  multa», `late_fee_enabled`, `late_fee_cents`, 15 € se non indicato).
- Il **1°, il 10 e il 15** del mese, dalle 9:00 ora del club: un'email e una
  notifica a ogni famiglia con la **mensilità del mese corrente** ancora da
  pagare, che avvisa della multa. Con la prova caricata la quota è già pagata e
  l'avviso non parte.
- Il **16 dalle 9:00**: per ogni mensilità del mese ancora da pagare nasce una
  quota `FINE` (`period = atraso-AAAA-MM`, scadenza a 7 giorni), una sola per
  atleta e mese, con email e notifica.
- Conta solo la mensilità del mese corrente. Il job gira ogni ora
  (`club_payment_reminders_task`, `club/payment_reminders.py`); ogni avviso
  parte una volta sola (`club_reminders_sent`).

## Il personale del club

`club/staff_work.py`, `club_staff_tasks`, `club_staff_messages`; nella
segreteria la sezione **👥 Personale** (che comprende il cartellino).

- **Il mese** (`GET /club/admin/staff-work?month`): persona per persona ore
  del cartellino, tariffa e costo delle ore (`accounting.staff_costs`),
  compiti e lavoretti con il loro costo, il totale e quanto resta da pagare.
- **Compiti svolti** (`TASK`): li scrive chi lavora nel club dalla sua area
  («Il mio lavoro», `POST /club/staff/work/tasks`): che cosa, quando, quanto
  tempo. Può toglierli finché non sono pagati.
- **Lavoretti occasionali** (`ODD_JOB`): li scrive la segreteria, anche per
  chi non ha un account (basta il nome), con il costo.
- **Pagare** un compito o un lavoretto (con il suo costo, o indicandolo)
  crea la spesa `COLLABORATORS` nella contabilità (`expense_id`), una volta
  sola; una riga pagata non si cancella più da qui. Chi ha un account riceve
  la notifica.
- **Comunicazioni**: ogni persona dello staff ha due conversazioni, con la
  segreteria del suo club (canale `CLUB`, Personale → Messaggi) e con
  JudoArteVida (canale `JAV`, console → 💬 Messaggi dello staff,
  `/club-platform/staff-messages`). Chi scrive avvisa l'altra parte con una
  notifica; la risposta avvisa la persona. Le conversazioni mostrano i non
  letti e il «letto» (✓✓).

## Lo shop della rete sul sito

- `/loja` (`jav_market/public_router.py`, `GET /public-site/shop`): lo
  **shop unico di JudoArteVida** si guarda senza account (mai i prodotti dei
  club), con ricerca, categorie e «Mostra altri prodotti»; i prezzi sono
  **IVA compresa**. La vetrina si vede anche a negozio spento (si guarda
  soltanto), qui come nell'area: l'interruttore dello Shop chiude solo gli
  acquisti.
- «Acquista» porta a `/loja/comprar`: per comprare bisogna essere soci di un
  club della rete. Chi è socio entra (e trova lo Shop nella sua area); gli
  altri scelgono un club (`/c/<slug>`) o vanno a «Crea il tuo club».
- Il catalogo di suplementos24.com si carica con
  `scripts/import_suplementos24.py` (dati in `scripts/shop_import/`): le
  cinque grandi categorie e le sottocategorie «Grande › Sotto», il prezzo
  netto `prezzo × 100 / (100 + IVA)` così al cliente arriva il prezzo del sito,
  le foto copiate nel bucket dei media. Di default prova soltanto; `--apply`
  scrive; idempotente.

## Crea il tuo club

- `/criar-clube` (nel menu «Chi siamo»): due strade.
  **Ho già un club** e voglio il supporto gestionale della rete (portale,
  quote, gare, ranking, pagina pubblica e shop), oppure **parto da zero con il
  Judo Team Matias Luwawa** (corso per istruttore, aiuto a trovare lo spazio,
  formazione amministrativa e tecnica; solo in Portogallo).
- La richiesta (nome, email, telefono, città, nome del club e atleti, oppure
  esperienza e spazio, e un messaggio) arriva a JudoArteVida come messaggio di
  contatto con argomento `NEW_CLUB` (`contact_messages.topic`): console →
  Messaggi, con il filtro «Creare un club». Lo staff la valuta e risponde.

## Chi compare sul sito (dalla migrazione 0029)

- Ogni atleta dei club pubblici **parte con la scheda sportiva pubblica**,
  senza foto (`club_athlete_public_profiles.basis = LEGITIMATE_INTEREST`,
  creata con l'atleta da `site.ensure_default_profile`): «Nome I.», club,
  cintura, fascia, medaglie, risultati, punti. Il club può comunque metterla
  in pausa (`published = false`: resta in classifica come «Nome I.», senza
  pagina).
- La famiglia può **opporsi** dalla scheda dell'atleta («Mi oppongo»,
  `opted_out_at`): la scheda sparisce dal sito e l'atleta anche da
  classifiche, eventi e medaglie; il club non la può ripubblicare. Con «Rendi
  di nuovo pubblica» torna (`basis = CONSENT`).
- La **foto** e i video restano un consenso esplicito (`show_photo`).
- Base giuridica e analisi: docs/legal.md.

## Privacy, cookie e termini

`/privacidade`, `/cookies`, `/termos`, link nel footer, banner dei cookie al
primo accesso e contenuti di terzi (YouTube, Vimeo) solo dopo il consenso:
tutto in docs/legal.md. Job notturno di conservazione
(`domains/legal/retention.py`, 04:20): messaggi dal sito oltre 24 mesi,
sessioni scadute.

## Eventi nell'area riservata e ordine

- Il calendario degli eventi del sito (`components/site/events-explorer.tsx`)
  c'è anche nell'area: per le famiglie è la prima scheda di «Gare»
  (🗓️ Eventi), per gli atleti la prima di «Gare e stage» (accanto a
  «Voglio partecipare»). Stessa grafica, dati pubblici
  (`components/club/area-events.tsx`).
- **Tornare al calendario**: nell'area il link di un evento è
  `/eventos/<id>?from=area` e, prima di aprirlo, salva dove si era (sezione
  dell'area, vista, mese, filtri, pagina della lista, giorno scelto,
  scorrimento) in sessionStorage (`lib/events-return.ts`, mezz'ora). La pagina
  dell'evento mostra «← Torna al calendario»; tornando (anche con l'indietro
  del browser) l'area riapre le gare e il calendario riparte da lì, poi il
  punto si cancella.
- La lista mette **in cima i prossimi eventi** (dal più vicino), poi quelli
  già fatti (dal più recente); nell'anno in corso arriva fino a dicembre
  dell'anno dopo. A pagine da 12.
- Gli elenchi lunghi sono **a pagine numerate** (`components/ui/pagination.tsx`,
  `usePaged`); lo Shop (area e `/loja`) chiede al server una pagina alla volta.

## I prodotti dei partner

Lo Shop di JudoArteVida si presenta come **«I prodotti dei nostri partner e
amici»**, sul sito (`/loja`) e nell'area: una fascia nera con il logo di
Suplementos24 come un banner (`components/site/partner-banner.tsx`,
`public/partners/suplementos24.png`). Le categorie scorrono di lato con le
frecce ‹ › (`components/ui/chip-scroller.tsx`). Il link «Loja» del menu apre
la categoria delle proteine. La
vetrina si vede anche a negozio spento, sul sito e nell'area
(`/jav-market/products/mine/page` con `showcase`): l'interruttore chiude solo
gli acquisti. A negozio spento le schede di JudoArteVida hanno
`purchasable: false` e la pagina `jav_open: false`; l'area mostra «Gli acquisti
apriranno presto» al posto di «Acquista» e «Aggiungi al carrello», e il
checkout le rifiuta comunque. Lo shop del club vende sempre.

## Social e WhatsApp

- **I social della rete** (piè di pagina di ogni pagina del sito, icone che
  si accendono del colore del social): Facebook, Instagram, YouTube, TikTok
  in console → Impostazioni → «Social della rete»
  (`organizations.settings.social_*_url`, `GET /public-site/network`).
  Finché YouTube è vuoto vale il canale @ml8126. Ogni link solo verso il
  suo sito (`site.check_social_url`).
- **I social del club**: Instagram, Facebook, YouTube e ora **TikTok**
  (`club_sites.tiktok_url`, migrazione 0030), dalla segreteria in Sito →
  contatti; compaiono nella pagina del club.
- **WhatsApp**: una voce come le altre, con l'icona di WhatsApp, subito
  sotto il telefono: scheda nella pagina `/contactos` (email, telefono,
  WhatsApp, dove siamo), riga nel piè di pagina, voce nelle informazioni
  della pagina del club. Apre la chat con lo stesso numero (`wa.me`, un numero di 9 cifre
  senza prefisso diventa +351; `components/site/social-icons.tsx`).


## La tabella atleti e le prove di pagamento della segreteria

- **Tabella atleti** (`components/club/athletes-table.tsx`,
  `GET /club/admin/athletes`): oltre alla scheda dell'atleta l'API dà
  `member_number`, l'encarregado (`guardian_name`, `guardian_email`,
  `guardian_phone` da `customers.phone`) e `invited_by`: `PERSON` se la
  famiglia si è registrata dal link «Invita un amico» di una persona del club
  (`friend_referrals`, sorgente `CLUB_LINK`; `user_id` per i simboli del
  ruolo), `WRITTEN` se il modulo d'iscrizione ha un nome in «chi ti ha
  invitato» (`club_applications.referred_by`), altrimenti nulla (= il club).
  Tutto in poche query (`router.py::_athlete_registry`). La ricerca `q`
  guarda anche nº de sócio, licenza FPJ ed email dell'encarregado.
  Ordinamento, filtri rapidi e CSV lavorano nel browser.
- **Prove di pagamento** (`components/club/proofs-panel.tsx`,
  `GET /club/admin/payment-proofs?q=&method=&from=&to=`): la ricerca e i
  filtri li fa l'API (`service.py::list_proofs`, giorni di Lisbona), così una
  prova vecchia si trova anche oltre il limite di 500; lo stato si sceglie
  nel browser con i conteggi. Le quote si mostrano nella lingua di chi guarda
  quando sono mensilità o iscrizioni normali (dal tipo e dal periodo); per il
  resto resta la descrizione del server. La ricevuta si apre in una finestra
  (URL firmato), il rifiuto chiede un motivo con quattro motivi pronti.

## Piani con colore, prove dalle quote, staff da account esistenti, rete inviti

- **Colore del gruppo**: `club_plans.color` (#RRGGBB, migrazione 0031); senza
  colore la scheda prende la tavolozza (`plans-panel.tsx::PLAN_PALETTE`).
  `GET /club/admin/plans` dà anche `athletes_count` (attivi).
- **Prova dalla quota**: nelle quote della segreteria (`GET /club/admin/fees`,
  quadro del mese) ogni quota porta `proof_id`/`proof_status`, l'ultima prova
  collegata anche se rifiutata (`service.py::latest_proofs_of_fees`); la si
  apre con lo stesso visualizzatore dei Comprovativos.
- **Staff da un account esistente**: `clubs.py::add_staff` con l'email di un
  account **dello stesso club** gli aggiunge il ruolo (niente invito, la
  password resta); un account di un altro club è rifiutato. Il menu utente
  mostra le aree del club per chi ha più ruoli (`area-switcher.tsx::clubAreasFor`).
- **Rete inviti**: `GET /club/invite` dà anche `balance_cents` (saldo
  JavCash) e `network`: gli atleti delle famiglie entrate dal link, «Nome I.»,
  mensilità pagate e credito reso (`referrals.py::_network`: i crediti
  `CLUB_REFERRAL` per quota, esclusi quelli stornati). La home dell'atleta ha
  «Segna la tua presenza» (porta alle lezioni) e la scheda d'invito.
- **Loja**: i nomi predefiniti delle sezioni sono «Judogi, cinture e
  abbigliamento judo», «Equipaggiamento sportivo del club», «Prodotti
  partner Suplementos24» e si mostrano tradotti finché l'amministratore non
  li cambia (`sections.*.custom`, `labels_custom`); la Loja si apre sul primo
  negozio con prodotti.

## Gruppi con turmas, giorni delle presenze

- **Turmas dentro i gruppi** (`plans-panel.tsx::GroupSchedule`): le turmas di
  un gruppo sono quelle la cui fascia d'età tocca quella del piano
  (`site.py::plan_slots`, la regola del sito e di JAVBOT); niente colonna
  nuova. Il popup della turma è `course-modal.tsx` (anche dalla pagina Turmas)
  e ora sceglie il treinador tra gli istruttori (`GET /club/admin/staff` dà
  anche il `name`). Le turmas senza età sono segnalate in «Planos e preços».
- **Giorni delle presenze** (`attendance-tool.tsx::DayStrip`): le lezioni del
  mese da `GET /club/staff/lessons?from&to` (massimo due mesi), raggruppate per
  giorno con presenze segnate e iscritti.
- **Pagine larghe**: `AppShell` ha `wide` (main senza `max-w-7xl`), usato
  dalla tabella atleti in segreteria e nella console.

## Risultati dal treinador, scheda dell'evento e relatórios

- **Risultati dal treinador** (`competition_staff.py`, rotte
  `/club/staff/competitions…`, permesso `club.instruct`): l'elenco degli
  eventi (prossimi o passati) con quanti atleti del club sono iscritti e
  quanti hanno già un risultato; per ogni iscrizione si scrivono, un campo
  alla volta (`PATCH …/entries/{entry_id}`), peso e categoria alla pesata,
  poi piazzamento, posizione vera (il 9° di un open: `rank`, solo con la
  partecipazione) e nota. **Il piazzamento passa da
  `competitions.record_results`**, la funzione della segreteria: il Jav
  Ranking lo somma allo stesso modo e la gara del club passa a DONE.
  Peso e categoria non toccano lo stato della gara. Un treinador lavora solo
  sulle iscrizioni del suo club (`ClubScope`): quelle di un altro club sono
  «non trovate». Interfaccia: `components/club/coach-results.tsx` (medaglie
  🥇🥈🥉 da toccare, salvataggio automatico all'uscita da ogni campo); la
  segreteria la trova in «Eventos e provas» → «Risultati».
- **Scheda dell'evento** (`components/club/competition-detail-modal.tsx`):
  toccando il nome di una prova nel calendário, negli elenchi della
  segreteria e nei risultati si apre la scheda con descrizione, date e ore,
  luogo, scadenza, livello, età, quota, categorie, circolare e gli atleti del
  club iscritti. Lo staff (`GET /club/staff/competitions/{id}`) vede nome
  intero, età, peso, risultato e **i contatti**: dell'encarregado per un
  minorenne, dell'atleta adulto se ha un account con email o telefono veri
  (`contacts_for`; gli indirizzi `@atleta.invalid` non contano), con link per
  chiamare, scrivere e WhatsApp. Atleti e famiglie
  (`GET /club/calendar/events/{id}`, `club.athlete`) vedono la stessa scheda
  senza contatti né pesi, gli iscritti come «Nome I.».
- **Relatórios degli eventi** (`event_reports.py`, tabelle
  `club_event_reports`, `club_event_report_costs`, `club_event_report_photos`,
  migrazione 0033): titolo, descrizione, il racconto del treinador, le spese
  per voce (alloggio, viaggio/voli, carburante, pasti, iscrizioni, altro:
  importo in centesimi e nota, una riga per voce, UNIQUE (relatório, voce)) e
  fino a 12 foto. **Uno per autore e per evento** (UNIQUE club, evento,
  autore). I risultati non si copiano: si leggono dalle iscrizioni ogni
  volta, quindi un piazzamento corretto dopo corregge anche il relatório. Il
  treinador vede e modifica solo i suoi (quelli di un collega per lui non
  esistono: 404); la segreteria (`club.manage`) li vede, crea e modifica
  tutti. Le foto vanno nel **bucket privato** (documento interno con minori),
  ottimizzate prima con `optimize_image` come quelle del sito, e si aprono
  con URL presigned di 15 minuti. Interfaccia: `components/club/event-reports.tsx`
  (`EventReportsPanel`, e `CoachEventsPanel` per l'area del treinador:
  risultati + relatórios).
- **PDF dei relatórios** (`GET /club/admin/event-reports/pdf?from&to`, solo
  `club.manage`; `event_reports.render_pdf`): un PDF unico per il periodo
  (un mese, un anno, da… a…, al massimo tre anni), con gli eventi che
  **cominciano** nel periodo. Copertina con la barra dorata del flyer, il
  logo JudoArteVida, i numeri (relatórios, atleti, ori, argenti, bronzi,
  spese) e l'indice; poi un relatório per pagina con l'evento nel colore del
  suo tipo, i risultati con le medaglie, le spese con il totale, il racconto
  e le foto. In portoghese, come il calendário. L'intestazione
  `X-Report-Count` dice quanti relatórios contiene.
- **Relatório final** (migrazione 0037, `club/event_articles.py`, colonne
  `club_event_reports.article_title | article | article_source |
  article_generated_at`): dal relatório si ricava un articolo breve «di
  giornale» — dove, quando, quanti atleti, medaglie e piazzamenti, il
  racconto del treinador, le spese in una frase — da rileggere e correggere.
  `POST /club/staff/event-reports/{id}/article {source}` lo (ri)scrive dai
  dati **salvati** (l'editor salva prima di chiederlo):
  - `TEMPLATE`: frasi fisse in portoghese, ogni frase esiste solo se c'è il
    suo dato (niente medaglie → niente frase sulle medaglie). Sempre attivo;
  - `AI`: Claude (`JAVBOT_MODEL`) scrive dagli stessi dati con l'istruzione
    di non inventare nulla (nomi, golpes, avversari, citazioni). **Spento**
    finché non si mettono `EVENT_REPORT_AI_ENABLED=true` e
    `ANTHROPIC_API_KEY`; `GET /club/staff/event-reports/ai` dice al browser
    se il bottone «Gerar com IA» è attivo. Se l'API non risponde l'errore
    lo dice e l'articolo resta com'era;
  - ritoccato a mano (`PATCH` con `article`/`article_title` diversi) diventa
    `MANUAL`; riscriverlo dai dati chiede conferma. Salvare il relatório
    senza toccare l'articolo non lo cambia.
  Stesse regole del relatório per chi lo vede e lo scrive (autore o
  segreteria).
- **PDF degli articoli** (`GET /club/staff/event-reports/articles/pdf?q&from&to`,
  `club.instruct`; `event_articles.render_pdf`): tutti i relatórios finali
  che chi chiede può vedere (la segreteria tutti, il treinador i suoi),
  filtrati con la stessa ricerca della scheda, dal più vecchio: copertina
  «Crónicas das provas» con l'indice, poi un articolo per pagina con
  occhiello colorato per tipo, titolo, firma, foto d'apertura, testo
  giustificato, il riquadro «Em números» e le altre foto.
- **Interfaccia**: le schermate (Eventos — solo segreteria —, Resultados,
  Relatórios, Relatórios finais) sono pulsanti grandi in una barra con la
  ricerca (`ProvasBar` in `components/club/event-reports.tsx`, lo stile
  della barra degli eventi del sito); sotto, filtri (con/senza relatório
  final, autore) e conteggio. Il popup «Novo relatório» ha la ricerca e il
  filtro «Só com inscritos e já concluídos» (acceso di default).

## L'area del treinador: Início, quaderno, turni, bacheca

Codice: `club/coach.py` (servizio), `club/coach_router.py` (API),
`club/coach_models.py` (tabelle), `club/workclock.py` (turni), `club/news.py`
(post dei treinadores); interfaccia `components/club/coach-home.tsx`,
`coach-notebook.tsx`, `coach-shifts.tsx`, `coach-board.tsx`. Migrazione 0034.
Tutte le rotte vogliono `club.instruct`; chi vede che cosa lo decide il
servizio con `manager` (chi ha anche `club.manage`, la segreteria).

- **Menu** dell'area: Início, Presenças, Calendário, Provas, Caderno,
  Cartellino, O meu trabalho, Mensagens, Mural, Cintos, Ranking (nei corsi
  JAV niente Provas, Cintos e Ranking, e al loro posto Ganhos).
- **Início** (`GET /club/staff/coach/home`): le lezioni di oggi con
  «Marcar presenças» sulla lezione in corso (apre le presenze su quel giorno
  e quel corso), i **registri vuoti** (lezioni degli ultimi 14 giorni già
  finite, con iscritti e nessuna presenza), il cartellino, le prove dei
  prossimi 60 giorni (il nome apre la scheda dell'evento), i messaggi non
  letti, gli atleti **da tenere d'occhio** (nessuna presenza da 21 giorni,
  certificato scaduto, in scadenza o mancante: solo lo stato, il file resta
  della segreteria) e le ultime note del quaderno.
- **Chi vede che cosa** (migrazione 0038, `courses.visible_course_filter`,
  unico punto in cui si decide): ogni treinador vede **tutti i corsi del
  club** e i loro atleti, più gli atleti attivi che non sono in nessun corso:
  nei club piccoli i treinador insegnano in tutti i gruppi, e un treinador
  senza corsi assegnati che apriva le presenze e non trovava nessuno era un
  errore (Lagos, 17/10/2026). La segreteria **toglie** un corso a una
  persona dalla scheda della turma («Treinadores que NÃO veem esta turma»,
  `club_course_coach_exclusions`, `GET/PUT
  /club/admin/courses/{id}/coach-exclusions`, audit
  `club.course_coach_exclusions_set`): quel corso, le sue lezioni, le sue
  note e gli atleti che stanno solo lì per lui non esistono (404). Chi
  insegna il corso (titolare o adjunto) lo vede comunque e lo trova per primo,
  segnato «minha» (`mine` su lezioni e corsi). Nella stessa scheda si
  scelgono gli adjunto (`PUT /club/admin/courses/{id}/staff`). Vedere un
  corso non è insegnarlo: la quota del treinador sui corsi JAV
  (`coach_earnings`, `coach_share_pct`) resta del titolare.
- **Presenze**: il treinador vede i corsi che vede (sopra), la
  segreteria tutti; i giorni passati si aprono dalla striscia del mese (che
  segue il mese del giorno scelto) o dal calendario e si correggono. Un
  giorno futuro si guarda ma non si segna. «Todos presentes» segna in un
  colpo chi non è ancora segnato; la nota per la segreteria non cambia più
  la presenza (prima segnava sempre «presente»). 📓 su un atleta apre la sua
  scheda, «Nota da aula» scrive la nota della lezione.
- **Turni** (`GET/POST /club/staff/clock/sessions`, `PATCH/DELETE
  /club/staff/clock/sessions/{id}`): la persona corregge entrata, uscita e
  nota dei suoi turni, ne toglie uno timbrato per sbaglio, ne aggiunge uno
  dimenticato (sempre con entrata e uscita). Regole, anche per la correzione
  della segreteria: niente futuro (5 minuti di tolleranza), uscita dopo
  l'entrata, al massimo 24 ore, **nessuna sovrapposizione** con un altro
  turno della stessa persona (uno aperto conta fino ad adesso); un turno
  chiuso non si riapre. La persona lavora solo su **questo mese e il mese
  scorso**: prima le ore sono già contate e pagate, e corregge la
  segreteria. Ogni modifica va nell'audit (`club.work_session_edited`,
  `_added`, `_deleted`, `_corrected`, con prima e dopo); sul turno restano
  `edited_at`/`edited_by_user_id` e `added_later`. La segreteria vede i
  segni nelle ore del mese e l'elenco delle modifiche
  (`GET /club/admin/work-sessions/changes?month=`).
- **Quaderno: note delle lezioni** (`club_lesson_notes`, `/club/staff/coach/lesson-notes`):
  corso + giorno, tema, tecniche (etichette separate da virgole, senza
  doppioni, al massimo 30), testo. Più note per la stessa lezione (titolare
  e adjunto). Si sfogliano come linea del tempo per mese, per corso, con la
  ricerca in tema/tecniche/testo e il filtro per tecnica; accanto le
  tecniche più lavorate del periodo. Le vedono i treinadores che vedono il
  corso e la segreteria; le corregge solo chi le ha scritte, le toglie anche la
  segreteria (audit).
- **Quaderno: note sugli atleti** (`club_athlete_notes`,
  `/club/staff/coach/athletes/{id}/notes`, `/club/staff/coach/athlete-notes/{id}`):
  una categoria (tecnica, comportamento, salute, obiettivo, gare, altro) e
  il testo. Le vedono **solo** i treinadores che vedono l'atleta (un corso
  a cui è iscritto, o nessun corso) e la segreteria; mai la famiglia né l'atleta, mai un altro club
  (404). Correggerle è di chi le ha scritte (il testo di prima resta
  nell'audit), toglierle anche della segreteria.
- **Os meus atletas** (`GET /club/staff/coach/athletes`, scheda
  `GET /club/staff/coach/athletes/{id}`): gli iscritti ai corsi che vede e
  gli attivi senza corso (la segreteria: tutti gli attivi) con cintura, presenze degli ultimi 30
  giorni, ultima presenza, stato del certificato e numero di note; la scheda
  ha le presenze di 90 giorni giorno per giorno e le note.
- **Mural** (`GET /club/staff/board`, `POST/PATCH/DELETE /club/staff/news`):
  la bacheca come la vedono i soci, e i post del treinador. Un treinador
  scrive solo per i soci del club (mai `NETWORK`), non fissa in cima, e
  corregge, nasconde o toglie solo i suoi; la segreteria li vede nella sua
  console («Notícias») con il nome dell'autore e li modera come i propri.
- **Ranking**: l'area del treinador chiamava `/club/admin/ranking`
  (`club.manage`) e `/club/config` (`club.family`) e riceveva 403: ora
  `RankingPanel admin` usa `/club/staff/ranking` e `/club/staff/config`.
- Non fatto di proposito: i risultati dei giochi (Dojo Academy) per atleta,
  perché il gestionale non legge i dati del gioco (docs/games.md).

## Pagamento parziale, mese esente e relatórios della segreteria (migrazione 0032)

Tre cose chieste dalla segreteria per il quadro «Mensalidades e quotas», più
un audit dei conti. Codice: `club/fee_splits.py` (parziale ed esenzione),
`club/money_reports.py` (relatórios), `club/money_router.py` (rotte, tutte
`club.manage`: la segreteria o il superadmin entrato nel club); interfaccia
`components/club/money-actions.tsx` e `components/club/money-reports.tsx`.

### Pagamento parziale

«½ Pagamento parziale» nel riquadro dell'atleta: la segreteria scrive quanto
è stato pagato davvero (meno del totale), come (contanti e a chi, MB Way,
bonifico, carta, come «Segna pagato»), una foto facoltativa e **perché** non
tutto (obbligatorio, con tre motivi pronti). Vede subito quanto resta.

Il modello è quello delle rate (`installment_no`), deciso al momento: la
quota **si divide in due righe**.

- La quota originale resta `PAID` con `amount_cents` = la parte pagata, e
  tiene tutto ciò che è congelato (listino, sconti, taxa de falta, corso e
  parte del treinador). La parte pagata ha la sua ricevuta
  (`staff_record_payment`, numero progressivo come ogni pagamento).
- Il resto nasce `DUE` con lo stesso tipo, la stessa scadenza, il periodo
  della quota più `/rN` (`2026-10/r1`; un resto pagato a sua volta in parte
  dà `/r2`), `split_from_fee_id` = la quota da cui nasce e `split_reason` =
  il motivo. La descrizione finisce con « · resto».

Così ogni conto che già esiste torna senza casi speciali: l'**incasso** è la
parte pagata, nel mese in cui è entrata (principio di cassa); l'**emesso**
del mese resta la mensilità intera (le due righe hanno la stessa scadenza);
il resto è un **debito** come gli altri: quadro del mese (stato `PARTIAL`,
«pagati X di Y», il motivo), «Questo mese» della famiglia (che lo paga con
una prova), calendario della stagione, scadute, avvisi della mensilità e
multa del 16 (`payment_reminders._due_monthly` legge anche `periodo/r%`),
debiti per anzianità, JAVBOT «chi non ha pagato». La taxa de falta mancata
si calcola dal netto congelato (`accounting.absence_cents`), non più da
`netto − importo`, che il parziale riduce.

Il credito invito (`referrals.on_fee_paid`) arriva **una volta sola**, con il
pagamento che chiude il mese (l'ultimo resto): un mese pagato in due volte
non accredita due volte, e conta un mese solo nella rete di chi ha invitato.

**Annullare**: «↶ Annulla parziale» (`POST /club/admin/fees/{id}/undo-partial`)
annulla la ricevuta della parte pagata (stato `REJECTED`, senza avvisare la
famiglia: è la segreteria che corregge se stessa) e la quota **riassorbe il
resto** (`merge_remainder`): torna una riga sola con l'importo di prima. Lo
stesso succede se la ricevuta si rifiuta da «Comprovativos» o la quota si
riapre. Il resto si riassorbe solo se è ancora intero (da pagare, senza resti
suoi, senza prove collegate): un resto già pagato va annullato prima.

API: `POST /club/admin/fees/{fee_id}/partial-payment` (multipart:
`amount_cents`, `reason`, `method`, `cash_received_by_user_id` o
`cash_received_by_name`, `file` facoltativo) → ricevuta e resto.

### Mese esente («Isenta este mês»)

«🎗️ Isenta este mês» nel riquadro: quel mese l'atleta non deve la mensilità
(assente, infortunato, in viaggio), con un motivo obbligatorio. Nel codice
c'erano già due cose simili, e nessuna era quella giusta da sola:

- `exempt_monthly` sull'atleta = non paga **mai** la mensilità (non gli si
  emette nemmeno la quota);
- `WAIVED` = **condono** di una quota: esce dall'emesso, dai debiti e dagli
  incassi, ma finisce nei «mancati incassi».

Il mese esente riusa `WAIVED` (così è già fuori da emesso, debiti, incassi,
avvisi, multa, quadro e calendario) con `waive_kind = EXEMPT`: la
contabilità lo toglie anche dai **mancati incassi** (sconti e taxa de falta
di quella quota compresi) e lo mostra a parte (`exempt_cents`, «Mesi esenti
(fuori dai conti)»). Il quadro mostra lo stato `MONTH_EXEMPT` con il motivo.

Se la mensilità di quel mese non è ancora emessa (un mese futuro, navigando
con ›), la si emette subito con le regole del job del 1° (gruppo dell'età
federale di quell'anno, sconti di oggi) e si esenta: il vincolo UNIQUE
impedisce al job di ricrearla. Non si esenta una mensilità pagata (o pagata
in parte): prima si annulla il pagamento. **Annullare**: «↶ Annulla
esenzione» (`POST /club/admin/fees/{id}/unexempt`): un mese già arrivato
torna da pagare; uno futuro torna senza quota (la emetterà il job, con i
prezzi di allora; la risposta è `null`).

API: `POST /club/admin/month/exempt` `{athlete_id, period: "AAAA-MM", reason}`.

### Relatórios

Nella Contabilità, scheda **📑 Relatórios**: si sceglie il relatório, la
**stagione** (settembre → agosto) o l'**anno**, si guarda e si scarica in
**CSV** (punto e virgola e virgola decimale, si apre bene con Excel in
portoghese) o **XLSX** (importi come numeri in euro, intestazioni fisse).
Tutto server-side (`GET /club/admin/reports/{report}?season=|year=&format=json|csv|xlsx&lang=`),
con poche query raggruppate e nessun totale salvato. Le intestazioni dei file
sono in portoghese, inglese o italiano (spagnolo → portoghese, francese,
tedesco e ucraino → inglese, come JAVBOT); a schermo le traduce
l'interfaccia.

| Relatório | Che cosa | Come si calcola |
|---|---|---|
| `matrix` — Atleti × mesi | Una riga per atleta (attivo, o con una mensilità nel periodo): nome, n.º sócio, gruppo; una casella per mese: pagato (importo, data, metodo, chi ha ricevuto i contanti), parziale (pagato / da pagare), da pagare, scaduto, esente con il motivo, condonato, non iscritto, futuro, non emessa; totali di riga e di colonna | Mensilità (`MONTHLY`, quota e resti) del periodo. L'XLSX ha le caselle colorate per stato, la legenda e un secondo foglio «Detalhe» con una riga per atleta e mese (per le tabelle pivot) |
| `collections` — Incassi per metodo | Mese × bonifico, MB Way, contanti, carta, credito | Le stesse quote pagate dell'incasso della contabilità (`paid_at`): la somma è l'incasso |
| `debts` — Debiti per famiglia | Famiglia, email, atleti, quote, le cinque fasce di anzianità, scaduto, totale, scadenza più vecchia, giorni di ritardo | Le quote da pagare di oggi (> 0 €), come `accounting.debts` |
| `adjustments` — Esenzioni e condoni | Ogni decisione di non incassare: mese esente, condono, taxa de falta intera e a metà, pagamento parziale; data, atleta, quota, importo, pagato, motivo, chi | Quote condonate (per data del condono), taxa de falta a metà (per scadenza), resti nati nel periodo |
| `cash` — Contanti per persona | Chi ha ricevuto contanti, mese per mese | Quote pagate in contanti, per `cash_received_by` |
| `pnl` — Entrate e uscite | Mese per mese: emesso, incassi (e di cui credito), riscossione, spese, personale, parte dei treinador, commissione, risultato, mancati incassi, mesi esenti | `accounting.monthly_figures`, gli stessi numeri del conto economico |

### Audit della contabilità (ottobre 2026)

Rivisto l'intero giro del denaro: emissione delle quote, pagamenti
(segreteria e famiglie), prove e rifiuti, condoni, credito del wallet e
crediti invito, spese e costi fissi, costo dello staff, conto economico,
libro cassa, debiti, «As minhas contas».

**Solido.** Niente totali salvati: ogni numero si ricalcola dalle righe, con
query raggruppate. Incasso per cassa (`paid_at`), emesso per scadenza.
Idempotenza con vincoli UNIQUE ovunque conti (quote, costi fissi,
percentuale della piattaforma, chiavi dei movimenti del wallet, credito
invito per quota e momento del pagamento). Il rifiuto di una prova riapre
esattamente le sue quote e restituisce il credito nella stessa transazione.
Percentuale della piattaforma e tariffe dello staff con lo storico (un
cambio non riscrive il passato), solo turni chiusi. Prezzi e sconti
congelati all'emissione. Ogni query filtra per club.

**Corretto (con test, `tests/test_club_money2.py`).**

1. **«Segna pagato» senza foto finiva in un errore 500.** La segreteria
   che registrava un pagamento MB Way, bonifico o carta senza allegare la
   foto (che l'interfaccia dice facoltativa) violava il vincolo
   `file_or_credit` delle prove, pensato per le prove delle famiglie. Ora
   una prova registrata dalla segreteria è già controllata
   (`reviewed_by_user_id`) e il vincolo l'accetta (migrazione 0032).
2. **Riaprire una mensilità con la taxa de falta intera** (condonata a 0 €)
   lasciava una quota «da pagare» da 0 €: contava tra chi deve pagare nel
   quadro, faceva partire gli avvisi e la **multa del 16** su una quota da
   0 €. Ora riaprirla toglie la taxa de falta e rimette il netto; avvisi,
   scadute e multa ignorano comunque le quote da 0 €.
3. La taxa de falta intera condonava la quota **senza dire chi né quando**
   (`waived_by_user_id`, `waived_at` vuoti): ora li registra, come ogni
   condono.
4. **Rifiuto di una prova**: il ritiro del credito invito girava prima del
   commit del rifiuto; un errore lì dentro fa rollback e si sarebbe portato
   via il rifiuto stesso (la prova restava accettata mentre la segreteria
   leggeva «rifiutata»). Ora gira dopo il commit, come il pagamento.
5. **Taxa de falta nei mancati incassi**: si calcolava come `netto −
   importo`, giusto solo finché l'importo non cambia per altro; ora si
   calcola dal netto congelato (stessa formula di `absence.apply`).
6. Con i pagamenti parziali: credito invito una volta sola per mese, mese
   contato una volta sola nella rete, resto incluso in avvisi, multa e
   JAVBOT.

**Raccomandazioni (non fatte, da decidere).**

- **Confine dei mesi in UTC.** La contabilità taglia i mesi in UTC
  (`accounting._month_of`), l'elenco delle prove in ora di Lisbona: un
  pagamento fatto tra mezzanotte e l'una del 1° (ora legale) entra nel mese
  prima. Passare tutta la contabilità all'ora del club cambia anche i mesi
  chiusi: va deciso, non corretto di nascosto (`docs/open-questions.md`).
- **Nessuna chiusura dei mesi.** Una correzione riscrive anche un mese già
  comunicato al commercialista (per scelta: niente totali salvati). A fine
  mese conviene scaricare e archiviare l'XLSX `pnl` e `collections`, o
  aggiungere una «chiusura» che congeli il mese.
- **Libro cassa**: la colonna metodo dice «prova» o «a mano», non il metodo
  vero (`payment_method`); il relatório `collections` lo dà, ma il libro
  cassa potrebbe mostrarlo.
- **«As minhas contas»**: il credito usato per le quote si somma per chi ha
  caricato la prova; un atleta adulto che carica con il credito del
  genitore non comparirebbe nel conto del genitore. Meglio sommarlo per
  famiglia delle quote coperte.
- **Commissione della piattaforma sul credito invito**: la percentuale si
  applica all'incasso compresa la parte pagata con il credito del wallet,
  che il club non ha ricevuto in denaro. È una scelta commerciale da
  confermare.
- **Costi fissi**: la spesa del primo mese porta il giorno del costo fisso
  anche se cade prima della data d'inizio.

### Eventi annullati e conti alla rovescia

Un evento della rete annullato resta in calendario con il nome che inizia per
«ANULADO — », stato `CLOSED` e il motivo nella descrizione (non si cancella:
le iscrizioni restano tracciate). Per questi eventi il conto alla rovescia non
compare. Il conto alla rovescia (`components/site/countdown.tsx`, istante da
`lib/event-time.ts::moment`) mostra la chiusura delle iscrizioni finché sono
aperte, poi l'inizio della gara; nella pagina della gara tutti e due, grandi.

## Il tema del club nelle aree riservate

Segreteria, treinador, famiglia e atleta vedono i **colori e il logo del loro
club** (quelli dell'editor del sito: `club_sites.brand_primary/secondary/accent`,
`logo_url`). `GET /club/branding` (qualunque utente del club; il superadmin
quello del club in cui è entrato) → `lib/club-branding.ts::useClubBranding`,
che genera le scale `brand-*` (dal colore principale, scurito quanto basta per
il testo bianco) e `accent-*` (`lib/brand.ts::paletteVars`) e le scrive su
`<html>`, così valgono anche per le finestre in portale. `AppShell clubBranding`
mostra in alto il logo e il nome del club (JAV se il club non ha un logo). La
console della piattaforma resta JAV. È dinamico: salvando il sito la segreteria
vede subito i colori nuovi; le altre aree li rileggono entro un minuto o
tornando sulla scheda.

## «Quero participar» e i debiti che bloccano

Su ogni evento del calendario (lista del sito e delle aree, pagina dell'evento,
prove dell'area atleta, pagina delle prove della famiglia) c'è il bottone
**Quero participar** (`components/club/participate-button.tsx`). Chi non è
entrato va al login e torna sulla pagina; se qualcuno del conto è già iscritto
il bottone diventa «Inscrito», spento; sugli eventi di altri club non compare.

Il clic apre una finestra con gli atleti del conto (`GET
/club/participation/{competition_id}`): già iscritto, può (il titolare iscrive,
l'atleta con il suo accesso avvisa il titolare), non può (età, atestado…) o
**ha debiti**. Le regole sono in `club/participation.py`:

- blocca ogni quota `DUE` con scadenza **prima di oggi**, dell'atleta o del
  conto (quota socio del titolare), escluse la quota della gara stessa e
  quelle segnate **non bloccanti**;
- il controllo è dentro `competitions.eligibility`, quindi vale per ogni
  iscrizione della famiglia (anche `POST /club/competitions/{id}/entries`), e
  per il «Voglio partecipare» dell'atleta (`/athlete-area/…/wish`);
- con debiti la finestra li elenca con il totale e il titolare li paga subito
  (`PayModal` con le quote già scelte); l'atleta che non è titolare legge che
  deve chiedere a chi lo ha iscritto.

`GET /club/participation/mine` dà le gare con un iscritto del conto e lo slug
del club; `POST /club/participation/{competition_id}` `{athlete_id}` iscrive o
manda la richiesta. Le rotte valgono per qualunque utente del club (come
`/club/branding`).

**Debito non bloccante** (migrazione `0036`, `club_fees.non_blocking`): nella
lista delle quote della segreteria, sotto lo stato di una quota scaduta, c'è
«🔓 Não bloquear provas» (`POST /club/admin/fees/{id}/blocking
{non_blocking}`, registrato nell'audit). La quota resta da pagare, ma non
impedisce più le iscrizioni; si torna indietro con lo stesso bottone.

### Relatórios di eventi e lezioni

- Segreteria: **Eventos e provas → Relatórios** (eventi, con costi, foto e PDF
  per periodo) e il nuovo menu **Relatórios das aulas** (`section=lessons`):
  il quaderno dei treinador in modalità segreteria (`CoachNotebook manager`),
  tutte le turmas e le note sugli atleti.
- Treinador: **Eventos** (relatório dell'evento fatto, risultati) e
  **Caderno** (relatório della lezione e note per atleta).

## Judogi: calcolatore, ordini e lista dei desideri (migrazione 0039)

Il calcolatore del sito vecchio (`judoartevida.com/jav/fatos`) e i «pedidos de
fato» del gestionale vecchio diventano una cosa sola, in `club/judogi.py`
(rotte in `club/judogi_router.py`).

**Il conto** è quello di prima, calcolato sempre sul server:

    totale = max(0, listino[tipo][marca][colore][taglia]
                    + personalizzazione obbligatoria
                    − round(listino[judogi restituito] × permuta %))

- **Il listino è un dato** (`club_judogi_prices`: tipo, marca, colore, taglia,
  prezzo, attivo), non un array nel codice. Ogni club parte con quello del
  calcolatore vecchio (`judogi.base_catalog()`: 4 tipi, 333 righe), caricato
  dalla migrazione nei club esistenti e da `clubs.create_club` nei nuovi; la
  segreteria lo cambia da **Judogi → Listino** (o lo ricarica se è vuoto).
  Due refusi corretti: il bianco da Treino 100 e 110 cm di Tochi Gi e NKL
  costava 13 e 14 €, ora 23 e 24.
- **Personalizzazione** (35 €) e **permuta** (50%) sono regole del club
  (`clubs.settings["judogi"]`, **Judogi → Regole**).
- **La taglia** si sceglie dall'altezza fra quelle che esistono per quel
  judogi: la prima non più piccola (il cotone si ritira, i bambini crescono),
  oltre l'ultima l'ultima. Il vecchio diceva «nessuna marca» a 95 cm.
- Il browser manda le scelte, mai un prezzo: `GET /club/judogi/catalog`
  (l'albero tipo → colore → marca → taglie con la taglia consigliata per
  `height_cm`) e `POST /club/judogi/quote`.

**Chi ordina** (`judogi.my_athletes`): il **titolare** per ognuno dei suoi
atleti; l'**atleta maggiorenne** (età reale ≥ 18) con il suo accesso, per sé.
L'atleta minorenne vede tutto ma **non compra**.

**L'ordine** (`POST /club/judogi/orders`) ricalcola il conto, controlla il
nome da ricamare (**sotto i 13 anni solo il nome proprio**, come prima) e lo
congela su `club_equipment_orders` (listino, personalizzazione, permuta,
codice del colore; `color` resta il nome, letto da `obligations.py`). Nasce la
quota **`EQUIPMENT`** dell'atleta (`period` = id dell'ordine, quindi una sola),
con scadenza a 14 giorni: si paga come ogni altra quota. Lo stesso judogi per
lo stesso atleta può essere **in attesa una volta sola** (indice unico
parziale): due clic non fanno due ordini. La segreteria riceve la notifica
`CLUB_JUDOGI_ORDER`.

**La segreteria** (menu **Judogi**): ordini per stato (Pendente → Em
preparação → Entregue, o Cancelado) con ricerca e **CSV per il fornitore**
(per default i pendenti); il titolare riceve `CLUB_JUDOGI_ORDER_STATUS`.
Un ordine annullato non si riapre; la sua quota, se non è pagata né dentro una
prova, se ne va con lui (una pagata resta: il rimborso lo decide la
segreteria). Gli ordini importati dal gestionale vecchio senza prezzo si
prezzano a mano («Definir o valor»), e solo allora nasce la quota. La
segreteria può anche ordinare per un atleta (`POST /club/admin/judogi/orders`).

**La lista dei desideri** (`club_wishlist_items`): nella **Loja** dell'area
dell'atleta il minorenne mette ♡ a un prodotto dello Shop o salva il judogi del
calcolatore; il titolare riceve `CLUB_WISHLIST_ADDED` (pallino sulla voce Shop).
In cima allo Shop della famiglia c'è «Os desejos dos teus filhos»: per un
judogi si apre il calcolatore già compilato e l'ordine chiude il desiderio
(`wish_id`); per un prodotto si apre la scheda dello Shop con l'atleta scelto,
e l'ordine dello Shop per quell'atleta chiude i desideri di quel prodotto
(`jav_market.create_order` → `judogi.mark_products_ordered`). Oppure «Já
comprado» / «Fica para outra vez» (`PATCH /club/wishlist/{id}`): l'atleta
riceve `CLUB_WISHLIST_DECIDED`. Un prodotto aperto una volta sola per atleta,
un solo judogi desiderato alla volta (il nuovo sostituisce il vecchio).


## La Loja del club (migrazione 0040)

Judogi ed equipaggiamento del club (t-shirt, camisola, calças, calções,
casaco, saco com o nome…) si comprano dalla **Loja**, in un carrello solo,
con le regole su per chi è ogni articolo. Codice: `club/loja.py`, rotte in
`club/loja_router.py`; il judogi passa ancora da `club/judogi.py`.

**Per chi è** (controllato all'ordine, sul server, non solo a schermo):
- un prodotto del club dice per chi è (`jav_market_products.audience_sex`
  ALL / F / M): un atleta vede la versione del suo sesso e quelle per tutti,
  l'altra **non si mostra** (sarebbe la stessa t-shirt due volte);
- l'**equipaggiamento di alta competizione** (`high_competition_only`) e il
  **judogi aprovado FIJ** (che riceve il backnumber oficial con PT sulla
  schiena) li **vedono tutti**, chiusi con il lucchetto, e li compra solo chi
  è di alta competizione;
- il judogi **rosa** e **a righe rosa** è solo per le ragazze: si vede, un
  ragazzo non lo compra.

**Alta competizione**: un segno sull'atleta (`club_athletes.high_competition`,
con chi l'ha messo e quando) che mettono e tolgono **la segreteria e il
treinador** che segue l'atleta (`PUT /club/staff/loja/athletes/{id}/high-competition`).
Si può mettere solo se il piano dell'atleta lo permette
(`club_plans.allows_high_competition`: il **Grupo 3**; la migrazione l'ha
acceso sui piani che si chiamano «Grupo 3…», gli altri li apre la segreteria
da Piani e prezzi). Se l'atleta cambia piano il segno resta ma **non vale più**
(`loja.high_competition_map`). Al banco la segreteria può ordinare qualunque
judogi per un atleta (`check_rules=False`).

**La vetrina** (`GET /club/loja/athletes/{id}`): i modelli di judogi con le
foto (`club_judogi_models`: una scheda per tipo + marca + colore del listino,
creata da sola; i prezzi restano nel listino) con il prezzo della taglia
giusta per l'altezza; i prodotti del club per l'atleta, con la **taglia
suggerita** (la prima variante con `max_height_cm` ≥ altezza, come per i
judogi); il **kit del club** (judogi bianco + prodotti `club_kit`: «Já tem» se
consegnato, «Encomendado» se in corso, «Em falta»); l'armadio dell'atleta.

**Il judogi** si sceglie con un percorso a passi (per chi, tipo, colore e
modello con foto, nome da ricamare, judogi usato, riepilogo). La **permuta**
può indicare un judogi dell'armadio (`trade_in.owned_order_id`): tipo, marca,
colore e taglia si leggono dall'ordine, e alla consegna del nuovo quello
restituito esce dall'armadio (`retired_reason` TRADED_IN). Alla fine:
«Adicionar ao carrinho» o «Comprar já e pagar», come un prodotto.

**Il carrello** (`club_cart_items`, uno per utente): righe di judogi
(configurazione, mai prezzi) e di prodotti (variante, quantità, il nome se il
prodotto `needs_name`), per uno o più atleti. Si ricalcola a ogni lettura; una
riga che non si può più ordinare dice perché. **All'ordine ogni riga diventa
un ordine a sé** (`club_equipment_orders`, `kind` JUDOGI o PRODUCT) con la sua
quota `EQUIPMENT` (14 giorni), **tutti o nessuno**: la segreteria li prepara e
consegna uno per uno, la famiglia li paga **tutti insieme** con una prova
(«Encomendar e pagar já» apre il pagamento con le nuove quote già scelte) o
più tardi dalla home («Encomendar, pago depois»). La scorta delle varianti
scende all'ordine e torna se l'ordine si annulla prima della consegna. Un
desiderio dell'atleta si chiude quando parte l'ordine. «Comprar já»
(`POST /club/loja/buy-now`) fa lo stesso con un articolo solo, senza toccare il
carrello. Un minorenne non compra: mette nei desideri, come prima.

**La quota dell'attrezzatura** compare tra le cose da pagare del mese **da
subito**, qualunque sia la scadenza (`month_board.py`): è un acquisto già
fatto. Gli ordini del club stanno anche in «As minhas encomendas» con lo stato
e il bottone per pagare.

**La segreteria** (menu Judogi): gli ordini della Loja (judogi ed
equipaggiamento, stessa lista, stessi stati, stesso CSV per il fornitore),
le **foto dei modelli** di judogi (`/club/admin/loja/judogi-models`, foto
caricate come quelle dei prodotti), il listino. Nello shop del club ogni
prodotto ha «Para quem é» (sesso, alta competizione, kit, nome) e ogni
variante l'altezza fino a cui va bene.

**L'armadio dei judogi** (`GET /club/staff/loja/judogis`, segreteria e
treinador, ognuno con gli atleti che vede): i judogi consegnati e non ritirati
di ogni atleta (più quelli in arrivo), con bianco / azul / FIJ e «pequeno» se
la taglia è sotto l'altezza attuale. Con una **prova** mostra solo i suoi
iscritti e che cosa manca (bianco o azul): il treinador porta il judogi del
club a chi non ce l'ha. Un judogi che l'atleta aveva già si aggiunge a mano
(`origin` MANUAL, senza prezzo né quota); uno piccolo, rovinato o perso esce
dall'armadio (`retired_on`, `retired_reason`). Gli obblighi dell'atleta
(`obligations.py`) contano solo i judogi non ritirati.


## Un treinador, più club (migrazione 0041)

Un account solo può allenare in più club (Matias in tutti, un altro in due):
ogni club in cui è treinador è una riga di `club_staff_memberships` (ACTIVE).
Codice: `club/staff_clubs.py`, rotte in `club/staff_clubs_router.py`, la
scelta del club in `club/scope.py`.

- **Entrando** nell'area del treinador vede il saluto con il suo nome e la sua
  foto (`users.photo_url`, o quella della sua scheda di atleta) e i club in cui
  allena, con logo, atleti attivi e i suoi corsi (`GET /club/staff/my-clubs`):
  sceglie dove entrare. La scelta sta nel cookie `jav_staff_club` e arriva
  all'API come `X-Jav-Staff-Club`.
- **La scelta vale solo per le rotte del treinador** (`club.instruct`) e per il
  tema dell'area del treinador (`/club/current` e `/club/branding` con
  `?area=staff`). Famiglia, atleta e segreteria restano sul club dell'account
  (`users.club_id`): un treinador che è anche genitore non mescola i dati.
- **In un club che non è il suo è solo treinador**: `ClubUser.home` è falso e
  nessun controllo «è segreteria» (`_manager`, `_is_manager`, `_can_manage`,
  le liste dei corsi) lo fa manager, qualunque ruolo abbia a casa.
- **Chi assegna**: il superadmin (`POST/DELETE /clubs/{id}/coaches`, elenco
  `GET /clubs/coaches`, foto `PUT /clubs/coaches/{id}/photo`). La segreteria
  che aggiunge come istruttore un'email di un altro club manda una richiesta
  (REQUESTED, notifica `CLUB_COACH_REQUESTED` allo staff della piattaforma)
  che il superadmin approva; segreteria e superadmin tolgono da un club un
  treinador che viene da fuori (`DELETE /club/admin/coaches/{id}`,
  `DELETE /clubs/{id}/coaches/{user}`). Un
  istruttore nuovo creato dalla segreteria entra ACTIVE nel suo club.
- **Nelle liste del club** (persone, staff, chi riceve contanti, costi dello
  staff) il treinador di un altro club compare **solo come treinador** (né
  genitore né segreteria), con l'icona del treinador. I treinador di un club
  (`staff_clubs.active_coach_ids`) sono i suoi istruttori (finché hanno il
  ruolo, anche senza la riga: gli importati) più le appartenenze ACTIVE di chi
  viene da fuori. Per questo nel club dell'account non si toglie
  l'appartenenza: si toglie il ruolo di istruttore.

