# Istruzioni operative per Claude Code

Questo file viene letto all'inizio di ogni sessione. Contiene le cose che
**non si deducono leggendo il codice** e che, se ignorate, fanno danni:
convenzioni, trappole già pagate una volta, e i comandi esatti che funzionano
su questo server.

Jav è un gestionale per palestre e club di judo: portale famiglie (quote,
prove di pagamento, certificati, gare, Jav Ranking), segreteria, istruttori,
più la base generica su cui è costruito (rete commerciale e provvigioni,
contratti, catalogo e ordini, Shop, portafoglio JavCash, assistenza). La
specifica del dominio club è `docs/club-portal.md`.

Per installare da zero (server nuovo, o un nuovo club) la guida è
`docs/server-migration-guide.md` — §12 è un runbook pensato per essere
eseguito passo per passo, verifiche comprese.

---

## 1. Le tre cose da sapere prima di toccare qualsiasi cosa

**Questo server ospita l'installazione su `jav.ecodo.ai`.** Non esiste un
ambiente di staging: quello che si deploya qui è quello che vedono gli utenti.
L'HTTPS lo fa Caddy sull'host (`/etc/caddy/sites/jav.caddy`, copia di
`infrastructure/caddy/jav.caddy`), che rinnova da solo il certificato; il
nginx dello stack ascolta solo su `127.0.0.1:8081` ed è il router interno.

**"dev" qui significa produzione.** Lo stack gira con
`docker-compose.dev.yml` e `ENVIRONMENT=development` nel `.env`, ma è
l'installazione reale. `docker-compose.production.yml` esiste nel repository
ma **non è quello in esecuzione**. Ogni comando in questo file usa
`-f docker-compose.dev.yml` per questo motivo, non per distrazione.

**Le immagini sono cotte.** I container non montano il sorgente. Modificare
un file e fare `restart` non cambia niente: il container riparte con il
codice di prima. Serve sempre:

```bash
docker compose -f docker-compose.dev.yml build <servizio>
docker compose -f docker-compose.dev.yml up -d <servizio>
```

**`celery-worker` e `celery-beat` hanno immagini loro**, distinte da quella
di `api` anche se costruite dallo stesso sorgente: vanno **ricostruite**
insieme ad `api` a ogni deploy del backend, e poi ricreate con
`--force-recreate`. Il solo `--force-recreate` le riavvia con il codice
vecchio, e i lavori automatici (quote mensili, promemoria, chiusura gare)
girerebbero su codice superato senza che nessuno se ne accorga.

```bash
set -o pipefail   # un build fallito deve fermare tutto: niente `| grep` che ne nasconda l'errore
docker compose -f docker-compose.dev.yml build api celery-worker celery-beat
docker compose -f docker-compose.dev.yml up -d api
docker compose -f docker-compose.dev.yml up -d --force-recreate celery-worker celery-beat
docker compose -f docker-compose.dev.yml images | grep jav   # stesse date
```

---

## 2. Test

Il database di test viene **cancellato e ricreato** all'inizio di ogni
sessione di pytest (`tests/conftest.py`, `drop_all` + `create_all`). Puntarlo
al database reale distrugge i dati di produzione. Il nome giusto è
`jav_test`, **mai** `jav`: controllalo nella stringa di connessione ogni
volta, prima di premere invio.

