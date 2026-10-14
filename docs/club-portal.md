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
| Genitore (o atleta adulto) | `CUSTOMER` | Gestisce la famiglia: figli, quote, prove di pagamento, certificati, gare, ordini di materiale |
| Segreteria del club | `SECRETARY` | Piani, gare, risultati, eccezioni sui pagamenti, staff e IBAN del club — solo del suo club |
| Istruttore | `INSTRUCTOR` | Corsi, presenze, passaggi di cintura — solo del suo club |
| Superadmin della piattaforma | `SUPER_ADMIN` | Crea i club, ci entra per sistemarli, gestisce lo Shop |

**Solo il genitore accede.** I figli sono *atleti* senza account: non hanno
email né password. Un adulto che si allena è un genitore con un atleta
"me stesso" (`Athlete.is_self`).

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
- `plan_id` → piano assegnato. **Calcolato dall'età** alla creazione e a ogni
  inizio stagione; la segreteria può forzarlo (`plan_locked = true`).
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
- **L'età si calcola al 1° settembre** della stagione in corso, come nelle
  categorie federali: un bambino non cambia piano a metà anno perché compie
  gli anni a febbraio.

### Quota — `club_fees`
- `athlete_id`, `kind`: `MONTHLY` / `ENROLLMENT` / `COMPETITION` / `MEMBERSHIP`.
  `MEMBERSHIP` (quota socio del genitore) non ha atleta: ha `guardian_user_id`.
