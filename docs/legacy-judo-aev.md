# Il gestionale che i club usano oggi (judo-aev) e come entra in Jav

I club della rete (Judo Clube de Albufeira, Judo Clube de Lagos, Judo Team
Matias Luwawa) lavorano oggi con un gestionale PHP su hosting condiviso
("judo-aev", `judoartevida.com/judo`). Questo documento dice **che cosa fa**,
**che cosa ne prende Jav** (funzione per funzione) e **come si importano i
suoi dati**. La specifica completa del vecchio software, letta file per file,
sta fuori dal repository, accanto alla sua copia: `/opt/legacy/judo-aev/analysis/`
(`backoffice.md`, `portale.md`). Qui non c'è nessun dato personale.

## Dove sta la copia

| Cosa | Dove |
|---|---|
| Sorgente estratto (sola lettura, root 700) | `/opt/legacy/judo-aev/src` |
| Backup SQL originale | `/opt/legacy/judo-aev/src/u142879407_judo_aev.sql` |
| Database caricato, per studiarlo e importarlo | container `legacy-mariadb` (MariaDB 11.8), rete `legacy-net`, nessuna porta pubblicata, volume `legacy-mariadb-data`; password di root in `/opt/legacy/judo-aev/.mariadb_root_pw` |

Il dump non contiene `provas` / `inscricoes_provas` (prima versione, sostituite
da `eventos` / `inscricoes_eventos`) né il database dell'app `jav/` (iscrizione
alle gare per telefono): non servono, le loro funzioni sono altrove.

**Il vecchio gestionale è ancora in uso.** L'importazione è quindi
**rilanciabile**: ogni riga importata ha la sua corrispondenza
(`legacy_import_map`), rilanciarla aggiorna e aggiunge, non duplica. Il
giorno del passaggio definitivo si fa un ultimo dump e si rilancia.

## I dati (ottobre 2026)

80 atleti (68 non cancellati, 54 email di famiglia: 9 famiglie con più figli),
403 pagamenti (246 file di prova), 326 mesi pagati, 194 quote annuali (142
rate pagate), 93 eventi del calendario comune, 175 iscrizioni di cui 133 con
medaglia, 41 sessioni di allenamento con 267 presenze, 15 documenti di atleti,
72 consensi RGPD, 10 ordini di judogi, 6 richieste di modifica, 12 registri di
pulizia, 14 pagamenti a collaboratori, 5 compensi di treinadores esterni, 2
relatori.

## Funzione per funzione

Legenda: ✅ c'è già in Jav · 🟡 c'è, va esteso · 🆕 manca, si costruisce.

