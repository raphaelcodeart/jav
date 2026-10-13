# Guida alla Migrazione del Server / Ricostruzione da Zero

Questo documento serve a un solo scopo: permettere a chiunque (umano o AI) di
ricreare **esattamente** questa piattaforma su un nuovo server, partendo da zero,
senza dover indovinare nulla. Se stai leggendo questo perché il server attuale è
stato perso, compromesso, o semplicemente vuoi migrare altrove — segui questa
guida nell'ordine in cui è scritta. Se invece l'obiettivo è usare questo stesso
codice per far partire **un'altra rete/azienda** (non un doppione di Jav
) su un server nuovo, la procedura di installazione è la stessa (sezioni
1-8), più la §11 alla fine che elenca cosa è specifico del brand Jav e
va cambiato prima di andare in produzione con un cliente diverso.

Non duplica `README.md` o `docs/architecture.md` — li presuppone. Qui ci sono solo
le informazioni operative specifiche per un trasloco/ricostruzione: cosa
installare, in che ordine, quali bug reali sono già stati trovati e corretti (per
non doverli riscoprire), e come verificare che tutto funzioni.

## 1. Cos'è questo progetto, in breve

Gestionale Jav: FastAPI (backend) + Next.js 16 (frontend/BFF) + PostgreSQL
16 + Redis + Celery + MinIO, orchestrato con Docker Compose, dietro nginx. Vedi
`docs/architecture.md` per il quadro completo, `docs/implementation-progress.md`
per cosa è realmente implementato e cosa no.

Repository: `https://github.com/raphaelcodeart/jav`, branch `main`.

## 2. Server di riferimento (quello su cui questo progetto gira oggi)

Utile per dimensionare un eventuale nuovo server in modo equivalente:

| | |
|---|---|
| Provider | Hetzner Cloud (datacenter nbg1 — Norimberga) |
| Hostname | `jav-4gb-nbg1-2` |
| OS | Ubuntu 26.04 LTS |
| CPU | 2 vCPU |
| RAM | 3.7 GiB + **2 GB di swap** (`/swapfile`, vedi §3) |
| Disco | 38 GB (al 2026-10-04: ~28 GB usati, di cui ~13 GB immagini Docker, 355 MB database, 378 MB file MinIO, 200 MB backup) |
| IP pubblico | vedi il pannello Hetzner del progetto — cambia se si ricrea il server |

Un nuovo server con specifiche pari o superiori (2 vCPU / 4 GB RAM / 40 GB disco
minimo) è sufficiente per l'intero stack in questa fase (dati demo, traffico
basso). Se il volume di contratti/agenti cresce di ordini di grandezza, rivedere
il dimensionamento di Postgres in particolare.

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
cd /opt   # o dove preferisci
git clone https://github.com/raphaelcodeart/jav jav
cd jav
```

Serve una chiave SSH autorizzata sul repo GitHub (deploy key o chiave
dell'account). Se non ce l'hai già configurata sul nuovo server:

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
  reale. **Stato attuale**: configurato con la casella `noreply@example.com`
  ospitata su Aruba (`SMTP_HOST=smtps.aruba.it`, porta 587, STARTTLS) — è
  l'endpoint standard di invio per caselle Aruba agganciate a un dominio i cui
  nameserver sono `arubadns.net`/`technorail.com`, verificato con un login SMTP
  reale prima di scriverlo in `.env`.

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

Verifica che tutti gli 8 container siano `healthy` (aspetta 30-60 secondi):

```bash
docker compose -f docker-compose.dev.yml ps
```

Se qualcosa non diventa `healthy`, guarda la sezione 6 ("Problemi noti già
risolti") prima di improvvisare un fix — è quasi certamente uno dei 6 bug già
scoperti e corretti in questo stesso processo la prima volta.

### 4.4 Popola i dati

**Scenario A — nuovo server, dati demo (nessuna migrazione dati reali):**
```bash
docker compose -f docker-compose.dev.yml exec api python -m app.seed
```
Salva l'`Organization ID` stampato in output — serve per fare login.

**Scenario B — stai migrando dati reali dal vecchio server:** vedi sezione 5
("Migrare i dati da un server esistente") invece di eseguire il seed.

**Scenario C — stai avviando un'AZIENDA NUOVA (né la demo, né un ripristino):**
non eseguire `python -m app.seed`. Quel comando crea venti promoter finti,
una cinquantina di clienti e i relativi contratti, ed è l'ultima cosa che
vuoi dentro il database di un cliente reale. Usa invece il bootstrap, che
crea **solo** ciò senza cui l'applicazione non parte (permessi, ruoli, gradi,
piano provvigioni) più un unico amministratore:

```bash
docker compose -f docker-compose.dev.yml exec api \
  python -m app.seed.bootstrap \
    --organization-name "Nome Azienda" \
    --legal-name "Nome Azienda S.r.l." \
    --admin-email "titolare@azienda.it"
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

Poi prosegui con la §12, che è la procedura completa per un cliente diverso
da Jav (rebranding compreso).

**Opzionale — arricchire la demo con più contenuti (Session 14):** il seed
base crea solo 20 agenti/6 livelli e una manciata di clienti. Per popolare
l'albero della rete vendita fino a 12 livelli con più rami (utile per demo
commerciali) e ~50 clienti/contratti in stati vari, esiste uno script
ADDITIVO separato che va eseguito DOPO il seed base, sulla stessa
organizzazione:
```bash
docker compose -f docker-compose.dev.yml exec api python -m app.seed.expand_demo
```
Vedi §4.7 sotto per come rimuovere tutto questo contenuto demo prima di
passare in produzione con clienti reali.

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

### 4.7 Rimuovere i dati demo prima della produzione (Session 14)

Sia il seed base (`python -m app.seed`) sia lo script additivo
`app.seed.expand_demo` (§4.4) creano contenuti chiaramente marcati come demo,
pensati per essere rimossi prima che clienti reali usino il sistema:

| Contenuto | Marcatore |
|---|---|
| Agenti creati da `expand_demo` | `promoter_codes.code` inizia per `DEMO-` |
| Clienti creati da `expand_demo` | `customers.email` termina per `@demo-expansion.jav` |
| Contratti creati da `expand_demo` | `contracts.notes` contiene `[DEMO-EXPANSION]` |
| Tutti gli utenti/agenti/clienti del seed base | password `DemoPass123!`, email `*@jav.demo` |

Query indicativa per rimuovere SOLO il contenuto aggiunto da `expand_demo`
(lascia intatto il seed base, se vuoi comunque tenere qualche account demo
per test interni):
```sql
-- Documenti dei contratti demo (rispetta i vincoli di chiave esterna --
-- prima i figli, poi i genitori)
DELETE FROM documents WHERE contract_id IN (
  SELECT id FROM contracts WHERE notes LIKE '%[DEMO-EXPANSION]%'
);
DELETE FROM commission_movements WHERE contract_id IN (
  SELECT id FROM contracts WHERE notes LIKE '%[DEMO-EXPANSION]%'
);
DELETE FROM contract_status_history WHERE contract_id IN (
  SELECT id FROM contracts WHERE notes LIKE '%[DEMO-EXPANSION]%'
);
DELETE FROM contracts WHERE notes LIKE '%[DEMO-EXPANSION]%';
DELETE FROM customers WHERE email LIKE '%@demo-expansion.jav';
DELETE FROM promoter_codes WHERE code LIKE 'DEMO-%';
DELETE FROM network_nodes WHERE agent_id IN (
  SELECT id FROM agent_profiles WHERE id IN (
    SELECT agent_id FROM promoter_codes WHERE code LIKE 'DEMO-%'
  )
);
DELETE FROM agent_profiles WHERE id NOT IN (SELECT agent_id FROM network_nodes);
```
Per ripartire completamente da zero prima della produzione (rimuovere ANCHE
il seed base), è più semplice e sicuro ricreare il database da capo (§4.3)
piuttosto che disfare selettivamente ogni riga -- questo stack non ha ancora
dati reali da preservare finché non lo si mette in produzione con clienti
veri.

Non dimenticare i file binari: i documenti/foto demo restano su MinIO anche
dopo aver cancellato le righe Postgres corrispondenti (le righe portano solo
la `storage_key`, il file resta nel bucket finché non lo elimini
esplicitamente con `mc rm` o svuotando il bucket).

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
  di build, **mai i volumi**. Ogni build lascia l'immagine vecchia (~1,4 GB):
  il 2026-10-02 il disco era arrivato al 97%.

Nota il parametro `dev`, non `production`: su questo server è il file
`docker-compose.dev.yml` quello effettivamente in esecuzione (container
`jav-dev-*`) — `docker-compose.production.yml` esiste ma non è quello
usato qui, nonostante il nome. Su un server diverso, verifica prima quale
compose file è realmente attivo prima di copiare queste righe.

