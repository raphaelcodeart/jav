# Istruzioni operative per Claude Code

Questo file viene letto all'inizio di ogni sessione. Contiene le cose che
**non si deducono leggendo il codice** e che, se ignorate, fanno danni:
convenzioni, trappole già pagate una volta, e i comandi esatti che funzionano
su questo server.

Per la ricostruzione completa da zero (server nuovo, o progetto rifatto per
un'altra azienda) la guida è `docs/server-migration-guide.md` — §12 è un
runbook pensato per essere eseguito passo per passo, verifiche comprese.

---

## 1. Le tre cose da sapere prima di toccare qualsiasi cosa

**Questo server ospita l'installazione su `jav.ecodo.ai`.** Non esiste un
ambiente di staging: quello che si deploya qui è quello che vedono gli utenti.
L'HTTPS lo fa Caddy sull'host (`/etc/caddy/sites/jav.caddy`, copia di
`infrastructure/caddy/jav.caddy`); il nginx dello stack ascolta solo su
`127.0.0.1:8081`.

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
vecchio. È successo (Session 87): per una settimana i lavori automatici
giravano su codice di otto giorni prima, e la sync notturna dei prodotti
AliExpress falliva a ogni giro su una colonna rinominata — un cliente ha
trovato non disponibile un prodotto che per noi era in vendita.

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
`jav_test`, **mai** `jav`: controllalo nella stringa di
connessione ogni volta, prima di premere invio.

Gli hostname `postgres` e `minio` del `.env` esistono solo dentro la rete
Docker: dall'host non risolvono. In più sull'host gira un *altro* Postgres
su `127.0.0.1:5432`, con credenziali diverse — puntarci dà
`password authentication failed for user "jav"`, che sembra una password
sbagliata ma è il server sbagliato. Usa gli IP dei container:

```bash
cd /opt/webapps/jav/apps/api
POSTGRES_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
  $(docker compose -f ../../docker-compose.dev.yml ps -q postgres))
MINIO_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
  $(docker compose -f ../../docker-compose.dev.yml ps -q minio))
set -a && . <(grep -E "^(S3_|MINIO_|POSTGRES_PASSWORD)" /opt/webapps/jav/.env) && set +a
export S3_ENDPOINT_URL="http://$MINIO_IP:9000"
TEST_DATABASE_URL="postgresql+psycopg://jav:${POSTGRES_PASSWORD}@${POSTGRES_IP}:5432/jav_test" \
  .venv/bin/python -m pytest -q
```

Le variabili S3 servono davvero: i test dei documenti caricano file veri su
MinIO. Senza, falliscono con `EndpointConnectionError`.

La suite completa impiega ~2,5 minuti: lanciala in background e nel
frattempo fai altro. Il driver è `psycopg`, non `asyncpg`. Il venv
`apps/api/.venv` ogni tanto è indietro rispetto a `pyproject.toml` (è già
successo con `stripe`): se la *collection* fallisce su un
`ModuleNotFoundError`, installa il pacchetto e vai avanti.

---

## 3. Verifiche prima di un deploy

```bash
cd apps/api      && .venv/bin/python -c "import app.main"   # vedi sotto
cd apps/dashboard && pnpm typecheck && pnpm build
```

`import app.main` non è pedanteria: un `NameError` in un router non lo prende
nessun test (i test esercitano i servizi, non le rotte) e si manifesta come
un 500 al primo utente che apre quella schermata. È già successo.

`pnpm lint` **non passa** su questo repository: ci sono 15 errori
preesistenti, quasi tutti `react-hooks/set-state-in-effect`. Il criterio non
è "lint verde" ma "lint non peggiora": conta gli errori prima e dopo, o
verifica che i tuoi file non compaiano nell'elenco. Stessa cosa per `mypy` e
per `ruff` su `alembic/` e `tests/`.

`react-hooks/set-state-in-effect` è comunque un **errore**, non un warning:
nel codice nuovo i valori si derivano durante il render, non si sincronizzano
con un `useEffect`.

---

## 4. Migrazioni e schema

Una modifica ai modelli richiede tre cose, non una:

1. un file nuovo in `apps/api/alembic/versions/` (numerazione progressiva
   `00NN_nome.py`, `down_revision` = la revision precedente);
2. `./scripts/backup.sh` **prima** di applicarla in produzione;
3. `./scripts/dump-schema.sh` dopo, e il diff di `docs/database-schema.sql`
   committato insieme al resto.

Il punto 3 sembra burocrazia e non lo è: quel file è l'artefatto con cui si
ricostruisce il database su un altro server, ed è già andato fuori
sincrono due volte (mancavano interi domini). Il diff deve contenere
**solo** ciò che la migrazione dichiara di fare: se contiene altro, qualcuno
ha modificato il database a mano.

Il container `api` esegue `alembic upgrade head` da solo all'avvio. Non serve
lanciarlo a parte dopo un `up -d`.

Lo schema da solo non basta a far partire l'applicazione: permessi, ruoli,
gradi e piano provvigioni sono **dati**, non struttura. Vedi
`docs/server-migration-guide.md` §6.1 e `python -m app.seed.bootstrap`.

---

## 5. Regole di dominio che non si negoziano

Sono scritte per esteso in `docs/business-rules.md`; qui l'essenziale.

- **Ogni calcolo economico è server-side.** Il browser sceglie una chiave
  (`FULL`, `MONTHLY_12`, un id prodotto), mai un importo. Un prezzo che
  arriva dal frontend non si usa nemmeno per visualizzarlo.
- **L'idempotenza si ottiene con un vincolo UNIQUE su una chiave
  deterministica**, mai con un flag applicativo e mai con un UUID generato
  al volo dal client. Bonus, cashback, provvigioni e pagamenti non devono
  poter essere accreditati due volte: è già successo, e la causa era un
  `retry` dopo un errore di invio email.
- **I webhook Stripe si verificano con la firma**, e l'`event.id` si registra
  *prima* di eseguire qualsiasi handler.
- **Gli snapshot sono congelati**: la rete al momento dell'attivazione, il
  prezzo al momento della creazione del contratto. Non si ricalcolano mai a
  posteriori.
- **Marketplace (CJ = 1, Shopify = 2, AliExpress = 3, «Fai la Spesa con
  Jav» = 4, «Market Kappa» = 5, «Marketplace VAITTO» = 6)**: regole solo in `domains/marketplaces/rules.py` — **nessuno sconto a chi paga
  con bonifico** (tolto nella Session 86: non si può fare, vale ovunque, anche
  per i contratti) e **mai un aumento sulla carta** (vietato in Italia);
  niente cashback; JavCash 30% sui nuovi prodotti e mai 100% (max 99,
  vincolo nel DB). I tre shop sono domini isolati
  (`cj_dropshipping`, `shopify_dropshipping`, `aliexpress_dropshipping`,
  `jav_market`, `kappa_market`, `vaitto_market`, `symphonya_market`, `soleil_market`) ma la *gestione* è unificata: ordini cliente, ordini admin e
  Contabilità mostrano una lista sola. Un quinto shop si costruisce clonando
  uno di questi domini e riusando `rules.py`, non copiandone le regole —
  `jav_market` (Session 79) è l'esempio più recente, ed è anche l'unico
  senza fornitore: il catalogo lo scrive l'amministratore. `kappa_market`
  (Session 87, solo Kappa e Robe di Kappa) è il suo clone, e `vaitto_market`
  (Session 88) il clone di Kappa rifornito da un feed CSV (`feed.py`);
  `symphonya_market` (Session 89, «Shop Beauty» per il cliente) è il clone di
  VAITTO rifornito dall'API di Symphonya; `soleil_market` (Session 90,
  «Fai la Spesa con Jav 2» per il cliente, prima «Market 7») è il clone di
  Symphonya rifornito dall'API affiliati SoleilDrop (dal 13/10/2026) o
  dall'Excel del portale. La
  chiave è `soleil_market` e non `soleildrop_market` perché `carts.shop` e
  `shop_categories.shop` sono `String(16)`. VAITTO, Symphonya e SoleilDrop
  calcolano il JavCash con la stessa formula (prezzo ÷ 1,22 − costo, metà
  in JavCash): se cambia in uno, va cambiata negli altri. **Ogni vetrina cliente va a
  pagine** (`marketplaces/paging.py`, rotte `…/page`, «Mostra altri
  prodotti»): mai restituire tutto il catalogo in una risposta (Symphonya
  erano 63 MB e mezzo GB di RAM per apertura) -- regola dell'utente.
