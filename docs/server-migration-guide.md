# Guida alla Migrazione del Server / Ricostruzione da Zero

Questo documento serve a un solo scopo: permettere a chiunque (umano o AI) di
ricreare **esattamente** questa piattaforma su un nuovo server, partendo da zero,
senza dover indovinare nulla. Se stai leggendo questo perché il server attuale è
stato perso, compromesso, o semplicemente vuoi migrare altrove — segui questa
guida nell'ordine in cui è scritta. Se invece l'obiettivo è installare la
piattaforma per **un nuovo club**, la procedura di installazione è la stessa
(sezioni 1-8), più la §11 (cosa personalizzare) e la §12 (il runbook
completo, passo per passo).

Non duplica `README.md` o `docs/architecture.md` — li presuppone. Qui ci sono solo
le informazioni operative specifiche per un trasloco/ricostruzione: cosa
installare, in che ordine, quali bug reali sono già stati trovati e corretti (per
non doverli riscoprire), e come verificare che tutto funzioni.

## 1. Cos'è questo progetto, in breve

Jav, gestionale per palestre e club di judo: FastAPI (backend) + Next.js 16
(frontend/BFF) + PostgreSQL 16 + Redis + Celery + MinIO, orchestrato con
Docker Compose; nginx come router interno su `127.0.0.1:8081`, Caddy
sull'host per l'HTTPS. Vedi
`docs/architecture.md` per il quadro completo, `docs/implementation-progress.md`
per cosa è realmente implementato e cosa no.

Repository: `https://github.com/raphaelcodeart/jav`, branch `main`.

## 2. Server di riferimento (quello su cui questo progetto gira oggi)

Utile per dimensionare un eventuale nuovo server in modo equivalente:

| | |
|---|---|
| Provider | Hetzner Cloud (datacenter fsn1 — Falkenstein) |
| Hostname | `ubuntu-4gb-fsn1-1` |
| OS | Ubuntu 26.04 LTS |
| CPU | 2 vCPU |
| RAM | 3.7 GiB + **2 GB di swap** (`/swapfile`, vedi §3) |
| Disco | 38 GB (le immagini Docker sono la voce più grossa: vedi la pulizia in §4.8) |
| IP pubblico | vedi il pannello Hetzner del progetto — cambia se si ricrea il server |

Un nuovo server con specifiche pari o superiori (2 vCPU / 4 GB RAM / 40 GB disco
minimo) è sufficiente per l'intero stack in questa fase (dati demo, traffico
basso). Se il volume di contratti/agenti cresce di ordini di grandezza, rivedere
il dimensionamento di Postgres in particolare.

Sullo stesso server girano anche altri siti (statici in `/opt/sites`, altre
webapp in `/opt/webapps`), tutti dietro lo stesso Caddy: ognuno ha il suo file
in `/etc/caddy/sites/`.

## 3. Prerequisiti sul nuovo server

Sistema operativo Ubuntu 24.04+ o equivalente (Debian-based). Da installare:

```bash
apt-get update
apt-get install -y docker.io docker-compose-v2 git openssl
systemctl enable --now docker
```

Verifica:
```bash
docker --version          # atteso: Docker version 27+ (qualsiasi versione recente va bene)
docker compose version     # atteso: Docker Compose version 2.x
```

**Swap: obbligatorio con 4 GB di RAM.** Senza, ogni `docker compose build`
(soprattutto l'immagine `dashboard`) esaurisce la memoria e il kernel uccide
processi a caso -- è successo per un'intera giornata il 2026-08-26. Il server
di riferimento ha 2 GB di swap:
```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
swapon --show              # atteso: /swapfile 2G
```

`python3` serve sull'host (c'è già su Ubuntu): `scripts/backup.sh` lo usa per
la rotazione delle copie.

Non serve installare Python, Node, PostgreSQL, Redis o MinIO direttamente
sull'host: girano tutti dentro i container Docker. (Se invece vuoi sviluppare o
fare debug SENZA Docker, vedi `docs/deployment.md` e il `README.md` per
l'installazione locale di `postgresql`, `nodejs`/`npm`/`pnpm` — utile solo per
verifica/debug, non necessaria per l'esecuzione normale.)

## 4. Passo per passo: ricostruzione completa

### 4.1 Clona il repository

```bash
mkdir -p /opt/webapps && cd /opt/webapps
git clone https://github.com/raphaelcodeart/jav jav
cd jav
```