**Cosa NON è coperto (scelta dell'utente, Session 89)**: i backup stanno
**sullo stesso disco** del database -- un server perso o cancellato si porta
via anche loro -- e i file caricati su MinIO (fatture dei riscatti, documenti
delle pratiche, foto: 378 MB) non sono salvati. Prima di dismettere o
ricreare il server, **copia fuori `./backups/` e il `.env`** (vedi §5).

**Bug reale trovato e corretto in questa sessione**: `scripts/backup.sh` fa
`source .env` per leggere le credenziali Postgres — se un valore in `.env`
contiene uno spazio e non è tra virgolette (es. `COMPANY_BANK_HOLDER=Jav
` invece di `COMPANY_BANK_HOLDER="Jav"`), bash lo interpreta
come un comando da eseguire e l'intero script si interrompe con un errore
criptico ("Energy: command not found"), fallendo silenziosamente il backup.
**Ogni valore in `.env` con uno spazio deve stare tra virgolette.**

## 5. Migrare i dati da un server esistente (non solo il codice)

Cosa serve, oltre al codice che sta su GitHub:

| Cosa | Dove sta sul vecchio server | Perché |
|---|---|---|
| Database | `./backups/jav_dev_*.sql.gz` (o un `scripts/backup.sh dev` fresco) | tutti i dati: utenti, rete, contratti, ordini, wallet, impostazioni dei negozi (anche le chiavi API di Vaitto e Symphonya, salvate nel database) |
| `.env` | `/opt/webapps/jav/.env` o `./backups/env/env_*` | segreti: password del database e di MinIO, `SECRET_KEY` (firma dei login), chiavi Stripe/SMTP. **Usa lo stesso `.env`**: con una `SECRET_KEY` nuova tutti dovranno rifare il login, con password diverse il dump si carica lo stesso ma l'app non si collega |
| File caricati | volume MinIO (`jav-media`, `jav-documents`) | foto, documenti delle pratiche, fatture: vedi `mc mirror` sotto |
| Certificati HTTPS | `./certbot/` | facoltativo: si possono richiedere da capo (§4.6) |

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
ecc.). Dalla Session 14 esistono anche file binari reali su MinIO (foto
profilo/prodotto nel bucket pubblico `jav-media`, documenti sensibili nel
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
rigenerabile con `scripts/dump-schema.sh`) di un database costruito **dalle
migrazioni**, non una ricostruzione a memoria (**rigenerato 2026-09-22 da un
database vuoto portato a `alembic upgrade head`; ultima rigenerazione
2026-10-04, revision `c4a9e2f71d58` / migrazione `0076_invoice_redemption_card_review`**;
`--no-owner`/`--no-privileges` lo rendono portabile anche se il nuovo server
usa un utente Postgres diverso da `jav`). È il **modello della struttura senza
dati**: nessuna riga di nessuna tabella, quindi si può condividere e committare
senza esporre niente di un cliente. Contiene tutte le **113 tabelle** con
tipi esatti, vincoli, indici, foreign key. **Dopo ogni nuova migrazione,
rilancia `scripts/dump-schema.sh` e committa il diff** — altrimenti questo
file torna a essere stale (è già successo più di una volta: era rimasto
indietro di interi domini prima di essere risincronizzato — in Session 33, e
di nuovo in Session 38, quando mancavano le tre tabelle del plugin prodotti
importati e tutte le colonne economiche dei contratti).

Se hai bisogno di verificare in un secondo che il file sia ancora allineato,
senza rileggerlo tutto:

```bash
# revision attesa dal codice (ultima migrazione nel repo)
ls apps/api/alembic/versions/*.py | tail -1   # __pycache__ ordina dopo, va escluso
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

**Non usare `git diff` come prova che il dump sia aggiornato** (Session 46):
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
  docs/database-schema.sql` direttamente (funziona, essendo SQL puro, ma poi non
  far girare `alembic upgrade head` sopra uno schema già creato così, o l'idempotenza
  delle migration passate va verificata a mano)

Elenco delle 71 tabelle per dominio (dettagli in `docs/database-model.md`):

```
Identità/tenancy:  organizations, users, roles, permissions, role_permissions,
                    user_roles, sessions, audit_log, password_reset_tokens,
                    email_verification_tokens, otp_codes (codici generici
                    a scopo -- verifica email, conferma OTP per spendere
                    crediti wallet al checkout, ecc.)
Rete commerciale:  agent_profiles (ha anche photo_url, approved_by_user_id/
                    approved_at/rejection_reason, is_blacklisted,
                    first_name/last_name -- display_name resta derivato),
                    network_nodes, network_edges, network_closure,
                    network_assignment_history, network_snapshots,
                    network_snapshot_nodes
Referral:          promoter_codes, referral_events, referral_sessions,
                    customer_attributions, attribution_corrections
Catalogo/clienti:  products (ha anche category: INTERNAL/DROPSHIPPING/
                    PARTNER), product_versions (ha anche
                    contract_duration_months, token per grado su
                    commissions.services.rank_evaluation,
                    credit_discount_percentage, cashback_enabled,
                    contract_cashback_percentage,
                    first_referrer_bonus_enabled/_cents),
                    customers (ha anche photo_url, pec), customer_profiles,
                    companies, addresses, supply_points (ha anche label)
Contratti:         contracts (ha anche activated_at/expires_at/iban, email
                    per-contratto separata dall'email di login, e da
                    Session 38: chi lo ha creato e con quale ruolo,
                    activated_by_promoter_id/first_referrer_agent_id,
                    lo snapshot economico netto/IVA/lordo congelato alla
                    firma, i campi di pagamento Stripe e la prova di
                    accettazione delle condizioni),
                    contract_status_history, contract_events,
                    contract_attributions, documents (documenti sensibili
                    del contratto -- bucket privato jav-documents),
                    contract_commission_plans (anteprima provvigioni
                    accettata, Session 50), contract_instalments (rate
                    del cliente e quote di provvigione rilasciate),
                    contract_requests (la pratica di attivazione: N POD
                    = N contratti con dati, indirizzo, documenti comuni e
                    pagamento unico, Sessions 52-53; ogni contratto ha
                    contract_request_id, e un documento appartiene a un
                    contratto OPPURE a una pratica),
                    contract_request_checkouts (ogni Checkout Stripe
                    aperto per una pratica, con i contratti e gli importi
                    congelati)
Supporto:          tickets, ticket_messages
Provvigioni:       ranks, agent_rank_history, commission_plan_versions,
                    commission_rule_versions, commission_calculations,
                    commission_calculation_steps, commission_movements,
                    commission_adjustments, commission_offsets,
                    commission_reversals
Notifiche:         notifications (in-app, popolate da approvazioni,
                    promozioni/retrocessioni di grado, cashback, ordini, ecc.)
Documentazione:    documentation_posts (news/materiale admin per clienti e
                    promoter, allegati sul bucket pubblico jav-media)
Wallet ("JavCash"): wallets (saldo interno per utente, indirizzo stile
                    crypto -- mostrato in dashboard come "JavCash", non EUR),
                    wallet_transactions (ledger globale ricariche/cashback,
                    trasferimenti P2P, storni, debiti d'acquisto)
Partner/cashback:  partners (anagrafica fornitori esterni), invoice_redemptions
                    (riscatto fattura partner in JavCash: upload, verifica
                    admin, pagamento del 5% con bonifico O carta, accredito)
Ordini Shop:       orders (acquisto prodotti DROPSHIPPING/PARTNER: sconto
                    crediti opzionale, "riscuoti subito cashback" 5%
                    opzionale, pagamento con bonifico O carta -- vedi
                    dominio `accounting`, nessuna tabella propria, che
                    unisce questa tabella e wallet_transactions in
                    un'unica vista di sola lettura per il cliente)
Prodotti importati ("Acquisti Jav", plugin Session 34 -- catalogo
                    PARALLELO, volutamente separato da products):
                    import_providers (credenziali API del fornitore, api_key
                    mascherata in risposta), imported_products (nessun campo
                    cashback: servono solo a SPENDERE JavCash, mai a
                    guadagnarne), imported_product_orders (specchio di
                    orders meno i campi cashback)
Shop Jav Partner (CJ Dropshipping, Session 60 -- secondo negozio importato,
                    collegato via API): cj_settings (chiave API mascherata,
                    token CJ, regole di prezzo, sandbox, invio automatico),
                    cj_products e cj_variants (catalogo importato, costo USD,
                    stock, prezzo calcolato), cj_orders (checkout come gli
                    altri negozi + indirizzo, spedizione, invio a CJ,
                    tracking)
"Invita un amico" (Session 39 -- rete a UN livello, staccata da quella
                    commerciale, nessuna provvigione):
                    friend_referral_codes (il link personale di chi ha un
                    login, distinto da promoter_codes che invece paga),
                    friend_referrals (la lista piatta "chi ho invitato"),
                    friend_referral_reward_claims (le richieste di omaggio --
                    una gift card da 25 euro ogni 5 invitati con contratto
                    attivo, ripetibile, consegnata a mano dallo staff)
Pagamenti:         stripe_webhook_events (idempotenza a livello di evento
                    Stripe: l'event.id viene registrato PRIMA di eseguire
                    qualsiasi handler, e il vincolo UNIQUE decide quale di
                    due consegne concorrenti procede)
Outbox:            domain_outbox
Alembic:           alembic_version (gestita automaticamente, non toccare a mano)
```

**Object storage (non nel database Postgres)**: due bucket MinIO/S3, entrambi
creati/gestiti dall'applicazione, mai a mano:
- `jav-documents` (`S3_BUCKET_DOCUMENTS`) — privato, nessuna policy
  pubblica, accesso solo via URL presigned a scadenza breve (vedi
  `security-model.md`). Ci vivono i documenti KYC dei contratti (dominio
  `documents`), le foto/PDF di riscatto fattura e le relative prove di
  pagamento (`invoice_redemptions`), e le prove di pagamento degli ordini
  Shop (`orders.payment_proof_storage_key`) -- ognuno con il proprio
  prefisso di chiave, stesso bucket, stesso modello di accesso.
