# Privacy, cookie e termini: l'analisi

Le pagine pubbliche: `/privacidade`, `/cookies`, `/termos` (in portoghese, la
lingua che fa fede), link nel footer di ogni pagina del sito, nel modulo di
iscrizione (`/c/<slug>`) e in quello dei promoter (`/r/<code>`). I dati del
titolare stanno in un posto solo: `apps/dashboard/lib/legal.ts`.

## Chi risponde

- JudoArteVida **non è una società**: è la rete dei tre club (Judo Clube de
  Lagos, Judo Clube de Albufeira, Judo Team Matias Luwawa), coordinata da
  Matias Rosário Luwawa, persona singola senza partita IVA.
- **Responsabile del trattamento** della piattaforma e del sito: **Judo Clube
  de Lagos**. Ogni club è **corresponsabile** (art. 26 RGPD) per i dati dei
  suoi soci; punto di contatto unico `info@judoartevida.com`.
- **Da fare (fuori dal codice)**: un accordo scritto di corresponsabilità tra
  i tre club; NIPC e sede legale completa del Judo Clube de Lagos in
  `lib/legal.ts` (finché sono vuoti la pagina non li mostra); contratti di
  trattamento (DPA) con Hetzner e Hostinger; decidere se e quando attivare
  JAVBOT con Anthropic (va dichiarato prima: è già scritto nella privacy,
  «apenas se for ativado»).

## I trattamenti (sintesi dell'inventario del codice)

| Dati | Dove | Base | Conservazione dichiarata |
|---|---|---|---|
| Conta: email, username, password hash, lingua, `privacy_accepted_at` | `users` | contratto | conta + 5 anni |
| Sócio e encarregado: nome, contatti, indirizzo, NIF, documento | `customers`, `club_athlete_records` | contratto, obbligo (FPJ, assicurazione) | sócio + 5 anni |
| Atleta (anche minore): nascita, sesso, peso, cintura, presenze, gare | `club_athletes`, `club_attendances`, `club_competition_entries`, `club_belt_grades` | contratto, legittimo interesse | sócio; risultati come storico |
| **Certificato medico** (salute) | `club_medical_certificates`, bucket privato | art. 9.2 b/h, Lei 5/2007 | validità + 1 anno |
| Judo adattato (può rivelare salute) | `club_athletes.adapted_judo` | consenso esplicito | sócio |
| Quote, prove di pagamento, wallet, ordini | `club_fees`, `club_payment_proofs`, `wallets`, `jav_market_orders` | contratto, obbligo fiscale | 10 anni |
| Scheda pubblica «Nome I.» | `club_athlete_public_profiles` | **legittimo interesse + opposizione** | fino all'opposizione / uscita |
| Foto e video pubblici | stesso, `show_photo`, `club_athlete_media` | **consenso** (art. 8) | fino al ritiro |
| Lettere scuola, trasporto | `club_school_letters`, `club_transport_requests` | legittimo interesse, richiesta famiglia | stagione + 1 anno |
| Staff: ore, tariffe, compiti, messaggi, firme pulizie | `club_work_sessions`, `club_staff_*`, `club_cleaning_logs` | contratto, obbligo | 10 anni; messaggi 2 anni |
| Messaggi dal sito (ip_hash, UA) | `contact_messages` | pre-contrattuale, legittimo interesse | 24 mesi |
| JAVBOT | `javbot_*` | contratto | 90 giorni di inattività |
| Voce dettata a JAVBOT | mai salvata (`javbot/voice.py`, `apps/stt`) | richiesta dell'utente | nessuna: trascritta sul server e scartata |
| Sessioni, audit (IP, UA) | `sessions`, `audit_log` | legittimo interesse | 30 giorni; 2 anni |
| Promoter, contratti, IBAN, KYC | `contracts`, `documents`, provvigioni | contratto, obbligo | 10 anni dopo il contratto |
| Giochi | schema `game` | contratto | conta |

## Il sito pubblico e gli atleti

- **Ogni atleta parte con la scheda sportiva pubblica**, senza foto (migrazione
  0029, `basis = LEGITIMATE_INTEREST`, `site.ensure_default_profile` alla
  creazione): «Nome I.», club, cintura, fascia, medaglie, risultati, punti.
  È la richiesta del titolare; la base giuridica è il legittimo interesse
  sportivo (come una classifica), **non** un consenso presunto: un consenso
  pre-dato non sarebbe valido (art. 7 RGPD, CGUE Planet49), tanto meno per i
  minori.
- **Opposizione** (art. 21): la famiglia, dalla scheda dell'atleta, «Mi
  oppongo» → `opted_out_at`: via la scheda, via da classifiche, eventi e
  medaglie (`_ranking_athletes` esclude chi si è opposto); il club non può
  ripubblicarla. Tornare pubblici si può, con lo stesso bottone.
- **La foto resta un consenso esplicito** (`show_photo`), mai d'ufficio.
- Le pagine dei judoca restano `noindex`.

## Cookie

- Solo cookie tecnici (nessuna pubblicità né statistica): `jav_session`,
  `jav_refresh_token`, `jav_lang`, `jav_club`, `jav_referral`, `jav_cookies`;
  localStorage `jav_course_pref`, `jav-sidebar-collapsed`, `jav.board.seen`;
  sessionStorage `javbot-public`. Per questi basta l'informativa (Lei
  41/2004, art. 5).
- **Contenuti di terzi** (YouTube, Vimeo, miniature `i.ytimg.com`, il video
  di sfondo della home): **solo dopo il consenso**. Il banner
  (`components/legal/cookie-banner.tsx`) compare al primo accesso con
  «Aceitar todos» e «Só os necessários» con la stessa evidenza; la scelta sta
  nel cookie `jav_cookies` per 6 mesi (`lib/cookie-consent.ts`). Finché non
  si accetta, al posto del video c'è `ThirdPartyGate` («Aceitar e ver»).
  «Gerir cookies» nel footer riapre la scelta. Google Maps si apriva già solo
  al clic.

## Lacune ancora aperte (codice)

1. **Conservazione automatica**: i termini dichiarati sopra non sono ancora
   tutti applicati da un job (oggi: JAVBOT 90 giorni, sessioni a scadenza).
   Da fare: un job notturno che cancelli messaggi del sito oltre 24 mesi,
   audit oltre 2 anni, certificati scaduti da più di un anno, token scaduti.
2. **Diritti**: export dei dati della famiglia (portabilità) e richiesta di
   cancellazione dall'area: oggi si fanno a mano su richiesta via email
   (come dice la privacy).
3. **Foto nel bucket pubblico**: le foto degli atleti sono in `jav-media` con
   chiave casuale; quelle senza consenso non sono linkate dal sito, ma
   l'URL resta raggiungibile da chi lo conosce.
4. **Backup** sullo stesso disco del server e non cifrati: meglio una copia
   cifrata fuori dal server.
5. `club_consents` (consensi PRIVACY/PHOTOS/MARKETING dell'import legacy) non
   è usata dal codice nuovo.
6. Lo sblocco dell'account da parte dell'admin imposta `privacy_accepted_at`
   per conto dell'utente: andrebbe chiesto all'utente al primo accesso.
