# JAV Games

L'area giochi dell'area riservata: **Dojo Academy** (quiz a tempo ed esami
di cintura del gioco), **Judo Career** (la simulazione della carriera di un
judoca fino ad aprire e gestire un club) e **Randori del Club** (incontri con
gli amici del proprio club). Si apre da «Jogos/Giochi» nel menu della
famiglia e da `/giochi` (link nell'area dell'atleta).

Ogni gioco ha il bottone **⛶ Schermo intero** (`components/game/game-frame.tsx`):
la Fullscreen API sulla pagina (`document.documentElement`) più il gioco
steso su tutta la finestra (`fixed inset-0`), così le finestre, i toast e le
scene dei combattimenti — che vivono in un portal su `<body>` — restano
visibili. Su Safari per iPhone, dove la Fullscreen API degli elementi non
c'è, resta solo la sovrapposizione a tutta finestra. Si esce con ✕, Esc o il
gesto del sistema; uscendo dal gioco lo schermo intero si chiude da solo.

Lingue: i testi del gioco sono in portoghese, italiano e inglese; spagnolo →
portoghese, francese/tedesco/ucraino → inglese, sia nel browser
(`components/game/i18n.ts::gameLangIndex`) sia nel server (`service._lang`).

## Un progetto a parte, con dati finti

- Codice: `apps/api/app/game/` (modelli, contenuti, servizio, API `/game/...`)
  e `apps/dashboard/components/game/`. Nessun import dal gestionale, tranne
  una lettura in `service._identity`: nome da mostrare («Nome I.») e nome del
  club, copiati come testo nel giocatore.
- Dati: schema Postgres **`game`** (stesso database, schema separato), con
  una `MetaData` sua (`app.game.models.GameBase`), **nessuna chiave esterna
  verso le tabelle del gestionale**. `players.user_id` è l'id dell'account,
  senza FK. Le cinture, i club e gli atleti del gioco **non sono** quelli
  veri: un esame superato nel gioco non cambia la cintura vera.
- Migrazioni: le tabelle del gioco non stanno in `Base.metadata`, quindi
  l'autogenerate del gestionale non le vede. Una modifica ai modelli del
  gioco va scritta a mano in una migrazione nuova (come `0021_giochi.py`,
  `schema="game"`). I test creano lo schema a parte (`tests/conftest.py`).
- Per togliere tutto: `DROP SCHEMA game CASCADE` non tocca nient'altro.

## Dojo Academy

- Contenuti in `app/game/content.py`: una banca di domande (storia, etichetta,
  tecniche, regole, vocabolario) in portoghese, italiano e inglese, i
  **percorsi** (un quiz per tema) e gli **esami di cintura** del gioco
  (giallo → nero, in ordine; passa il 70%, il nero l'80%).
- Il server sceglie domande e ordine delle risposte e corregge ogni
  risposta (`POST /game/attempts/{id}/answer`): il browser non riceve mai la
  risposta giusta prima di aver risposto. Punti: 10 per risposta giusta più
  fino a 5 di velocità. Il tempo per domanda è di **30 secondi** (28 nell'esame
  di cintura nera).
- XP: di un percorso solo il **miglioramento** del record (rifarlo non
  fabbrica XP); un esame superato la prima volta dà il suo premio.

## Judo Career

- Lo stato della partita lo calcola il browser
  (`components/game/career/engine.ts`, settimane di gioco) e si salva in
  `game.careers` come JSON (`PUT /game/career`).
- Controlli del server: dimensione massima, XP che cresce al massimo di
  1500 per salvataggio, cintura del personaggio mai oltre l'ultimo esame
  superato in Dojo Academy (per passare di cintura nella carriera si studia
  e si fa l'esame nell'altro gioco), statistiche del personaggio (tecnica,
  físico, mental, energia tra 0 e 100, infortunio tra 0 e 10): contano
  anche nei combattimenti decisi dal server.
- Interfaccia (`judo-career.tsx`): in alto un **banner sempre visibile**
  (`hud.tsx`, sticky sotto la barra della pagina o in cima a schermo intero)
  con avatar, cintura, data di gioco e i contatori — tecnica, forza, mental,
  energia, salute, soldi (o saldo del club), fama — più XP, salvataggio e
  avvisi. Sotto, su uno schermo largo (≥ 1024 px) il **piano della
  settimana** a sinistra (il dojo, la prossima gara, le azioni, «Avança») e
  le schede a destra (Progressi, Calendario, Club, Atleti, Soldi, Avvisi,
  Trofei, Diario); sul telefono tutto a schede con il bottone della
  settimana fisso in basso. Pensato per stare in 1366×768 senza scorrere.
  I salvataggi vecchi si aprono come prima: lo stato non è cambiato.
- **Le gare**: nella settimana di una gara a cui si è iscritti, «Avança»
  chiede come combattere:
  - **Simulato**: il motore del browser, come prima (la scena animata);
  - **Passo a passo**: il torneo (`career/tournament.tsx`) chiede al server
    un incontro per turno (`POST /game/career/fights {comp_id, round}`). Il
    server controlla sulla carriera salvata che la gara sia di questa
    settimana, che il personaggio sia iscritto e non infortunato, e che il
    turno prima sia stato vinto; ogni turno ha una chiave unica
    (`career:{seed}:{gara}:r{turno}`): un turno perso non si rifà, uno a
    metà si riprende (`GET /game/career/fights/{comp_id}`). L'avversario è
    forte come nel motore (`LEVEL_BASE + turno·3 + caso`). Alla fine i turni
    passano al motore (`WeekPlan.compFights`), che conta vittorie, medaglia,
    XP e premi come sempre. Il resto della carriera resta calcolato dal
    browser.

## Combattimenti (server)

`app/game/fight.py` (motore puro), `fight_content.py` (le situazioni),
`fights.py` (servizio), tabella `game.fights`.

- Un incontro è una serie di **scambi**. In ognuno il server sceglie una
  situazione — l'avversario attacca («Ele entra com O-goshi!»), hai
  l'iniziativa, lotta di presa (kumi-kata), a terra sopra o sotto
  (ne-waza) — e propone 3-4 risposte vere di judo (bloccare con l'anca,
  Ura-nage, Utsuri-goshi, sukashi, gaeshi, osaekomi, shime-waza...). Ogni
  risposta ha una qualità (ottima, buona, rischiosa, sbagliata) e i suoi
  esiti se riesce o se va male; dopo lo scambio si mostra il **perché**.
- L'esito: probabilità = base del tipo di scambio + 0,9 × (qualità della
  risposta − qualità che giocherebbe l'avversario, dalla sua tecnica e
  testa) + differenza di **forza** / 26. La forza viene da tecnica, físico,
  mental, il **fiato** che resta (cala a ogni scambio, meno per chi ha più
  físico) e la **salute** (un infortunato vale meno). Il caso fa il resto; un
  ippon può restare waza-ari o yuko.