Se il repository è privato serve una chiave SSH autorizzata (deploy key o
chiave dell'account). Se non ce l'hai già configurata sul nuovo server:

```bash
ssh-keygen -t ed25519 -C "nuovo-server-deploy" -f ~/.ssh/id_ed25519_github -N ""
cat ~/.ssh/id_ed25519_github.pub
# aggiungi questa chiave pubblica su GitHub:
# https://github.com/raphaelcodeart/jav -> Settings -> Deploy keys -> Add deploy key
# (spunta "Allow write access" solo se questo server deve anche fare push)
cat >> ~/.ssh/config <<'EOF'

Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_github
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh -T git@github.com   # deve rispondere "successfully authenticated"
```

### 4.2 Crea il file `.env`

**Non è nel repository** (per design — vedi `.gitignore`). Deve essere ricreato
da zero su ogni server. Usa `.env.example` come riferimento della lista completa
delle variabili, poi genera segreti reali:

```bash
cp .env.example .env

# genera segreti forti al posto dei placeholder:
python3 -c "
import secrets
minio_secret = secrets.token_hex(24)
print('POSTGRES_PASSWORD=' + secrets.token_hex(24))
print('JWT_SECRET_KEY=' + secrets.token_hex(32))
print('MINIO_ROOT_USER=jav_minio_admin')
print('MINIO_ROOT_PASSWORD=' + minio_secret)
print('S3_ACCESS_KEY=jav_minio_admin')
print('S3_SECRET_KEY=' + minio_secret)   # <-- SAME value as MINIO_ROOT_PASSWORD, not a separate one -- see §8 #12
"
# incolla questi valori dentro .env al posto dei placeholder corrispondenti
```

Variabili che vanno adattate al nuovo server (non generate a caso):
- `NEXT_PUBLIC_APP_URL` e `PUBLIC_APP_BASE_URL` — stesso valore, l'URL pubblico
  con cui si accederà (`http://IP-NUOVO-SERVER` o `https://tuodominio.it` se hai
  già DNS+TLS pronti). `PUBLIC_APP_BASE_URL` è usata server-side dall'API per
  costruire il link nelle email di reset password.
- `API_INTERNAL_URL` — lascialo `http://api:8000` (è interno alla rete Docker, non
  cambia mai tra server)
- `MINIO_REGION` — deve essere UGUALE a `S3_REGION` (default `eu-central-1` in
  entrambi) — vedi §8 #12 se li disallinei per errore.
- `SMTP_*` — opzionali, lascia `SMTP_HOST` vuoto per partire senza email (i link
  di reset password restano validi, solo loggati invece che inviati — vedi
  `business-rules.md §Password reset`); compilali quando hai un provider SMTP
  reale (verifica host, porta e STARTTLS con un login SMTP vero prima di
  scriverli in `.env`).
- `ENABLE_API_DOCS=false` in produzione: altrimenti `/backend/docs` è
  pubblico.
- `ANTHROPIC_API_KEY` — opzionale: la chiave dell'API di Claude per JAVBOT
  dell'area riservata (`javbot/assistant.py`). Vuota, JAVBOT risponde con le
  parole chiave come prima e la base di conoscenza si può già riempire.
  `JAVBOT_MODEL` (predefinito `claude-opus-5-5`) e `JAVBOT_EFFORT`
  (predefinito `low`) la regolano. Dopo averla cambiata vanno ricreati
  `api` e i due worker (`up -d --force-recreate api celery-worker
  celery-beat`): il `.env` si legge all'avvio.
- `STT_URL` — opzionale, predefinito `http://stt:8001`: il servizio Whisper
  del microfono di JAVBOT (container `stt`, fino a 1,2 GB di RAM). Il
  microfono oggi è **nascosto** nell'interfaccia e il container sta dietro il
  profilo compose `voice`: non parte con `up -d` (per accenderlo,
  `--profile voice up -d stt`). Senza il servizio il microfono risponde «non
  disponibile».

**Mai committare `.env` nel repository.** È già in `.gitignore`; se `git status`
lo mostra come modificabile, fermati e controlla prima di fare qualsiasi `git add`.

### 4.3 Costruisci e avvia lo stack

```bash
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d
```

Le migrazioni Alembic girano **automaticamente** all'avvio del container `api`
(vedi il `command` del servizio `api` in `docker-compose.dev.yml`) — non serve
lanciarle a mano la prima volta.

Verifica che gli 8 container (postgres, redis, minio, api, celery-worker,
celery-beat, dashboard, nginx) siano `healthy` o `Up` (aspetta 30-60 secondi).
`stt`, il microfono di JAVBOT, non c'è: è nel profilo opzionale `voice`.

```bash
docker compose -f docker-compose.dev.yml ps
```

Se qualcosa non diventa `healthy`, guarda la §8 ("Problemi noti già
risolti") prima di improvvisare un fix.

### 4.4 Popola i dati

**Scenario A — nuovo server, dati demo (nessuna migrazione dati reali):**
```bash
docker compose -f docker-compose.dev.yml exec api python -m app.seed
```
Salva l'`Organization ID` stampato in output — serve per fare login.

**Scenario B — stai migrando dati reali dal vecchio server:** vedi sezione 5
("Migrare i dati da un server esistente") invece di eseguire il seed.

**Scenario C — stai avviando un CLUB NUOVO (né la demo, né un ripristino):**
non eseguire `python -m app.seed`. Quel comando crea venti promoter finti,
una cinquantina di clienti e i relativi contratti, ed è l'ultima cosa che
vuoi dentro il database di un cliente reale. Usa invece il bootstrap, che
crea **solo** ciò senza cui l'applicazione non parte (permessi, ruoli, gradi,
piano provvigioni) più un unico amministratore:

```bash
docker compose -f docker-compose.dev.yml exec api \
  python -m app.seed.bootstrap \
    --organization-name "Nome Club" \
    --legal-name "Nome Club A.S.D." \
    --admin-email "segreteria@club.it"
```

Stampa l'`Organization ID` e, se non hai passato `--admin-password`, una
password generata **mostrata una sola volta**: salvala subito, non è
recuperabile (si può solo fare un reset password, che però richiede l'SMTP
già configurato — e a quel punto non lo è ancora). È idempotente: se il primo
tentativo si interrompe a metà, rilancialo senza paura.

L'amministratore appena creato ha l'email già marcata come verificata — nasce
da un comando eseguito sul server, prova di controllo più forte di un link
cliccato, e all'ora del bootstrap l'SMTP di solito non esiste ancora. Privacy
e dati anagrafici restano invece vuoti **di proposito**: sono atti di una
persona vera, e l'interfaccia glieli chiede al primo accesso. Non è un
bootstrap incompleto.

Poi prosegui con la §12, che è la procedura completa per un nuovo club.

### 4.5 Verifica

```bash
scripts/health-check.sh dev
curl -s http://localhost/login   # deve rispondere 200
```

Poi prova il login vero (vedi `docs/user-guide.md` per la procedura completa
lato utente) con le credenziali del seed (`DemoPass123!`) o le credenziali reali
migrate.

### 4.6 Dominio e HTTPS

**Il login richiede HTTPS**: il cookie di sessione è `Secure` e un browser lo
scarta in silenzio su `http://` (il login "ricarica" `/login` senza errori).

L'HTTPS lo fa **Caddy sull'host**, non un container: ottiene e rinnova da solo
il certificato Let's Encrypt, quindi non c'è certbot né cron di rinnovo. Il
nginx dello stack ascolta solo su `127.0.0.1:8081` in HTTP (vedi il commento
in testa a `infrastructure/nginx/nginx.conf`) e Caddy gli inoltra tutto.

```bash
# 1. Il DNS del dominio deve puntare SOLO all'IP del server (un secondo record
#    A, ad es. il parcheggio del registrar, fa fallire il certificato a caso).
getent ahosts jav.ecodo.ai

# 2. Caddy sull'host (una volta per server)
apt-get install -y caddy
#    /etc/caddy/Caddyfile deve definire lo snippet `common` (compressione,
#    header di sicurezza, log) e fare `import sites/*.caddy`.

# 3. Il sito: cambia il dominio nel file se non è jav.ecodo.ai
cp infrastructure/caddy/jav.caddy /etc/caddy/sites/jav.caddy
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl reload caddy

# 4. Verifica
curl -sI https://jav.ecodo.ai/login          # 200, certificato Let's Encrypt
curl -sI http://jav.ecodo.ai/login           # 308 verso https://
```

`NEXT_PUBLIC_APP_URL` e `PUBLIC_APP_BASE_URL` nel `.env` devono essere lo
stesso `https://<dominio>`: il secondo costruisce ogni link nelle email.

### 4.7 Rimuovere i dati demo prima della produzione

Il seed demo (`python -m app.seed`) crea utenti, agenti e clienti marcati
come demo: password `DemoPass123!`, email `*@jav.demo`. Non va mai eseguito
sul database di un club vero; se è stato eseguito per errore, la strada più
semplice e sicura è ricreare il database da capo (§4.3) invece di disfare
selettivamente ogni riga.

Non dimenticare i file binari: i documenti e le foto demo restano su MinIO
anche dopo aver cancellato le righe Postgres corrispondenti (le righe portano
solo la `storage_key`), finché non li elimini con `mc rm` o svuotando il
bucket.

### 4.8 Backup automatico e lavori pianificati

Su questo server (`crontab -l` come root, 2026-10-04):

```bash
0 4 * * * cd /opt/webapps/jav && ./scripts/backup.sh dev >> ./backups/backup.log 2>&1
0 5 * * 0 cd /opt/webapps/jav && ./scripts/verify-backup.sh dev >> ./backups/backup.log 2>&1
30 5 * * 0 docker image prune -f >> /opt/webapps/jav/backups/backup.log 2>&1 && docker builder prune -f >> /opt/webapps/jav/backups/backup.log 2>&1
```

Su un server nuovo si rimettono uguali con `crontab -e`.

- **`scripts/backup.sh`** (ogni notte alle 4): `pg_dump` compresso in
  `./backups/jav_dev_<data>.sql.gz` (~20 MB), con rotazione: tutte le
  copie degli ultimi 7 giorni, poi una a settimana fino a 5 settimane, poi
  una al mese fino a 6 mesi (~17 copie a regime). Salva anche il `.env` in
  `./backups/env/env_<data>` (solo root, una copia nuova solo quando cambia).
  Un dump sotto i 100 KB è considerato un errore. Se un passo fallisce, lo
  staff riceve una notifica nell'app (`scripts/notify-staff.sh`).
- **`scripts/verify-backup.sh`** (domenica alle 5): ripristina l'ultima copia
  in un database usa e getta (`jav_backup_check`), controlla che
  abbia le stesse tabelle del database vero e righe nelle tabelle principali,
  poi lo cancella; avvisa lo staff se fallisce o se l'ultima copia ha più di
  due giorni. Non tocca mai il database vero.
- **Pulizia Docker** (domenica alle 5:30): solo immagini senza nome e cache
  di build, **mai i volumi**. Ogni build lascia l'immagine vecchia (~1,4 GB),
  e senza pulizia il disco si riempie in poche settimane.

Nota il parametro `dev`, non `production`: su questo server è il file
`docker-compose.dev.yml` quello effettivamente in esecuzione (container
`jav-dev-*`) — `docker-compose.production.yml` esiste ma non è quello
usato qui, nonostante il nome. Su un server diverso, verifica prima quale
compose file è realmente attivo prima di copiare queste righe.

**Cosa NON è coperto**: i backup stanno **sullo stesso disco** del database
-- un server perso o cancellato si porta via anche loro -- e i file caricati
su MinIO (prove di pagamento, certificati medici, documenti delle pratiche,
foto) non sono salvati. Prima di dismettere o
ricreare il server, **copia fuori `./backups/` e il `.env`** (vedi §5).

**Attenzione**: `scripts/backup.sh` fa `source .env` per leggere le
credenziali Postgres — se un valore in `.env` contiene uno spazio e non è tra
virgolette (es. `NOME=Judo Club` invece di `NOME="Judo Club"`), bash
interpreta la seconda parola come un comando da eseguire e l'intero script si
interrompe con un errore criptico ("Club: command not found"), fallendo il
backup.
**Ogni valore in `.env` con uno spazio deve stare tra virgolette.**

## 5. Migrare i dati da un server esistente (non solo il codice)

Cosa serve, oltre al codice che sta su GitHub:

| Cosa | Dove sta sul vecchio server | Perché |
|---|---|---|
| Database | `./backups/jav_dev_*.sql.gz` (o un `scripts/backup.sh dev` fresco) | tutti i dati: utenti, atleti, quote, rete, contratti, ordini, wallet, impostazioni |
| `.env` | `/opt/webapps/jav/.env` o `./backups/env/env_*` | segreti: password del database e di MinIO, `JWT_SECRET_KEY` (firma dei login), SMTP. **Usa lo stesso `.env`**: con una chiave nuova tutti dovranno rifare il login, con password diverse il dump si carica lo stesso ma l'app non si collega |
| File caricati | volume MinIO (`jav-media`, `jav-documents`) | foto, prove di pagamento, certificati, documenti delle pratiche: vedi `mc mirror` sotto |
| Sito Caddy | `/etc/caddy/sites/jav.caddy` | si ricopia da `infrastructure/caddy/jav.caddy`; il certificato Caddy lo richiede da solo (§4.6) |

Se il vecchio server è ancora raggiungibile, **non ripartire dal seed** — porta i
dati veri:

```bash
# Sul VECCHIO server:
cd /opt/webapps/jav
scripts/backup.sh dev
# produce ./backups/jav_dev_TIMESTAMP.sql.gz

# copia il file sul nuovo server, es:
scp ./backups/jav_dev_*.sql.gz nuovo-server:/opt/webapps/jav/backups/

# Sul NUOVO server, DOPO aver fatto girare `docker compose up -d` (serve postgres attivo):
cd /opt/webapps/jav
gunzip -c backups/jav_dev_TIMESTAMP.sql.gz | \
  docker compose -f docker-compose.dev.yml exec -T postgres psql -U jav jav
```

Questo restituisce SOLO i dati Postgres (utenti, rete, contratti, provvigioni,
ecc.). I file binari stanno su MinIO (foto profilo/prodotto/atleta nel
bucket pubblico `jav-media`, documenti, prove di pagamento e certificati nel
bucket privato `jav-documents`, vedi `docs/security-model.md`) -- questi vanno
sincronizzati separatamente, non li copia `scripts/backup.sh` (che fa solo
`pg_dump`):
```bash
# Sul VECCHIO server (mc = MinIO client, https://min.io/docs/minio/linux/reference/minio-mc.html):
mc alias set old http://localhost:9000 <MINIO_ROOT_USER> <MINIO_ROOT_PASSWORD>
mc mirror old/jav-media ./minio-export/jav-media
mc mirror old/jav-documents ./minio-export/jav-documents
# copia ./minio-export sul nuovo server, poi sul NUOVO server:
mc alias set new http://localhost:9000 <MINIO_ROOT_USER> <MINIO_ROOT_PASSWORD>
mc mirror ./minio-export/jav-media new/jav-media
mc mirror ./minio-export/jav-documents new/jav-documents
```
Il bucket `jav-documents` è privato (nessuna bucket policy) -- assicurati che
`mc mirror` non ne aggiunga una per errore; verifica con `mc anonymous get
new/jav-documents` che risponda `none`.

**Se il vecchio server non c'è più** e hai solo una copia di `./backups/`: ricrea
il server (§3), clona il codice (§4.1), rimetti il `.env` salvato
(`./backups/env/env_<la più recente>` → `/opt/webapps/jav/.env`), avvia lo stack
(§4.3) e carica il dump più recente col comando `gunzip -c … | psql` qui sopra.
**Non** lanciare il seed (§4.4): i dati arrivano dal dump. Poi `crontab -e` come
in §4.8 e le verifiche della §15.3.

**Non usare `scripts/restore.sh`** per questo scenario — quello script è pensato
per ripristinare un backup nello **stesso** ambiente dopo un disastro (crea un
database `_restoring` separato per sicurezza). Per una migrazione a database
vuoto su un server nuovo, il comando diretto sopra è più semplice e corretto.

## 6. Struttura completa del database

La fonte di verità assoluta è **`docs/database-schema.sql`** in questa stessa
cartella — è un dump reale (`pg_dump --schema-only --no-owner --no-privileges`,
rigenerabile con `scripts/dump-schema.sh dev --from-migrations`) di un
database costruito **dalle migrazioni**, non una ricostruzione a memoria
(`--no-owner`/`--no-privileges` lo rendono portabile anche se il nuovo server
usa un utente Postgres diverso da `jav`). È il **modello della struttura senza
dati**: nessuna riga di nessuna tabella, quindi si può condividere e committare
senza esporre niente di un club.

**Stato attuale**: due migrazioni. `0001_schema_iniziale.py` (revision
`0001`) crea 85 tabelle con tipi esatti, vincoli, indici, foreign key e la
sequenza `shop_order_number_seq`. La storia precedente delle migrazioni è
stata sostituita da questa, generata dai modelli e verificata confrontando
colonna per colonna lo schema migrato con quello dei modelli (zero
differenze). `0002_piu_club.py` aggiunge la tabella `clubs` e `club_id` sulle
tabelle del club e sugli utenti (docs/club-portal.md, "Più club"): in tutto
**86 tabelle**, 87 `CREATE TABLE` nel dump contando `alembic_version`.
**Dopo ogni nuova migrazione, rilancia
`scripts/dump-schema.sh dev --from-migrations` e committa il diff.**

Se hai bisogno di verificare in un secondo che il file sia ancora allineato,
senza rileggerlo tutto:

```bash
# revision attesa dal codice (ultima migrazione nel repo)
ls apps/api/alembic/versions/*.py | tail -1
# revision realmente applicata al database in esecuzione
docker compose -f docker-compose.dev.yml exec -T postgres \
  psql -U jav -d jav -tAc "SELECT version_num FROM alembic_version;"
# tabelle nel dump vs tabelle nel database
grep -c '^CREATE TABLE' docs/database-schema.sql
docker compose -f docker-compose.dev.yml exec -T postgres \
  psql -U jav -d jav -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
```

I tre numeri devono coincidere. Se non coincidono, il dump è stale: rilancia
`scripts/dump-schema.sh` prima di fidarti di quel file per una ricostruzione.

**Non usare `git diff` come prova che il dump sia aggiornato**:
`pg_dump` 16.14 scrive in cima e in fondo al file un token casuale
(`\restrict …` / `\unrestrict …`) che cambia a **ogni** esecuzione, quindi un
dump rigenerato risulta sempre "modificato" anche quando lo schema è
identico. Conta quello che c'è *dentro* il diff, non il fatto che esista: se
le uniche due righe cambiate sono quelle, il file era già allineato e vale la
pena fare `git checkout docs/database-schema.sql` invece di committare
rumore.

La spiegazione **concettuale** (perché ogni tabella esiste, come si collegano,
diagramma ER) è in `docs/database-model.md` — leggila insieme allo schema SQL,
non al posto suo.

Il modo **corretto e canonico** per ricreare lo schema da zero non è applicare
`database-schema.sql` a mano: è lasciare che Alembic lo faccia, che è esattamente
quello che succede automaticamente al primo avvio del container `api` (vedi
4.3). Il file `.sql` serve come:
- riferimento per capire esattamente cosa esiste, senza dover leggere tutti i
  file `app/domains/*/models.py` uno per uno
- verifica: se un giorno lo schema reale e questo file divergono, è un segnale
  che qualcuno ha modificato il database a mano bypassando Alembic — da
  correggere subito
- materiale di partenza se, in un contesto di emergenza estremo, Alembic stesso
  non fosse disponibile e servisse ricreare lo schema con `psql -f
  docs/database-schema.sql` direttamente (funziona, essendo SQL puro; poi
  `alembic stamp head`, o Alembic proverebbe a ricreare tutto)

Elenco delle tabelle per dominio (dettagli in `docs/database-model.md`):

```
Identità/tenancy:  organizations, users, roles, permissions, role_permissions,
                    user_roles, sessions, audit_log, password_reset_tokens,
                    email_verification_tokens, otp_codes, spend_pins
Rete commerciale:  agent_profiles, network_nodes, network_edges,
                    network_closure, network_assignment_history,
                    network_snapshots, network_snapshot_nodes
Referral:          promoter_codes, referral_events, referral_sessions,
                    customer_attributions, attribution_corrections
"Invita un amico": friend_referral_codes, friend_referrals,
                    friend_referral_reward_claims
Catalogo/clienti:  products, product_versions, customers, customer_profiles,
                    companies, addresses, product_requests,
                    product_request_messages
Contratti:         contracts, contract_requests (la pratica), contract_status_history,
                    contract_events, contract_attributions,
                    contract_commission_plans, contract_instalments,
                    documents
Provvigioni:       ranks, agent_rank_history, commission_plan_versions,
                    commission_rule_versions, commission_calculations,
                    commission_calculation_steps, commission_movements,
                    commission_adjustments, commission_offsets,
                    commission_reversals, domain_outbox
Supporto/notifiche: tickets, ticket_messages, notifications,
                    documentation_posts
Wallet ("JavCash"): wallets, wallet_transactions
Ordini e Shop:     orders, carts, cart_items, shop_categories,
                    shop_category_products, jav_market_settings,
                    jav_market_producers, jav_market_products,
                    jav_market_variants, jav_market_orders,
                    jav_market_order_items
Club:              club_plans, club_athletes, club_fees,
                    club_payment_proofs, club_payment_proof_fees,
                    club_medical_certificates, club_belt_grades,
                    club_courses, club_course_slots, club_course_athletes,
                    club_attendances, club_competitions,
                    club_competition_entries, club_reminders_sent
```

### 6.1 Dati di riferimento: ciò che lo schema NON contiene

Uno schema vuoto non è un'applicazione funzionante. Dopo `alembic upgrade
head` ci sono 85 tabelle e nessuna riga: nessun permesso, nessun ruolo,
nessun grado, nessun piano provvigioni, nessun utente con cui fare login. Le righe indispensabili sono queste quattro famiglie, e nessuna
delle quattro sta in `docs/database-schema.sql` (che è `--schema-only` di
proposito: i dati veri sono in `scripts/backup.sh`, gitignorato).

| Tabella | Cosa ci deve stare | Da dove arriva |
|---|---|---|
| `permissions` | un codice per permesso (`contracts.approve`, `club.family`, …), **globale**, senza `organization_id` | costante `PERMISSIONS` in `app/domains/rbac/models.py` |
| `roles` + `role_permissions` | i ruoli di sistema dell'organizzazione (incluso `INSTRUCTOR`) e cosa può fare ciascuno | `SYSTEM_ROLES` + `DEFAULT_ROLE_PERMISSIONS`, stesso file |
| `ranks` | la scala dei gradi della rete (S1…MD5) con i gettoni per grado | `app/seed/ranks.py` — **valori placeholder**, vedi `docs/open-questions.md` #1 |
| `commission_plan_versions` | almeno una versione `ACTIVE`: senza, il motore provvigioni non ha su cosa appoggiarsi | idem |

Più, ovviamente, **un utente con cui entrare la prima volta**.

Tutte e cinque le cose le crea un solo comando, `python -m app.seed.bootstrap`
(§4.4 scenario C) — che a differenza del seed demo non inventa nessun
promoter, cliente, prodotto o contratto. È idempotente: rilanciarlo aggiunge
solo ciò che manca, riallinea permessi e ruoli al codice (è il modo di dare
a un'installazione esistente un permesso nuovo), non duplica e **non
sovrascrive la password di un amministratore già esistente**.

Verifica rapida che il minimo indispensabile ci sia:

```bash
docker compose -f docker-compose.dev.yml exec -T postgres psql -U jav -d jav -tAc "
  SELECT
    (SELECT count(*) FROM permissions)                                    AS permessi,
    (SELECT count(*) FROM roles)                                          AS ruoli,
    (SELECT count(*) FROM role_permissions)                               AS concessioni,
    (SELECT count(*) FROM ranks)                                          AS gradi,
    (SELECT count(*) FROM commission_plan_versions WHERE status='ACTIVE') AS piani_attivi,
    (SELECT count(*) FROM users)                                          AS utenti;"
```

`gradi` deve essere 12, `piani_attivi` almeno 1, e nessuno degli altri 0.

## 7. Mappa del codice (per orientarsi velocemente)

```
apps/api/app/
  core/            config, connessione DB, sicurezza (hashing, JWT),
                   dipendenze FastAPI, storage.py (upload MinIO/S3),
                   email.py (SMTP, fallback a log se non configurato),
                   rate_limit.py (limite per-IP via Redis su endpoint auth)
  domains/<nome>/  un dominio di business per cartella: models.py, schemas.py,
                   service.py, router.py (+ calculators/policies per commissions)
                   -- include "support" (ticket cliente/promoter <-> staff),
                   "club" (atleti, quote, prove, certificati, cinture, corsi,
                   presenze, gare, ranking, job; vedi docs/club-portal.md),
                   "jav_market" (lo Shop), "carts", "orders", "accounting"
  domains/catalog/pricing.py
                   L'UNICO posto dove si decide l'IVA e il prezzo di un
                   contratto (privato = niente IVA, azienda = prezzo + IVA),
                   quali clienti possono comprare quale prodotto, e da dove
                   nasce un accredito JavCash. Ogni importo del sistema
                   passa di qui ed è calcolato lato server: nessun prezzo
                   arriva mai dal browser. Vedi business-rules.md#vat
  core/email.py    send_html_email() (solleva eccezione: usalo SOLO per reset
                   password e OTP, dove l'email È il risultato) e
                   send_html_email_best_effort() (non solleva mai: per ogni
                   notifica inviata DOPO un commit -- vedi §8 #12)
  celery_app.py    app Celery -- STESSO codice dell'api, non duplicato (vedi
                   apps/worker/README.md e docs/adr/0001-modular-monolith.md);
                   beat: outbox, valutazione gradi, quote mensili, nuova
                   stagione, promemoria, chiusura iscrizioni gare
  seed/            dati demo (python -m app.seed) e bootstrap di un club
                   nuovo (python -m app.seed.bootstrap)
  main.py          entry point FastAPI, monta tutti i router

apps/dashboard/app/
  login/           pagina di login
  customer|promoter|admin/   le dashboard per ruolo (il cliente è il genitore:
                   la sua home è il portale famiglia del club)
  api/auth/        route handler BFF (login/logout/forgot-password/reset-password)
                   -- QUESTI, non FastAPI direttamente, sono ciò che il browser
                   chiama su /api/*
  api/public/      altre route pubbliche BFF (registrazione via referral,
                   risoluzione codice referral) -- nessuna sessione richiesta
  api/proxy/       proxy autenticato per chiamate client-side (TanStack Query),
                   inoltra anche upload multipart (foto) mantenendo il boundary
  proxy.ts         (era middleware.ts in Next <16) protegge le route autenticate

infrastructure/caddy/jav.caddy    il sito Caddy sull'host: HTTPS, header di
                                  sicurezza, proxy verso 127.0.0.1:8081
infrastructure/nginx/nginx.conf   router interno, solo HTTP: /backend/ -> FastAPI diretto
                                  (proxy_pass STATICO, vedi §8 #11),
                                  /media/ -> MinIO (foto pubbliche, vedi §6),
                                  tutto il resto -> dashboard (BFF, proxy_pass
                                  con variabile + resolver per rebuild senza
                                  downtime)
docker-compose.dev.yml            topologia completa (8 servizi)
scripts/                          deploy, backup (+ verify-backup, notify-staff), restore,
                                  health-check, migrate, rollback, dump-schema
```

Altri punti utili:

- `apps/api/app/domains/carts/` — il carrello, uno per (cliente, negozio).
  Non conosce i prezzi: li chiede al negozio (registro `SHOPS` in
  `service.py`).
- `apps/api/app/domains/marketplaces/` — regole comuni dello Shop
  (`rules.py`), la sequenza dei numeri d'ordine (`models.py`) e la vetrina a
  pagine (`paging.py`).
- `apps/api/alembic/versions/0001_schema_iniziale.py` — lo schema iniziale;
  poi `0002_piu_club.py` … `0006_sito_pubblico.py`. La prossima è `0007_…`.

## 8. Problemi noti già risolti (leggi PRIMA di fare debug da zero)

Questi bug sono stati scoperti e corretti eseguendo per davvero
`docker compose up --build` su questo stesso server. Se ricreando lo stack su un
nuovo server incontri sintomi simili, **il fix è già nel codice** — molto
probabilmente il problema è un altro. Documentati per intero in
`docs/implementation-progress.md`; riassunto:

1. **Build del dashboard fallisce su `groupadd`**: `node:22-slim` ha già un
   utente `node` a uid/gid 1000 — il Dockerfile ora lo riusa invece di crearne uno.
2. **`pnpm install` fallisce con `ERR_PNPM_IGNORED_BUILDS`**: corepack scaricava
   pnpm `latest` (11.x), più restrittivo sugli script nativi. Il `packageManager`
   è pinnato in `package.json` alla versione con cui è stato generato il lockfile.
3. **Build fallisce su `apps/dashboard/public` non trovato**: creata la cartella
   (vuota, con `.gitkeep`).
4. **`celery-beat` va in crash loop**: cercava di scrivere il file di schedule in
   `/app` (di proprietà di root). Ora scrive in `/tmp`.
5. **`celery-worker`/`celery-beat` risultano "unhealthy"**: ereditavano
   l'healthcheck HTTP dell'immagine api, inutile per un processo senza server
   HTTP. Sostituito con `celery inspect ping` (worker) e disabilitato (beat).
6. **Il dashboard risulta "unhealthy" anche se funziona**: il server standalone
   di Next si legava all'IP di interfaccia del container invece che al wildcard.
   Risolto con `HOSTNAME=0.0.0.0`.
7. **(Il più insidioso) Login "funziona" ma nessuna pagina protetta si apre**:
   nginx instradava `/api/` direttamente a FastAPI, intercettando anche le route
   BFF del dashboard (`/api/auth/login`, `/api/proxy/*`) che vivono sulla stessa
   porta 80. Risolto spostando l'accesso diretto al backend su `/backend/`,
   lasciando `/api/*` esclusivamente al dashboard.
8. **Login "non fa nulla" su un sito servito in HTTP puro**: il cookie di
   sessione è marcato `Secure`, e i browser reali (non `curl`) lo scartano
   silenziosamente se la pagina non è servita su HTTPS. Non è un bug da
   correggere abbassando il livello di sicurezza (rimuovere `Secure` esporrebbe
   i token in chiaro) — la correzione corretta è attivare HTTPS, vedi sezione
   4.6. Sintomo tipico: il form di login sembra caricare per un paio di secondi
   e poi resta sulla pagina di login, senza errori visibili nella UI (l'errore
   compare solo nella console del browser: *"Cookie ... rifiutato in quanto un
   cookie non-HTTPS non può essere impostato come 'secure'"*).
9. *(Voce tolta: riguardava una funzione che non esiste più. Il numero resta perché altri punti di questa guida citano i numeri successivi.)*
10. **`nginx -s reload` non basta dopo aver MODIFICATO `nginx.conf`**:
    su questo server un semplice reload non ha ripreso il file bind-mountato
    aggiornato (89 righe attese, 73 lette) finché non si è fatto
    `docker compose up -d nginx --force-recreate` (o `restart nginx`). Se dopo
    un reload `nginx -t` dice "syntax ok" ma il comportamento non cambia,
    ricrea il container prima di sospettare altro.
11. **`/backend/*` risponde 500 "invalid URL prefix in http://" su OGNI
    richiesta**: succede se in `location /backend/` il `set $variabile` sta
    DOPO `rewrite ... break`: `break` ferma tutto il modulo rewrite, `set`
    compreso, e `proxy_pass http://$variabile` resta vuoto. Il `set` va
    PRIMA del `rewrite` (com'è oggi in `nginx.conf`). Una volta `/backend/`
    aveva un target statico (`proxy_pass http://api:8000/;`) per evitare
    questo errore, ma così, dopo ogni deploy che ricrea `api` con un IP
    nuovo, `/backend/*` rispondeva **502** finché non si riavviava nginx. E
    `/backend/api/public-site/*` lo usa il calendario degli eventi nell'area
    di atleti e famiglie (17/10/2026: «Não consigo carregar os eventos»).
    Verifica dopo un deploy:
    `curl -s -o /dev/null -w '%{http_code}' https://<dominio>/backend/health` → 200.
12. **Upload foto (customer/promoter/product) fallisce con
    `SignatureDoesNotMatch` su OGNI richiesta a MinIO**: due cause distinte,
    entrambe reali su questo server, controllale entrambe:
    - `S3_ACCESS_KEY`/`S3_SECRET_KEY` in `.env` NON erano identiche a
      `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` (stessa lunghezza per
      coincidenza, valori diversi — probabilmente generate separatamente in
      una sessione precedente, mai avendo mai avuto un consumatore reale
      finché non è stato scritto `core/storage.py`). Devono essere
      **letteralmente la stessa stringa**.
    - `MINIO_REGION` non era impostata sul container MinIO (default
      `us-east-1`), mentre il client boto3 firma le richieste per
      `S3_REGION=eu-central-1` — il mismatch di regione rompe la firma SigV4
      indipendentemente dalle credenziali. Imposta `MINIO_REGION` uguale a
      `S3_REGION`.
13. **Foto caricata non si vede nel browser (404 o connessione rifiutata)**:
    MinIO non è raggiungibile da internet (nessuna porta pubblicata per la
    9000 nel compose) — un browser non può MAI caricare
    `http://minio:9000/...` (hostname Docker interno, non risolve fuori dalla
    rete Docker). Le foto vanno sempre servite tramite
    `https://tuodominio/media/...`, che nginx inoltra internamente a MinIO
    (`location /media/` in `nginx.conf`) — se manca quel blocco, aggiungilo
    prima di sospettare un bug nell'upload.
14. ** Qualsiasi pulsante "Salva modifiche" risponde 405, in TUTTE
    le schermate (cliente, promoter, prodotto, punto di fornitura, ...),
    fin dal giorno in cui ciascuna di quelle funzionalità è stata costruita**:
    il proxy generico del BFF (`apps/dashboard/app/api/proxy/[...path]/route.ts`)
    implementava SOLO `GET` e `POST`, mai `PATCH` -- nessuno se n'era accorto
    perché ogni sessione precedente aveva verificato dal vivo altre parti delle
    stesse funzionalità (es. l'upload della foto, un POST) ma mai il vero
    pulsante di salvataggio, che è un PATCH. Fix: aggiunti handler reali
    `PATCH`/`PUT`/`DELETE` che condividono la stessa logica di inoltro del
    `POST` esistente (branch multipart-vs-JSON identico). Se un pulsante di
    salvataggio sembra non fare nulla, verifica prima con `curl -X PATCH
    https://tuodominio/api/proxy/<risorsa>` che il proxy risponda 200, non 405.
15. *(Voce tolta: riguardava una funzione che non esiste più. Il numero resta perché altri punti di questa guida citano i numeri successivi.)*
16. *(Voce tolta: riguardava una funzione che non esiste più. Il numero resta perché altri punti di questa guida citano i numeri successivi.)*

17. ** "Ricarica wallet" mostra "Si è verificato un errore" su
    una ricarica che in realtà È ANDATA A BUON FINE — e ricliccando il
    wallet viene ricaricato DUE VOLTE**: `wallets/service.py::credit_wallet`
    fa `db.commit()` e *poi* manda l'email di conferma. Quel blocco
    catturava solo `EmailNotConfiguredError`, cioè uno solo dei tanti modi
    in cui un server di posta reale fallisce. `send_html_email()` apre una
    connessione smtplib **bloccante con timeout di 10 secondi** verso un
    host esterno: un login rifiutato, un timeout, un problema DNS o TLS
    sfuggivano e diventavano un 500 su un'operazione già committata e già
    scritta nell'audit. L'amministratore vedeva l'errore, ricliccava, e --
    poiché la dashboard generava una `idempotency_key` nuova **a ogni
    clic** -- accreditava una seconda volta.
    Fix su entrambi i lati: `core/email.py::send_html_email_best_effort()`
    non solleva mai e ora è usato in **ogni** punto in cui una notifica
    parte DOPO un commit (ordini, ticket, inviti account, accrediti wallet,
    avvisi del club) -- ma deliberatamente **NON** per i
    link di reset password e gli OTP, dove l'email *è* il risultato e
    fallire rumorosamente è corretto. Lato dashboard, una sola chiave per
    ricarica, rigenerata solo dopo un successo, così riprovare è innocuo.
    Corretto nello stesso passaggio: `db.flush()` stava **fuori** dal
    recupero `IntegrityError` in tutti e quattro i percorsi di scrittura
    del wallet (era coperto solo `commit()`).
    Il test di regressione (`tests/test_wallet_topup_resilience.py`) rompe
    SMTP al confine vero, `smtplib.SMTP`, **non** a un nome di modulo: la
    prima versione del test faceva monkeypatch di `send_html_email` sul
    modulo sbagliato e **passava anche contro il codice bacato**. Verificato
    6 fallimenti su 6 prima del fix, 6 successi su 6 dopo. Se un giorno
    riscrivi quel test, rompi la socket, non il nome.

18. ** Un cliente clicca "Continua" in Attiva Contratto e riceve
    "Si è verificato un errore imprevisto"**: il promoter che lo aveva
    invitato era stato **disattivato** dopo la sua iscrizione.
    `create_contract()` rifiuta — giustamente — di attribuire un contratto a
    un agente non ACTIVE (un contratto che si attiva e non paga nessuno), ma `POST /contracts/mine`
    non catturava quel rifiuto, quindi una condizione di business che il
    sistema capisce benissimo usciva come eccezione non gestita → 500 →
    messaggio generico della dashboard, e il cliente senza nessuna via
    d'uscita. Tre clienti reali erano in questo stato.
    Fix: `network/service.py::resolve_nearest_active_agent` risale al primo
    sponsor ATTIVO sopra (decisione di business esplicita: risalire, non
    bloccare), la sostituzione finisce in `audit_log` come
    `contract.producer_substituted`, e i due endpoint self-service catturano
    comunque `InvalidProducerAgentError` come 400. Se davvero non esiste
    nessun attivo in tutta la catena, il cliente riceve una frase italiana
    azionabile invece di una stringa tecnica con un UUID dentro.
    **Lezione generale**: ogni eccezione di dominio sollevata da un service
    deve essere catturata da OGNI router che lo chiama. Qui `POST /contracts`
    (staff) la catturava e i due endpoint self-service no — e il percorso
    non coperto era proprio quello usato dai clienti.

19. **`docker compose up` si ferma con `pull access denied for minio/minio`**:
    l'immagine `minio/minio` non è più pubblicata su Docker Hub. Il compose
    usa `cgr.dev/chainguard/minio:latest` (stessa MinIO, ha `sh` e `mc` per
    l'healthcheck, entrypoint già `/usr/bin/minio`). Se anche quella
    sparisse, serve un'altra build di MinIO con `mc` dentro.

20. **Una migrazione generata con `--autogenerate` fallisce con
    `relation "…" does not exist`** su un database vuoto: autogenerate ordina
    le tabelle per dipendenza, ma con chiavi esterne cicliche (organizations
    ↔ users, ordini dello Shop ↔ atleti) nessun ordine funziona. La
    migrazione iniziale crea prima tutte le tabelle e poi tutte le chiavi
    esterne (`op.create_foreign_key`); fai lo stesso se una migrazione nuova
    aggiunge tabelle che si citano a vicenda.

Se un problema NON è in questa lista, è nuovo — documentalo qui dopo averlo
risolto, per lo stesso motivo per cui questi lo sono.

## 9. Cosa NON aspettarsi che funzioni già

Elenco di cosa manca davvero oggi (dettaglio in
`docs/implementation-progress.md`):

- **Pagamenti con carta** -- non esistono, per scelta: si paga con bonifico
  (confermato dall'amministrazione, o dichiarato dal genitore con la prova
  per le quote del club) e con JavCash.
- **Motore AI/pgvector** (ricerca semantica, assistente interno) --
  esiste solo come documento di design, `docs/ai-architecture.md`, nessun
  codice.
- **CI/CD** -- nessuna pipeline automatica (lint/test/build su push);
  test/ruff/mypy vanno lanciati a mano (vedi `CLAUDE.md` §2-3).
- **MFA** -- non applicato.
- **Scansione antivirus sugli upload** -- interfaccia pluggable presente,
  nessuno scanner reale collegato; i download restano comunque gated da
  permessi (vedi `security-model.md §Documents`).
- **Backup off-server** e backup dei file MinIO -- `scripts/backup.sh` copia
  solo il database, sullo stesso disco (vedi §4.8).

**Cosa invece ESISTE, per evitare di ricostruirlo per errore credendolo
mancante**:
- **Portale club** (backend): atleti, piani per età, quote automatiche,
  prove di pagamento, certificati, cinture, corsi e presenze, gare e
  risultati, Jav Ranking, medaglie, promemoria -- `docs/club-portal.md`.
- **Pagamento dei contratti** con bonifico in unica soluzione, 3 o 12 rate,
  rate confermate dall'amministrazione (`business-rules.md#contract-payment`).
- **Notifiche**, sia in-app (campanella) sia email brandizzate
  (`core/email_templates.py::render_email`) per OTP, cashback, ordini,
  reset password, ticket, avvisi del club.
- **Wallet interno "JavCash"**, cashback su prodotto e su contratto, sezione
  "Contabilità".
- **Upload documenti sensibili** (identità, codice fiscale, visura), prove di
  pagamento e certificati medici, nel bucket privato -- vedi
  `security-model.md §Documents`.
- **HTTPS** con Caddy (§4.6) e **backup giornaliero automatico** (§4.8).

## 10. Assunzioni di business ancora provvisorie

Le cifre del piano carriera/provvigionale (S1-S3, TL1-4, MD1-5, regola del 33%,
ecc.) sono **placeholder documentati**, non le regole reali del club — il
documento con il piano carriera reale non è mai stato fornito. Vedi
`docs/open-questions.md` per l'elenco esatto e dove intervenire quando il
documento reale sarà disponibile.

## 11. Installare per un nuovo club: cosa personalizzare

La procedura di installazione (sezioni 1-8) è identica per ogni club. Cambia
solo ciò che è scritto nel codice invece che nel database. Il modello
`Organization` ha già `name`/`legal_name`/`settings` per club (multi-club a
livello di schema), ma **logo, colori e nome dell'app sono unici per
installazione**, non per organizzazione.

**Prima di tutto — non cosmetico**:

- `apps/api/app/domains/network/collaboration_documents.py`: il contratto
  di collaborazione che un promoter accetta è un **modello** con segnaposto
  tra parentesi quadre (`[RAGIONE SOCIALE]`, `[SEDE LEGALE]`, `[CITTÀ]` del
  foro, …). Va compilato con i dati del club, fatto rivedere da un legale e
  la `version` cambiata, così chi aveva accettato una versione precedente
  riceve la nuova.
- `apps/api/app/domains/organizations/service.py`:
  `DEFAULT_ADMIN_NOTIFICATION_EMAIL = "admin@example.com"` è solo il
  segnaposto finché la segreteria non imposta la sua casella in
  Impostazioni: impostala subito, o gli avvisi dei ticket non arrivano a
  nessuno.

**Brand**:
- Email: `apps/api/app/core/email_templates.py` — `LOGO_URL` è il logo
  dell'app stessa (`{PUBLIC_APP_BASE_URL}/logo.png`), `BRAND_COLOR`, il
  testo del footer. Un'unica modifica cambia ogni email.
- Frontend: `apps/dashboard/public/logo.png`, `app/icon.png`,
  `app/apple-icon.png`, titolo in `app/layout.tsx`, nome PWA in
  `app/manifest.ts`, e i token di colore in `app/globals.css` (`@theme`):
  il redesign li centralizza lì.
- Il nome "Jav" compare in testi e oggetti delle email: `grep -rni "jav"
  apps/api/app apps/dashboard/app apps/dashboard/components`.

**Dominio**: `infrastructure/caddy/jav.caddy` (il nome del sito) e, nel
`.env`, `NEXT_PUBLIC_APP_URL` / `PUBLIC_APP_BASE_URL`.

**Dati demo**: `python -m app.seed` crea un'organizzazione demo con email
`@jav.demo` — solo per provare lo stack, mai per un club vero (vedi §4.7 per
toglierla). I nomi interni (`POSTGRES_DB=jav`, bucket `jav-*`) non li vede
nessuno: si possono lasciare.

## 12. Runbook: installare per un nuovo club, dall'inizio alla fine

L'*ordine* in cui fare tutto, scritto per essere eseguito da cima a fondo —
anche da un agente — senza dover decidere nulla per conto proprio. Ogni passo
ha una verifica: se la verifica non passa, il passo successivo non va fatto.

Serve, prima di cominciare: un server (§2/§3), un dominio con il DNS già
puntato **solo** all'IP del server, e dal club **nome e ragione sociale**,
un **logo**, l'**email del primo amministratore** e (per andare in
produzione, non per installare) IBAN, credenziali SMTP, piani e corsi.

### Passo 1 — Server e codice

```bash
apt-get update && apt-get install -y docker.io docker-compose-v2 git openssl caddy
systemctl enable --now docker
mkdir -p /opt/webapps && git clone https://github.com/raphaelcodeart/jav /opt/webapps/jav
cd /opt/webapps/jav
```

**Verifica**: `docker compose version` risponde 2.x; swap da 2 GB attivo (§3).

### Passo 2 — Personalizzazione, PRIMA di costruire le immagini

Le immagini Docker sono *cotte*: ogni modifica al sorgente fatta dopo la
build richiede una rebuild. Fai adesso quello che dice la §11: contratto di
collaborazione, logo e icone, colori, nome.

**Verifica**: il `grep` della §11 non mostra testi da cambiare davanti a un
utente.

### Passo 3 — `.env`

```bash
cp .env.example .env
openssl rand -hex 32   # JWT_SECRET_KEY
openssl rand -hex 24   # POSTGRES_PASSWORD
openssl rand -hex 24   # MINIO_ROOT_PASSWORD = S3_SECRET_KEY (stesso valore, §8 #12)
```

Nessuna impostazione è obbligatoria a livello di codice (hanno tutte un
default), il che è **pericoloso in produzione**: uno stack con
`JWT_SECRET_KEY` lasciato vuoto parte senza lamentarsi. Controlla a mano i
segreti, `NEXT_PUBLIC_APP_URL` e `PUBLIC_APP_BASE_URL` (il dominio vero, in
`https://`) e `ENABLE_API_DOCS=false`.

**Verifica**:

```bash
grep -E "^(JWT_SECRET_KEY|POSTGRES_PASSWORD|S3_SECRET_KEY|NEXT_PUBLIC_APP_URL|ENABLE_API_DOCS)=" .env
```

### Passo 4 — Stack su

```bash
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d
```

Il container `api` esegue `alembic upgrade head` da solo all'avvio, e crea i
due bucket MinIO: lo schema e lo storage non si toccano a mano.

**Verifica**: `docker compose -f docker-compose.dev.yml ps` — tutti `healthy`
(celery-beat e nginx non hanno healthcheck: basta `Up`). Se no, §8.

### Passo 5 — Il club e il primo amministratore

**Non** `python -m app.seed` (è la demo: venti promoter finti).

```bash
docker compose -f docker-compose.dev.yml exec api \
  python -m app.seed.bootstrap \
    --organization-name "Nome Club" \
    --legal-name "Nome Club A.S.D." \
    --admin-email "segreteria@club.it"
```

Salva subito `Organization ID` e la password stampata (una volta sola).

**Verifica**: la query di §6.1 — 12 gradi, almeno un piano provvigioni
attivo, un solo utente.

### Passo 6 — Dominio e HTTPS

Segui la §4.6: `infrastructure/caddy/jav.caddy` in `/etc/caddy/sites/`,
con il dominio del club.

**Verifica**: `curl -sI https://<dominio>/login` → `200`, certificato
Let's Encrypt, e `http://` che redirige a `https://`.

### Passo 7 — Configurazione dall'interfaccia (non dal codice)

Entra come amministratore. Ti verrà chiesto di completare il profilo: è
normale, vedi §4.4 scenario C. Poi:

- **SMTP** (nel `.env`, poi rebuild/up di `api`, `celery-worker`,
  `celery-beat`) — finché non è configurato, nessuna email parte: niente
  reset password, niente avvisi di quote e certificati.
- **Impostazioni organizzazione**: IBAN e intestatario (li vedono i genitori
  per pagare), istruzioni per il bonifico, email della segreteria.
- **Club** (§13): piani per fascia d'età, corsi e orari, istruttori, prime
  gare.
- **Shop** (§14): prodotti, taglie, spedizione.

**Verifica**: da una casella esterna, prova un "password dimenticata" e
controlla che l'email arrivi davvero.

### Passo 8 — Backup

Le righe di crontab della §4.8. Sono l'unica cosa di questo runbook che, se
dimenticata, non dà nessun errore immediato: i backup semplicemente non
esistono il giorno in cui servono.

**Verifica**: `crontab -l` mostra le righe, e un `./scripts/backup.sh dev`
eseguito a mano produce un file in `./backups/`.

### Cosa un club nuovo NON eredita

- **La scala dei gradi e i gettoni** (`app/seed/ranks.py`) sono
  **placeholder** — vedi `docs/open-questions.md` #1. Vanno rivisti prima di
  pagare una sola provvigione, se il club usa la rete promoter.
- **Piani, corsi, gare, prodotti**: si creano dall'interfaccia.
- **Le regole del club** (punti del ranking, mesi fatturati, età al 1°
  settembre) sono valori di partenza: vedi `docs/open-questions.md` #13.

## 13. Configurare il club

La piattaforma ospita più club (docs/club-portal.md, "Più club"). Un club
nuovo **non è un'installazione nuova**: lo crea il superadmin dall'area
amministrazione, sezione **Club** → **Nuovo club** (nome, indirizzo per le
famiglie, email della segreteria, IBAN delle quote). La segreteria riceve
l'email per scegliersi la password; **senza SMTP configurato l'email non
parte** e il link di primo accesso compare a chi crea il club, che lo
consegna a mano. Anche la registrazione delle famiglie chiede di confermare
l'email: per un club in produzione l'SMTP va configurato.

Dopo un aggiornamento che porta ruoli o permessi nuovi (come `SECRETARY`,
`clubs.manage`, `clubs.enter` della migrazione 0002) va rilanciato il
bootstrap con il nome dell'organizzazione esistente: aggiunge solo ciò che
manca.

Il resto dall'interfaccia, area del club (la segreteria ci arriva dal login,
il superadmin con **Entra**); permesso `club.manage`:

1. **Piani**: uno per fascia d'età (es. 4–7, 8–13, 14+, adulti), con quota
   mensile, quota d'iscrizione annuale, giorno di scadenza e mesi fatturati
   (default settembre–giugno). Il piano di un atleta lo sceglie il sistema
   dall'età al 1° settembre.
2. **Istruttori**: li aggiunge la segreteria da **Impostazioni → Staff**
   (ruolo `INSTRUCTOR`, legati al club): vedono i propri corsi, segnano le
   presenze e assegnano le cinture.
3. **Corsi**: nome, fascia, istruttore e slot settimanali; gli atleti si
   iscrivono dal portale famiglia o li iscrive la segreteria.
4. **Gare**: data, luogo, livello (club/regionale/nazionale/internazionale),
   scadenza iscrizioni, quota, età, se serve il certificato agonistico. A
   gara finita la segreteria inserisce i piazzamenti: il Jav Ranking si
   aggiorna da solo.

I lavori automatici (Celery beat, `apps/api/app/celery_app.py`): quote
mensili il 1° del mese alle 03:00, nuova stagione il 1° settembre alle 03:30,
promemoria ogni giorno alle 08:00, chiusura iscrizioni alle gare ogni giorno
alle 01:00. Sono idempotenti; la segreteria può lanciare a mano la
generazione delle quote di un mese (`POST /club/admin/jobs/generate-monthly-fees`).

**Verifica**: un genitore di prova si registra dal link del club
(`/c/<slug>`) e registra un figlio → compaiono iscrizione e quota del mese;
carica una foto come prova → le quote risultano pagate e la segreteria vede
la prova in "Prove caricate". La segreteria di un altro club non vede né
l'atleta né la prova.

## 14. Lo Shop

Un solo negozio, `jav_market` («Fai la Spesa con Jav»), con catalogo scritto
dall'amministratore (permesso `shop.manage`): prodotti, varianti (taglie),
aziende produttrici, spedizione fissa, ordine minimo e soglia di spedizione
gratuita (Impostazioni del negozio). Nasce spento: si accende dal suo pannello.
Si paga con bonifico (confermato dall'amministrazione) e JavCash; un ordine
può indicare per quale atleta è. Regole: `business-rules.md#jav-market`.

## 15. Reinstallare tutto in autonomia (per un agente)

Questa sezione è scritta perché un agente — Claude Code o chi per lui — possa
ricostruire l'installazione su un server nuovo **senza fare domande**, e possa
verificare da solo di averla fatta giusta. Ogni passo ha un comando e un
risultato atteso: se il risultato non torna, ci si ferma lì invece di andare
avanti e scoprirlo tre passi dopo.

Le istruzioni lunghe stanno nelle sezioni sopra (§4 per un doppione di questo
sistema, §12 per un nuovo club). Qui c'è la sequenza minima e come
controllarla.

### 15.1 Cosa serve prima di cominciare

- Ubuntu con `docker.io docker-compose-v2 git openssl caddy postgresql-client`;
- accesso SSH come root (e una deploy key, se il repository è privato);
- un dominio che punta **solo** all'IP del server, se serve HTTPS;
- **niente altro**: nessuna credenziale di terze parti è necessaria per
  arrivare a un'applicazione funzionante. L'SMTP si configura dopo, ed è
  facoltativo (senza, le email finiscono nel log dell'api).
- 2 GB di swap (§3) e i lavori pianificati di §4.8.

### 15.2 La sequenza

```bash
git clone https://github.com/raphaelcodeart/jav /opt/webapps/jav
cd /opt/webapps/jav
cp .env.example .env            # poi genera i segreti: vedi §4.2
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d
```

Il container `api` esegue `alembic upgrade head` **da solo** all'avvio e
costruisce l'intero schema. Non serve caricare `docs/database-schema.sql`: è
un artefatto di documentazione e di confronto, non un metodo di
installazione. Se lo si carica a mano con `psql -f`, poi bisogna fare
`alembic stamp head`, altrimenti Alembic proverà a ricreare tutto.

Poi i dati minimi, che lo schema **non** contiene (organizzazione, permessi,
ruoli, gradi, piano provvigioni, primo amministratore):

```bash
docker compose -f docker-compose.dev.yml exec api python -m app.seed.bootstrap
```

### 15.3 Come verificare, in ordine

```bash
# 1. Tutti i servizi sani
docker compose -f docker-compose.dev.yml ps
./scripts/health-check.sh              # atteso: "All health checks passed."

# 2. Lo schema è quello giusto
docker compose -f docker-compose.dev.yml exec -T postgres \
  psql -U jav -d jav -tc "SELECT version_num FROM alembic_version;"
# atteso: la revision dell'ultima migrazione (oggi 0030,
#         0030_social_tiktok_e_biografia.py: `ls apps/api/alembic/versions | sort | tail -1`)

docker compose -f docker-compose.dev.yml exec -T postgres \
  psql -U jav -d jav -tc \
  "SELECT count(*) FROM information_schema.tables
    WHERE table_schema='public' AND table_type='BASE TABLE';"
# atteso: lo stesso numero di CREATE TABLE in docs/database-schema.sql
#         (oggi 132, alembic_version compresa: `grep -c "^CREATE TABLE"
#         docs/database-schema.sql`) -- se non torna, lo schema e il
#         codice sono fuori sincrono

# 3. L'applicazione risponde. Attenzione: solo nginx espone una porta sull'host
#    (127.0.0.1:8081, dietro Caddy), la dashboard no -- `curl localhost:3000`
#    da' sempre 000 e non vuol dire che sia rotta. Dall'interno della rete Docker:
docker compose -f docker-compose.dev.yml exec -T api python -c \
  "import urllib.request; print(urllib.request.urlopen('http://dashboard:3000/login').status)"
# atteso: 200

# ...oppure dall'esterno, una volta che dominio e certificato ci sono:
curl -s -o /dev/null -w "%{http_code}\n" https://IL-TUO-DOMINIO/login   # 200

# 4. L'accesso diretto all'API (/backend/) risponde: il calendario degli
#    eventi dell'area lo usa dal browser. Rifallo dopo ogni deploy che
#    ricrea `api` (§8 #11).
curl -s -o /dev/null -w "%{http_code}\n" https://IL-TUO-DOMINIO/backend/health   # 200
curl -s -o /dev/null -w "%{http_code}\n" "https://IL-TUO-DOMINIO/backend/api/public-site/events?from=2026-01-01&to=2026-12-31"   # 200

# 5. Le foto si aprono e si ricomprimono (Pillow nell'immagine api)
docker compose -f docker-compose.dev.yml exec -T api python -c \
  "import PIL.features as f; print(f.check('jpg'), f.check('webp'))"   # True True
```

Per entrare la prima volta in un account esistente (una segreteria importata,
il super admin) senza email configurata: `./scripts/set-password.sh EMAIL`
dal terminale del server (chiede la password due volte, non la mostra), o dal
super admin il bottone **🔑 Link di accesso** accanto allo staff di un club.

Un confronto più severo, che dice **cosa** è diverso e non solo quanto:

```bash
# Ricostruisce uno schema vuoto dalle migrazioni e lo confronta con
# l'artefatto committato. Nessuna riga in uscita = allineati.
./scripts/dump-schema.sh dev --from-migrations
git diff docs/database-schema.sql
```

Due righe cambiano **sempre**, a ogni esecuzione, e non vogliono dire niente:
`\restrict` e `\unrestrict` portano un token casuale che `pg_dump` genera da
capo ogni volta. Se il diff contiene solo quelle, schema e migrazioni sono
allineati.

### 15.4 Errori che si fanno e come riconoscerli

| Sintomo | Causa quasi certa |
|---|---|
| Il codice cambia ma il sito no | Le immagini sono cotte: serve `build`, non `restart` (CLAUDE.md §1) |
| `password authentication failed for user "jav"` da riga di comando | Stai parlando con un Postgres diverso da quello del container: usa la rete Docker o l'IP del container (§2 di CLAUDE.md) |
| I test cancellano dati veri | `TEST_DATABASE_URL` punta a `jav` invece che a `jav_test` |
| Un vincolo che «non esiste» in una migrazione | Il naming convention raddoppia il prefisso: in `op.drop_constraint` va il nome **nudo** (`quantity_positive`, non `ck_x_quantity_positive`) |
| Lo Shop non compare al cliente | Nasce spento, ed è voluto: si accende dal suo pannello |
| `relation "…" does not exist` applicando una migrazione nuova | Chiavi esterne cicliche: creale dopo le tabelle (§8 #20) |
| Il certificato di un dominio non arriva | Il DNS ha un secondo record (redirect o parcheggio del registrar) oltre all'IP del server |
| Celery riparte con il codice vecchio | `celery-worker` e `celery-beat` vogliono `--force-recreate` |
| Nell'area «Não consigo carregar os eventos», `/backend/*` 502 | nginx con un target statico verso un IP vecchio di `api`: la `location /backend/` deve avere `set` + `rewrite` + `proxy_pass` con variabile (§8 #11) |
| Una foto viene rifiutata («non è un'immagine leggibile») | Il file è rotto o non è un'immagine: il server la apre con Pillow prima di salvarla (`core/storage.py::optimize_image`) |
| Il server ha poca RAM libera | Il container `stt` è stato acceso a mano (`--profile voice`): fermalo, il microfono è nascosto |
| `/customer` dà «Qualcosa è andato storto» | Un accesso solo atleta (o di altro ruolo) è arrivato sull'area famiglia: oggi viene rimandato a `/area`; se si ripete, controlla i ruoli nel token |

### 15.5 Cosa l'installazione nuova non eredita

Lo schema porta la **struttura**, non le scelte commerciali. Dopo
l'installazione sono tutti a zero o al default, e vanno decisi:

- piani, corsi, gare del club;
- prezzi, prodotti, categorie dello Shop e piano provvigioni;
- aliquota IVA, percentuali JavCash;
- credenziali SMTP, IBAN;
- personalizzazione (nome, logo, colori, contratto di collaborazione): vedi
  §11 e §12, Passo 2, **prima** di costruire le immagini.

E soprattutto: le regole di business che questo progetto ha scelto stanno in
`docs/business-rules.md` e `docs/club-portal.md`, non nel codice sparse. Chi
installa per un nuovo club le legge lì e decide quali tenere.