- `jav-media` (`S3_BUCKET_MEDIA`) — pubblico in lettura (foto profilo
  cliente/promoter, foto prodotto), creato automaticamente con la sua policy
  di lettura anonima al primo avvio del container `api`
  (`app/core/storage.py::ensure_media_bucket()`, chiamata da un evento di
  startup FastAPI in `main.py`) -- non serve `mc mb` manuale. Le foto sono
  servite al browser tramite `https://tuodominio/media/...`
  (`infrastructure/nginx/nginx.conf`, proxy diretto a MinIO), MAI tramite
  l'host Docker interno `minio:9000`, che non è raggiungibile da fuori la rete
  Docker.

### 6.1 Dati di riferimento: ciò che lo schema NON contiene

Uno schema vuoto non è un'applicazione funzionante. Dopo `alembic upgrade
head` ci sono 63 tabelle e praticamente nessuna riga: tre migrazioni dati
(0011, 0012, 0013) inseriscono **qualche** codice in `permissions`, e basta.
Nessun ruolo, nessun grado, nessun piano provvigioni, nessun utente con cui
fare login. Le righe indispensabili sono queste quattro famiglie, e nessuna
delle quattro sta in `docs/database-schema.sql` (che è `--schema-only` di
proposito: i dati veri sono in `scripts/backup.sh`, gitignorato).

| Tabella | Cosa ci deve stare | Da dove arriva |
|---|---|---|
| `permissions` | un codice per permesso (`contracts.approve`, …), **globale**, senza `organization_id` | costante `PERMISSIONS` in `app/domains/rbac/models.py`; alcune migrazioni dati (0011, 0012, 0013) ne inseriscono già una parte con `ON CONFLICT DO NOTHING` |
| `roles` + `role_permissions` | i ruoli di sistema dell'organizzazione e cosa può fare ciascuno | `SYSTEM_ROLES` + `DEFAULT_ROLE_PERMISSIONS`, stesso file |
| `ranks` | la scala dei gradi della rete (S1…MD5) con i gettoni per grado | `app/seed/ranks.py` — **valori placeholder**, vedi `docs/open-questions.md` #1 |
| `commission_plan_versions` | almeno una versione `ACTIVE`: senza, il motore provvigioni non ha su cosa appoggiarsi | idem |

Più, ovviamente, **un utente con cui entrare la prima volta**.

Tutte e cinque le cose le crea un solo comando, `python -m app.seed.bootstrap`
(§4.4 scenario C) — che a differenza del seed demo non inventa nessun
promoter, cliente, prodotto o contratto. È idempotente: rilanciarlo aggiunge
solo ciò che manca, non duplica e **non sovrascrive la password di un
amministratore già esistente**.

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
                   "imported_products" (catalogo parallelo dropshipping, vedi
                   database-model.md §15), "cj_dropshipping" (Shop Jav
                   Partner via API CJ, §17 -- client.py è l'unica porta
                   verso CJ: token, limite 1 richiesta/secondo, errori) e "payments" (Stripe: creazione
                   sessioni di checkout + webhook, vedi §9)
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
                   apps/worker/README.md e docs/adr/0001-modular-monolith.md)
  seed/            dati demo (python -m app.seed)
  main.py          entry point FastAPI, monta tutti i router

apps/dashboard/app/
  login/           pagina di login
  customer|promoter|admin/   le tre dashboard per ruolo
  api/auth/        route handler BFF (login/logout/forgot-password/reset-password)
                   -- QUESTI, non FastAPI direttamente, sono ciò che il browser
                   chiama su /api/*
  api/public/      altre route pubbliche BFF (registrazione via referral,
                   risoluzione codice referral) -- nessuna sessione richiesta
  api/proxy/       proxy autenticato per chiamate client-side (TanStack Query),
                   inoltra anche upload multipart (foto) mantenendo il boundary
  proxy.ts         (era middleware.ts in Next <16) protegge le route autenticate

infrastructure/nginx/nginx.conf   reverse proxy: /backend/ -> FastAPI diretto
                                  (proxy_pass STATICO, vedi §8 #11),
                                  /media/ -> MinIO (foto pubbliche, vedi §6),
                                  tutto il resto -> dashboard (BFF, proxy_pass
                                  con variabile + resolver per rebuild senza
                                  downtime)
docker-compose.dev.yml            topologia completa (8 servizi)
scripts/                          deploy, backup (+ verify-backup, notify-staff), restore,
                                  health-check, migrate, rollback, dump-schema
```

**Aggiunti dopo la stesura di questa mappa** (Sessions 75-80):

- `apps/api/app/domains/carts/` — il carrello, uno per (cliente, negozio).
  Non conosce i prezzi: li chiede al negozio. Il registro `SHOPS` in
  `service.py` è l'unico punto da toccare per dare il carrello a un negozio
  in più.
- `apps/api/app/domains/jav_market/` — Marketplace 4, il negozio senza
  fornitore (§14.4).
- `apps/api/app/domains/kappa_market/` — Marketplace 5, «Market Kappa»:
  clone del 4 con tabelle sue, solo Kappa e Robe di Kappa (§14.5).
- `apps/api/app/domains/vaitto_market/` — Marketplace 6, «Marketplace
  VAITTO»: clone del 5 rifornito dal feed di Vaitto (`feed.py`, §14.6).
- `apps/api/app/domains/symphonya_market/` — «Shop Beauty»: clone di VAITTO
  rifornito dall'API di Symphonya (`feed.py`, §14.7). Session 89.
- `apps/api/app/domains/soleil_market/` — «Market 7»: clone di Symphonya
  rifornito dall'Excel del portale SoleilDrop (`feed.py`, §14.8). Session 90.
- `apps/api/app/domains/marketplaces/models.py` — la sequenza condivisa dei
  numeri d'ordine, l'unica cosa di schema che i negozi hanno in comune.
- `apps/api/app/domains/marketplaces/paging.py` — la vetrina del cliente a
  pagine, usata da tutti i negozi (Session 89).
- `apps/api/app/domains/invoice_redemptions/` — «Riscatta Cashback»: con la
  carta i JavCash arrivano alla conferma di Stripe e la fattura si controlla
  dopo (`review_status`, migrazione 0076, Session 89).
- `apps/dashboard/components/shop-cart.tsx`, `cart-checkout-modal.tsx`,
  `marketplace-checkout-bits.tsx` — carrello e checkout lato cliente; il
  checkout serve tutti i negozi cambiando solo il prefisso delle rotte.

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
9. **Dopo aver rigenerato `certbot/conf` (`rm -rf` + ricreato), nginx vede una
   cartella vuota anche se sull'host i file ci sono**: un bind mount Docker
   stabilito PRIMA che la cartella host venga cancellata e ricreata resta
   agganciato al vecchio inode (ormai orfano), non alla nuova directory. Un
   `nginx -s reload` non basta — serve ricreare il container
   (`docker compose up -d nginx --force-recreate`) perché il bind mount venga
   ristabilito contro il percorso host attuale.
10. **`nginx -s reload` non basta anche solo dopo aver MODIFICATO
    `nginx.conf`** (non solo dopo aver toccato `certbot/conf`, vedi punto 9):
    su questo server un semplice reload non ha ripreso il file bind-mountato
    aggiornato (89 righe attese, 73 lette) finché non si è fatto
    `docker compose up -d nginx --force-recreate` (o `restart nginx`). Se dopo
    un reload `nginx -t` dice "syntax ok" ma il comportamento non cambia,
    ricrea il container prima di sospettare altro.