Gli hostname `postgres` e `minio` del `.env` esistono solo dentro la rete
Docker (`jav-dev_default`): dall'host non risolvono, e Postgres non è
pubblicato sull'host. Il modo più semplice è far girare i test in un
container sulla stessa rete, con il sorgente montato (così si prova il codice
attuale, non quello cotto nell'immagine):

```bash
cd /opt/webapps/jav
PG=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)
docker compose -f docker-compose.dev.yml exec -T postgres \
  psql -U jav -d postgres -qc "CREATE DATABASE jav_test OWNER jav;"   # la prima volta
docker run --rm -u 0 --network jav-dev_default -v "$PWD/apps/api:/src" -w /src \
  --env-file .env -e S3_ENDPOINT_URL=http://minio:9000 \
  -e TEST_DATABASE_URL="postgresql+psycopg://jav:${PG}@postgres:5432/jav_test" \
  --entrypoint sh jav-dev-api -c 'pip install -q pytest pytest-asyncio polyfactory aiosqlite && python -m pytest -q'
```

In alternativa, da un venv sull'host, gli IP dei container
(`docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' …`)
al posto di `postgres` e `minio`.

Le variabili S3 servono davvero: i test dei documenti e delle prove di
pagamento caricano file veri su MinIO. Senza, falliscono con
`EndpointConnectionError`.

Se `drop_all` fallisce con `DependentObjectsStillExist`, il database di test
contiene tabelle che i modelli non conoscono più (una tabella tolta): non è
un bug, ricrea `jav_test` vuoto (`DROP DATABASE jav_test WITH (FORCE)`).

La suite completa impiega ~5 minuti: lanciala in background e nel frattempo
fai altro. Il driver è `psycopg`, non `asyncpg`.

**Il sorgente montato vale solo dalla sua cartella.** L'immagine contiene
il pacchetto `app` già installato (site-packages). `python -m pytest` o
`python -m app...` lanciati con `-w /src` usano `/src/app`; uno script
lanciato come `python /qualcosa.py` usa invece il codice **cotto
nell'immagine**, cioè quello vecchio. Per uno script fuori da `/src`
aggiungi `-e PYTHONPATH=/src`.

---

## 3. Verifiche prima di un deploy

```bash
python -c "import app.main, app.celery_app"            # nel container, vedi §2
cd apps/dashboard && pnpm typecheck && pnpm build
```

`import app.main` non è pedanteria: un `NameError` in un router non lo prende
nessun test (i test esercitano i servizi, non le rotte) e si manifesta come
un 500 al primo utente che apre quella schermata.

`pnpm lint` **non passa** su questo repository: ci sono errori preesistenti,
quasi tutti `react-hooks/set-state-in-effect`. Il criterio non è "lint verde"
ma "lint non peggiora": conta gli errori prima e dopo, o verifica che i tuoi
file non compaiano nell'elenco. Stessa cosa per `mypy` e per `ruff` su
`tests/`.

`react-hooks/set-state-in-effect` è comunque un **errore**, non un warning:
nel codice nuovo i valori si derivano durante il render, non si sincronizzano
con un `useEffect`.

---

## 4. Migrazioni e schema

La storia delle migrazioni è ripartita da zero: c'è **una sola migrazione
iniziale**, `apps/api/alembic/versions/0001_schema_iniziale.py` (revision
`"0001"`), generata dai modelli. Le chiavi esterne sono create dopo tutte le
tabelle, perché molte si citano a vicenda; la sequenza
`shop_order_number_seq` è scritta a mano (autogenerate non la crea).

Una modifica ai modelli richiede tre cose, non una:

1. un file nuovo in `apps/api/alembic/versions/`: il prossimo è
   `0002_nome.py` con `down_revision = "0001"`, poi `0003_…` e così via;
2. `./scripts/backup.sh` **prima** di applicarla in produzione;
3. `./scripts/dump-schema.sh dev --from-migrations` dopo (costruisce un
   database usa e getta dalle migrazioni con l'immagine `api` già
   ricostruita), e il diff di `docs/database-schema.sql` committato insieme al
   resto.

Il punto 3 sembra burocrazia e non lo è: quel file è l'artefatto con cui si
verifica una reinstallazione. Il diff deve contenere **solo** ciò che la
migrazione dichiara di fare: se contiene altro, qualcuno ha modificato il
database a mano.

Il container `api` esegue `alembic upgrade head` da solo all'avvio. Non serve
lanciarlo a parte dopo un `up -d`.

Lo schema da solo non basta a far partire l'applicazione: permessi, ruoli,
gradi e piano provvigioni sono **dati**, non struttura, e li crea
`python -m app.seed.bootstrap` (idempotente: rilanciarlo riallinea permessi e
ruoli al codice). Vedi `docs/server-migration-guide.md` §6.1.

**I giochi (JAV Games) sono un mondo a parte**: schema Postgres `game`, una
`MetaData` sua (`app/game/models.py::GameBase`), nessuna FK verso il
gestionale (`players.user_id` senza FK). L'autogenerate non vede quelle
tabelle: una loro modifica si scrive a mano in una migrazione nuova con
`schema="game"`. I test creano lo schema a parte in `tests/conftest.py`. Mai
far leggere al gestionale i dati del gioco, né scrivere dal gioco nel
gestionale: i dati del gioco sono finti. Vedi `docs/games.md`.

---

## 5. Regole di dominio che non si negoziano

Sono scritte per esteso in `docs/business-rules.md` e `docs/club-portal.md`;
qui l'essenziale.

- **Ogni calcolo economico è server-side.** Il browser sceglie una chiave
  (`FULL`, `MONTHLY_12`, un id prodotto, le quote da pagare), mai un
  importo. Un prezzo che arriva dal frontend non si usa nemmeno per
  visualizzarlo.
- **L'idempotenza si ottiene con un vincolo UNIQUE su una chiave
  deterministica**, mai con un flag applicativo e mai con un UUID generato
  al volo dal client. Bonus, cashback, provvigioni, quote e pagamenti non
  devono poter essere creati o accreditati due volte.
- **Si paga con bonifico o con JavCash.** Non esistono pagamenti online con
  carta: un bonifico lo conferma l'amministratore (ordini, contratti, rate),
  oppure — per le quote del club — lo dichiara il genitore caricando la
  prova. Le quote del club si pagano anche in **contanti** (il genitore dice
  a chi li ha dati) o con la **carta al POS** del club (lo segna la
  segreteria): ogni quota pagata registra il metodo (`payment_method`). Il
  bottone "Carta online" è spento finché non c'è un pagamento online.
- **Gli snapshot sono congelati**: la rete al momento dell'attivazione, il
  prezzo al momento della creazione del contratto, l'importo di una quota al
  momento in cui è emessa. Non si ricalcolano mai a posteriori.
- **Club** (`domains/club`):
  - **più club sulla stessa piattaforma**: ogni query del dominio filtra per
    `club_id` (le funzioni ricevono un `ClubScope`), e su quale club lavora
    una richiesta lo decide solo `club/scope.py` — mai un id che arriva dal
    browser. Lo Shop, il catalogo e JavCash sono della piattaforma, uno per
    tutti i club;
  - le quote sono UNIQUE per (atleta, tipo, periodo): i job mensili e di
    inizio stagione possono girare due volte senza effetti;
  - **la prova di pagamento caricata segna subito le quote come pagate**; la
    segreteria può rifiutarla (le quote tornano da pagare e il genitore
    viene avvisato), ma nessuna prova resta in attesa di qualcuno;
  - l'età per il piano è l'**età federale** (anni compiuti entro il 31
    dicembre, `seasons.federal_age`): a gennaio chi entra nella fascia dopo
    paga la mensilità del gruppo nuovo, i mesi già emessi non cambiano
    (salvo `plan_locked`). Le fasce del Jav Ranking contano invece l'età al
    1° settembre;
  - **ogni file personale sta nel bucket privato** (`upload_document`):
    prove di pagamento, certificati, giustificazioni per la scuola,
    ricevute delle spese. Si apre solo con un URL presigned di pochi minuti
    dato dopo il controllo di chi lo chiede. Nel bucket pubblico dei media
    solo foto pensate per essere viste (loghi, foto del sito, foto profilo);
  - senza certificato agonistico valido alla data della gara non ci si
    iscrive a una gara che lo richiede;
  - la cintura attuale e il Jav Ranking si **calcolano** dallo storico e dai
    risultati, non si salvano mai a mano.
- **Shop** (`jav_market`, catalogo scritto dall'amministratore): regole in
  `domains/marketplaces/rules.py`. JavCash mai al 100% del prezzo (max 99,
  vincolo nel DB). **La vetrina cliente va a pagine**
  (`marketplaces/paging.py`, rotte `…/page`): mai restituire tutto il
  catalogo in una risposta.
- **L'IVA si aggiunge al prezzo esposto** negli ordini dello Shop:
  `vat_mode` sull'ordine dice quale regola valeva quando è stato creato.
- **Il carrello** (`domains/carts`) è uno per (cliente, negozio). Un ordine
  porta N righe e **il denaro resta sulla testata**.
- **Un'email che non parte non deve mai far fallire l'operazione che la
  precede** — c'è `send_html_email_best_effort()` per questo. Con due
  eccezioni volute: i link di reset password e i codici OTP, dove se l'invio
  fallisce l'utente *deve* saperlo.
- **Disco**: ogni build lascia le immagini vecchie senza nome; a fine
  sessione `docker image prune -f && docker builder prune -f` (mai
  `volume prune`).
- **Backup** (`scripts/backup.sh`): database con rotazione 7 giorni /
  settimanali / mensili + `.env`, prova di ripristino settimanale
  (`verify-backup.sh`); i lavori pianificati sono in
  `docs/server-migration-guide.md` §4.8.

---

## 6. Interfaccia

- L'interfaccia è in **sette lingue: portoghese (pt-PT, la predefinita),
  inglese, italiano, spagnolo, francese, tedesco e ucraino**, scelte con la
  bandierina in alto (cookie `jav_lang`, letto dal layout radice; elenco in
  `lib/i18n/config.ts`, bandiere SVG in `components/language-switcher.tsx`).
  Un testo nuovo non si scrive nel componente: si aggiunge una chiave nei
  sette file di
  `apps/dashboard/lib/i18n/messages/` (`it.ts` è la sorgente, gli altri non
  compilano se manca una chiave; una chiave assente ricade sull'inglese) e si usa `const { t, fmt } = useI18n()`; importi e date con
  `fmt.euro` / `fmt.shortDate`, mai con `"it-IT"` scritto a mano. Per le
  etichette che arrivano come codice dall'API (cinture, livelli, traguardi)
  `t.dyn(\`chiave.${codice}\`, etichettaApi)`.
  **Tradotto**: sito pubblico, login e recupero password, barra e menu, area
  famiglie, area atleta, area staff, quasi tutta la segreteria del club.
  Ancora solo in italiano: la console della piattaforma (clienti, promoter,
  prodotti, impostazioni), l'area promoter, carrello e wallet, contratti, e i
  messaggi che arrivano dal backend (errori, notifiche, email, motivi di non
  idoneità a una gara). JAVBOT e i giochi parlano pt, en, it: spagnolo →
  portoghese, francese/tedesco/ucraino → inglese (`javbot/texts.py::NEAREST_LANG`,
  `game/service.py::_lang`). Una lingua nuova: un file in `messages/`, la
  voce in `config.ts` (tag Intl e nome), la bandiera, `translate.ts`, le
  due mappe del backend, `club/contact.py::LOCALES`, la chiave
  `inbox.locale.<lingua>` — e un alfabeto nuovo vuole i suoi caratteri in
  `app/layout.tsx` (per il cirillico: subset `cyrillic` di Inter e Russo One
  dietro Audiowide, che ha solo il latino).
- Ogni messaggio, anche di errore, è scritto per chi lo legge. Chi usa questa
  applicazione — un genitore dal telefono — non è tecnico: "Si è verificato
  un errore" è un fallimento, non un messaggio.
- Il `detail` di un errore FastAPI 422 è un **array**, non una stringa.
  Passarlo a React produce `[object Object]` sullo schermo. La traduzione sta
  in `apps/dashboard/lib/api-error.ts`: usala, non reinventarla.
- Il redesign in corso (vedi `docs/implementation-progress.md`) porta a un
  **tema chiaro unico** con i colori del club (rosso, giallo, grigio) come
  token Tailwind v4 in `apps/dashboard/app/globals.css`: un componente nuovo
  usa i token e i componenti di `components/ui/`, non classi colore scritte
  a mano.
- Animazioni ed effetti 3D rispettano sempre `prefers-reduced-motion`.

---

## 7. Documentazione da aggiornare

Non è opzionale: questo repository si regge sulla documentazione, ed è il
motivo per cui è ricostruibile.

| Quando | Cosa |
|---|---|
| sempre, a fine lavoro | `docs/implementation-progress.md` — una voce per sessione, in italiano, che dice cosa è cambiato **e perché** |
| nuova regola di business | `docs/business-rules.md` (o `docs/club-portal.md` se è del club) |
| nuova tabella o colonna | `docs/database-model.md` **e** `docs/database-schema.sql` (rigenerato) |
| cambia qualcosa per l'utente | `docs/user-guide.md` |
| cambia l'installazione | `docs/server-migration-guide.md` — e §15 se cambia il modo di **verificarla** |
| decisione lasciata in sospeso | `docs/open-questions.md` |

---

## 8. Git

Branch `main`, remote unico `https://github.com/raphaelcodeart/jav` (il
server pusha con una deploy key, alias SSH `github-jav`). Si committa solo
quando l'utente lo chiede e **si pusha solo quando l'utente lo chiede
esplicitamente**, mai di propria iniziativa. Ogni commit termina con:

```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Il corpo del messaggio si scrive in italiano e spiega **perché**, non cosa:
il cosa si legge dal diff.

---

## 9. Come è fatto

FastAPI + SQLAlchemy async + Alembic + Pydantic v2 su PostgreSQL 16, Celery
con Redis, MinIO per i file, Next.js 16 (App Router) davanti, nginx come
router interno, Caddy sull'host per l'HTTPS, tutto in Docker Compose.

```
apps/api/app/domains/<dominio>/   models.py schemas.py service.py router.py
apps/api/app/domains/club/        atleti, piani, quote, prove, certificati, cinture,
                                  corsi e presenze, gare, ranking, medaglie, job
apps/api/app/core/                config, db, security, storage, email
apps/api/alembic/versions/        migrazioni (0001_schema_iniziale.py, poi 0002_…)
apps/api/tests/                   pytest
apps/dashboard/app/               rotte Next.js (+ BFF in app/api/proxy)
apps/dashboard/components/        UI (components/ui/ = sistema di componenti)
infrastructure/nginx/             nginx.conf (router interno, solo HTTP)
infrastructure/caddy/             jav.caddy (sito Caddy sull'host)
scripts/                          backup, restore, deploy, migrate, dump-schema
```

Il frontend non parla mai direttamente con l'API: passa dal proxy BFF in
`apps/dashboard/app/api/proxy/[...path]`, che è dove vive il cookie di
sessione.

La regola di scrittura del codice è una sola: il codice nuovo deve
assomigliare a quello che ha intorno — stessa densità di commenti, stessi
nomi, stesse abitudini. E un commento spiega *perché* una cosa è fatta così,
non *cosa* fa la riga sotto.

---

## 10. Reinstallare tutto su un altro server

La procedura completa, con le verifiche, è `docs/server-migration-guide.md`
(§4 per un doppione di questo sistema, §12 per un nuovo club). In sintesi,
nell'ordine:

1. Server Ubuntu con `docker.io docker-compose-v2 git openssl caddy`; clona
   `https://github.com/raphaelcodeart/jav` in `/opt/webapps/jav`.
2. `.env` da `.env.example`, con segreti nuovi (guida §4.2).
3. `docker compose -f docker-compose.dev.yml build && … up -d`: il container
   `api` esegue `alembic upgrade head` da solo e costruisce **tutto** lo schema.
4. Dati minimi: `python -m app.seed.bootstrap` (organizzazione, permessi,
   ruoli, gradi, piano provvigioni, primo amministratore) — oppure il
   ripristino di un backup con dati (`scripts/restore.sh`).
5. Caddy + HTTPS (§4.6), crontab dei backup (§4.8).
6. Verifiche della guida §15.3, in particolare
   `https://<dominio>/backend/health` → 200: il calendario degli eventi
   dell'area chiama `/backend/` dal browser, e nginx deve seguire l'IP di
   `api` dopo ogni deploy (variabile + `set` prima del `rewrite`).
7. Dall'interfaccia: SMTP, IBAN e intestatario del conto, piani del club,
   corsi, prodotti dello Shop. Per entrare in un account senza email
   configurata: `./scripts/set-password.sh EMAIL` dal server, o il bottone
   **🔑 Link di accesso** del super admin per lo staff di un club.

Il container `stt` (il microfono di JAVBOT, nascosto) **non parte** con
`up -d`: sta nel profilo compose `voice`. Si accende solo se si riattiva il
microfono (`--profile voice up -d stt`, 1,2 GB di RAM).

`docs/database-schema.sql` è il **modello della struttura** (solo struttura,
nessun dato), generato da un database costruito da Alembic: serve a
verificare che una reinstallazione sia identica (stesso numero di tabelle,
stessa revision) o a leggere lo schema senza avviare nulla. Non va caricato
a mano al posto delle migrazioni: se proprio lo si usa (`psql -f`), poi
`alembic stamp head`, altrimenti Alembic proverebbe a ricreare tutto.