- `period` (`YYYY-MM` per le mensili, l'anno solare `YYYY` per iscrizione e
  quota socio, l'id della gara per le gare), `amount_cents`, `due_date`.
- `gross_amount_cents` (listino), `discount_cents`, `discount_note` (gli
  sconti in parole): congelati con il prezzo.
- `status`: `DUE` → `PAID` (oppure `WAIVED`, condonata dalla segreteria).
  La segreteria può anche segnarla pagata a mano (contanti in palestra) e
  riaprire un condono o un "pagata a mano" sbagliato; una quota pagata con
  una prova si riapre solo rifiutando la prova.
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

### Prova di pagamento — `club_payment_proofs`
- Il file (foto o PDF) nel bucket privato documenti, come le prove dei bonifici
  degli ordini. Si scatta dal telefono (`<input capture="environment">`).
- Una prova copre **una o più quote** (`club_payment_proof_fees`): un genitore
  con due figli fa un bonifico solo.
- `status`: `ACCEPTED` / `REJECTED`, `reviewed_by_user_id`, `rejection_reason`.

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
- Slot settimanali: giorno della settimana, ora inizio/fine, sala.
- Presenza: (`athlete_id`, `course_id`, `date`) UNIQUE, segnata dall'istruttore
  da tablet o telefono con un tocco per atleta.

### Gare — `club_competitions`, `club_competition_entries`
- Gara: nome, data inizio/fine, luogo, organizzatore, livello (`CLUB` /
  `REGIONAL` / `NATIONAL` / `INTERNATIONAL`), scadenza iscrizioni, quota di
  iscrizione, `requires_agonistic_certificate`, età minima/massima
  facoltative (al giorno della gara), stato `OPEN` / `CLOSED` / `DONE`.
- Iscrizione: atleta, categoria (età/peso, testo), stato `REGISTERED` /
  `WITHDRAWN`, e il risultato: `placement` (1, 2, 3, 5, 7, oppure
  partecipazione), inserito dalla segreteria a gara finita.
- Iscriversi crea la quota `COMPETITION` (se la gara ha una quota), che si
  paga con la stessa prova di pagamento di tutto il resto. Ritirarsi entro la
  scadenza condona la quota non pagata; reiscriversi la riapre.
- **Gara o stage** (`kind`): lo stage (allenamento collegiale) si gestisce
  come una gara (iscrizioni, quota, certificato) ma non ha piazzamenti e non
  dà punti né medaglie.

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
- Punti per risultato × coefficiente del livello di gara, per stagione:

| Risultato | Punti | | Livello | Coefficiente |
|---|---|---|---|---|
| 1° | 100 | | Club | 1 |
| 2° | 70 | | Regionale | 2 |
| 3° | 50 | | Nazionale | 3 |
| 5° | 30 | | Internazionale | 4 |
| 7° | 20 | | | |
| Partecipazione | 10 | | | |

- Classifiche per stagione, sesso e fascia d'età (Bambini fino a 7,
  Fanciulli 8–9, Ragazzi 10–11, Esordienti 12–13, Cadetti 14–16, Juniores
  17–19, Seniores 20+, all'età del 1° settembre). Calcolata dai risultati,
  mai salvata a mano: correggere un risultato corregge la classifica.
  Ex aequo: stessa posizione, e i posti successivi si saltano (1, 1, 3).
- Nella classifica il nome è "Nome I.": la vedono tutte le famiglie.

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
| 1° del mese, 03:00 | Genera le quote mensili di ogni atleta `ACTIVE` dal suo piano |
| 1° gennaio, 03:30 | Anno nuovo: iscrizioni dell'anno e quote socio dei genitori |
| 1° settembre, 03:30 | Nuova stagione: ricalcola i piani per età (salvo `plan_locked`) |
| Ogni giorno, 08:00 | Avvisi: quote scadute, certificati in scadenza/scaduti, tesseramenti in scadenza, scadenze iscrizioni gare |
| Ogni giorno, 01:00 | Chiude le iscrizioni alle gare con scadenza passata e prepara (o manda) la richiesta di trasporto |
| Ogni giorno, 03:10 | I costi fissi del club diventano le spese del mese in corso (vedi "Contabilità") |

Ogni job gira club per club, solo sui club attivi, ed è idempotente
(vincoli UNIQUE, non flag applicativi). I promemoria
già inviati stanno in `club_reminders_sent` (UNIQUE su tipo, entità,
gradino): un avviso a 30 giorni, uno a 7, uno a scadenza passata, ciascuno
una volta sola. La segreteria può rilanciare a mano la generazione delle
quote del mese e l'inizio stagione (`/club/admin/jobs/...`).

## Sito pubblico

Il portale **JudoArteVida** (`/`, `/clubes`, `/clubes/<slug>`, `/judocas/<id>`,
`/eventos`, `/eventos/<id>`, `/ranking`) presenta la rete dei club come una
federazione: chi è, i club attivi in un carosello, gli eventi, il ranking, le
ultime medaglie, e come iscriversi. Non serve il login; il login resta a un
clic ("Entrar" in alto). Le API sono `GET /public-site/...`, senza
autenticazione (`club/site_router.py`, servizio `club/site.py`).

**Si scrive poco, il resto arriva da solo.** La segreteria scrive solo la
pagina del club (`club_sites`: frase, presentazione, città, copertina, logo,
galleria, allenatori, contatti, social) dall'editor della pagina
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
- negli eventi, gli iscritti senza consenso contano nel totale ma non hanno
  nome;
- le pagine dei judoca non si indicizzano (`noindex`): un minore non deve
  finire nei motori di ricerca con il suo nome;
- ogni consenso, ritiro e pubblicazione va nell'audit con chi l'ha deciso
  (`consent_by_user_id`).

**Gli allenatori** si presentano a mano nell'editor (nome, ruolo, foto): un
account da istruttore non è un consenso a comparire sul web.

**Le foto** vanno nel bucket pubblico dei media (`upload_media`, come le foto
degli atleti): JPG, PNG o WebP fino a 5 MB, galleria di al massimo 24 foto.
Gli indirizzi (social, mappa, sito) devono essere `http(s)://`.

### La scheda del judoca

`/judocas/<id>` è la pagina personale di ogni judoca pubblico, in stile
scheda IJF: ritratto sul gradiente del club, nome, club, cintura, Portogallo,
i numeri chiave (posto nel ranking della sua fascia nella stagione, punti
della stagione e di sempre, medaglie, gare), la scheda (club, fascia,
categoria, cintura, tecnica, guardia), e le sezioni Risultati, Prossime
gare, Foto, Video, Percorso (le cinture con le date). Il ranking (pagina
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
Il backend è `apps/api/app/domains/javbot/`; per ora il "cervello" è
deterministico (parole chiave in portoghese, italiano e inglese), ma è
costruito come un agente vero: strumenti con nome, descrizione e parametri
in JSON Schema, che un modello linguistico potrà usare tali e quali.

### Che cosa sa fare

Nell'area privata (`/api/javbot/...`, qualsiasi utente con una sessione):

| Chiede | Risponde / fa |
|---|---|
| "Quanto devo pagare?" | Le quote da pagare per figlio (più la quota socio), quelle scadute, la prossima scadenza, IBAN e intestatario del club, il bottone "Carica un pagamento" |
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
scrivere, idempotente; uso nel docstring).

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

### Come collegare un modello vero (Claude) più avanti

Il punto da cambiare è uno: `Planner.reply` in `javbot/planner.py` (la
docstring del modulo ha i passi). In breve: al modello si danno
`REGISTRY.specs(audience="private")` come strumenti, un prompt di sistema con
le regole qui sopra e gli ultimi messaggi; ogni chiamata del modello passa da
`REGISTRY.call` (stessi permessi, stesso club); le azioni che scrivono restano
proposte (`JavbotTask` PENDING) che solo l'utente conferma. Router,
tabelle e interfaccia non cambiano. Per il sito, lo stesso con
`audience="public"` in `javbot/public.py`.

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