11. **`/backend/*` risponde 500 "invalid URL prefix in http://" su OGNI
    richiesta**: `location /backend/ { rewrite ^/backend/(.*)$ /$1 break; set
    $api_upstream api:8000; proxy_pass http://$api_upstream; }` — combinare un
    `rewrite ... break` con una VARIABILE in `proxy_pass` innesca questo bug
    nginx reale (non solo teorico: riprodotto su questo server). Fix: per
    `/backend/` usa un `proxy_pass` STATICO senza variabile
    (`proxy_pass http://api:8000/;`, senza `rewrite`, con `/` finale sia sulla
    location che sul target — nginx allora fa da solo lo strip del prefisso,
    ma SOLO perché non c'è una variabile di mezzo). Con un target statico
    perdi la ri-risoluzione DNS automatica se il container `api` viene
    ricreato con un IP diverso mentre nginx resta su — accettabile per
    `/backend/` (accesso sviluppatore, non il traffico applicativo vero),
    NON accettabile per `location /` (il proxy verso `dashboard`), che infatti
    resta con la variabile + `resolver`.
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
14. **(Session 14) Qualsiasi pulsante "Salva modifiche" risponde 405, in TUTTE
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
15. **(Session 33) Il webhook Stripe risponde SEMPRE 404, un pagamento con
    carta va a buon fine su Stripe ma l'ordine resta bloccato su "in attesa
    di pagamento" per sempre**: l'endpoint webhook registrato su Stripe è
    `/api/payments/stripe/webhook/{organization_id}` -- ma `/api/*` in
    questo file è di competenza esclusiva del BFF del dashboard (vedi bug
    #7), non del backend FastAPI, che infatti espone quella stessa rotta
    (montata con `prefix="/api"` in `main.py`) senza che nginx la inoltri
    mai lì. Confermato nel log di accesso di nginx: ogni consegna webhook
    arriva con user agent `Stripe/1.0` e riceve 404, e Stripe segna
    l'evento come `pending_webhooks: 1` (mai consegnato con successo).
    **Nessun ordine pagato con carta è mai stato confermato automaticamente
    prima di questo fix** -- solo riconciliati a mano chiamando
    `mark_paid_via_stripe()` direttamente. Fix: aggiunto un blocco
    `location /api/payments/stripe/webhook/` DEDICATO in `nginx.conf`, più
    specifico (nginx sceglie il prefisso più lungo tra location semplici,
    quindi vince su `location /` indipendentemente dall'ordine di
    dichiarazione) che inoltra dritto ad `api:8000` con variabile +
    resolver (non target statico come `/backend/`, perché un webhook deve
    restare funzionante anche dopo che il container `api` viene ricreato
    con un IP diverso, non solo per un uso da sviluppatore). Dopo il fix,
    verifica con `curl -X POST https://tuodominio/api/payments/stripe/webhook/<org-id>`
    che risponda 400 (firma mancante attesa), mai 404.
16. **(Session 33, stesso giorno) Webhook risponde 500 invece di 200 anche
    con firma valida, un pagamento continua a non confermarsi anche DOPO il
    fix del bug #15**: `payments/service.py::handle_webhook_event` leggeva
    `session.get("metadata")` -- ma `session` (e anche `session.metadata`)
    è un `stripe.StripeObject`, non un `dict`: in questa versione dell'SDK
    Stripe `StripeObject` NON implementa `.get()` (lo fa apposta, solleva
    `AttributeError` e rimanda a `.to_dict()`/accesso per attributo). Ogni
    test esistente chiamava `mark_paid_via_stripe()` direttamente, saltando
    `construct_event()` e quindi non passava mai da un vero `StripeObject`
    -- il bug è arrivato in produzione due volte prima di essere scoperto
    da una segnalazione utente reale. Fix: `getattr(getattr(session,
    "metadata", None), "kind", "order")` invece di `.get()`. Aggiunto
    `tests/test_payments.py`, che firma davvero un payload con HMAC-SHA256
    (stesso schema di Stripe) e chiama `handle_webhook_event()` per
    intero, così un futuro uso scorretto di `.get()`/altri metodi dict su
    un oggetto Stripe fallisce nei test invece che in produzione.

17. **(Session 38) "Ricarica wallet" mostra "Si è verificato un errore" su
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
    parte DOPO un commit (ordini, ordini importati, riscatti, ticket,
    inviti account, accrediti wallet) -- ma deliberatamente **NON** per i
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

18. **(Session 38) Un cliente clicca "Continua" in Attiva Contratto e riceve
    "Si è verificato un errore imprevisto"**: il promoter che lo aveva
    invitato era stato **disattivato** dopo la sua iscrizione.
    `create_contract()` rifiuta — giustamente — di attribuire un contratto a
    un agente non ACTIVE (vedi `paid-contract-commission-audit.md`: un
    contratto che si attiva e non paga nessuno), ma `POST /contracts/mine`
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

Se un problema NON è in questa lista, è nuovo — documentalo qui dopo averlo
risolto, per lo stesso motivo per cui questi lo sono.

## 9. Cosa NON aspettarsi che funzioni già

Aggiornato Session 33 -- la versione precedente di questa sezione elencava
"pagamenti reali" e "notifiche" come non ancora costruiti: era vero quando
fu scritta, non lo è più da diverse sessioni. Elenco corretto di cosa
manca davvero oggi (vedi `docs/implementation-progress.md` per il dettaglio
sessione per sessione):

- **Motore AI/pgvector** (ricerca semantica, assistente interno) --
  esiste solo come documento di design, `docs/ai-architecture.md`, nessun
  codice.
- **CI/CD** -- nessuna pipeline automatica (lint/test/build su push);
  test/ruff/mypy vanno lanciati a mano (vedi comandi in questo file e in
  `README.md`).
- **MFA** -- schema presente (`sessions`, pensato per un futuro
  `user_mfa_methods`), non applicato in v1.
- **Scansione antivirus sugli upload** -- interfaccia pluggable presente
  (`document_scan_results`), nessuno scanner reale collegato; i download
  restano comunque gated da permessi indipendentemente dallo stato di
  scansione (vedi `security-model.md §Documents`).
- **OCR sulle fatture di riscatto cashback** -- il cliente digita
  l'importo a mano, un admin verifica sempre contro il documento caricato
  prima di sbloccare qualunque pagamento; deliberatamente rimandato, non
  uno stub rotto (vedi `cashback-partner-invoices-plan.md`).
- **Backup off-server** -- `scripts/backup.sh` gira già in cron (vedi §4.8),
  ma resta solo sullo stesso disco del database; nessuna copia automatica
  su un host/object-storage separato.
- ~~**Pagamento del CONTRATTO**~~ — **costruito in Session 44**: soluzione
  unica, 3 rate o 12 rate, con abbonamento Stripe reale
  (`mode="subscription"`) che si addebita da solo e si ferma dopo N rate.
  Tutto creato via API per singolo contratto: nessun Product/Price da tenere
  allineato a mano nel pannello Stripe. L'idempotenza del webhook è ora a
  livello di evento (`stripe_webhook_events`), non più solo a valle. Le 3
  rate non usano nessun finanziatore esterno — è Jav che rateizza la
  propria fattura — quindi la domanda aperta sulla "finanziaria Stripe"
  decade. Vedi `business-rules.md#contract-payment`.

**Cosa invece ESISTE ed è realmente in produzione, per evitare di
ricostruirlo per errore credendolo mancante**:
- **Pagamenti reali con carta (Stripe) e bonifico** -- sia per gli ordini
  Shop sia per il canone di riscatto cashback fattura, self-checkout
  cliente incluso, webhook Stripe verificato per organizzazione (vedi
  `cashback-partner-invoices-plan.md`, `business-rules.md
  §Partner-invoice-cashback`). Serve solo che un SUPER_ADMIN inserisca le
  chiavi Stripe reali dal pannello (`Impostazioni Azienda -> Pagamenti`) --
  il codice è già lì, verificato con chiavi di test.

  > ⚠️ **Stato al 2026-09-14: le chiavi salvate in produzione sono ancora
  > quelle di TEST** (`sk_test…` / `pk_test…`, più un `whsec_…` valido),
  > mentre il pulsante "Paga con carta" è attivo e visibile ai clienti su
  > `https://jav.ecodo.ai`. `is_stripe_configured()` restituisce `True`
  > e non distingue test da live, quindi **nessun incasso reale sta
  > avvenendo**. Prima di aprire i pagamenti veri vanno sostituite le tre
  > chiavi dal pannello e rifatto un pagamento di prova end-to-end
  > (checkout → webhook → ordine PAID → accredito wallet).
- **Notifiche**, sia in-app (campanella nell'header, ogni dashboard) sia
  email brandizzate con logo (`core/email_templates.py::render_email`) per
  OTP, cashback accreditato, ordini, riscatti, reset password, ticket --
  vedi `business-rules.md` e `security-model.md`.
- **Wallet interno "JavCash"**, cashback su prodotto e su riscatto
  fattura partner, sezione "Contabilità" cliente.
- **Upload documenti sensibili di contratto** (carta d'identità, codice
  fiscale, bolletta, visura camerale) -- ESISTE dalla Session 14, vedi
  `security-model.md §Documents`.
- **HTTPS** -- attivo dalla Session 3, vedi §4.6 sopra.
- **Backup giornaliero automatico** -- ESISTE dalla Session 25: cron alle
  04:00 esegue `scripts/backup.sh dev` con retention 14 giorni, vedi §4.8
  sotto.

## 10. Assunzioni di business ancora provvisorie

Le cifre del piano carriera/provvigionale (S1-S3, TL1-4, MD1-5, regola del 33%,
ecc.) sono **placeholder documentati**, non le regole reali di Jav — il
documento `Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf` non era
presente nel repository quando questo sistema è stato costruito. Vedi
`docs/open-questions.md` per l'elenco esatto e dove intervenire quando il
documento reale sarà disponibile.

## 11. Riusare questo stesso codice per un business diverso (Session 33)

Se lo scopo di installare su un nuovo server non è ripristinare/duplicare
**questa stessa** rete Jav ma far girare **un'altra azienda** (altro
nome, altro logo, altra rete commerciale) sullo stesso codice, la procedura
di installazione (sezioni 1-8 sopra) resta identica -- la differenza sono i
punti dove il nome "Jav" e il suo brand sono scritti nel codice
sorgente invece che in una riga di database. Il modello `Organization` ha già
`name`/`legal_name`/`settings` per-tenant (multi-org è supportato a livello
di schema), ma oggi **nessuna email, titolo di pagina o logo legge
effettivamente da quella riga** -- ogni stringa "Jav" è nel codice.
Prima di mettere in produzione per un cliente diverso, cambia:

**PRIMA DI TUTTO IL RESTO — tre costanti che non sono cosmetiche** (Session 46).
Le altre voci di questa sezione sono branding: se le dimentichi, il cliente
vede il logo sbagliato. Queste tre no.

- `apps/api/app/domains/auth/service.py`: `PASSWORD_RESET_DELEGATE_EMAIL` e
  `PASSWORD_RESET_DELEGATE_FOR`. Sono una deviazione *voluta e documentata*
  per Jav: i link di reset password di due account amministrativi
  specifici (`superadmin@example.com`, `admin@example.com`) vengono
  recapitati a un indirizzo personale di terza parte invece che alla casella
  dell'account. Su un deployment di un'altra azienda quella riga va
  **svuotata** (`PASSWORD_RESET_DELEGATE_FOR = frozenset()`), altrimenti resta
  un recapito di terzi dentro il flusso di recupero password di un cliente
  che non c'entra nulla. È la prima cosa da togliere, prima ancora del logo.
- `apps/api/app/domains/organizations/service.py`:
  `DEFAULT_ADMIN_NOTIFICATION_EMAIL = "info@example.com"` — la casella a cui
  arrivano le notifiche amministrative finché l'organizzazione non ne imposta
  una propria. Va messa quella del cliente, o le sue notifiche arrivano a
  Jav.
- `apps/api/app/domains/network/collaboration_documents.py`: è il **contratto
  di collaborazione vero** che un promoter accetta per lavorare con Jav
  , testo legale incluso il nome di una persona fisica e una PEC. Non è
  riutilizzabile da un'altra azienda: va sostituito integralmente con il
  contratto del cliente (stessa struttura a blocchi, vedi i costruttori
  `heading/paragraph/clause/bullets/table/signature` in cima al file) e la
  `version` va cambiata, così chi aveva già accettato la vecchia versione
  riceve la nuova da accettare.

**Email (branding condiviso da ogni email del sistema)**:
- `apps/api/app/core/email_templates.py`: `LOGO_URL` (oggi hotlinkato a
  `example.com/img/logo.png`), `BRAND_COLOR` (`#f97316`), il testo
  `alt="Jav"` e la riga di footer "Jav S.r.l. · ...".
  Un'unica modifica qui cambia il logo/colore su OGNI email (OTP, cashback,
  ordini, reset password, ticket, ...).
- Oggetti/corpi email con "Jav" scritto a mano, uno per dominio:
  `auth/service.py` (verifica email, reset password, OTP),
  `invoice_redemptions/service.py`, `wallets/service.py`, `orders/service.py`
  (anche `company_bank_holder: str = "Jav"` in `core/config.py`,
  quello è già sovrascrivibile da `.env`/`COMPANY_BANK_HOLDER`),
  `contracts/service.py`, `support/service.py` (prefisso oggetto
  `[Jav]`). Tutte modifiche di stringa, nessuna logica da toccare.

**Frontend**:
- Logo: `apps/dashboard/public/logo.png` (file statico, va sostituito) più
  ogni `alt="Jav"` in `login/page.tsx`, `r/[code]/page.tsx`,
  `verify-email/page.tsx`, `reset-password/page.tsx`,
  `forgot-password/page.tsx`, `app-shell.tsx`.
- `apps/dashboard/app/layout.tsx` (titolo/description pagina),
  `apps/dashboard/app/manifest.ts` (nome PWA), `icon.png`/`apple-icon.png`
  (favicon/icona app) -- tutti file/stringhe specifiche Jav.
- Testo "Jav" sparso in decine di componenti (label, placeholder tipo
  `nome@jav.demo` in `login/page.tsx`, copy varie) -- ricerca
  case-insensitive "Jav" nell'intero `apps/dashboard/` per trovarle
  tutte.
- **Colore del brand NON è centralizzato**: non esiste un file tema/config
  Tailwind con un colore "primary" -- le classi `orange-500`/`orange-600`/
  `amber-*` sono usate direttamente in quasi ogni componente
  (`apps/dashboard/components/**`). Cambiare il colore del brand richiede
  una sostituzione a livello di intero albero componenti, non una singola
  modifica di config.

**Dominio/infrastruttura**:
- `infrastructure/nginx/nginx.conf`: i due blocchi `server_name`
  (`example.com`/`www.example.com` e `jav.ecodo.ai`) e i relativi
  path `ssl_certificate` vanno rifatti per il nuovo dominio -- stessa
  procedura di §4.6, con un `-d` diverso.
- `infrastructure/marketing-site/` è un sito statico interamente
  specifico Jav (copy, immagini, favicon) -- per un business
  diverso serve un sito nuovo, o va tolto il blocco `server` dedicato in
  `nginx.conf` che lo serve.

**Dati demo**: `apps/api/app/seed/data.py`/`expand_demo.py` creano
un'organizzazione "Jav Demo" con email `@jav.demo` -- utile
solo per verifica dello stack, non eseguirlo per un cliente reale diverso
(vedi anche §4.7 per come rimuoverlo se già eseguito per errore). I nomi
generici in `.env.example` (`POSTGRES_USER=jav`, `POSTGRES_DB=jav`,
`S3_BUCKET_DOCUMENTS=jav-documents`, ecc.) sono solo identificatori interni
cosmetici, sicuri da lasciare invariati o rinominare liberamente -- non
compaiono mai a un utente finale.

**Non ancora fatto, da considerare se questo diventa un prodotto
multi-cliente reale**: rendere `LOGO_URL`/`BRAND_COLOR`/nome azienda
letti da `Organization.settings` invece che costanti nel codice, così un
singolo deployment potrebbe servire brand diversi per organizzazione senza
toccare il codice sorgente ad ogni nuovo cliente -- oggi il sistema supporta
più `organizations` nello schema (multi-tenant a livello dati), ma il
branding è comunque unico per deployment, non per organizzazione.

## 12. Runbook: rifare il progetto per un'altra azienda, dall'inizio alla fine (Session 46)

La §11 elenca *cosa* è specifico di Jav. Questa sezione è l'*ordine*
in cui farlo, scritta per essere eseguita da cima a fondo — anche da un
agente — senza dover decidere nulla per conto proprio. Ogni passo ha una
verifica: se la verifica non passa, il passo successivo non va fatto.

Serve, prima di cominciare: un server (§2/§3), un dominio con i DNS già
puntati all'IP del server, e dal cliente il **nome e la ragione sociale**,
un **logo**, l'**email del primo amministratore** e (per andare in
produzione, non per installare) IBAN aziendale, credenziali SMTP e chiavi
Stripe.

