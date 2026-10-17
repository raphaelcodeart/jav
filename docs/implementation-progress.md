# Implementation Progress

Aggiornato alla fine di ogni sessione di lavoro. È il registro autorevole di
"cosa è fatto davvero e cosa no": `architecture.md` descrive l'obiettivo, questo
file la realtà. Una voce per sessione, in italiano, che dice cosa è cambiato
**e perché** (CLAUDE.md §7).

## Stato dei moduli

### Backend (`apps/api/app/domains/`)

| Modulo | Stato | Note |
|---|---|---|
| `auth`, `users`, `organizations`, `rbac`, `audit` | costruito | login con Organization ID, sessioni con rotazione del refresh token, reset password (sempre alla casella dell'account), verifica email, OTP, PIN JavCash, blocco dopo 5 tentativi, controlli d'ingresso (profilo, privacy). Ruoli di sistema incluso `INSTRUCTOR` |
| `club` | costruito (backend) | atleti gestiti dal genitore, piani per età (1° settembre), quote mensili/iscrizione/gara idempotenti, prove di pagamento accettate subito e rifiutabili, certificati medici, cinture, corsi e presenze, gare e risultati, Jav Ranking, livelli e medaglie, promemoria. 4 job Celery beat. **Più club** sulla stessa piattaforma (`clubs`, `club_id`, `club/scope.py`), segreteria per club, registrazione delle famiglie dal link del club. Spec: `club-portal.md` |
| `network`, `referral`, `friend_referrals` | costruito | rete a closure table, snapshot all'attivazione, link promoter, "Invita un amico" a un livello |
| `commissions` | costruito, con placeholder | motore deterministico con anteprima accettata dall'amministrazione, quote per rata, valutazione mensile dei gradi. Cifre dei gradi provvisorie (`open-questions.md` #1); regola del 33% non collegata (#6) |
| `customers`, `catalog`, `contracts` | costruito | contratti generici (nessun punto di fornitura), pratica con N contratti e un bonifico, piani FULL / 3 / 12 rate confermati dall'amministrazione, prezzo e IVA congelati, cashback sul contratto, fascicolo zip |
| `orders` | costruito | acquisti dal catalogo, bonifico + JavCash, cashback opzionale |
| `jav_market`, `carts`, `marketplaces`, `shop_categories` | costruito | lo Shop con catalogo scritto dall'amministratore, varianti, carrello, spedizione, ordine minimo, invio alle aziende produttrici, `athlete_id` sull'ordine |
| `wallets` | costruito | JavCash, bonus di benvenuto, trasferimenti abilitati per promoter, storni, lock in ordine di id contro i deadlock |
| `accounting` | costruito | movimenti in euro e JavCash per cliente e per organizzazione, dettaglio con cronologia |
| `documents`, `documentation`, `notifications`, `support`, `product_requests`, `reports`, `outbox` | costruito | |

### Frontend (`apps/dashboard`)

| Parte | Stato |
|---|---|
| Pulizia delle funzioni tolte (fornitori esterni, carta, Google Drive, riscatti) | fatta, typecheck verde |
| Redesign: tema chiaro unico con i colori del club, sistema di componenti, animazioni ed effetti 3D, card atleta, login con scena 3D | **in corso** |
| Interfaccia del portale club (famiglia, segreteria, istruttori) | **da fare**, sopra il redesign |
| Rimozione dei campi luce/gas dall'interfaccia | **in corso** insieme al redesign |

### Infrastruttura

| Parte | Stato |
|---|---|
| Docker Compose (`docker-compose.dev.yml`, in esecuzione), nginx interno su `127.0.0.1:8081`, Caddy sull'host per l'HTTPS | fatto |
| MinIO da `cgr.dev/chainguard/minio` (`minio/minio` non è più su Docker Hub) | fatto |
| Migrazione unica `0001_schema_iniziale.py` (85 tabelle) e `database-schema.sql` rigenerato | fatto |
| Backup in cron (§4.8 della guida) | da verificare sul server |
| SMTP | da configurare |

### Non costruito (e non previsto a breve)

Pagamenti con carta (scelta: solo bonifico e JavCash), CI/CD, MFA,
scansione antivirus degli upload, backup off-server e dei file MinIO, motore
AI/pgvector (`ai-architecture.md` è solo un progetto).

## Sessione 1 — 2026-10-13/14 — Nasce Jav: gestionale per palestre e club di judo

Il progetto riparte da zero come prodotto nuovo, su una base di codice
esistente dell'autore. Cosa è cambiato e perché:

- **Nome e marchio.** Il software si chiama Jav. Tolti dal codice, dai nomi
  dei file, dallo schema e dalla documentazione ogni nome, logo, dominio,
  email e dato reale (IBAN, codici fiscali, PEC, persone) della base di
  partenza. Nuovo logo e icone. Repository git nuovo, remote unico
  `https://github.com/raphaelcodeart/jav`.
- **Reset password.** Tolto il recapito delegato per gli account
  amministratori: il link va sempre alla casella dell'account, perché un
  recapito di terzi nel recupero password è un rischio, non una comodità.
- **Contratto di collaborazione** trasformato in un modello con segnaposto
  (`[RAGIONE SOCIALE]`, …): il testo legale va compilato dal club e rivisto da
  un legale.
- **Tolte le funzioni che non servono a un club**, per avere una base
  pulita e senza chiavi API:
  - pagamenti con carta (Stripe): si paga con bonifico confermato
    dall'amministrazione, o con la prova caricata dal genitore per le quote;
  - i sette negozi collegati a fornitori esterni e l'import prodotti: resta
    lo Shop con catalogo scritto dall'amministratore;
  - Google Drive, partner e cashback sulle bollette;
  - tutta la parte luce/gas (punti di fornitura, POD/PDR, tipo energia):
    contratti, pratiche e catalogo sono generici, il tipo di prodotto
    `SERVICE` prende il posto di quello energetico.
- **Nuovo dominio `club`** (backend, 65 endpoint, test dedicati): vedi
  `club-portal.md`. Scelta di fondo: il club si autogestisce — le quote si
  generano da sole e la prova caricata dal genitore vale come pagamento,
  salvo rifiuto della segreteria.
- **Bug trovato e corretto**: i permessi `organization.manage`,
  `users.manage_lifecycle` e `wallet.credit` esistevano solo grazie a vecchie
  migrazioni dati, e il bootstrap non li assegnava: un'installazione nuova
  non li aveva. Ora sono nel catalogo `PERMISSIONS`.
- **Nuovo endpoint** `GET /organizations/me/payment-info`: IBAN, intestatario
  e istruzioni per ogni utente collegato (prima arrivavano da un endpoint del
  modulo riscatti, tolto).
- **Database**: la storia delle migrazioni è sostituita da una sola
  migrazione iniziale generata dai modelli; le chiavi esterne sono create
  dopo tutte le tabelle per via dei cicli. Verificata confrontando colonna
  per colonna lo schema migrato con quello dei modelli: nessuna differenza.
  Upgrade, downgrade e di nuovo upgrade funzionano.
- **Infrastruttura**: HTTPS con Caddy sull'host, nginx solo interno; MinIO
  da Chainguard.
- **Test**: 413 verdi sulla suite completa prima della migrazione unica.
- **Documentazione** riscritta per il prodotto nuovo; tolti i documenti che
  descrivevano solo funzioni rimosse.
- **In corso**: redesign grafico (tema chiaro, rosso/giallo/grigio del
  logo del club, animazioni ed effetti 3D) e poi l'interfaccia del portale
  club; deploy della nuova versione su `https://jav.ecodo.ai` dopo i test.

## Sessione 2 — 2026-10-14 — Tre lingue: portoghese, inglese, italiano

- **Bandierina della lingua** in alto (barra dell'app e pagine di accesso):
  portoghese europeo per primo e come lingua predefinita, poi inglese e
  italiano. Perché: il club ha famiglie che non leggono l'italiano.
- **Come funziona**: la scelta sta in un cookie (`jav_lang`), non nell'URL,
  così ogni link, redirect ed email esistente continua a funzionare; il layout
  radice lo legge e il server disegna già la lingua giusta (niente sfarfallio).
  Nessuna libreria nuova: un dizionario per lingua in
  `apps/dashboard/lib/i18n/messages/`, con `it.ts` come sorgente e i tipi che
  impediscono di dimenticare una chiave in `pt.ts`/`en.ts`. Bandiere in SVG,
  perché Windows non ha le emoji delle bandiere.
- **Tradotto**: accesso, recupero password e conferma email; barra, menu e
  notifiche (le etichette); area famiglie del club (home, atleti, certificati,
  pagamento delle quote, gare, ranking, corsi); cinture, livelli, piazzamenti,
  traguardi e fasce d'età in base al codice. Importi e date seguono la lingua.
- **Login**: la rotta BFF restituisce anche un `code` (`invalid`, `locked`,
  `rate`, `disabled`), così l'errore si mostra nella lingua scelta.
- **Non ancora tradotto**: admin, promoter, staff, Shop, contratti, wallet; i
  testi generati dal backend (errori, titoli delle notifiche, email, motivi di
  non idoneità a una gara). Il passo successivo è passare la lingua all'API
  (`Accept-Language` dal proxy BFF) e salvarla sull'utente per le email.

## Sessione 3 — 2026-10-14 — Più club, e la prova di pagamento che chiede "per cosa"

**Cosa.** La piattaforma ospita più club. Il superadmin crea un club (per
esempio "Judo Clube de Lagos") con il suo indirizzo per le famiglie
(`/c/judo-clube-de-lagos`) e la sua segreteria; la segreteria entra e vede
solo il suo club: atleti, quote, prove, certificati, gare e iscrizioni, corsi,
più due sezioni nuove, **Ordini Shop** (gli ordini delle famiglie del club, in
sola lettura) e **Impostazioni** (IBAN delle quote, link di registrazione,
staff). Il superadmin vede l'elenco dei club e con **Entra** apre la gestione
di uno come la vede la sua segreteria.

"Carica un pagamento" ora chiede per prima cosa che cosa si è pagato:
**quote del club** (come prima: pagate subito, IBAN del club) oppure un
**ordine dello Shop** (si sceglie l'ordine e si allega la ricevuta, che la
piattaforma guarda prima di confermare il bonifico). La prova per gli ordini
dello Shop prima non esisteva: le colonne c'erano, la rotta no, e il pulsante
"Vedi prova di pagamento" del pannello ordini rispondeva 404.

**Perché così.** Lo Shop resta unico (scelta dell'utente), quindi il club non
poteva essere un'organizzazione a sé: catalogo, JavCash e ordini sono della
piattaforma. Il club è un livello sotto l'organizzazione (`clubs`, migrazione
`0002`), con `club_id` su ogni tabella del dominio club e sugli utenti. Chi
lavora su quale club lo decide un posto solo, `club/scope.py`: un account di
un club è chiuso nel suo, lo staff della piattaforma sceglie (cookie
`jav_club` → intestazione `X-Jav-Club` nel proxy BFF). Le funzioni del
servizio ricevono un `ClubScope` invece di un `organization_id`, così una
query che dimentica il club non compila più con il nome sbagliato.

**Altro.**
- Nuovo ruolo `SECRETARY` (segreteria di un club) e permessi `clubs.manage`
  (creare i club) e `clubs.enter` (entrarci); area `/club` per la segreteria.
- Le famiglie si registrano dal link del club (`POST /auth/register-family`),
  senza promoter.
- I job automatici girano club per club, solo sui club attivi: prima il
  promemoria di scadenza iscrizioni di una gara sarebbe arrivato alle
  famiglie di tutti i club.
- Senza SMTP l'invito alla segreteria non parte: il link di primo accesso
  compare a chi crea l'account, che lo consegna a mano.
- La migrazione ha messo i dati che c'erano (genitore e atleti demo) in un
  club "Club demo" (`/c/club-demo`).
- Creati gli account `superadmin@judoartevida.com` (SUPER_ADMIN) e
  `admin@judoartevida.com` (ADMIN) della piattaforma.
- Test: `tests/test_club_multi.py` (isolamento tra club, chi lavora su quale
  club, creazione, registrazione, prova di un ordine Shop); i test del club
  usano la fixture `scope`.

## Sessione 4 — 2026-10-14 — Fornitori dello Shop, sconti, iscrizione annuale, trasporti

**Shop e fornitori.** Ogni categoria dello Shop può avere un'azienda
fornitrice; il fornitore di un prodotto è il suo, altrimenti quello della
categoria (`jav_market/service.py::resolve_suppliers`), e si congela sulla riga
d'ordine. La sezione **Fornitori da avvisare** raccoglie le righe pagate e non
ancora mandate, per fornitore: "Prepara email" apre la lettera (modificabile),
"Invia" la manda da info@ (impostazione dello Shop) con copia nella stessa
casella. Le righe si segnano come mandate solo se l'invio riesce; doppio clic
e invii incrociati con il pulsante per ordine non mandano due volte (migrazione
`0003`). Perché: un ordine con tre fornitori diventa tre email, e dieci ordini
dello stesso fornitore una sola.

**Prezzi del club** (`club/pricing.py`, migrazione `0004`). Iscrizione
sull'anno solare a pro rata, senza sconti (comprende quota di socio, taxa de
falta, assicurazione, federazione, associazione distrettuale); quota socio del
genitore per chi ha un atleta minorenne, una per famiglia; sconti solo sulla
mensilità: escalão A/B/C in percentuale (judo adattato = A, li imposta la
segreteria), poi sconto famiglia in euro. Tutti i valori li decide il club.
Il prezzo e gli sconti si congelano sulla quota.

**Inviti e credito.** Ogni account del club ha il suo link d'invito; quando
una famiglia invitata paga una mensilità, chi ha invitato riceve credito nel
wallet (ritirato se il pagamento salta). Il credito si usa per pagare le
quote, con PIN o codice come ogni spesa di JavCash; se copre tutto la ricevuta
non serve, e torna nel wallet se la prova è rifiutata.

**Eventi e trasporto.** Un evento è una gara o uno stage (lo stage non dà
punti). Con "chiedi il trasporto", alla chiusura delle iscrizioni il sistema
scrive la lettera al comune nella lingua del club, con gli iscritti veri, e
avvisa la segreteria, che la corregge e la manda con un clic (o parte da sola
se l'evento lo prevede). Risposte e copia all'email del club.

**Infrastruttura.** `core/email.py` accetta mittente, Reply-To e Bcc;
`core/email_templates.py::render_letter` impagina una lettera scritta da una
persona (testo semplice, escape, paragrafi).

## Sessione 5 — 2026-10-14 — Console JudoArteVida, persone e staff, presenze, sito pubblico

**Perché.** L'amministrazione era ancora quella del gestionale commerciale
(contratti, pratiche, promoter): per JudoArteVida non c'entra più niente. Ora
la console della piattaforma (`components/admin/admin-console.tsx`) ha la
panoramica di tutti i club, l'elenco e la creazione, il selettore del club in
testata e, dentro il club, le stesse sezioni della sua segreteria nel menu
laterale a gruppi (persone, quote e pagamenti, attività, club); poi Shop e
fornitori, wallet, assistenza, impostazioni. Il codice dei vecchi domini resta
ma non è più raggiungibile dall'interfaccia; anche il menu delle famiglie
mostra solo ciò che serve a un club. Il vecchio account amministratore è stato reso anonimo ed è
sospeso (riattivabile): la piattaforma la gestisce superadmin@judoartevida.com.

**Persone del club** (`club/people.py`, migrazione `0005`): un elenco con
simboli per tipo (atleta, genitore, segreteria, treinador, treinador adjunto,
monitor, monitor adjunto — questi ultimi solo etichetta) e, da ogni nome, la
scheda con debiti, pagamenti, risultati e investimenti. Gli investimenti sono
ricariche del wallet della famiglia per un atleta, solo del superadmin.

**Treinador** (area `/staff`): presenze di oggi (si apre sulla lezione in
corso, un tocco per atleta, nota per la segreteria; giorni passati
correggibili), calendario della settimana dei suoi corsi (titolare o adjunto,
`club_course_staff`), cartellino entrata/uscita (`club_work_sessions`, un
turno aperto per persona). La segreteria vede le ore, il registro presenze
del giorno e la taxa de falta proposta dalle presenze, che applica con un clic.

**Genitori**: "Oggi in palestra" segna la presenza dei figli solo il giorno
stesso e solo nelle loro lezioni; non toglie ciò che ha segnato lo staff. Le
lezioni usano l'ora locale del club (Europe/Lisbon di default).

**Sito pubblico** (`club/site*.py`, migrazione `0006`, `components/site/*`):
`/` è il portale JudoArteVida (carosello dei club, eventi, ranking, medaglie),
con `/clubes`, `/clubes/<slug>`, `/judocas/<id>`, `/eventos`, `/ranking`. Ogni
club cura la sua pagina dall'editor (sezione "Sito del club"). Un atleta è
pubblico solo con il consenso del genitore e la scelta del club, e mostra
solo nome, iniziale del cognome, cintura, fascia d'età e risultati. Il
portale legge sempre l'API senza cache dei dati: con la cache di Next una
pagina tolta (o un consenso ritirato) restava visibile, perché la risposta
404 non sostituiva quella vecchia. I contenuti iniziali dei club (Lagos,
Albufeira, Judo Team Matias Luwawa) vengono dal vecchio judoartevida.com
(Wayback Machine, solo la home era archiviata).

Il portale ha poi avuto il suo ridisegno grafico: header a tutto schermo con
il video di JudoArteVida dietro (lettore YouTube, visibile solo quando parte
davvero) e luce in movimento; "JudoArteVida TV", un carosello 3D con gli
ultimi 15 video del canale letti dal feed pubblico (`club/videos.py`, cache di
mezz'ora: un video nuovo compare da solo); nastro di parole, fasce
fotografiche, onde di raccordo. Le foto sono quelle del sito attuale di
judoartevida.com (illustrative, nessuna persona reale); le foto di bambini
veri del vecchio sito non sono state pubblicate senza consenso.

## Sessione 6 — 2026-10-14 — Contabilità, JAVBOT, pagine del progetto

**Contabilità** (`club/accounting*.py`, migrazione `0007`). Ogni club ha in
apertura la dashboard dei soldi (incassato del mese, costi, commissione JAV,
risultato, quote scadute, 12 mesi, tasso di riscossione, previsione) e la
pagina Contabilità (conto economico, libro cassa con CSV, spese con ricevuta,
costi fissi che si registrano da soli ogni mese, tariffe orarie e costo dello
staff dal cartellino, debiti per anzianità). La commissione della piattaforma
è il 10% degli incassi (decisione del proprietario), modificabile club per
club dal superadmin con storico (`club_platform_fees`): un cambio non
riscrive i mesi chiusi. Il superadmin vede il contatore dei guadagni JAV e il
confronto tra club; ogni famiglia o atleta ha "I miei conti".

**JAVBOT** (`domains/javbot`, migrazione `0008`). Assistente dell'area privata
con strumenti tipizzati e un pianificatore a regole (pronto a essere
sostituito da un modello vero senza toccare gli strumenti): quanto devo
pagare, come caricare la prova, judogi dall'altezza fino all'ordine (sempre
dopo una conferma esplicita, task idempotente), certificati, gare, lezioni di
oggi, invito, wallet, messaggio alla segreteria; per lo staff chi non ha
pagato e le lezioni del giorno. Il bot del sito pubblico guida i nuovi clienti
senza dati personali; i prezzi solo se il club li rende pubblici.

**Sito**: menu professionale (Início, Sobre nós con Quem somos / Visão / O
projeto, Clubes, Eventos, Ranking, Seja patrocinador), logo al doppio,
quattro pagine nuove; `/area` porta ognuno nella sua area (prima "A minha
área" portava sempre all'area promoter). Mittente delle email ai fornitori:
info@judoartevida.com.

## Sessione 7 — 2026-10-14 — Cursos JAV nelle scuole, scheda del judoca

**Cursos JAV** (`club/kinds.py`, `club/jav_courses.py`, migrazione `0009`).
JAV non è un club ma gestisce club e corsi esterni nelle scuole: un'unità
speciale (`clubs.kind = 'JAV_COURSES'`, una per organizzazione) con dentro i
corsi, ognuno nella sua scuola e gestibile da solo. Regole del proprietario:
iscrizione e quota socio 0, mensilità 25 €, niente cinture, gare, ranking;
nessuna commissione del 10%: il 50% delle mensilità pagate del corso va al
treinador responsabile, il resto è di JAV (riga a parte nel contatore). La
mensilità è attribuita al corso, al treinador e alla percentuale del momento
e congelata sulla riga. Gli atleti dei corsi non sono mai pubblici, nemmeno
col consenso (`site._publishable_club`). Pagina pubblica `/cursos`, area
treinador "Os meus ganhos", passaggio della famiglia a un club ufficiale
(bloccato con quote scadute).

**Scheda del judoca** (migrazione `0010`). `/judocas/[id]` ridisegnata in
stile IJF: ritratto, club, cintura, posizione nel ranking, medaglie,
risultati, prossime gare, percorso delle cinture, foto e video YouTube
pubblicati dal club (`club_athlete_media`), link al profilo IJF validato.
Media visibili solo con consenso, permesso foto e pubblicazione; il ritiro del
consenso li rimette tutti non pubblicati.

**Pagina del club in stile pagina Facebook e messaggi dal sito**
(migrazione `0011`). Il titolare voleva che la pagina di ogni club fosse
"del club": copertina, logo, i suoi colori, e in fondo un modo per
scrivergli. `/clubes/[slug]` è ridisegnata: copertina velata nei colori del
club, logo rotondo che sporge, numeri (atleti, gruppi, allenamenti,
allenatori, medaglie), Inscrever / Enviar mensagem, social, schede fisse
(Sobre, Grupos e preços, Horário, Treinadores, Fotos, Provas, Ranking),
riquadro Informações, e il modulo in fondo. I colori sono tre colonne su
`club_sites` (`brand_*`, CHECK sul formato); il tema con il contrasto
controllato (WCAG AA) lo calcola l'API (`club/brand.py`) e la pagina lo
mette in variabili CSS (`club-*` in `globals.css`): perché un colore scelto
male non deve mai rendere illeggibile un bottone, e perché la regola stia
in un posto solo (l'editor la rifà in `lib/brand.ts` solo per l'anteprima).
I gruppi della pagina sono quelli di JAVBOT (`site.plan_slots`, ora usato
anche dal bot), i prezzi solo con "Mostra i prezzi". I social si accettano
solo verso il loro sito. Messaggi: tabella `contact_messages`
(`club/contact.py`), `POST /public-site/clubs/{slug}/message` e
`/public-site/contact`, campo trappola, limite per IP su Redis più un tetto
nel database (5 l'ora per mittente, perché il limite di Redis lascia
passare se Redis è giù), consenso obbligatorio, notifica `CONTACT_MESSAGE`
alla segreteria o agli amministratori, email best effort con Reply-To verso
chi scrive (senza SMTP non parte e la richiesta riesce). Caselle
"Messaggi" per la segreteria e per la console (messaggi a JAV; quelli dei
club solo con `clubs.manage`). Nuova pagina `/contactos` (nel menu "Chi
siamo", nel piè di pagina e da schermo largo nella barra) con i contatti di
JAV e il modulo; i link generici a JAV (progetto, sponsor) portano lì.
Script: `scripts/load_club_branding.py` (logo dai file ripuliti in
`scripts/club_branding/`, colori, Facebook e YouTube dei tre club) e in
`load_official_prices.py` gli orari di Alvor. `docs/database-schema.sql`
rigenerato da un database costruito dalle migrazioni.

## Sessione 8 — 2026-10-14 — JAVBOT: prezzi, gruppi e sconti dei club

Il titolare ha chiesto al bot del sito "quanto costa la mensilità di Lagos"
e ha avuto "il club non pubblica i prezzi": Lagos non ha piani e ha i prezzi
nascosti, e il bot non distingueva i due casi. Ora la scheda del club
(`javbot/public.py::_prices`, `tools.py::public_club_info`) dice gruppi ed
età sempre, i soldi solo con `show_prices` (mensilità, iscrizione, giorno di
scadenza, mesi, descrizione del piano, quota socio, pro rata, ciò che
comprende l'iscrizione, sconti accesi), gli allenamenti di ogni gruppo dai
corsi con la stessa fascia d'età, e un messaggio onesto quando i piani non
ci sono. Nuove intenzioni `groups` e `discounts` (con le frasi vere nei
test); "inscrição" da sola va ai prezzi. I corsi JAV dicono la loro
mensilità. Pricing: escalão e judo adattato non si sommano, vale il
maggiore (prima il judo adattato prendeva sempre l'A, anche se un club
avesse dato di più a B o C). Script `scripts/load_official_prices.py` per la
tabella ufficiale 2026 (tre gruppi, 120 € di quote annuali = sócio judoca +
taxa de faltas, scadenza il 15, sconti A25/B15/C5, famiglia 5 €, invito
5 €, orari di Lagos). Nessuna migrazione.

## Lacune note

- Traduzione incompleta: vedi Sessione 2 (aree staff/admin/promoter e testi
  del backend).

- Interfaccia del portale club da costruire (il backend è pronto).
- Valori provvisori da confermare: gradi e gettoni, regola del 33%, regole
  del club (`open-questions.md`).
- `domains/marketplaces/rules.py` nomina ancora nel docstring un'impostazione
  di sconto bonifico che non esiste più: da ripulire.
- Ruff segnala stili preesistenti nei test
  (criterio: non peggiorare, CLAUDE.md §3).
- SMTP non configurato: senza, le famiglie che si registrano dal link del
  club non ricevono l'email di conferma, gli inviti allo staff vanno
  consegnati a mano, e le lettere a fornitori e comuni non partono (restano
  pronte, con il motivo). Anche i messaggi dal sito arrivano solo nelle
  caselle "Messaggi", senza l'email di avviso.
- Il dominio judoartevida.com va puntato su questo server e aggiunto a
  Caddy; le foto dei club le caricano i club dall'editor (Instagram non si
  può leggere in automatico).
- Le nuove schermate sono tradotte; il resto del pannello del club è ancora
  solo in italiano, anche per la segreteria di un club portoghese.
- `test_organizations.py::test_a_missing_organization_resolves_to_the_only_one`
  fallisce nella suite completa (passa da solo): i test di concorrenza dei
  wallet lasciano organizzazioni nel database di test.

---

## Sessione 9 — 2026-10-14 — "Cinto preto", non "negro"

In portoghese europeo la cintura nera è il **cinto preto**: "negro" è un
calco dallo spagnolo, sbagliato e stonato per le famiglie. Corretti i
quattro testi di `pt.ts` (traguardo `BLACK_BELT` e la sua descrizione,
`belt.BLACK` "Preto N.º dan", l'esempio di biografia nel consenso del sito).
Nessun dato nel database conteneva la parola. Ricostruito solo `dashboard`.

## Sessione 10 — 2026-10-14 — JAVBOT conosce chi gli scrive

Il titolare voleva che il bot dell'area riservata sapesse "tutto"
dell'utente: quanto ha pagato, quanto deve, i suoi dati. Scelta del
titolare: **niente modello esterno**, i dati non escono dal server; si resta
al pianificatore a regole, con più strumenti e più domande riconosciute.

Tre strumenti nuovi in `javbot/tools.py`, tutti in sola lettura e sui soli
dati di chi chiede: `family_payments` (le cifre di "I miei conti",
`accounting.personal_account`, più gli ultimi pagamenti), `my_profile`
(anagrafica dell'utente e scheda di ogni atleta; senza `club.family` solo
l'utente) e `family_progress` (cintura e da quando, presenze del mese e
della stagione, ranking, medaglie, livello; niente cinture e gare nei corsi
JAV). Riusano le funzioni delle pagine, così bot e schermo non si
contraddicono. Intenzioni nuove: `payments_made`, `overview` ("cosa sai di
me?"), `my_profile`, `belts`, `attendance_stats`, `ranking`; "debito /
dívida / debt" vanno a `fees_due`, e un genitore che chiede "estou em
dívida?" riceve le sue quote invece del rifiuto dello strumento della
segreteria. Un nome di atleta nella domanda restringe la risposta a lui.
Nuovo bottone `accounts` → scheda "I miei conti" (`lib/javbot.ts`).
Suggerimenti della famiglia, saluto e aiuto aggiornati. Nessuna migrazione.

## Sessione 11 — 2026-10-14 — La pagina del club diventa un mini-sito

Il titolare voleva pagine dei club "potenti", stile pagina Facebook con
sotto un vero mini-sito, riempite con i dati veri dei club. Migrazione
**0012** (`club_sites`: `founded_year` con CHECK, `venue`, e le liste JSONB
`highlights`, `history`, `pillars`, `news`, `videos`); grado e due righe
per gli allenatori (nel JSONB, senza migrazione). Pagina rifatta:
copertina più alta che "respira" (`animate-ken-burns`, spenta con riduci
movimento), nome sotto la copertina, badge della rete, numeri che salgono,
"Próximo treino" dal vivo, capolettera, numeri del club, pilastri, novità
come post, storia a linea del tempo, allenatori con grado, foto e video
separati, video del canale YouTube del club in automatico
(`/public-site/clubs/{slug}/videos`), mappa caricata solo su richiesta,
barra mobile. Editor: le nuove liste (`RowsCard`), sede, anno, grado e bio.

Contenuti caricati con `scripts/load_club_pages.py` (fonti nel docstring:
blog del JC Albufeira, judoartevida.com, racius, postal.pt; Facebook e
Instagram non si leggono senza login). Niente nomi di minorenni, niente
foto di giornali; copertina vera solo ad Albufeira (Lagos e Alvor tengono
la loro finché la segreteria non carica una foto del club). Applicato
anche `load_club_branding.py` (loghi, colori, social), che falliva con
`NoReferencedTableError`: ora importa `app.main` per registrare tutti i
modelli, come `load_club_pages.py`.

Poi, su richiesta del titolare: la pagina è diventata **a schede** (una
alla volta, bottoni grandi, "Horários e preços" con card per gruppo e
calendario della settimana) e `load_official_prices.py --apply
--show-prices` è stato applicato ai tre club (piani, prezzi visibili, orari
di Lagos e Alvor; Albufeira senza orario finché il club non lo dà). Lo
script aveva lo stesso `NoReferencedTableError`: ora importa `app.main`. Le email di contatto dei club restano
`matiasluwawa@gmail.com` (le fonti danno indirizzi propri per ogni club).
`scripts/backup.sh` segnala "sospettosamente piccolo" sotto i 100 KB, ma il
database è ancora così piccolo: il dump era completo.

## Sessione 12 — 2026-10-14 — Il conto dell'atleta

Il titolare voleva che ogni atleta avesse la sua area, anche i bambini senza
email, e che il "conto famiglia" restasse per chi paga. Decisioni del
titolare: accesso dei figli **con nome utente + password e con QR**; un
minorenne **vede** lezioni e quote e **segna la presenza**, non paga; a 18
anni **proposta** di diventare titolare (mai automatica). Migrazione
**0013** (`users.username`, `club_athletes.user_id`,
`club_athlete_login_codes`), ruolo `ATHLETE` e permesso `club.athlete`
(anche a `CUSTOMER`: il genitore apre l'area dei figli). Pagine `/atleta`
e `/entrar/<codice>`; scheda dell'atleta → *Acesso*; nel conto famiglia il
riquadro "Área do atleta". Dettagli in docs/club-portal.md, "Il conto
dell'atleta". Test: `tests/test_club_athlete_access.py`.

Dopo il deploy va rilanciato `python -m app.seed.bootstrap` (crea il ruolo
ATHLETE e il permesso).

SFTP: impostata una password nuova per `webadmin` (chroot su /opt) su
richiesta del titolare.


## Sessione 13 — 2026-10-15 — Età federale, mensilità mese per mese, giustificazione per la scuola

**Età federale.** Il titolare: l'età dei gruppi è quella federale, gli anni
che si compiono entro il 31 dicembre; quando si passa nella fascia del
gruppo dopo, la mensilità sale. `seasons.federal_age` sostituisce l'età al
1° settembre nella scelta del piano (`assign_plan(year=…)`). Il gruppo si
sceglie **mese per mese** in `generate_monthly_fees`: a gennaio chi cambia
fascia paga già il gruppo nuovo, `plan_id` lo segue (solo per il mese in
corso o futuri: rigenerare un mese passato non lo riporta indietro) e il
titolare riceve `CLUB_PLAN_CHANGED`. I mesi già emessi non cambiano. Le
fasce del Jav Ranking restano all'età del 1° settembre. Nessun atleta reale
cambiava gruppo con la regola nuova (i club veri non hanno ancora iscritti
attivi): niente da riallineare.

**Come si paga una mensilità** (migrazione **0014**). Ogni quota pagata dice
come (`club_fees.payment_method`: bonifico, contanti, carta, credito) e per
i contanti a chi (`cash_received_by_user_id` / `_name`, nome congelato). Il
genitore, nella finestra di pagamento, sceglie Bonifico (ricevuta, come
prima), Contanti (a chi: staff del club o nome scritto; prova con
`method = CASH` senza file, la persona riceve `CLUB_CASH_DECLARED`) o Carta
online, **spenta** finché il club non ha Stripe. La segreteria segna pagata
con una finestra (metodo + a chi) al posto del vecchio `prompt`;
`mark_fee_paid` richiede il metodo. Rifiuto e riapertura cancellano il
metodo. Le quote già pagate con una prova hanno ricevuto il metodo dalla
migrazione; quelle segnate a mano prima no.

**Il calendario delle mensilità** (`club/months.py`, componente
`SeasonMonthsPanel`): le dodici caselle della stagione per atleta, verde
pagata, giallo da pagare, rosso scaduta, tratteggiata prevista (con
l'importo previsto calcolato dal server, cambio di gruppo compreso). Un mese
si apre con il dettaglio (gruppo ed età federale, scadenza, sconti, quando e
come pagato, ricevuta) e da lì si paga. Sopra, una ciambella
pagato/da pagare/scaduto/previsto e le presenze mese per mese (recharts).
È nella scheda Quote dell'atleta (famiglia), nell'area dell'atleta (in
lettura) e nella scheda atleta della segreteria (con "Segna pagata"). Nella
pagina della famiglia una barra per atleta (`FamilyRead.season_months`).
Nell'interfaccia l'età mostrata al genitore è quella vera; la segreteria e
lo staff vedono quella federale.

**Giustificazione per la scuola** (`club/school_letters.py`, tabella
`club_school_letters`). In "Iscritti e risultati" ogni iscritto ha
"Giustificazione": testo proposto nella lingua delle lettere del club (al
maschile o al femminile, con data di nascita e tesseramento), la segreteria
lo corregge e genera il PDF su carta intestata (logo, recapiti e colore
della pagina del club; `storage.read_media_url` legge il logo lato server).
Il PDF va nel bucket **privato**, si apre con URL presigned di 5 minuti; il
titolare lo scarica dalla pagina delle gare quando è pronto. Una per
iscrizione, rigenerarla cancella il file vecchio. La regola "dopo la
scadenza nessuno si iscrive" c'era già (`eligibility`): ora ha un test.

**Privacy dei file.** Verificato: prove di pagamento, certificati e ricevute
delle spese erano già nel bucket privato (policy `private`, nessun accesso
anonimo); il bucket media è pubblico in sola lettura per oggetto, senza
elenco. Regola scritta in CLAUDE.md §5. Le foto degli atleti restano nel
bucket media (servono alla pagina pubblica del judoca, con consenso): vedi
open-questions se vanno spostate.

Test: `tests/test_club_months.py` (9); suite completa 534 passati, 1 fallito
(`test_organizations::test_a_missing_organization_resolves_to_the_only_one`,
il problema noto della sessione 8). Typecheck verde, lint dei file toccati
pulito. Backup prima della migrazione (55 KB, completo: l'avviso
"sospettosamente piccolo" è la soglia dei 100 KB).

Poi, su richiesta del titolare: nel sito pubblico "Cursos nas escolas" è
passato dalla barra alla tendina "Quem somos" (con la sua riga di
spiegazione), per lasciare spazio nel menu; il bottone "A minha área" /
"Entrar" è diventato rosso del club, in gradiente, con icona e freccia.

## Sessione 14 — 2026-10-15 — Due JAVBOT: quello del sito e l'assistente dei soci

Il titolare voleva distinguere i due JAVBOT: quello del **sito pubblico**
va bene così, semplice, con poche risposte generiche; quello **dell'area
riservata**, per chi fa login, deve essere "potente" e conoscere i
documenti, con una base di conoscenza **comune a tutti i club** e la
possibilità, per ogni club, di aggiungere i suoi PDF e un suo prompt.

**L'assistente** (`javbot/assistant.py`). Nell'area riservata risponde
Claude, con gli stessi strumenti che usava il pianificatore (solo quelli
che leggono e solo quelli che i permessi dell'utente consentono) più
`search_knowledge`. Il pianificatore a parole chiave non sparisce: tiene i
percorsi guidati che scrivono (judogi, messaggio alla segreteria, presenza,
ricevuta) con il compito da confermare, perché un modello che conferma da
sé sarebbe un passo indietro sull'idempotenza; e risponde quando il modello
non può (senza chiave, API giù, rifiuto, oltre 150 risposte al giorno per
utente). Così la chat non si spegne mai e, **finché il `.env` non ha
`ANTHROPIC_API_KEY`, tutto funziona esattamente come prima**. Modello
`claude-opus-5-5` con sforzo `low` (configurabili), regole fisse in cache,
`fallbacks: "default"` per i rifiuti.

**La base di conoscenza** (`javbot/knowledge.py`, migrazione 0015).
PDF nel bucket privato, testo estratto con `pypdf`, a pezzi di ~1.500
caratteri, normalizzato e cercato con il full-text di Postgres in
configurazione `simple`. Niente embedding: con 3,7 GB di RAM e due core un
modello di embedding sul server costava più di quanto rendeva per qualche
decina di PDF, e un servizio esterno era un'altra chiave da gestire. Chi
cerca è il modello, che riprova con altre parole: per una base piccola
basta. Istruzioni: una comune e una per club; quella del club vince in caso
di contrasto.

**Interfaccia.** Sezione "JAVBOT" nel menu del club (segreteria, o la
piattaforma entrando nel club): istruzioni del club, PDF del club, e in sola
lettura le istruzioni e i documenti comuni. Nella console, "JudoArteVida →
JAVBOT" (solo superadmin, API con `clubs.manage`) per la base comune. Se la
chiave manca, un avviso dice che i documenti si possono già preparare.
Testi nelle tre lingue.

Rimane aperto (open-questions §17): l'informativa privacy prima di
accendere la chiave, i costi da misurare, le scansioni senza testo.

Test: `tests/test_javbot_knowledge.py` (12, con un finto client al posto
dell'API: niente chiamate vere e niente costi); i test di `test_javbot.py`
passano invariati.

Poi, su richiesta del titolare: l'API dell'AI si collega più avanti, e
**intanto la base di conoscenza deve rispondere senza modello**. Il
pianificatore, prima di dire "non ho capito", cerca nei PDF e mostra fino a
due estratti con titolo e pagina (`Planner.from_knowledge`,
`knowledge.passages` / `knowledge.excerpt`); una domanda agganciata a una
sola parola chiave va ai documenti se questi rispondono alla domanda intera
(almeno due parole e due terzi). Si cita e basta: senza modello non si
riassume. Test: `test_javbot_knowledge.py` ora 15, suite JAVBOT 30 passati.

## Sessione 15 — 2026-10-15 — Il gestionale dei club entra in Jav (fase 1)

Il titolare ha mandato il backup completo del gestionale che i club usano
oggi (PHP + MariaDB, "judo-aev"): da studiare, da cui prendere tutte le
funzioni che a Jav mancano, e i cui dati vanno importati. Studio, confronto
e piano: `docs/legacy-judo-aev.md`; la specifica completa del vecchio, file
per file, sta fuori dal repository (`/opt/legacy/judo-aev/analysis/`),
perché descrive anche le sue falle di sicurezza.

**Isolamento.** Il sorgente in `/opt/legacy/judo-aev` (root, 700: la
cartella SFTP di webadmin non lo vede), il database in un MariaDB a parte
(`legacy-mariadb`, rete sua, nessuna porta). Lo zip conteneva documenti
d'identità ed era scaricabile senza password dal sito da cui è arrivato: il
titolare è stato avvisato.

**Decisioni del titolare**: mensilità su 12 mesi come facevano i club;
ranking con la loro tabella punti per livello e medaglia; le segreterie
importate subito, gli amministratori generali più avanti.

**Fondamenta (migrazione 0016).** La ficha de inscrição (nº de sócio, nome
sul judogi, documenti, contatti dei genitori in una tabella letta solo
dalla segreteria), MB Way, quote a rate, escalão D, esenzioni e sconto
personale, multe, numero di ricevuta atomico, eventi della rete
(`club_id` NULL: il calendario comune che nel vecchio era di tutti), i 10
livelli portoghesi, le cinture intermedie, documenti, consensi RGPD con
storico, richieste di modifica, domande d'iscrizione, ordini di judogi,
pulizie con firma, compensi dei treinadores esterni, relatori.

**L'importazione** (`app/legacy/judo_aev.py`) è rilanciabile
(`legacy_import_map`), non manda email, e si è provata su una copia del
database prima di toccare quello vero. La prova ha trovato e fatto
correggere: le date "0000-00-00" di MySQL, un peso scritto come categoria,
i livelli più lunghi di 16 caratteri, e soprattutto le rate del vecchio che
non tornano con i pagamenti (ora conta l'importo vero, e ogni euro finisce
in una quota pagata, perché la contabilità conta le quote). Esiti in
`docs/legacy-judo-aev.md`, "Che cosa ha detto la prova".

Una trappola pagata durante il collaudo, scritta in CLAUDE.md §2: uno
script lanciato fuori da `/src` usa il codice cotto nell'immagine.

Test: `tests/test_club_legacy_features.py` (7); aggiornati i test del
ranking (nuova tabella punti) e del listino ufficiale (escalão D).

Poi, su richiesta del titolare:
- **Link di accesso per lo staff** (console → Club → 🔑 accanto a ogni
  segreteria o istruttore): un link per scegliere la password, valido 7
  giorni, lo stesso meccanismo dell'invito. Serve alle segreterie importate,
  che non hanno mai avuto una password; la password non passa mai da chi lo
  genera. In più `scripts/set-password.sh` dall'host, per il superadmin.
- **Contabilità**: judogi e multe nella ripartizione degli incassi (prima
  sparivano dal grafico).
- **Documenti del club** (migrazione 0017, `club/club_documents.py`):
  certidões, atas, rivalidazione FPJ, assicurazioni, statuto, con scadenza e
  avviso alla segreteria; e il **certificato medico caricato dall'atleta**
  dalla sua area. Test in `test_club_legacy_features.py`.
- **Sito pubblico**: ranking per anno solare, Grupo 1/2/3 e Veteranos, di
  tutta la rete (classifica generale su `/ranking`, del solo club sulla sua
  pagina), con tutti gli atleti come "Nome I." e la pagina solo con il
  consenso; il calendario degli eventi rifatto (lista, calendario, anno,
  ricerca e filtri); testate con le foto dei club su eventi, ranking e club.

## Sessione 16 — 2026-10-16 — Bacheca del club, orari che si correggono, simboli accanto ai nomi

Su richiesta del titolare (migrazione 0018):
- **Bacheca** per atleti e famiglie (`club/news.py`, `news_router.py`): le
  notizie del club come un post (titolo, testo, foto, video YouTube/Vimeo
  incorporato o link) scritte dalla segreteria in **📰 Notizie**, con
  anteprima, evidenza e bozze; e i **documenti del club condivisi**
  (`club_documents.shared_with_members`). Voce «Bacheca» nell'area famiglia,
  sezione nell'area dell'atleta. Solo area riservata, non sito pubblico.
- **Orari dei corsi** che si correggono (`PATCH /club/admin/slots/{id}`):
  prima si potevano solo togliere e rifare.
- **Simboli accanto ai nomi** (`components/club/person-marks.tsx`) negli
  elenchi di segreteria e istruttori, da `/club/staff/people-kinds` (solo i
  tipi, senza soldi né contatti). Nuovo tipo **árbitro** (`club_referees`);
  un adulto che si allena porta anche 👪 se ha altri atleti sul conto e 🧑‍🏫
  se ha l'account da istruttore.

Test: `tests/test_club_board.py` (3).

Poi, sempre il 2026-10-16 (migrazione 0019):
- **Pagina del club**: sotto la copertina una barra nel colore del club con
  logo, nome, numeri e azioni (strisce, riflesso animato, filo nel colore
  d'accento); classifica del club cliccabile con la scheda in popup.
- **Ranking pubblico**: periodi (anno, mese, sempre), ricerca istantanea,
  righe grandi con foto e logo del club, scheda del judoca in popup stile
  IJF (`/public-site/ranking/judoka/{id}`, ridotta senza consenso) e la
  **Taça dos Clubes** con albo d'oro (`/public-site/ranking/clubs`).
- **Messaggi**: argomento (`contact_messages.topic`), destinatario
  sceglibile su `/contactos`, modulo sponsor su `/patrocinadores`, filtro e
  badge in casella; il superadmin parte da «Tutti».
- **Sponsor** (`sponsors`): console → 🤝 Sponsor, barra di loghi animata in
  home, pagina `/patrocinadores/<slug>`. Caricati: Câmara Municipal de
  Lagos, de Albufeira, de Portimão, Estamparia Cordavida (senza sito: non
  trovato, da completare in console). Loghi da caricare in console.

Test: `tests/test_public_portal_extras.py` (3); `test_club_brand.py`
aggiornato alla regola «tutti in classifica come Nome I.».

Poi (migrazione 0020): **il quadro del mese** (`club/month_board.py`,
`GET /club/admin/month`, `this_month` nella pagina della famiglia), in cima
alla Panoramica, prima scheda di Quote e card «Questo mese» della famiglia;
«Segna pagato» di più quote insieme (anche MB Way). **Immagine delle
prove** (`club_competitions.image_url`) e icona grande per tipo negli
elenchi della segreteria e delle famiglie. Test:
`tests/test_club_month_board.py`.

Poi (migrazione 0021):
- Sito: l'header resta bianco pieno anche scorrendo.
- **Calendário JudoArteVida** (`club/calendar.py`): periodo da/a, viste
  schede/lista/tabella e PDF diviso per mesi, per staff e famiglie.
- **JAV Games** (`app/game`, schema `game`, docs/games.md): Dojo Academy
  (quiz a tempo corretti dal server, percorsi ed esami di cintura del
  gioco), Judo Career (simulazione della carriera e del club, salvata come
  JSON) e classifica di tutti i club. Voce «Giochi» per le famiglie,
  `/giochi` per gli atleti. Test: `tests/test_game.py`.


Poi (migrazioni 0022–0025):
- **Email** con la veste di JudoArteVida o del club (`core/email_templates.py`,
  `domains/club/email_brand.py`) e **testi personalizzabili**
  (`domains/email_texts`, console → 📧 Email, con anteprima e invio di prova):
  docs/emails.md.
- **Scheda «salute sportiva»** dell'atleta (`club/obligations.py`,
  `club_athletes.white_judogi`): judogi del club, judogi bianco, certificato,
  quota annuale, pronto per le gare; foto caricabile.
- **Bacheca del circuito** (pubblico CLUB o NETWORK, post di JudoArteVida,
  «mi piace» `club_news_likes`, prove dei prossimi 90 giorni come post).
- **Shop dei club** (`jav_market_products/orders.club_id`,
  `club/shop_router.py`): vetrina con venditore e filtro, carrello di un
  venditore solo, bonifico all'IBAN del club, niente IVA sui prodotti del club.

Poi (migrazioni 0026–0028):
- **Aiuto del club** (`club_athlete_supports`, `club/support.py`): i costi
  pagati dal club per un atleta, nel wallet della famiglia come ricarica più
  addebito; riquadro dei soldi nella scheda dell'atleta.
- **Area dell'atleta** con il menu a sinistra; «Gare e stage» con «Voglio
  partecipare» (email e notifica al titolare); il minorenne non carica il
  certificato; «Convide um amigo» con i bottoni dei social.
- **Avvisi della mensilità** (1, 10, 15 alle 9:00) e **multa del 16**
  (`club/payment_reminders.py`, impostazione del club, job ogni ora).
- **Flyer del mese** del Calendário (`calendar.render_flyer`).
- **Shop della rete sul sito** (`/loja`, `/public-site/shop`, prezzi IVA
  compresa) con «per acquistare devi essere socio di un club»; importatore
  del catalogo suplementos24.com (`scripts/import_suplementos24.py`).
- **Crea il tuo club** (`/criar-clube`, messaggio con argomento `NEW_CLUB`,
  migrazione 0027).
- **Personale del club** (`club_staff_tasks`, `club_staff_messages`,
  `club/staff_work.py`, migrazione 0028): il mese del personale, compiti
  svolti, lavoretti occasionali pagati come spesa COLLABORATORS, messaggi
  dello staff con la segreteria o con JudoArteVida.
- Pagina di accesso a tutto schermo con la scheda al centro; Dojo Academy
  con 10 secondi in più per domanda.
- Corretto: la prova di pagamento dall'area dell'atleta usava una funzione
  inesistente (`athlete_access.scope_of`) e sarebbe finita in errore 500.

Test: `tests/test_club_payment_reminders.py`, `tests/test_club_area_extras.py`,
`tests/test_club_staff_work.py`, `tests/test_public_shop.py`.

Poi (migrazione 0029): eventi del sito nell'area di famiglie e atleti; lista
eventi con i prossimi in cima; pagine numerate; «prodotti dei nostri partner e
amici»; ogni atleta parte con la scheda pubblica senza foto, con
l'opposizione della famiglia (`basis`, `opted_out_at`); pagine
`/privacidade`, `/cookies`, `/termos`, banner dei cookie e contenuti di terzi
solo con consenso; job di conservazione. Analisi: docs/legal.md. Test:
`tests/test_data_retention.py`, test del sito aggiornati alla nuova regola.

Poi: lo Shop JudoArteVida in vetrina anche nell'area a shop spento
(`purchasable`, `jav_open`), e acceso. **Microfono di JAVBOT**: bottone 🎤
nelle due chat, la voce trascritta dal nuovo servizio `stt` (Whisper `small`
sul nostro server, l'audio non si salva), il testo nel campo da rileggere.
Vedi club-portal.md, «Il microfono». Test: `tests/test_javbot_voice.py`.
Poi il microfono è stato **nascosto** (lento e impreciso su 2 CPU) e `stt`
fermato. Telefono: niente più pagine più larghe dello schermo nella
dashboard. La causa comune erano le griglie a una colonna, che si allargavano
al testo troncato o alle tabelle: in `globals.css` `.grid > * { min-width: 0 }`
e `overflow-x: clip` su html e body. Misurato con un browser headless a 390 e
360 px su una copia del backup (admin con Lagos, una famiglia): tutte le
sezioni stanno nello schermo. Sistemati anche le caselle dei totali della
console, l'indirizzo del wallet e le cinture del login.

Poi (migrazione 0030): dettaglio evento rifatto (scheda pratica con icone,
iscritti nello stile del ranking con il popup del judoca); WhatsApp sotto i
telefoni; social della rete nel piè di pagina (Impostazioni) e TikTok per i
club; schede Biografia/Foto/Video sempre presenti nella pagina del judoca e
biografia fino a 1500 caratteri; categorie dello Shop con le frecce e banner
nero con il logo di Suplementos24; «Loja» apre le proteine. **Sei lingue**:
spagnolo, francese e tedesco tradotti interi (es.ts, fr.ts, de.ts); JAVBOT e
giochi rispondono in portoghese a chi sceglie spagnolo e in inglese a chi
sceglie francese o tedesco. Test: `tests/test_network_socials.py`.


Poi: nell'area degli atleti «Provas e estágios» diceva «Não consigo carregar
os eventos». Il calendario chiama `/backend/api/public-site/events`, e
`/backend/` in nginx aveva un target statico: dopo il deploy, che ha ricreato
`api` con un IP nuovo, rispondeva 502. Ora usa variabile + resolver, con il
`set` prima del `rewrite` (guida di migrazione, punto 11). Nessuna
migrazione.

Poi: **ritaglio delle foto profilo** (`components/ui/image-cropper.tsx`) nella
scheda dell'atleta (famiglia, area e segreteria), per allenatori del sito del
club, clienti e promoter; il server salva **ogni immagine ottimizzata**
(`core/storage.py::optimize_image`: EXIF girato, 1600/800 px, niente
metadati, JPEG q85 o PNG con trasparenza). **«Torna al calendario»** nella
pagina di un evento aperta dall'area, con lo stato del calendario
(`lib/events-return.ts`). Il PNG di prova di `test_judoka_page.py` era rotto
(ora rifiutato): ne genera uno vero. Test: `tests/test_image_optimize.py`.
Nessuna migrazione.

Poi: `/customer` aperta da un accesso solo atleta (ariel.83, con l'«indietro»
del browser dopo il cambio di account) dava «Qualcosa è andato storto»: la
pagina chiede i contratti, che un atleta non può leggere (403). Ora chi non ha
il ruolo CUSTOMER viene mandato a `/area`, cioè nella sua area.

Poi: sul telefono il calendario del mese degli eventi sembrava vuoto (solo
puntini da 6 px, l'elenco del mese fuori schermo). Ora il giorno con eventi
è un cerchio colorato con puntini più grandi e il numero di eventi; toccarlo
porta all'elenco di quel giorno; l'intestazione mostra l'iniziale del giorno
(«SEGUNDATERÇA…» si sovrapponeva). Computer invariato.

Poi: **contatti** con la scheda WhatsApp (come email e telefono, icona di
WhatsApp) tra telefono e «Dove siamo»; nella **home** le schede dei club
sopra la copertina del carosello; nella scheda dell'atleta **«Ha già il
judogi bianco»** è un interruttore dentro il riquadro. **Settima lingua:
ucraino** (`uk.ts`, 2833 testi, bandiera, `uk-UA`; JAVBOT e giochi in
inglese), con il cirillico nei font (Inter `cyrillic`, Russo One per i
titoli). Il servizio `stt` sta nel profilo compose `voice` (non parte con
`up -d`). Guida di migrazione §15 aggiornata (revision 0030, 132 tabelle,
`/backend/health`, Pillow, `set-password.sh`).

Poi: **WhatsApp** come voce con l'icona anche nel piè di pagina e nella
pagina del club. **Comprovativos** rifatti (riepilogo, ricerca e filtri
nell'API, schede per metodo, ricevuta dentro la pagina, rifiuto con motivi
pronti, tutto tradotto). **Tabella atleti** con ruolo, nº de sócio, licença
FPJ, nascita, età federativa, género, encarregado, contatto e «invitato
da», ordinamento, filtri rapidi e CSV. Password del super admin
reimpostata su richiesta. Test: `tests/test_club_admin_lists.py`. Nessuna
migrazione.

Poi: **piani e prezzi** con il colore del gruppo (migrazione 0031), **prova
di pagamento** apribile dalle quote e dal quadro del mese, **staff da un
account esistente** (Matias e Marco Piccolo ora treinador di Lagos) e menu
utente con le aree, **rete inviti** con saldo JavCash, «Segna la tua
presenza» e invito nella home dell'atleta, **Loja** con i nomi nuovi e
tradotti, logo del login verso il sito. **Traduzione completa
dell'interfaccia**: circa 2.500 testi spostati nelle chiavi (8 agenti, un
prefisso ciascuno), controllata aprendo ogni sezione di ogni ruolo in
portoghese. Test: `test_club_admin_lists.py` (staff da account esistente),
`test_club_pricing.py` (rete inviti).