- Regole IJF 2025 semplificate: 4 minuti; ippon o due waza-ari finiscono;
  gli yuko non si sommano; 3 shido = hansoku-make; a pari punti golden
  score (vince il primo che segna); dopo 3 minuti di golden score decide il
  gioco (punti, meno shido, più fiato). Ogni scambio consuma 14-32 secondi.
- **Passo a passo**: il browser riceve la situazione e le risposte (id ed
  etichetta, in ordine mescolato), mai la qualità; manda
  `POST /game/fights/{id}/act {seq, option}`. Il server accetta solo una
  delle risposte mostrate, per lo scambio in corso (`seq`), una volta sola
  (riga bloccata con `FOR UPDATE`), e niente su un incontro finito. Si
  risponde entro 20 s (+6 di rete): dopo, conta come «hai esitato». Chi
  riapre un incontro a metà ha di nuovo il tempo per rispondere, ma la
  scadenza dell'incontro no: dopo **20 minuti** fermo è perso per abbandono
  (kiken). Un solo incontro in corso per giocatore. `POST …/forfeit` =
  abbandonare (perso).
- **Simulato**: la stessa cosa, ma le risposte le sceglie il judoca da
  solo, tanto meglio quanto più ha tecnica e testa; si rivede scambio per
  scambio.
- Interfaccia: `components/game/fight/fight-arena.tsx` (tabellone con
  orologio, yuko/waza-ari/shido e fiato; tatami; la domanda con il conto
  alla rovescia; l'esito e il perché; alla fine «Che cosa hai imparato»).

## Randori del Club

`GET /game/randori`, `POST /game/randori/challenge {opponent_id, mode}`
(SIM o STEP), `components/game/randori/club-randori.tsx`.

- Si sfidano solo i giocatori con lo **stesso club** (`players.club_label`,
  il nome copiato da `_identity`), mai sé stessi; nomi sempre «Nome I.».
  L'amico non deve essere collegato: combatte con le statistiche della sua
  carriera salvata (o con quelle della sua cintura del gioco, se non ne ha
  una).
- Punti (`players.randori_points`, si parte da 1000): chi vince prende i
  punti di chi perde, alla Elo — 32 × (1 − probabilità di vincere), minimo
  4, massimo 32, mai sotto zero. Più punti se si batte chi è più forte. La
  somma dei punti del club non cambia.
- Contro le «fabbriche» di punti: al massimo **3 incontri al giorno con lo
  stesso amico** (nei due sensi) e **10 sfide lanciate al giorno**; un
  incontro passo a passo abbandonato è perso.
- La pagina: i miei punti e la posizione, il mio judoca (le statistiche e
  l'avviso se sono infortunato o stanco), gli amici con «più forte / alla
  pari / meno forte» e quanto si vince o si perde, la classifica del club
  (punti, vittorie, sconfitte) e gli ultimi incontri (anche subiti). Il
  randori non cambia la carriera e non dà XP.

## Classifica

`GET /game/leaderboard`: tutti i giocatori per XP (quiz + carriera), quelli
del proprio club, e i club per somma dell'XP dei loro giocatori.