### Passo 1 — Server e codice

```bash
# §3: docker, git, openssl
apt-get update && apt-get install -y docker.io docker-compose-v2 git openssl
systemctl enable --now docker
git clone <repo> /opt/<nome-progetto> && cd /opt/<nome-progetto>
```

**Verifica**: `docker compose version` risponde 2.x.

### Passo 2 — Rebranding, PRIMA di costruire le immagini

Farlo adesso e non dopo: le immagini Docker sono *cotte*, quindi ogni
modifica al sorgente fatta dopo la build richiede una rebuild (§8). In
ordine di rischio, non di visibilità:

1. Le **tre costanti non cosmetiche** in cima alla §11
   (`PASSWORD_RESET_DELEGATE_*`, `DEFAULT_ADMIN_NOTIFICATION_EMAIL`, il
   contratto di collaborazione). Queste vanno fatte anche se il cliente
   accetta di lanciare con il branding provvisorio.
2. Logo ed email: `apps/api/app/core/email_templates.py`
   (`LOGO_URL`, `BRAND_COLOR`, footer), `apps/dashboard/public/logo.png`,
   `apps/dashboard/app/icon.png`, `apple-icon.png`.
3. Titoli e nomi: `apps/dashboard/app/layout.tsx`,
   `apps/dashboard/app/manifest.ts`.
4. Tutto il resto delle stringhe, con una ricerca esplicita:

```bash
grep -rniE "jav" apps/ infrastructure/ --include='*.py' \
  --include='*.tsx' --include='*.ts' --include='*.conf' -l
```

**Verifica**: lo stesso `grep` rieseguito non elenca più nessun file sotto
`apps/api/app/` e `apps/dashboard/` che finisca davanti a un utente. Restano
legittimamente i nomi interni (`POSTGRES_DB=jav`, i bucket
`jav-*`): non li vede nessuno, cambiarli è facoltativo e costa una
migrazione dei dati se fatto dopo.

**Nota onesta sul colore**: il colore del brand **non** è centralizzato. Le
classi `orange-*`/`amber-*` sono scritte a mano in quasi ogni componente
(§11). Cambiare colore è una sostituzione su tutto `apps/dashboard/
components/`, non una riga di config. Se il cliente non ha un vincolo di
brand forte, lasciarlo arancione è una scelta legittima.

### Passo 3 — `.env`

```bash
cp .env.example .env
openssl rand -hex 32   # JWT_SECRET_KEY
openssl rand -hex 24   # POSTGRES_PASSWORD
openssl rand -hex 24   # MINIO_ROOT_PASSWORD / S3_SECRET_KEY
```

`.env.example` è tenuto **sovrainsieme** del `.env` reale: se una variabile
serve, è lì dentro con un commento. Nessuna impostazione dell'applicazione è
obbligatoria a livello di codice (hanno tutte un default), il che è comodo in
sviluppo e **pericoloso in produzione**: uno stack con `JWT_SECRET_KEY`
lasciato al placeholder parte senza lamentarsi. Controlla a mano che i tre
segreti sopra e `NEXT_PUBLIC_APP_URL` (il dominio vero, in `https://`) siano
valorizzati.

**Verifica**:

```bash
grep -E "^(JWT_SECRET_KEY|POSTGRES_PASSWORD|S3_SECRET_KEY|NEXT_PUBLIC_APP_URL)=" .env
```

Nessuno dei quattro deve contenere `change-me`, `placeholder` o il valore di
`.env.example`.

### Passo 4 — Stack su

```bash
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d
```

Il container `api` esegue `alembic upgrade head` da solo all'avvio, e crea i
due bucket MinIO al primo startup: lo schema e lo storage non si toccano a
mano.