| Funzione del vecchio gestionale | In Jav | Che cosa si fa |
|---|---|---|
| Più club, utenti admin/clube | ✅ | `club/scope.py`, ruoli e permessi veri (il ruolo "viewer" del vecchio non era applicato) |
| Atleti: lista, filtri, scheda | 🟡 | La scheda si allarga con i dati della **ficha de inscrição**: nº de sócio, nome sul judogi, altezza, nazionalità, indirizzo, documento d'identità e passaporto, dati del responsabile (nome, telefoni di padre e madre, NIF, documento), licença FPJ con anno di rivalidazione, categoria di peso, note. I dati d'identità in una tabella a parte (`club_athlete_records`), letta solo dalla segreteria |
| Gruppi 1/2/3 per età (anno − anno di nascita) e mensilità 35/60/85 | ✅ | È la nostra età federale e i piani "Grupo 1/2/3" già configurati |
| Mensilità mese per mese, scadenza il 15, mese d'iscrizione a metà | ✅ | `club/months.py`; i mesi da pagare sono quelli del piano |
| Pagamento di più mesi insieme | ✅ | Una prova di pagamento copre N quote |
| **MB Way** come forma di pagamento | 🆕 | Nuovo metodo `MBWAY` (quote e prove), con la ricevuta come il bonifico |
| Contanti "entregue a" | ✅ | `cash_received_by_*` (migrazione 0014) |
| Verifica dei comprovativos (por verificar → pago / rejeitado) | ✅ | Da noi la prova segna subito pagato e la segreteria può rifiutarla: più veloce, stesso controllo |
| Numero di comprovativo (MEN-2-2026-0001) | 🆕 | Numero progressivo per club e anno, **unico nel database** (il vecchio contava le righe e poteva duplicare) |
| Quote annuali: Sócio Judoca + Taxa de Faltas (a pro rata), Sócio Pai/Mãe per i minori | ✅ | Iscrizione annuale (120 € = 60 + 60) e quota socio del genitore |
| Quote **a rate** (1–4 prestações) | 🆕 | Una quota si divide in rate (`installment_no` / `installments_total`), ognuna con la sua scadenza; il genitore o la segreteria scelgono quante |
| Sconti Segurança Social A/B/C/**D**, família, staff, órgãos sociais, sconti del club | 🟡 | Escalão D in più; **esenzione** (staff, órgãos sociais: 100%) e **sconto personale** dell'atleta (fisso o %, su mensilità, quote o entrambi, con la sua descrizione) |
| Multa (es. 35 € faltas) | 🆕 | Una quota `FINE` emessa dalla segreteria, che si paga come le altre |
| Debiti (dívidas) per quote e mensilità | ✅ | "Conto dell'atleta" e contabilità; il debito è la somma delle quote DUE, una sola regola (il vecchio ne aveva tre che davano risultati diversi) |
| Blocco dell'iscrizione alle gare con mensilità in ritardo | 🆕 | Regola del club (attivabile): con mensilità scadute la famiglia non iscrive; la segreteria sì |
| Calendario eventi **comune a tutta la rete** (FPJ, ADJA, opens, estágios, formazioni, arbitragem) | 🆕 | **Calendário da rede**: eventi della piattaforma, visibili a tutti i club; ogni club ci iscrive i suoi atleti. Tipi: gara, estágio, arbitragem, formação, reunião, outro; livelli regional, zonal, opens, nacional, Taça da Europa, Europeo, Mondiale, Olimpiadi; escalões (CSV); trasporto; circolare PDF |
| Import del calendario da PDF | 🆕 | Si carica il PDF, si rivedono le righe riconosciute, si salvano (parser del vecchio, in Python) |
| Iscrizione a gare dal portale, con comprovativo | ✅ | Iscrizione + quota `COMPETITION` + prova |
| Risultati (classificação, medalha, notas) | ✅ | `placement` sull'iscrizione; si aggiunge la medaglia e le note |
| **Ranking a punti per livello** (regional 5/3/2/1 … Olimpiadi 35/30/25/8), per gruppo, di tutta la rete | 🟡 | Il Jav Ranking usa **la tabella punti dei club** (la conoscono già le famiglie) e i livelli nuovi; classifica di rete e del club, per gruppo |
| Ranking FPJ nazionale (link esterno) | 🆕 | Link dalla scheda dell'atleta |
| Pagina pubblica dei risultati e ranking pubblico | ✅ | Già nostri, con il consenso e "Nome I." (il vecchio mostrava nomi interi senza consenso) |
| Presenze: calendario settimanale, sessioni, registro, consultazione per atleta e matrice mensile | 🟡 | Corsi, slot e presenze ci sono; si aggiunge la **matrice mensile** e la % di assiduità per atleta |
| Accesso delle famiglie con **codice via email** (senza password) | 🆕 | "Entra con un codice": 6 cifre via email, 15 minuti, **monouso**, tentativi limitati. Le famiglie importate entrano così dal primo giorno |
| Più atleti per famiglia (fratelli) | ✅ | Il titolare e i suoi atleti |
| Consensi RGPD (política obrigatória con versione, fotografias per atleta, storico, export JSON) | 🟡 | Si aggiunge il registro dei consensi con versione della politica, storico e revoca; il consenso foto pilota la pagina pubblica |
| Richieste di modifica dei dati (grau, categoria de peso, peso) | 🆕 | Il genitore chiede, la segreteria approva o rifiuta |
| Ordine di judogi ("pedido de fato": tipo, colore, marca, taglia, nome da ricamare, < 13 anni solo il nome) | 🆕 | **Pedidos de fato** del club (stati pendente → em preparação → entregue / cancelado), con la quota da pagare; export per il fornitore |
| Calcolatore prezzo judogi con permuta al 50% | 🆕 | Listino dei judogi del club e permuta: il prezzo lo calcola il server |
| Documenti dell'atleta (Segurança Social, giustificazioni, autorizzazione parentale…) | 🆕 | Archivio documenti dell'atleta nel bucket privato |
| Domanda d'iscrizione pubblica (ficha completa) → approvazione → nº de sócio + email di benvenuto | 🟡 | Il modulo pubblico del club si allarga ai campi della ficha; all'approvazione nasce l'atleta con il nº de sócio |
| Export atleti CSV, **Excel FPJ**, **Allianz (Anexo 5)** | 🆕 | Export dalla lista atleti |
| **Relatórios**: matrice mensilità × mesi; **relatório de atividades** in PDF (atleti, allenamenti, presenze, gare, podi, formazione + 3 testi liberi) con archivio | 🆕 | Sezione Relatórios del club, PDF con i colori del club, archivio dei relatori generati |
| **Registos de limpeza** (ore × €/ora, firma su schermo, pagato) | 🆕 | Registro delle pulizie con firma; segnarlo pagato crea la spesa in contabilità |
| Pagamenti a collaboratori | 🟡 | Sono spese (`club_expenses`, categoria collaboratori) |
| Compensi dei treinadores esterni (ore feriali/weekend, € per allievo) | 🆕 | Calcolo del compenso mensile; pagato = spesa |
| Galleria foto/video | ✅ | Media della pagina del club (la galleria vecchia è vuota) |
| Email di compleanno | 🆕 | Job giornaliero, una volta per atleta e anno |
| Notifiche della dashboard (da verificare, iscrizioni nuove, risultati da registrare) | 🟡 | Si aggiunge "risultati da registrare" |
| Pagine di diagnostica, judo_system v1, app jav per telefono | ✗ | Non si portano: erano debug o versioni superate |

Cose del vecchio che **non** si ripetono, di proposito: codici OTP
riutilizzabili, documenti d'identità raggiungibili per URL, endpoint che
espongono il NIF senza login, conteggi non atomici, prezzi scritti nel codice,
tre calcoli diversi dello stesso debito.

## Come si importa

Uno script (`apps/api/app/legacy/judo_aev.py`, lanciato con `python -m
app.legacy.judo_aev`) legge il MariaDB della copia e scrive nel nostro
database con i servizi di Jav, in una transazione per club. Prima si prova su
una copia del database (ripristino dell'ultimo backup in un database usa e
getta), si confrontano i totali, poi si lancia sul database vero dopo
`scripts/backup.sh`.

| Vecchio | Jav |
|---|---|
| `clubes` 1/2/3 | i club esistenti con lo stesso nome; colori e logo se mancano. Il club 4 (JAV) è la piattaforma |
| `utilizadores` (admin/clube) | utenti dello staff del club (segreteria), **senza password**: entrano con il codice via email |
| `atletas.portal_email` | il **titolare** (`users`, ruolo famiglia): uno per email, con tutti i suoi atleti. Adulto con la sua email = atleta "me stesso" |
| `atletas` | `club_athletes` + `club_athlete_records`; `grau` → storico cinture; sconti → escalão / esenzione / sconto personale; `ano/mes_inscricao` → `joined_on`; cancellati → `LEFT` |
| `pagamentos` pagati | una **prova di pagamento** (con il file, nel bucket privato) e le quote che paga: mensilità (`meses_ref` / `prestacoes_mensalidades`, un mese = una quota `MONTHLY` pagata), quote annuali (rate), evento (quota `COMPETITION`), equipamento (ordine del judogi) |
| `pagamentos` rifiutati | prova `REJECTED` con il motivo |
| `pagamentos` cancellati (`apagado`) | non si importano |
| `pagamentos_quotas` + `prestacoes_quotas` | Sócio Judoca + Taxa de Faltas → iscrizione annuale; Sócio Pai/Mãe → quota socio del titolare; rate pagate e rate da pagare con lo stesso importo del vecchio |
| `eventos` | calendario della rete; `circular_path` → file nel bucket |
| `inscricoes_eventos` | iscrizione dell'atleta, con stato, quota, medaglia e posizione |
| `treinos_calendario` / `treinos_sessoes` / `presencas` | corsi con gli slot (per gruppo e modalità) e presenze per data |
| `atleta_documentos` | documenti dell'atleta (file nel bucket privato) |
| `consentimentos_rgpd` | registro dei consensi, con data, versione e origine |
| `pedidos_fatos`, `pedidos_alteracao` | ordini di judogi, richieste di modifica |
| `registos_limpeza`, `pagamentos_colaboradores`, `pagamentos_treinadores_externos` | registro pulizie (con la firma), spese, compensi |
| `relatorios_gerados` + PDF | archivio dei relatori |
| `inscricoes` | domande d'iscrizione (storico) |

**Nessuna email parte durante l'importazione**: né benvenuto, né conferme, né
notifiche. Le famiglie ricevono il benvenuto solo quando il club decide di
aprire Jav, con un invio esplicito dalla console.

## In che ordine si costruisce

1. **Fondamenta e importazione**: le tabelle e i campi nuovi che servono ai
   dati (ficha, MB Way, rate, sconti personali, esenzioni, multa, calendario
   della rete, documenti, consensi, ordini di judogi, richieste di modifica,
   pulizie, compensi, relatori, corrispondenza dell'import); lo script; la
   prova su una copia; l'importazione vera.
2. **Accesso con codice via email**, così le famiglie importate possono
   entrare.
3. **Le schermate nuove**: ficha completa, calendario della rete e
   iscrizioni, ranking a punti, ordini di judogi, richieste di modifica,
   consensi, documenti.
4. **Gestione**: relatórios (matrice e PDF delle attività), pulizie con
   firma, compensi dei treinadores, export FPJ / Allianz / CSV, import del
   calendario da PDF, email di compleanno.

## Come si lancia

Il MariaDB della copia deve essere raggiungibile dalla rete dello stack
(`docker network connect jav-dev_default legacy-mariadb`, e `disconnect`
alla fine). Poi, dopo `./scripts/backup.sh`:

```bash
PG=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)
docker run --rm -u 0 --network jav-dev_default -v "$PWD/apps/api:/src" \
  -v /opt/legacy/judo-aev/src/judo:/legacy/judo:ro -w /src --env-file .env \
  -e DATABASE_URL="postgresql+psycopg://jav:${PG}@postgres:5432/jav" -e S3_ENDPOINT_URL=http://minio:9000 \
  -e LEGACY_DB_PASSWORD="$(cat /opt/legacy/judo-aev/.mariadb_root_pw)" \
  --entrypoint sh jav-dev-api -c 'pip install -q pymysql && python -m app.legacy.judo_aev --dry-run'
```

Senza `--dry-run` importa. Il riepilogo finale conta righe ed euro, mai nomi.
Prima di farlo sul database vero si prova su una copia (`jav_imptest`,
ripristinata dall'ultimo backup, con `S3_BUCKET_DOCUMENTS` e
`S3_BUCKET_MEDIA` di prova).

## Che cosa ha detto la prova (15 ottobre 2026)

- **I soldi tornano al centesimo.** Ogni prova di pagamento ha quote pagate
  per tutto il suo importo: Albufeira 1.780,00 €, Lagos 22.540,50 €, Judo
  Team ML 703,00 €. Le rate del vecchio non sempre tornavano con il
  pagamento: si usa l'importo vero del pagamento, diviso sui mesi o sulle
  rate. In più ci sono 450 € che il vecchio segnava pagati senza ricevuta
  (2 iscrizioni "liquidate" a mano, 4 judogi segnati pagati).
- **Tre pagamenti di Lagos (301 €) non si importano**: non hanno un atleta e
  il nome scritto non corrisponde a nessuno. Vanno ricollegati a mano (id
  vecchi 242, 243, 260, tutti "equipamentos").
- **Ranking**: 668 punti nel vecchio, 670 in Jav. La differenza sono due
  gare senza livello nel vecchio (0 punti), che in Jav valgono come gara di
  club (la partecipazione, 1 punto).
- **Mensilità scoperte**: le stesse del vecchio, con due eccezioni che sono
  correzioni: un'atleta esente al 100% (il vecchio la contava in debito in
  una delle sue tre regole) e un pagamento di maggio che il vecchio non
  aveva collegato all'atleta.
- **Tutte le pagine dell'API** (134 GET, come genitore, segreteria e
  superadmin) rispondono senza errori sui dati importati.