- **Disco**: ogni build lascia le immagini vecchie senza nome; a fine
  sessione `docker image prune -f && docker builder prune -f` (mai
  `volume prune`; lo fa anche il cron della domenica). Il 2026-10-02 il
  disco era al 97% e i test fallivano.
- **Backup** (`scripts/backup.sh`, cron 04:00): database con rotazione
  7 giorni / settimanali / mensili + `.env`, solo sul server (scelta
  dell'utente); prova di ripristino ogni domenica (`verify-backup.sh`);
  un errore avvisa lo staff nell'app.
- **Il carrello** (`domains/carts`) è uno per (cliente, negozio): righe di
  negozi diversi non possono finire nello stesso ordine, perché le regole si
  escludono a vicenda. Un ordine porta N righe e **il denaro resta sulla
  testata** — è la ragione per cui pagamenti, webhook e Contabilità non sono
  cambiati quando il carrello è arrivato.
- **L'IVA si aggiunge al prezzo esposto** (Session 78), non è contenuta:
  `vat_mode` sull'ordine dice quale regola valeva, perché prima era il
  contrario e le stesse colonne hanno significato opposto.
- **Le credenziali dei fornitori non si scrivono a mano nel DB**: Shopify e
  AliExpress si collegano con un giro OAuth dal pannello ("Collega...") e
  rinnovano i token da soli; nessun endpoint restituisce mai un secret,
  solo "configurato" e le ultime 4 cifre.
- **Un'email che non parte non deve mai far fallire l'operazione che la
  precede** — c'è `send_html_email_best_effort()` per questo. Con due
  eccezioni volute: i link di reset password e i codici OTP, dove se l'invio
  fallisce l'utente *deve* saperlo.

---

## 6. Interfaccia

- Tutto ciò che vede un utente è **in italiano**, incluso ogni messaggio di
  errore. Chi usa questa applicazione non è tecnico: "Si è verificato un
  errore" è un fallimento, non un messaggio.
- Il `detail` di un errore FastAPI 422 è un **array**, non una stringa.
  Passarlo a React produce `[object Object]` sullo schermo. La traduzione sta
  in `apps/dashboard/lib/api-error.ts`: usala, non reinventarla.
- Dark e light: ogni classe di colore ha la sua variante `light:`. Un
  componente nuovo va guardato in entrambi i temi.
- Tailwind v4, niente file di configurazione del tema. Il colore del brand
  (`orange-*`/`amber-*`) è scritto a mano in ogni componente.

---

## 7. Documentazione da aggiornare

Non è opzionale: questo repository si regge sulla documentazione, ed è il
motivo per cui è ricostruibile.

| Quando | Cosa |
|---|---|
| sempre, a fine lavoro | `docs/implementation-progress.md` — una voce per sessione, in italiano, che dice cosa è cambiato **e perché** |
| nuova regola di business | `docs/business-rules.md` |
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
con Redis, MinIO per i file, Next.js 16 (App Router) davanti, tutto dietro
nginx, tutto in Docker Compose.

```
apps/api/app/domains/<dominio>/   models.py schemas.py service.py router.py
apps/api/app/core/                config, db, security, storage, email
apps/api/alembic/versions/        migrazioni
apps/api/tests/                   pytest
apps/dashboard/app/               rotte Next.js (+ BFF in app/api/proxy)
apps/dashboard/components/        UI
infrastructure/nginx/             nginx.conf
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
(§4 per un doppione di questo sistema, §12 per un'altra azienda, §14 per i
Marketplace). In sintesi, nell'ordine:

1. Server Ubuntu con `docker.io docker-compose-v2 git openssl`; clona
   `https://github.com/raphaelcodeart/jav` in `/opt/webapps/jav`.
2. `.env` da `.env.example`, con segreti nuovi (guida §4.2).
3. `docker compose -f docker-compose.dev.yml build && … up -d`: il container
   `api` esegue `alembic upgrade head` da solo e costruisce **tutto** lo schema.
4. Dati minimi: `python -m app.seed.bootstrap` (organizzazione, permessi,
   ruoli, gradi, piano provvigioni, primo amministratore) — oppure il
   ripristino di un backup con dati (`scripts/restore.sh`).
5. nginx + HTTPS (§4.6), crontab di backup e certificato (§4.8).
6. Dall'interfaccia: SMTP, Stripe (webhook con `checkout.session.completed`,
   `invoice.paid`, `invoice.payment_failed`), IBAN, prodotti, poi i
   Marketplace (§14).

`docs/database-schema.sql` è il **modello della struttura** (solo struttura,
nessun dato), generato da un database costruito da Alembic: serve a
verificare che una reinstallazione sia identica (stesso numero di tabelle,
stessa revision) o a leggere lo schema senza avviare nulla. Non va caricato
a mano al posto delle migrazioni: se proprio lo si usa (`psql -f`), poi
`alembic stamp head`, altrimenti Alembic proverebbe a ricreare tutto.