**Verifica**: `scripts/health-check.sh dev` → tutte le righe OK. Se no, §8
("Problemi noti già risolti") prima di improvvisare.

### Passo 5 — L'organizzazione e il primo amministratore

**Non** `python -m app.seed` (è la demo di Jav: venti promoter finti).

```bash
docker compose -f docker-compose.dev.yml exec api \
  python -m app.seed.bootstrap \
    --organization-name "Nome Azienda" \
    --legal-name "Nome Azienda S.r.l." \
    --admin-email "titolare@azienda.it"
```

Salva subito `Organization ID` e la password stampata (una volta sola).

**Verifica**: la query di §6.1 — 12 gradi, almeno un piano provvigioni
attivo, un solo utente.

### Passo 6 — Dominio e HTTPS

Segui la §4.6 alla lettera, sostituendo il dominio. I due punti in cui si
sbaglia sempre sono già scritti lì: certbot rifiuta una cartella
`live/<dominio>` preesistente, e un bind mount Docker creato prima che la
cartella host venisse ricreata continua a vedere l'inode vecchio (serve
ricreare il container, un reload di nginx non basta).

**Verifica**: `curl -sI https://<dominio>/login` → `200`, certificato reale
(non self-signed), e `http://` che redirige a `https://`.

### Passo 7 — Configurazione dall'interfaccia (non dal codice)

Entra come amministratore. Ti verrà chiesto di completare il profilo: è
normale, vedi §4.4 scenario C. Poi, in Impostazioni organizzazione:

- **SMTP** — finché non è configurato, nessuna email parte: niente verifica
  email, niente reset password, niente notifiche. È il primo da fare.
- **Stripe** — chiavi API e **webhook secret**. Attenzione: `sk_test`/
  `pk_test` sono le chiavi di *prova*; con quelle il pulsante "Paga con
  carta" è visibile ai clienti ma nessun pagamento è reale. Prima di aprire
  al pubblico, chiavi live.
  Sul pannello Stripe, l'endpoint webhook
  `https://<dominio>/api/payments/stripe/webhook/<organization_id>` deve avere
  abilitati **tutti e tre** gli eventi: `checkout.session.completed` (primo
  pagamento), `invoice.paid` e `invoice.payment_failed` (le rate successive dei
  contratti a 3 o 12 rate). Con il solo primo evento Stripe addebita le rate
  ma l'app non le vede: niente cashback, niente provvigioni per rata, nessun
  avviso di rata fallita (trovato così in Session 51). Nessuna versione API
  fissata sull'endpoint: il codice legge sia la forma vecchia sia quella
  "basil/dahlia" delle fatture.
- **IBAN aziendale** e intestatario, per i pagamenti a bonifico.
- **Google Drive** — facoltativo, serve solo al pulsante "Invia su Drive"
  sul fascicolo di un contratto. Vedi §13.

Poi, sempre dall'interfaccia: i **prodotti** reali (con i gettoni per grado,
che il bootstrap lascia ai valori placeholder di `app/seed/ranks.py`), e solo
dopo i primi **promoter**.

**Verifica**: da una casella esterna, prova un "password dimenticata" e
controlla che l'email arrivi davvero.

- **Marketplace** — facoltativi: Prodotti AliExpress, Prodotti CJ
  Dropshipping, Prodotti Shopify (§14).

### Passo 8 — Backup e rinnovo certificato

Le due righe di crontab della §4.8. Sono l'unica cosa di questo runbook che,
se dimenticata, non dà nessun errore immediato: il certificato scade dopo 90
giorni e i backup semplicemente non esistono il giorno in cui servono.

**Verifica**: `crontab -l` mostra entrambe le righe, e un
`./scripts/backup.sh dev` eseguito a mano produce un file in `./backups/`.

### Cosa il cliente NON eredita da Jav

Perché niente di tutto questo è nel database di una nuova azienda:

- **La scala dei gradi e i gettoni** (`app/seed/ranks.py`) sono
  **placeholder** — interpolati fra quattro valori di esempio del cliente
  originale, vedi `docs/open-questions.md` #1. Vanno riviste con il cliente
  prima di pagare una sola provvigione.
- **Il contratto di collaborazione** e il suo allegato (§11) sono di Jav
  .
- **I prodotti**, e con essi le percentuali di cashback, i bonus primo
  segnalatore e le durate contrattuali: nessuno viene creato dal bootstrap.
- **Il sito vetrina** `infrastructure/marketing-site/` è interamente Jav
  : o se ne fa uno nuovo, o si toglie il blocco `server` che lo serve
  in `infrastructure/nginx/nginx.conf`.

## 13. Collegare Google Drive (Session 48)

Serve a una cosa sola: il pulsante **"Invia su Drive"** sul fascicolo di un
contratto, che crea una cartella `<nome cliente>-<id contratto>` con dentro
tutti gli allegati e il PDF riassuntivo. Senza questa configurazione il resto
dell'applicazione funziona identico — e il pulsante "Scarica tutto (ZIP)",
che fa la stessa cosa in locale, non richiede nulla.

I file finiscono sul Drive dell'**account che autorizza**. Un normale account
Gmail gratuito va benissimo: non serve Google Workspace.

### 13.1 Creare il client OAuth su Google Cloud

Una volta sola, da fare con l'account Google che ospiterà i fascicoli.

1. [console.cloud.google.com](https://console.cloud.google.com/) → crea un
   progetto (un nome qualsiasi, es. "Gestionale <Azienda>").
2. **API e servizi → Libreria** → cerca **Google Drive API** → *Abilita*.
   Senza questo passaggio ogni chiamata torna 403 con un messaggio che parla
   di API non abilitata, e si perde tempo a cercare l'errore altrove.
3. **API e servizi → Schermata consenso OAuth**:
   - tipo di utente **Esterno** (con un account Gmail non c'è altra scelta);
   - nome dell'applicazione, email di assistenza, email di contatto;
   - alla voce **Ambiti** non serve aggiungere niente a mano: l'ambito
     (`drive.file`) lo chiede l'applicazione al momento del consenso;
   - in **Utenti di test** aggiungi l'indirizzo Google che autorizzerà.
     Finché l'app resta "in test", solo gli utenti elencati lì possono
     collegarla — ed è esattamente ciò che serve: non è un'app pubblica.
4. **API e servizi → Credenziali → Crea credenziali → ID client OAuth**:
   - tipo **Applicazione web**;
   - in **URI di reindirizzamento autorizzati** incolla l'URI che la
     dashboard mostra in *Impostazioni → Google Drive* (è
     `https://<tuo dominio>/admin/google-drive-callback`). Deve combaciare
     **carattere per carattere**, `https` compreso: se non combacia, Google
     rifiuta con `redirect_uri_mismatch` e non dice altro.
5. Copia **Client ID** e **Client Secret**.

### 13.2 Collegare dalla dashboard

*Impostazioni → Google Drive*:

1. incolla Client ID e Client Secret, **Salva**;
2. facoltativo: **ID cartella di destinazione** — apri su Drive la cartella
   dove vuoi che nascano i fascicoli e copia la parte dell'indirizzo dopo
   `/folders/`. Se lo lasci vuoto, le cartelle nascono nella radice del
   Drive;
3. **Collega Google Drive** → autorizzi su Google → torni indietro e la
   riga di stato diventa verde con l'indirizzo collegato.

Da quel momento il pulsante funziona per **tutti** gli amministratori
dell'organizzazione, perché i file vanno sul Drive di chi ha autorizzato.

**Verifica**: apri un contratto qualunque dalla dashboard amministratore,
premi *Invia su Drive*, e apri il link alla cartella che compare. Premilo una
seconda volta: non deve nascere una seconda cartella, e il messaggio deve
dire che i file sono stati *aggiornati*, non ricaricati.

### 13.3 Cosa questa applicazione può e non può fare sul tuo Drive

L'ambito richiesto è **`drive.file`**, non `drive`: l'applicazione vede e
tocca **soltanto i file e le cartelle che ha creato lei**. Non può leggere,
e nemmeno elencare, il resto del Drive dell'account collegato. È anche il
motivo per cui il controllo "esiste già una cartella con questo nome?"
funziona senza diventare una finestra sull'account.

Il **refresh token** è salvato in `Organization.settings`, accanto alle
chiavi Stripe e con lo stesso trattamento: non torna mai indietro da nessuna
risposta dell'API. *Scollega* lo dimentica; non cancella nulla di ciò che è
già su Drive, perché quei file appartengono all'account che li ospita.

### 13.4 Quando smette di funzionare

- **"Il collegamento non è più valido"** — l'utente ha revocato l'accesso
  dal proprio account Google, oppure il client OAuth è stato cancellato
  dalla console. Si risolve con *Ricollega*.
- **Un'app OAuth "in test" scade dopo sette giorni** se la schermata di
  consenso è in modalità test con utenti di prova. Se il collegamento cade
  ogni settimana è questo: sulla schermata consenso, *Pubblica app*.
- **`redirect_uri_mismatch`** — l'URI registrato non è identico a quello
  mostrato nelle impostazioni. Succede tipicamente cambiando dominio o
  passando da `http` a `https`: l'URI lo costruisce il server da
  `NEXT_PUBLIC_APP_URL`.


## 14. I Marketplace (Sessions 34-89)

Oggi sono sette: CJ, Shopify, AliExpress, «Fai la Spesa con Jav», Market
Kappa, VAITTO («Top Brand» per il cliente) e Symphonya («Shop Beauty»). Dalla
Session 89 **ogni vetrina del cliente arriva a pagine** (48 prodotti, «Mostra
altri prodotti», ricerca e categoria filtrate sul server:
`apps/api/app/domains/marketplaces/paging.py`): un negozio con decine di
migliaia di prodotti non deve mai essere restituito tutto in una risposta.
I nomi visti dal cliente sono impostazioni (`organizations.settings.
marketplace_labels`), quindi viaggiano con il database.

Quattro shop di prodotti importati, ognuno con le sue tabelle, che il cliente
vede nello Shop senza mai sapere la fonte: **Marketplace 1** (CJ), **2**
(Shopify), **3** (AliExpress) e **«Fai la Spesa con Jav»**, che a differenza
degli altri tre non ha un fornitore — il catalogo lo scrive l'amministratore. Tutti facoltativi: uno shop spento o vuoto non
compare. Le regole comuni stanno in `apps/api/app/domains/marketplaces/rules.py`
e si impostano dalla card **Regole dei Marketplace** in cima a ciascuna delle
tre pagine admin: nome nello Shop, sconto con bonifico (default 5%). JavCash:
30% sui prodotti nuovi, massimo 99% (vincolo nel database), mai cashback.
Vedi `docs/business-rules.md#marketplace`, anche per il perché dello sconto
sul bonifico invece di un aumento sulla carta (vietato in Italia).

**Prerequisiti comuni**: Stripe (per la carta) e IBAN (per il bonifico)
configurati come nel Passo 7 della §12. Gli ordini dei quattro Marketplace
compaiono nella stessa lista **Ordini** e in **Contabilità**.

**Cosa vale su tutti e quattro** (e che un'installazione nuova eredita senza
configurare niente):

- **Il carrello** (Session 75): uno per cliente e per negozio, mostrato come
  un carrello solo diviso in sezioni. Righe di negozi diversi non possono
  finire nello stesso ordine — le regole si escludono a vicenda — quindi si
  paga una sezione per volta. Un ordine porta N righe e **il denaro resta
  sulla testata**.
- **Il numero d'ordine** (Sessions 76-77): progressivo da 1000, assegnato dal
  database (`shop_order_number_seq`) e **condiviso fra i negozi**, così in
  "I miei Ordini" non esistono due «ordine 1042».
- **L'IVA si aggiunge al prezzo** (Session 78): il prezzo esposto è
  l'imponibile, in vetrina si legge «+ IVA» e al checkout l'imposta si somma.
  Aliquota in Regole dei Marketplace (22% di default). Si calcola sulla merce
  a prezzo pieno: né i JavCash né lo sconto bonifico la abbassano, e si
  congela alla creazione dell'ordine. `vat_mode` sull'ordine dice quale regola
  valeva, perché fino alla Session 77 l'IVA era *contenuta* nel prezzo.
- **Il tetto JavCash** è la somma delle righe: percentuale di ogni prodotto
  sul suo valore, spedizione esclusa. Quello che il cliente può davvero usare
  è `min(tetto, saldo del wallet)`.

### 14.1 Marketplace 3 — AliExpress (`aliexpress_dropshipping`, Session 71)
1. Su **openservice.aliexpress.com** crea un'app di categoria **Drop
   Shipping** nella stessa organizzazione dell'account venditore, e fatti
   abilitare il permesso **DS**: senza, il catalogo risponde "no permission".
   Registra come **Callback URL**
   `https://jav.ecodo.ai/api/aliexpress/oauth/callback` (sostituisci il
   dominio). Copia **App Key** e **App Secret** dalla console dell'app.
2. **Shop AliExpress → Impostazioni**: incolla App Key e App Secret, salva,
   premi **Collega AliExpress** (autorizzi sul portale e torni su una pagina
   di esito), poi **Verifica connessione**: se risponde, mostra alcune
   categorie lette davvero da AliExpress. Imposta paese/valuta/lingua di
   interrogazione (IT/EUR/it), ricarico, arrotondamento, spedizione, JavCash
   di default, invio automatico.
3. **Catalogo AliExpress**: cerca per parola chiave, apri un prodotto per
   vederne varianti e prezzi, importalo con nome e descrizione in italiano.
4. **Shop visibile ai clienti**: i prodotti compaiono come "Marketplace 3".
5. Il pagamento dell'ordine ad AliExpress resta manuale nell'account
   AliExpress: noi creiamo l'ordine, non lo paghiamo.

Resta disponibile, nella stessa pagina, la scheda **Prodotti inseriti a
mano** (`imported_products`): prodotti senza fornitore collegato, ordine al
fornitore fatto dall'amministrazione.

### 14.2 Marketplace 1 — CJ Dropshipping (`cj_dropshipping`)
1. Su cjdropshipping.com → My CJ → Authorization → API: copia la chiave.
2. **Prodotti CJ Dropshipping → Impostazioni**: incolla la chiave, **Verifica
   connessione e saldo**, cambio USD/EUR, ricarico (100% di default),
   arrotondamento, spedizione, JavCash di default (30).
3. **Sandbox** accesa finché si prova (ordini finti); spegnerla prima di
   aprire ai clienti. **Shop visibile ai clienti** per mostrarlo.
4. Catalogo CJ → importa. Celery sincronizza ordini (ogni 10-30 min) e
   prodotti (di notte): `celery-worker` e `celery-beat` devono girare.
Non serve saldo CJ anticipato: vedi business-rules.md#partner-shop.

### 14.3 Marketplace 2 — Shopify (`shopify_dropshipping`, Session 68)
Il fornitore è un negozio Shopify dell'azienda in cui un'app di dropshipping
(DSers, Syncee, Spocket...) tiene il catalogo ed evade gli ordini.
1. Shopify admin → Impostazioni → App → **Sviluppa app** → crea l'app nel
   **Dev Dashboard** (dal 2026 Shopify non crea più app con token fisso),
   nella stessa organizzazione Shopify del negozio. Nella versione dell'app:
   URL dell'app `https://jav.ecodo.ai`, **non** incorporata nell'admin
   Shopify, URL di reindirizzamento consentito
   `https://jav.ecodo.ai/api/shopify/oauth/callback` (serve se Shopify
   usa il flusso di installazione con OAuth: apre l'URL dell'app con
   `?shop=&hmac=`, `proxy.ts` lo manda a `/api/shopify/oauth/install`,
   `shopify_dropshipping/oauth.py` completa e salva un token offline).
   Salva prima dominio + Client ID/secret nel pannello, POI installa l'app. Ambiti Admin API: `read_products`,
   `read_inventory`, `read_orders`, `write_orders`, `write_draft_orders`,
   `read_fulfillments` (alcune app di dropshipping richiedono anche
   `read_assigned_fulfillment_orders` per il tracciamento). Rilascia la
   versione, installa l'app sul negozio, copia **Client ID** e **Client
   secret**: il token a 24 ore lo chiede e lo rinnova l'app da sola (client
   credentials grant). Un vecchio token `shpat_…` è ancora accettato.
2. **Shop Shopify → Impostazioni**: dominio `negozio.myshopify.com`, Client ID + secret,
   versione API (default `2025-07`), **Verifica connessione**. Prezzi: base
   "costo per articolo" (se manca, il prezzo del negozio), ricarico 100%,
   arrotondamento, cambio verso EUR (1 se il negozio è in euro), spedizione
   fissa o inclusa, JavCash di default 30, invio automatico.
3. Catalogo Shopify → importa i prodotti; **Shop visibile ai clienti**.
4. Nell'app di dropshipping del negozio attiva l'**evasione automatica degli
   ordini pagati**: quando il cliente paga, l'ordine viene creato nel negozio
   come bozza completata già pagata (tag `jav` + `jav-<id>`, mai
   duplicato anche se l'invio viene ripetuto), e il tracciamento torna da
   Shopify al cliente (notifica ed email a spedizione e consegna).

**Verifica**: un ordine di prova pagato con bonifico e confermato da
**Ordini** deve comparire nel negozio Shopify con il tag `jav`.

### 14.6 «Marketplace VAITTO» (`vaitto_market`, Session 88)

Da *Amministrazione → Marketplace VAITTO → Catalogo da Vaitto*: incollare
l'indirizzo del feed «universal.csv» con la chiave API (Vaitto lo fornisce
al rivenditore; il pannello non lo mostra più dopo il salvataggio), scegliere
il ricarico, «Aggiorna ora dal feed». Il primo import porta tutto il
catalogo **spento** (circa 3.500 prodotti, mezzo minuto, in background con
Celery); poi si accende per marca o categoria. L'import automatico ogni 3
ore è il task `vaitto_import_feed_all_task` di celery-beat.

**Verifica**: l'esito dell'ultimo import sotto i pulsanti («N prodotti nel
feed: …»); acceso un marchio e il negozio, nello Shop del cliente compare la
scheda «Marketplace VAITTO».

### 14.7 «Shop Beauty» — Symphonya (`symphonya_market`, Session 89)

Profumi e cosmetici dal grossista Symphonya (symphonya.eu), clone di VAITTO.
Da *Amministrazione → Shop Symphonya*: la **chiave API** di Symphonya (si
salva nelle impostazioni del negozio, nel database, mai nel codice né nel
`.env`), «Aggiorna ora». Il primo import porta ~31.900 prodotti spenti e poi
completa nomi italiani e descrizioni a poco a poco (Symphonya limita le
chiamate: ~1 ora); l'import automatico gira ogni 3 ore con celery-beat.
Prezzo = prezzo consigliato al pubblico, IVA inclusa; JavCash = metà di
(prezzo ÷ 1,22 − costo), come VAITTO; spedizione al cliente 10 € a ordine.
Gli ordini si inseriscono a mano su symphonya.eu.

**Verifica**: l'esito dell'ultimo import nel pannello; con negozio e prodotti
accesi, nello Shop del cliente compare la scheda «Shop Beauty» con «Mostra
altri prodotti» sotto la griglia.

### 14.8 «Market 7» — SoleilDrop (`soleil_market`, Session 90)

Il catalogo affiliato di SoleilDrop (soleildrop.com), clone di Symphonya.
Niente chiavi né import automatico: SoleilDrop non ha un'API da leggere. Da
*Amministrazione → Shop SoleilDrop* si carica l'Excel di «Il Mio Catalogo →
Esporta → Excel generico (.xlsx)» del portale (libreria `openpyxl` in
`pyproject.toml`); l'import gira nel celery-worker
(`soleil_import_feed_task`). Dopo un trasloco il catalogo è già nel
database: niente da rifare. Gli ordini si inseriscono a mano nel portale.

**Verifica**: carica l'Excel e controlla l'esito nel pannello; con negozio e
prodotti accesi, nello Shop del cliente compare la scheda «Market 7».

### 14.5 «Market Kappa» (`kappa_market`, Session 87)

Si configura esattamente come il §14.4, da *Amministrazione → Market Kappa*:
le «aziende» qui sono i **marchi** (Kappa, Robe di Kappa). Il catalogo non
fa parte dello schema: su un server nuovo si ricarica dal backup
(`scripts/restore.sh`) oppure a mano. Sul server attuale i 249 prodotti sono
stati caricati dal file di magazzino del negozio F652 (EAN come sku della
variante), nascosti e a prezzo provvisorio, in attesa dei prezzi. Le foto
vengono dal sito ufficiale kappa.com, abbinate per EAN (vedi
`implementation-progress.md`, Session 87) e salvate nel bucket media: su un
server nuovo si portano con la copia dei bucket MinIO (`mc mirror`, §4), non con il backup del database.

**Verifica**: acceso il negozio e attivato un prodotto con un prezzo vero,
nello Shop del cliente deve comparire la scheda «Market Kappa».

### 14.4 «Fai la Spesa con Jav» (`jav_market`, Sessions 79-80)

Il quarto negozio è l'unico **senza fornitore**: il catalogo lo scrive
l'amministratore, la merce la fa un'azienda vera e l'ordine le arriva per
email. Non c'è niente da collegare — nessun OAuth, nessuna chiave API — quindi
è anche il primo che conviene accendere su un'installazione nuova, perché
funziona subito.

Ne consegue il resto: nessun prezzo ricalcolato a ogni sync, nessun cambio
valuta, nessun ricarico su un costo (il prezzo che si scrive è quello di
vendita), e la spedizione è un **importo fisso** e non un minimo — senza
fornitore non esiste un costo reale da confrontare, a differenza di
AliExpress.

**Come si configura**, da *Amministrazione → Fai la Spesa con Jav*:

1. **Impostazioni del negozio** — Stato: Acceso. Spese di spedizione (una
   volta per ordine, non per articolo), tempi di consegna, e **Invio alle
   aziende**: «a mano» o «automatico al pagamento». Nasce spento e a mano:
   mandare una email a un'azienda vera è un'azione verso l'esterno, e la
   prima volta la si guarda.
2. **Gestisci aziende** — per ogni azienda: nome, **email per gli ordini**
   (è lì che arriva l'ordine: senza, non si può inviare), descrizione e sito
   (li legge il cliente), più partita IVA, telefono e sede che restano
   all'amministrazione. Il nome è unico per organizzazione, così non nascono
   due schede della stessa azienda scritte in modo appena diverso.
3. **Carica un prodotto** — nome, azienda, descrizione, tetto JavCash, costo
   per noi (facoltativo, serve solo al margine e non si mostra mai), e almeno
   una **variante** con prezzo e scorta. Un prodotto senza varianti non
   sarebbe comprabile, quindi non si può creare. Se di varianti non ne ha, si
   lascia «Unica» e il cliente non la vede nemmeno.
4. **Ordini** — «Conferma bonifico» quando il cliente ha pagato così, poi
   **«Invia alle aziende»**.

**Cosa succede all'invio**: parte **una email per azienda**, con dentro solo
le sue righe, l'indirizzo di consegna e le note del cliente. Un ordine può
contenere prodotti di aziende diverse, e ciascuna deve preparare la sua merce
senza vedere il resto. **Nessun prezzo nell'email**: quello che il cliente ha
pagato è un fatto nostro, e mandarlo al fornitore significherebbe mostrargli
il ricarico.

Si inoltra solo un ordine **già pagato**. Un'azienda senza email, o un
prodotto senza azienda assegnata, viene **segnalata** allo staff e scritta in
`forward_error` sull'ordine: merce che nessuno sta preparando è peggio di un
errore visibile. Il reinvio è ammesso — qui non si crea niente dall'altra
parte, a differenza di AliExpress dove un secondo invio sarebbe un secondo
acquisto.

Quando l'azienda risponde con il tracking, lo si inserisce in **Spedito**: è
quello il momento in cui il cliente riceve l'email con il numero.

**Verifica**: un ordine di prova pagato e inoltrato deve far arrivare una
email all'indirizzo dell'azienda, con la merce giusta e l'indirizzo di
consegna, e nessun importo.

## 15. Reinstallare tutto in autonomia (per un agente)

Questa sezione è scritta perché un agente — Claude Code o chi per lui — possa
ricostruire l'installazione su un server nuovo **senza fare domande**, e possa
verificare da solo di averla fatta giusta. Ogni passo ha un comando e un
risultato atteso: se il risultato non torna, ci si ferma lì invece di andare
avanti e scoprirlo tre passi dopo.

Le istruzioni lunghe stanno nelle sezioni sopra (§4 per un doppione di questo
sistema, §12 per un'altra azienda). Qui c'è la sequenza minima e come
controllarla.

### 15.1 Cosa serve prima di cominciare

- Ubuntu con `docker.io docker-compose-v2 git openssl postgresql-client`;
- accesso SSH come root e la chiave di deploy per il repository;
- un dominio che punta all'IP del server, se serve HTTPS;
- **niente altro**: nessuna credenziale di terze parti è necessaria per
  arrivare a un'applicazione funzionante. Stripe, SMTP, i fornitori dei
  Marketplace (CJ, Shopify, AliExpress, Vaitto, Symphonya) e Google Drive si
  collegano dopo, dall'interfaccia, e ciascuno è facoltativo. Se invece
  ripristini un dump (§5) quelle credenziali tornano con il database.
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
# atteso: la stessa revision citata in §6 (oggi c4a9e2f71d58, migrazione 0076)

docker compose -f docker-compose.dev.yml exec -T postgres \
  psql -U jav -d jav -tc \
  "SELECT count(*) FROM information_schema.tables
    WHERE table_schema='public' AND table_type='BASE TABLE';"
# atteso: lo stesso numero di CREATE TABLE in docs/database-schema.sql
#         (oggi 113) -- se non torna, lo schema e il codice sono fuori sincrono

# 3. L'applicazione risponde. Attenzione: solo nginx espone porte sull'host
#    (80 e 443), la dashboard no -- `curl localhost:3000` da' sempre 000 e
#    non vuol dire che sia rotta. Si chiede dall'interno della rete Docker:
docker compose -f docker-compose.dev.yml exec -T api python -c \
  "import urllib.request; print(urllib.request.urlopen('http://dashboard:3000/login').status)"
# atteso: 200

# ...oppure dall'esterno, una volta che dominio e certificato ci sono:
curl -s -o /dev/null -w "%{http_code}\n" https://IL-TUO-DOMINIO/login   # 200
```

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
| `password authentication failed for user "jav"` da riga di comando | Stai parlando con il Postgres **dell'host**, non con quello del container: usa l'IP del container (§2 di CLAUDE.md) |
| I test cancellano dati veri | `TEST_DATABASE_URL` punta a `jav` invece che a `jav_test` |
| Un vincolo che «non esiste» in una migrazione | Il naming convention raddoppia il prefisso: in `op.drop_constraint` va il nome **nudo** (`quantity_positive`, non `ck_x_quantity_positive`) |
| Un negozio non compare al cliente | Nasce spento, ed è voluto: si accende dal suo pannello |
| Celery riparte con il codice vecchio | `celery-worker` e `celery-beat` vogliono `--force-recreate` |

### 15.5 Cosa l'installazione nuova non eredita

Lo schema porta la **struttura**, non le scelte commerciali. Dopo
l'installazione sono tutti a zero o al default, e vanno decisi:

- prezzi, prodotti, categorie dello Shop e piano provvigioni;
- aliquota IVA, sconto bonifico, percentuali JavCash;
- credenziali di Stripe, SMTP, fornitori dei Marketplace, Google Drive;
- rebranding (nome, logo, colori): vedi §12, Passo 2, **prima** di costruire
  le immagini.

E soprattutto: le regole di business che questo progetto ha scelto stanno in
`docs/business-rules.md`, non nel codice sparse. Chi ricostruisce per
un'altra azienda le legge lì e decide quali tenere.
